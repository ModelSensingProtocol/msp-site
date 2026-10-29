# 核心模式：发布—订阅（`msp/publish-subscribe`）

| | |
|---|---|
| **协议修订** | `2026-10-10` |
| **状态** | ✅ 已实现（含发送侧 `sub` 授权过滤） |
| **本页定义** | 核心通讯模式 `msp/publish-subscribe`：广播模型（`publish` 扇出到所有已连对端、**无订阅表**）、接收方本地过滤（`on(path)`）、路径语法与通配符匹配算法（`pattern_matches` 逐行对应）、匹配边界与易错点、虚拟总线与版本化路径、安全考量 |

> 本页是 [patterns.md](../patterns.md) 的具体化。`msp/publish-subscribe` 是**核心模式**，直接实现在协议层，不进 `PATTERN_REGISTRY`，也没有 Handler 实例（理由见 [patterns.md §4.2](../patterns.md#42-为什么这两个是核心)）。

---

## 1. 概述

`msp/publish-subscribe` 的语义一句话：**发布方把一条 `type="signal"` 的报文扇出到所有已连对端；接收方在本地用路径模式过滤，命中的回调才触发。**

它的关键设计取舍是**没有订阅表**：

- **线上没有 subscribe / unsubscribe 信号**。发布方不知道谁「订阅」了什么，也不需要知道。
- **发布不需要协商**。`publish()` 直接把信号发给全部已连对端，包括从未表达过兴趣的对端。
- **过滤责任在接收方**。是否消费由接收方的 `on()` 模式决定。

这条取舍换来的是协议面的极小化：一个只实现 `msp/publish-subscribe` 的节点不需要维护任何对端订阅状态，也不需要处理订阅与断线的时序竞态（对端掉线后订阅是否还在？——不存在这个问题，因为没有订阅）。

代价是**带宽**：`N` 个已连对端就是 `N` 次发送，与「有多少人真的感兴趣」无关。这是**刻意的取舍，不是缺陷**（见 [architecture.md §已知缺口](../architecture.md#13-已知缺口)）。

### 1.1 在分层中的位置

| 能力 | 公开 API | 协议层实现 |
|---|---|---|
| 发布 | `node.publish(path, payload)` | `MSPProtocol.publish` |
| 订阅（本地过滤） | `node.on(path)` | `MSPProtocol.on`、`MSPProtocol._on_signal` |
| 路径匹配 | — | `protocol/matcher.py` → `pattern_matches` |
| 自动重复发布 | `@node.signal_source(path)` / `@node.signal(path)` | `MSPNode._run_signal_source` |

---

## 2. 契约

### 2.1 报文形态

`publish(path, payload)` 构造**恰好**如下信号：

```python
Signal.make(
    type=SignalType.SIGNAL,   # "signal"
    source=self.node_id,
    path=path,
    payload=payload,
)
```

**必须**满足：

| 字段 | 值 | 级别 |
|---|---|---|
| `type` | 恒为 `"signal"` | **必须** |
| `source` | 恒为本节点 `node_id` | **必须** |
| `path` | 调用方给出的路径，**必须**符合 `segment(.segment)*`（`[README.md §5.3](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#53-命名规范)`） | **必须** |
| `payload` | 调用方给出的字典 | **必须** |
| `target` | `None`（广播无单一目标） | **必须**为 `None` |
| `pattern` | `None`（核心模式不写路由键） | **必须**为 `None` |
| `reqid` | `None`（广播不需要应答关联） | **必须**为 `None` |
| `timestamp` | 由 `Signal.make` 自动填充 | **必须** |

**注意**：`payload` 内部**没有** `path` 字段——路径是**信封字段** `Signal.path`，不是载荷字段。实现**不得**把路径塞进 `payload`。

### 2.2 扇出语义

`publish()` **必须**：

1. 在锁内快照连接表（`list(self.connections.items())`），**不得**持锁执行网络发送；
2. 对**每一个**已连对端发送同一份报文的编码结果；
3. 对发送时抛 `ConnectionClosed` 的对端，**必须**触发该对端的断连清理（`_handle_disconnect(peer_id, conn)`），并继续发送给其余对端；
4. **不得**因为某个对端失败而中断整个扇出循环；
5. **不得**返回任何成功/失败计数——`publish()` 的返回值是 `None`。广播是「尽力而为」（best-effort），不是「全部送达」。

> 「尽力而为」的准确含义：若调用 `publish()` 时某对端的连接**已经**关闭，那它收不到；若连接在发送过程中关闭，扇出循环会感知并清理；若对端进程已经死了但 TCP 还没察觉，报文会被写入内核缓冲区然后随连接超时一起消失。**没有**送达确认，也**不应有**——需要确认就用 `msp/request-reply`。

### 2.3 接收方本地过滤

接收方**必须**按以下规则处理收到的 `signal`：

1. `_dispatch` 第 1 步不命中（`signal` 不是核心信号类型）；
2. `_dispatch` 第 2 步不命中（`pattern` 为 `None`）；
3. `_dispatch_core` 命中 `SignalType.SIGNAL` → `_on_signal(peer_id, msg)`；
4. `_on_signal` 在锁内快照回调列表，然后在锁外遍历；
5. 对每个 `(path_filter, func)`：
   - 若 `path_filter is None` → **无条件**调用；
   - 否则若 `pattern_matches(path_filter, msg.path)` 为真 → 调用；
   - 否则跳过。

**必须**满足：

| # | 条文 | 级别 |
|---|---|---|
| 1 | `path=None` 的回调**必须**匹配**全部**路径 | **必须** |
| 2 | 每个命中回调**必须**被调用一次；多个回调命中时**必须**全部调用 | **必须** |
| 3 | 单个回调抛出的任何异常**必须**被捕获（记 warning 日志），**不得**影响后续回调 | **必须** |
| 4 | 回调**必须**在协议层读循环线程上被调用（**不是**工作线程） | **必须** |
| 5 | 回调**不得**执行长耗时操作——它会阻塞该连接的消息接收（同 [patterns.md §3.5](../patterns.md#35-on_signal-的运行线程与阻塞禁令)） | **不得** |
| 6 | 回调注册**必须**可以随时进行，包括在读循环运行期间（注册表在锁内修改） | **必须** |
| 7 | 回调**不得**从回调内部注销自身——当前**没有**注销 API（见 §10 G1） | **不得** |

回调签名是 `func(sig)`，其中 `sig` 是完整的 `Signal` 对象（可取 `sig.source` / `sig.path` / `sig.payload` / `sig.timestamp`）。

### 2.4 注册 API

协议层 `on(path=None, callback=None)` 支持两种用法：

```python
# 用法一：装饰器
@proto.on(path="ai.state")
def handler(sig): ...

# 用法二：直接注册
proto.on(path="ai.state", callback=handler)
```

节点层 `node.on(path=None)` 只暴露装饰器形态：

```python
@node.on("ai.state")
def handler(sig): ...

@node.on()          # path=None：接收全部
def spy(sig): ...
```

**必须**满足：

1. 同一回调**可以**被注册多次，它就会被调用多次——实现**不得**去重；
2. 注册**必须**返回被装饰的函数本身（装饰器形态），使函数仍可正常调用；
3. `path` 参数**必须**允许为 `None`；
4. **不得**为 `path` 参数做格式校验——非法的路径模式不是错误，只是永不匹配（见 §4.5）。

### 2.5 自动重复发布

`@node.signal_source(path)`（别名 `@node.signal(path)`）装饰一个**生成器**函数。节点启动后，每个信号源在**独立线程**里持续迭代：

```
for payload in func():
    if not running: break
    if not isinstance(payload, dict): continue
    publish(path, payload)
```

**必须**满足：

1. 生成器的每次 `yield` **必须**是一个 `dict`；非 `dict` 的产出**必须**被跳过（不报错、不发布）；
2. 第一个产出到达前允许有任意延迟（常用于等订阅者就绪）；
3. 生成器函数内抛出的异常**必须**被捕获、记日志为「信号源异常终止」，**不得**影响其它信号源或节点；
4. `signal_source` **必须**同时声明路径（等价于调用一次 `declare_signal(path)`），使该路径出现在 `Manifest.signals` 中；
5. 节点停止后**不得**继续发布——`_running` 为假时循环中断。

---

## 3. 路径语法

路径是信号的**逻辑地址**，与传输地址、`node_id` 无关。

### 3.1 字符与分层

| 项 | 规定 |
|---|---|
| 分隔符 | 点号 `.` |
| 格式 | `segment(.segment)*` |
| 段内字符 | **应当**为 `[a-z0-9_-]`（与 `node_id` / 工具名同风格）；**不得**包含点号、空格、通配符 |
| 大小写 | **应当**全小写；匹配**必须**大小写敏感（`ai.state` ≠ `Ai.State`） |

### 3.2 域优先约定

路径**必须**遵循 **`<域>.<实体>.<动作>`**，域在最前：

| 层级 | 含义 | 例子 |
|---|---|---|
| 域 | 稳定、面向功能的分类 | `notify`、`system`、`ai`、`sensor`、`log`、`metric`、`auth`、`task` |
| 实体 | 信号的来源或主体 | `web`、`file`、`state`、`temperature` |
| 动作 | 具体发生了什么 | `download`、`modified`、`progress`、`changed` |

正确与错误的对比例子：

| 写法 | 评价 |
|---|---|
| `notify.web.download` | ✅ 域优先：接收方 `notify.**` 一劳永逸覆盖全部现有与未来通知 |
| `web.notify.download` | ❌ 实体优先：新增一个通知来源就要改过滤规则 |

域优先的**规范后果**：接收方**应当**按域为单位订阅（`notify.**`、`log.**`、`metric.**`），而不是按实体逐个订阅。这是「不为新增来源修改过滤规则」得以成立的前提。

### 3.3 与 Pattern ID 的区别

路径用点号，Pattern ID 用斜杠，两者**不得**混用：

| 对象 | 分隔符 | 格式 | 例子 |
|---|---|---|---|
| Signal path | `.` | `segment(.segment)*` | `notify.web.download` |
| Pattern ID | `/` | `[namespace/]name` | `msp/publish-subscribe` |

**不得**在路径里出现 `msp/...` 形式的分段，也**不得**把路径当作 `Signal.pattern` 的值。

### 3.4 通配符

通配符**只**允许出现在模式的**末尾**，且只允许两种形式：

| 形式 | 名称 | 语义 |
|---|---|---|
| `*` | 单段通配 | 恰好**一段**（≥ 1 个非空分段） |
| `**` | 多段通配 | **零或多段**（包含前缀本身） |

**必须**满足：

> 通配符**必须**只出现在模式末尾。出现在中间的 `*` 是**字面量**，不会产生通配语义，且该模式**永不匹配任何路径**（见 §4.5 易错点 1）。

### 3.5 路径声明（可选）

`node.declare_signal(path, schema=None, description="")` **可以**把一条路径写进 `Manifest.signals`，供订阅者参考：

- 这是**声明**，不产生信号；
- `schema` 是可选的 JSON Schema，**只用于对外宣告**，发布时**不做**校验、订阅时**不做**强制；
- `signal_source` 会隐式声明路径。

因此清单中的路径列表**可以**与运行时实际发布的路径不一致——实现**不得**把它当成准入清单。

---

## 4. 通配符匹配算法

匹配是**纯函数**：`pattern_matches(pattern, path) -> bool`。接收方对每个注册的模式独立调用它。本节逐行对应参考实现。

### 4.1 算法

```
pattern_matches(pattern, path):
    # 分支 1：精确相等
    if pattern == path:
        return True

    # 分支 2：多段通配 ".**"
    if pattern.endswith(".**"):
        prefix = pattern[:-3]                  # 去掉末尾 3 个字符 ".**"
        return path == prefix or path.startswith(prefix + ".")

    # 分支 3：单段通配 ".*"
    if pattern.endswith(".*"):
        prefix = pattern[:-2]                  # 去掉末尾 2 个字符 ".*"
        if not path.startswith(prefix + "."):
            return False
        return "." not in path[len(prefix) + 1:]   # 剩余部分不能再含点

    # 分支 4：其余一律不匹配
    return False
```

三条判定**必须**按上述顺序执行，命中即返回。

### 4.2 分支逐一说明

| 分支 | 条件 | 结果 | 关键点 |
|---|---|---|---|
| 1 | `pattern == path` | `True` | 无通配符的常规路径走这一支。**注意**：这一支对**含 `*` 的字符串也生效**——当模式与路径逐字相同时（例如两侧都是 `ai.*`）返回 `True` |
| 2 | 模式以 `.**` 结尾 | `path == prefix` **或** `path.startswith(prefix + ".")` | `prefix` 是去掉 `.**` 后的剩余部分。注意 `path == prefix` 分支意味着 `.**` 匹配**前缀自身**（零段） |
| 3 | 模式以 `.*` 结尾 | 前缀匹配且剩余部分不含点 | `.*` **不**匹配前缀自身——它要求**至少**一段 |
| 4 | 其它 | `False` | 这是「模式中间出现 `*`」与「模式不含通配符但不相等」的落点 |

### 4.3 按算法推导的匹配结果

下表**必须**与实现一致：

| 模式 | 语义 | 匹配示例 | 不匹配示例 |
|---|---|---|---|
| `ai.state` | 精确 | `ai.state` | `ai.state.x`、`ai`、`ai.states` |
| `ai.*` | 恰好一段 | `ai.state`、`ai.progress` | `ai`、`ai.state.x` |
| `system.**` | 零或多段 | `system`、`system.cpu`、`system.cpu.load.1` | `systematic`、`system.cpuX`（不含点则 `path == prefix` 只对 `system` 成立） |
| `*` | 中间/落单通配符（字面量） | —— | **全部路径**（恒为 `False`） |
| `ai.*.state` | 中间的 `*` 视为字面量 | —— | **全部路径**（恒为 `False`） |
| `**` | 不是以 `.**` 结尾 | —— | **全部路径**（恒为 `False`） |
| `*.state` | 中间的 `*` 视为字面量（不以 `.*` / `.**` 结尾，落第 4 分支） | 仅**逐字相同**的路径 `*.state` | 其余全部，含 `ai.state`、`*.x`、`*.a.b` |
| `` (空串) | 精确分支命中空路径 | 空路径 `""` | 其余全部 |

> 上表第 7、8 行的行为是算法的**字面结果**，不是设计意图。实现**不得**为了让它们「看起来更合理」而偏离算法——匹配规则是互操作契约的一部分（[README.md §1.3](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#1-修订历史) 规定改匹配算法**必须**发新修订号）。

### 4.4 两个易错点（**必须**明确）

**易错点 1：通配符只在模式末尾有效，中间的 `*` 是字面量且恒不匹配。**

`ai.*.state` **不会**匹配 `ai.cpu.state`。算法的第 3 分支只认「以 `.*` 结尾」，而 `ai.*.state` 以 `state` 结尾，于是落到第 4 分支返回 `False`。同理：

- `system.*.cpu` → 恒 `False`；
- `*.state` → 仅当路径**逐字等于** `*.state` 时为真，其余一律 `False`（它不以 `.*` 结尾，落第 4 分支）。

> 结论：需要「任意一层」时**不得**把 `*` 写在中间。改用 `**` 放在**末尾**（`ai.**`），它会匹配 `ai` 及其下任意深度——代价是它也匹配单段与更深的多段，精度低于「恰好一段」。

**易错点 2：空模式与「不含点号的前缀」按算法实际结果，不要臆测。**

逐个推导（`prefix` 为空的情况）：

| 模式 | `prefix` | 分支 2/3 的实际行为 | 实际结果 |
|---|---|---|---|
| `*` | 不适用 | 不以 `.**` 也不以 `.*` 结尾 → 落第 4 分支 | 恒 `False`（除逐字相等的路径 `"*"`） |
| `.*` | `""` | 第 3 分支：要求 `path.startswith(".")`，然后要求 `path[1:]` 不含点 | 匹配 `.a` 这类路径（字面以点开头）；对 `a.b` 为 `False` |
| `.**` | `""` | 第 2 分支：`path == ""` 或 `path.startswith(".")` | 匹配 `""` 与任何以点开头的路径 |
| `system.*` | `system` | 第 3 分支：`path.startswith("system.")`，且 `path[7:]` 不含点 | 匹配 `system.cpu`，不匹配 `system`（**`.*` 不匹配前缀自身**）与 `system.cpu.load` |
| `system.**` | `system` | 第 2 分支：`path == "system"` 或 `path.startswith("system.")` | 匹配 `system`、`system.cpu`、`system.cpu.load`（**`.**` 匹配前缀自身**） |
| `**` | 不适用 | 不以 `.**` 结尾（只有 2 个字符）→ 落第 4 分支 | 恒 `False` |

两个由此推出的规范级结论：

1. **`system.*` 不匹配 `system`**，而 **`system.**` 匹配 `system`**。想「域下所有内容（含域本身）」**必须**用 `.**`。
2. **裸 `*` 与裸 `**` 都不是有效模式**。它们恒不匹配（除逐字相等），**应当**被视为使用者笔误；实现**可以**在注册时警告，但**不得**把它们当成「匹配一切」的简写。

### 4.5 匹配的作用域

| 场景 | 是否使用路径通配符 |
|---|---|
| `signal` 的本地回调过滤（`on()`） | ✅ 是 |
| 工具名（`payload.tool`） | ❌ **否**——**必须**精确匹配（`_tools` 是字典查表） |
| Pattern ID（`Signal.pattern`） | ❌ **否**——**必须**精确匹配（`protocol.patterns` 是字典查表） |
| `node_id` | ❌ **否**——**必须**精确匹配（`connections` / `_neighbors` 是字典查表） |
| 授权表的 `pub` / `sub` 条目 | ✅ 复用 `pattern_matches`（[security.md §3.3](../security.md#33-四个动作)） |
因此：**工具调用不受通配符影响**。声明 `get_*` 这样的工具名**不会**让 `get_weather` 可被 `get_*` 调用。

---

## 5. 消息流

### 5.1 广播与本地过滤

```
 发布方 node_c                                   接收方 node_d
      │                                              │
      │ 1. @node.signal("ai.state") 的生成器 yield    │
      │      {"status": "thinking", "seq": 0}        │
      │ 2. node.publish("ai.state", payload)          │
      │ 3. 加锁快照 connections ─────────────────────┐│
      │                                              ││
      │ ── signal(path="ai.state", payload=…) ──────▶│ 4. 读循环 _dispatch
      │        （对每个已连对端各发一份）             │     第 1 步不命中
      │                                              │     第 2 步不命中（pattern=None）
      │                                              │     → _dispatch_core → _on_signal
      │                                              │ 5. 遍历回调表
      │                                              │     on("ai.state") 命中 → 调用
      │                                              │     on("ai.*")     命中 → 调用
      │                                              │     on("system.**") 不命中 → 跳过
      │                                              │ 6. 命中回调异常 → 记 warning，继续下一个
      ▼                                              ▼
```

### 5.2 扇出时的失败处理

```
 publish(path, payload)
        │
        ├─ 加锁：peers = list(connections.items())
        │
        └─ for peer_id, conn in peers:
               try:
                   conn.send(encoded)
               except ConnectionClosed:
                   _handle_disconnect(peer_id, conn)   ← 清理该对端，继续下一个
```

**必须**：一个对端的发送失败**不得**中断循环，**不得**向外抛出异常。

### 5.3 「没有总线的总线」

广播模型不需要中心 broker 就能拼出中间件拓扑：**每个中间件就是一个普通节点**。

```
 来源节点群                     中间件节点 fmt                观察者节点群
   │                              │                              │
   │ ── signal(log.app.raw) ────▶ │                              │
   │ ── signal(log.web.raw) ────▶ │                              │
   │                              │ @on("log.**") 收全部原始日志  │
   │                              │ 转换（时间戳、级别、脱敏）    │
   │                              │ publish("log.formatted.**")  │
   │                              │ ───────────────────────────▶ │ @on("log.formatted.**")
   ▼                              ▼                              ▼
```

规范条文：

1. 中间件**必须**是一个普通 `MSPNode`——**不得**要求协议层提供任何 broker/代理角色；
2. 中间件**应当**「订阅一个域、发布到另一个域」（`log.**` → `log.formatted.**`），使下游可以用域粒度切换「原始流」与「加工流」；
3. 中间件**不得**修改它转发的路径语义——**应当**通过**新增**域或层级（`log.formatted.*`）来表达加工，而不是复用原路径；
4. 中间件的转发**不得**造成同一路径上的自激循环（例如同时 `@on("log.**")` 与 `publish("log.x")`）；实现**应当**通过域隔离避免。

### 5.4 版本化路径

路径是**字符串**，因此演进靠**并行挂载**而不是改语义：

| 做法 | 评价 |
|---|---|
| `x.changed` 与 `x.changed.v2` **并行发布** | ✅ 推荐：老订阅者继续收 `x.changed`，新订阅者用 `x.changed.v2`；两者互不干扰，切换是订阅侧的选择 |
| 直接把 `x.changed` 的含义改成 v2 | ❌ **不得**：老订阅者会静默收到语义不同的数据 |

论证：

1. **匹配算法是前缀式的**。`x.changed.**` 会同时匹配 `x.changed` 与 `x.changed.v2`——因为第 2 分支要求 `path == "x.changed"` 或 `path.startswith("x.changed.")`，两种都成立。因此「用通配符一次订阅全部版本」**可以**做到，是升级期的便利。
2. **精确订阅是隔离手段**。只想锁定 v1 的订阅者用精确模式 `x.changed`，它**不会**匹配 `x.changed.v2`。
3. **域优先约定让版本可以放在动作之后**。`<域>.<实体>.<动作>` 的第三层是动作，版本号**应当**作为动作之后的新分段出现（`x.changed.v2`），**不得**插在域与实体之间（`x.v2.changed` 会破坏 `x.**` 的域粒度）。

**应当**：破坏性变更时**同时**发布旧版与新版至少一个版本周期，并在 `Manifest.signals` 中把两者都声明。

### 5.5 发布方的自我可见性

发布**不**回环到本节点：`publish()` 只遍历 `connections`，调用方自己的 `on()` 回调**不会**被自己发布的信号触发。

**必须**明确这一点——实现**不得**依赖「本地发布也会触发本地回调」的假设：

- 需要本地处理时**必须**在 `publish()` 之后直接调用本地函数，或**可以**实现一个显式的本地回环（非本规范要求）；
- 这是与 MQTT 等「客户端订阅自己的主题会收到自己消息」的模型的**已知差异**，跨实现互操作时**不得**假设对方会回环。

---

## 6. 数据类型

### 6.1 `signal` 信号的字段

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `type` | `"signal"` | **必须** | |
| `source` | `str` | **必须** | 发布方 `node_id`；接收方**可以**据此做来源过滤（当前**未**实现，见 §10 G4） |
| `path` | `str` | **必须** | 路径，见 §3 |
| `payload` | `object` | **必须** | 任意 JSON 对象；缺省 `{}` |
| `target` | `null` | **必须** | 广播无目标 |
| `pattern` | `null` | **必须** | 核心模式不写路由键 |
| `reqid` | `null` | **必须** | 广播不关联 |
| `timestamp` | `float` | **必须** | Unix 时间戳，发布方本地时钟 |

JSON 示例：

```json
{
  "type": "signal",
  "source": "node_c",
  "pattern": null,
  "target": null,
  "path": "ai.state",
  "reqid": null,
  "payload": {"status": "thinking", "seq": 0},
  "timestamp": 1791331200.5
}
```

`Signal` 信封字段一律 **snake_case**。`payload` 内部字段名由**发布者**自定，**应当**与发布者 `Manifest.signals[path].schema` 的声明一致；接收方**必须**对未知字段宽容（不得因未知字段报错）。

### 6.2 回调注册项

`handlers` 是 `list[tuple[Optional[str], Callable]]`：

| 元素 | 类型 | 说明 |
|---|---|---|
| 第 1 项 | `str \| None` | 路径模式；`None` 匹配全部 |
| 第 2 项 | `Callable[[Signal], None]` | 回调函数 |

**没有**注销 API、**没有**优先级、**没有**「只触发一次」语义。遍历顺序是注册顺序，但**不得**依赖顺序——见 §10 G2。

### 6.3 无订阅表

**必须**明确：实现中**不存在**订阅表（`PathMatcher` 容器已在广播模型落地时删除）。

| 维度 | 已删除的订阅表 | 本模式的 `handlers` | `sub` 授权过滤 |
|---|---|---|---|
| 位置 | 发布方远端 | 接收方本地 | 发布方本地 |
| 内容 | 「哪个对端想要哪个路径」 | 「本进程哪个回调关心哪个路径」 | 「允许哪个对端收哪些路径」 |
| 变更方式 | 需要 subscribe / unsubscribe 信号 | 本地调用 `on()`，**零线上报文** | 本地 Preset 配置 |
| 目的 | 带宽优化 | 消费分发 | **安全** |
| 状态 | 已删除 | ✅ 存在 | 🔵 规划中 |

`sub` 授权与已删除的订阅表**形状相似但性质不同**：订阅表回答「谁**想**要」，`sub` 授权回答「谁**能**看」。因此按**安全**需要加回 per-peer 过滤，**不掺**带宽优化（[security.md §3.7](../security.md#37-与广播模型的张力)）。

---

## 7. 边界

### 7.1 通配符的用武之地

| 场景 | 说明 |
|---|---|
| **观察 / 监控面板** | `on("metric.**")` 一次覆盖全部指标 |
| **日志聚合** | `on("log.**")` 收全部日志域 |
| **权限审计** | `on("auth.**")` 收全部鉴权事件 |
| **粗粒度感知** | `on("notify.**")` 覆盖全部现有与未来通知来源 |
| **任务旁观** | `on("task.**")` 旁观 `msp/task` 的状态与产物广播 |

共同点：**接收方预先不知道未来会出现哪些具体路径**，但知道它们**一定**落在某个域下。这正是域优先约定的服务对象。

### 7.2 通配符**不**适用之处

| 场景 | 原因 |
|---|---|
| 工具调用 | `payload.tool` **必须**精确匹配（`_tools` 字典查表）；工具名集合是**封闭**的、随握手宣告的 |
| Pattern 路由 | `Signal.pattern` **必须**精确匹配（`protocol.patterns` 字典查表） |
| `node_id` 定位 | 连接表与邻居表是字典查表；`node.connections()` / `on_connected` 的 peer 参数都是精确 ID |

**不应**把「通配符很方便」推广到这三处——它们都需要**确定性**：调用一个工具、路由一个模式、对着一个对端发包，都不能有「可能匹配到多个」的歧义。

### 7.3 已知行为边界

| 边界 | 说明 |
|---|---|
| 无送达确认 | `publish()` 返回 `None`，不知道谁收到了 |
| 无顺序承诺跨对端 | 不同对端的接收顺序不保证一致 |
| 无去重 | 同一路径收到两条内容相同的信号，**必须**当作两次事件 |
| 无历史 | 晚连接的对端收不到连接前的信号；**不得**期待补发 |
| 无本地回环 | 见 §5.5 |
| 无过滤下推 | 见 §8 |

---

## 8. 安全考量

### 8.1 广播 = 全发，无法按内容过滤

**必须**认清本模式的默认形态：**`publish()` 把信号发给每一个已连对端，不区分对象，也不看内容。**

由此推出的规范后果：

1. 发布**敏感数据**前，发布方**必须**确认接收面的信任假设：本机自组网下所有对端共享同一 OS 用户（§8.1 的前提，此时 `sub` 授权按设计**整表绕过**），跨机部署则**必须**配置 `sub` 授权——两者都不成立时，协议没有可依赖的拦阻；
2. 需要「只给某些对端看」时，**不得**依赖路径命名（给路径起个晦涩名字**不构成**访问控制）；
3. 正确的收窄手段是**发送侧扇出过滤**（`sub` 授权），见 §8.2。

### 8.2 `sub` 授权是发送侧扇出过滤（✅ 已实现）

按 [security.md §3.6](../security.md#36-执行点只有两处) 的设计，出站过滤的执行点**只有一处**：`publish()` 的扇出循环——每个对端查 `sub` 授权，未授权的跳过。

| 项 | 规定 | 状态 |
|---|---|---|
| 位置 | `publish()` 的扇出循环内，每个对端一次判定 | 🔵 规划中（设计已定稿） |
| 匹配方式 | 复用 `pattern_matches`，对 `sub` 的 path 模式列表逐条比对 | 🔵 |
| 默认 | `sub: False`（网络对端默认**不**收我的广播） | 🔵 |
| 本机例外 | loopback / UDS 同用户跳过整张授权表 | 🔵 |
| 与订阅表的区别 | 「谁**能**看」（安全），不是「谁**想**要」（带宽） | — |

**必须**：

1. `sub` 过滤**必须**在**发送侧**执行——**不得**依赖接收方自律（接收方可能是攻击者）；
2. 过滤**不得**改变报文字节（不裁剪 `payload`、不改 `path`），只决定「发或不发」；
3. 未实现授权时**必须**在文档与部署说明中明确「广播对全部已连对端可见」，**不得**默默假定安全。

### 8.3 接收侧不受信任

| 风险 | 对策 |
|---|---|
| 恶意对端洪泛广播 | 接收方**应当**做本地限流；协议层当前**没有**入站速率限制（§10 G5） |
| 回调抛出异常被用作放大手段 | 异常被捕获并记日志（§2.3 第 3 条）——但**日志本身**可能被洪泛淹没，实现**应当**做日志采样 |
| 回调中执行副作用 | 回调运行在读循环线程；实现**必须**把重活移交给工作线程（§2.3 第 5 条） |
| `payload` 承载恶意内容 | 接收方**必须**把 `payload` 当不可信输入解析；协议层**不**校验 `payload` 结构 |

### 8.4 路径命名不是权限

**不得**用路径命名承担授权功能：

- 路径是**公开的**（随广播发出，亦随 `Manifest.signals` 交换）；
- 路径匹配是**接收方本地**行为，攻击者可以注册任意模式；
- 因此「只有知道路径的人才能收到」**不成立**——在广播模型下，知道与否不影响**是否收到**，只影响**是否处理**。真正决定「是否收到」的只有发送侧的 `sub` 过滤。

辅助手段（**可以**采用，但**不得**当作唯一防线）：

- 内容级加密：`payload` 用对端公钥加密，使无密钥的对端即使收到也读不出；
- 分域发布：把敏感数据发到**独立的传输/网络**（如单独的 UDS 监听、单独的 TLS 通道），让不可信对端在传输层就够不着。

### 8.5 本机自组网的现实

在默认部署形态（localhost 自组网、同一 OS 用户）下，[security.md](../security.md#23-本机自组网为什么不做认证) 的结论适用：所有节点权限集合相等，广播可见性**不构成**额外风险——能够连上来的进程本来就能读到同样的东西。

**必须**明确的反面条件：一旦把监听扩展到 `0.0.0.0` 或跨机，上述前提**立即失效**，此时**必须**同时具备 TLS + 节点认证 + `sub` 授权（见 [security.md §2.4](../security.md#24-跨机安全随传输走)）。

---

## 9. 规范条文汇总（MUST/SHOULD 清单）

| # | 条文 | 级别 |
|---|---|---|
| P1 | `publish` 构造的 `type` **必须**是 `"signal"`，`target` / `pattern` / `reqid` **必须**为 `null` | **必须** |
| P2 | 路径**必须**放在 `Signal.path`，**不得**放进 `payload` | **不得** |
| P3 | 扇出**必须**遍历全部已连对端；发送失败**不得**中断循环 | **必须** |
| P4 | `publish()` **不得**返回送达确认；广播是尽力而为 | **不得** |
| P5 | `on(path=None)` **必须**匹配全部路径 | **必须** |
| P6 | 命中的每个回调**必须**被调用；回调异常**必须**被捕获且不影响其它回调 | **必须** |
| P7 | 回调**必须**在读循环线程上调用；**不得**在其中长耗时阻塞 | **不得** |
| P8 | 回调注册**必须**可重入（运行期可注册）；**不得**去重 | **必须** |
| P9 | 路径**必须**遵循域优先 `<域>.<实体>.<动作>` | **必须** |
| P10 | 路径**不得**包含点号以外的分隔符，**不得**与 Pattern ID 混用斜杠 | **不得** |
| P11 | 通配符**必须**只出现在模式末尾；中间的 `*` 是字面量且**必须**返回 `False` | **必须** |
| P12 | 匹配算法**必须**按 §4.1 的四分支顺序执行 | **必须** |
| P13 | `.**` **必须**匹配前缀自身；`.*` **必须**恰好匹配一段、**不得**匹配前缀自身 | **必须** |
| P14 | 裸 `*` / 裸 `**` / 中间含 `*` 的模式**必须**按算法返回 `False`，**不得**当作「匹配一切」 | **不得** |
| P15 | 匹配**必须**大小写敏感 | **必须** |
| P16 | 工具名 / Pattern ID / `node_id` **不得**使用通配符匹配 | **不得** |
| P17 | 信号源产出的非 `dict` 值**必须**被跳过 | **必须** |
| P18 | 信号源异常**必须**被隔离，**不得**影响其它信号源 | **必须** |
| P19 | 节点停止后**不得**继续发布 | **不得** |
| P20 | 破坏性路径变更**必须**用并行新路径（`x.changed` / `x.changed.v2`），**不得**原地改语义 | **不得** |
| P21 | 广播**不得**回环到发布方自身 | **不得** |
| P22 | `sub` 授权**必须**在发送侧扇出循环执行；未实现时**必须**在文档中声明广播的全发性质 | **必须** |
| P23 | 接收方**必须**把 `payload` 当不可信输入；协议层**不**校验其结构 | **必须** |

---

## 10. 已知缺口

| # | 缺口 | 影响 | 依据 |
|---|---|---|---|
| G1 | **没有注销 API**。`handlers` 只增不减，没有 `off()` / `unsubscribe()` | 动态订阅的生命周期只能靠「回调内部自行置标志位」模拟；长期运行且频繁注册的进程会持续增长 | `MSPProtocol.on` 只有注册路径；`handlers` 无移除点 |
| G2 | **无优先级的顺序依赖**。回调按注册顺序遍历，且无「停止传播」机制 | 实现**不得**依赖顺序；一个回调无法阻止后续回调运行 | `_on_signal` 的 `for path_filter, func in handlers` |
| G3 | **`pattern_matches` 无输入校验**。空模式、裸通配符、中间通配符都静默返回 `False` | 订阅写错时没有任何反馈——表现为「一条都收不到」 | `matcher.py` 第 36 行的兜底 `return False` |
| G4 | **无来源过滤**。`on()` 只有路径维度，没有 `sig.source` 维度 | 无法「只听 node_a 的 notify.**」；节点通配是 [DESIGN.md](../../designs.md) 记录的下一步 | `handlers` 的元素是 `(path, callback)` 二元组 |
| G5 | **无入站限速** | 恶意对端可以洪泛广播耗尽接收方 CPU / 日志 | `_on_signal` 逐条即时处理，无令牌桶 |
| G6 | ~~**`sub` 授权未实现**~~ ✅ 已实现 | 未授权的对端不再收到广播（发送侧逐对端过滤） | `publish()` 的扇出循环逐对端调 `grant_sub()`（`src/msp/protocol/protocol.py`）；本机对端按设计整表绕过（[security.md §3.5](../security.md#35-默认值与作用域)）。残留：`pub` / `sub` 没有「单模式全量放行」的写法（[security.md §9](../security.md#9-已知缺口) 第 5 条） |
| G7 | **发布无确认、无重传** | 对端掉线期间的信号永久丢失；晚连接者拿不到历史 | `publish()` 返回 `None` |
| G8 | **无本地回环** | 与 MQTT 语义不同，跨实现互操作时容易踩坑 | `publish()` 只遍历 `connections` |
| G9 | **`payload` 无 schema 校验** | `declare_signal(schema=...)` 只用于宣告，与 `node.tool` 的 `inputSchema` 同一缺口 | `declare_signal` 文档字符串明示「发布时不做校验」 |
| G10 | **节点层 `on()` 不支持 `callback=` 关键字** | `node.on(path="x", callback=cb)` 会失败；只能装饰器或直接用 `node.protocol.on(...)` | `MSPNode.on(path=None)` 只接收一个参数 |
| G11 | **`pattern_matches` 对 `pattern == path` 的逐字分支** | 若路径本身含 `*`（违反命名规范），含通配符的模式可能逐字命中，产生非预期匹配 | `matcher.py` 第 22–23 行 |

---

## 11. 参考实现映射

| 条文 | 源码文件与符号 |
|---|---|
| §2.1 报文形态 | `src/msp/protocol/protocol.py` → `MSPProtocol.publish` |
| §2.2 扇出与失败处理 | `src/msp/protocol/protocol.py` → `MSPProtocol.publish`、`_handle_disconnect` |
| §2.3 接收方过滤 | `src/msp/protocol/protocol.py` → `_dispatch`、`_dispatch_core`、`_on_signal` |
| §2.4 注册 API | `src/msp/protocol/protocol.py` → `MSPProtocol.on`；`src/msp/core/node.py` → `MSPNode.on` |
| §2.5 自动重复发布 | `src/msp/core/node.py` → `MSPNode.signal_source`、`signal`、`_run_signal_source`、`start` |
| §3.2 域优先约定 | `docs/DESIGN.md`「Signal path 的分层约定：域优先」；`src/msp/core/node.py` → `declare_signal`（路径只声明不校验） |
| §3.5 路径声明 | `src/msp/core/manifest.py` → `Manifest.add_signal`、`SignalDescriptor` |
| §4.1–4.3 匹配算法 | `src/msp/protocol/matcher.py` → `pattern_matches` |
| §4.4 两个易错点 | `src/msp/protocol/matcher.py` 模块文档字符串与第 22–36 行 |
| §4.5 匹配作用域 | `src/msp/protocol/protocol.py` → `_tools`、`patterns`、`connections`（均为字典精确查表） |
| §5.3 没有总线的总线 | `docs/DESIGN.md`「应用场景：虚拟总线」 |
| §5.4 版本化路径 | 依赖 `pattern_matches` 的前缀分支（`matcher.py` 第 25–34 行） |
| §5.5 无本地回环 | `src/msp/protocol/protocol.py` → `MSPProtocol.publish`（只遍历 `connections`） |
| §6.2 注册项结构 | `src/msp/protocol/protocol.py` → `MSPProtocol.handlers` 的类型注解 |
| §6.3 无订阅表 | `src/msp/protocol/matcher.py` 文档字符串「原来的 `PathMatcher` 容器已随之删除」 |
| §8.2 `sub` 授权 | `src/msp/protocol/protocol.py` → `MSPProtocol.grant_sub`（扇出循环的调用点）与 `MSPProtocol.publish`；授权表见 `src/msp/core/grants.py` |
| §10 G1 无注销 | `src/msp/protocol/protocol.py` → `MSPProtocol.on`（只有注册路径） |
| §10 G4 无来源过滤 | `docs/DESIGN.md`「未来扩展：节点通配（二维匹配）」 |
