# MSP 模式层（Pattern Layer）

| | |
|---|---|
| **协议修订** | `2026-10-10` |
| **状态** | ✅ 已实现（`msp/streaming`、`msp/callback-push`、`msp/async-polling` 为 🔵 规划中） |
| **本页定义** | 通讯模式的抽象契约（`PatternHandler`）、协议层到模式层的路由判定顺序、核心模式与可扩展模式的划分依据、降级与互斥语义、模式登记流程，以及三个规划中模式的完整报文定义 |

> 常量来源：信号类型、模式 ID、错误码、默认参数一律以 [README.md](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#5-规范常量速查) 为准。本页**不得**引入索引之外的新常量；模式私有信号类型在正文中逐条声明。

---

## 1. 概述

### 1.1 模式层的存在理由

模式层把「一种交互的语义」做成**可插拔单元**，目的是让新增模式**不修改协议核心**。

协议核心知道的只有一件事：一个 `Signal` 从哪条连接来、`type` 是什么、`pattern` 是什么。它不知道「请求—响应要等回包」，也不知道「发布要扇出」。这些属于语义，属于模式。

把语义从核心剥离带来三条可验证的收益：

1. **新增模式 = 新增一个文件 + 一条注册表条目**。协议层的 `_dispatch` 判定顺序不需要任何改动（见 §3），因为路由键 `Signal.pattern` 早就在信封里。
2. **模式之间互不感知**。`msp/task` 不知道 `msp/multi-round` 存在；两者都用到 `input_required` / `input_response` 这两个同名信号类型，靠 `pattern` 字段区分归属，互不冲突。
3. **模式可以失败而不拖垮连接**。没有登记的模式处理不了自己的信号，但路由契约保证它会降级到协议层默认分发，而不是让连接断开（见 §3.4）。

### 1.2 在分层中的位置

```
 用户 API 层     MSPNode（node.call / node.publish / node.on / node.tool …）
      │
 模式层          PatternHandler 实例（msp/multi-round、msp/task …）
      │  ▲            ▲
      │  └── protocol._send() ──┐
      ▼                         │
 协议层          MSPProtocol.patterns（路由表）· _dispatch（路由）
      ▼
 传输层          Connection.send / receive（只搬字节）
```

模式层**位于协议层之上**，但**不拥有**协议层：它通过 `protocol.patterns` 被登记，通过 `protocol._send()` 发包，通过 `on_signal(protocol, peer_id, sig)` 收包。

### 1.3 与其他页的关系

| 页 | 关系 |
|---|---|
| [README.md](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#52-模式-id) | 模式 ID 与状态的唯一权威清单 |
| [base-protocol.md](base-protocol.md) | `Signal` 信封与核心信号类型的定义 |
| [request-reply.md](patterns/request-reply.md) | 核心模式之一，本页 §4 说明它为何不走 Handler |
| [publish-subscribe.md](patterns/publish-subscribe.md) | 核心模式之二，同上 |
| [multi-round.md](patterns/multi-round.md) | 可扩展模式参考实现，示范「模式私有信号类型」惯例 |
| [task.md](patterns/task.md) | 可扩展模式参考实现，同上 |
| [schema.md](schema.md) | JSON 形态的完整字段定义 |

---

## 2. 契约：PatternHandler

`PatternHandler`（`src/msp/patterns/base.py`）是一个抽象基类（`abc.ABC`）。所有**可扩展模式**的实现**必须**是它的子类。

### 2.1 类属性

| 成员 | 类型 | 必需 | 语义 |
|---|---|---|---|
| `pattern_id` | `str` | **必须** | 模式的唯一标识，与 `Signal.pattern`、`Manifest.patterns` 中的字符串逐字一致 |
| `fallback_to` | `str \| None` | **可以**省略，缺省 `None` | 降级目标模式 ID（§6） |
| `conflicts_with` | `list[str]` | **可以**省略，缺省 `[]` | 与之互斥的模式 ID 列表（§4.3） |

`pattern_id` **必须**符合 [README.md §5.3](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#53-命名规范) 的 Pattern ID 格式 `[namespace/]name`。使用 `msp/` 前缀的模式**必须**由本规范定义；第三方模式**必须**使用自有前缀（例如 `acme/streaming`），**不得**占用 `msp/`。

参考实现示例（`msp/multi-round`）：

```python
class MultiRoundHandler(PatternHandler):
    pattern_id = "msp/multi-round"
    fallback_to = "msp/request-reply"
```

### 2.2 抽象方法 `on_signal`

```python
@abstractmethod
def on_signal(self, protocol, peer_id: str, sig) -> None: ...
```

| 形参 | 类型 | 语义 |
|---|---|---|
| `protocol` | `MSPProtocol` | 协议层实例，供 Handler 调用 `_send` 等方法 |
| `peer_id` | `str` | 发送该信号的**对端** `node_id` |
| `sig` | `Signal` | 完整信号对象 |

**必须**满足：

1. `on_signal` **必须**在**协议层的读循环线程**上被调用（路由是同步派发，不退避到工作线程）。因此它**不得**在其中执行长耗时操作。
2. 需要执行长时间工作（工具调用、网络往返、等待对端回答）的 Handler，**必须**把工作移交给独立线程（`threading.Thread(...).start()`），理由见 §3.5。
3. `on_signal` 的返回值为 `None`；模式的「响应」**必须**通过 `protocol._send()` 显式发出，**不得**依赖返回值回传。

### 2.3 可选方法 `install_api`

```python
def install_api(self, node) -> None:
    """向节点注入语法糖并保存节点反引用。默认什么都不做。"""
    pass
```

约定（源自 `base.py` 的文档字符串，并被 `msp/multi-round`、`msp/task` 遵循）：

1. **应当**保存 `self._node = node`，供自身公开方法内部使用，避免用户手动传 `protocol` / `node_id`。
2. **可以**在 `node` 上挂短名（如 `node.multiround = self`、`node.streaming = self`）。
3. 短名**必须**唯一，且**不得**与 `MSPNode` 的核心 API 冲突。核心 API 至少包括：`node_id`、`manifest`、`endpoint`、`preset`、`protocol`、`transport`、`discoveries`、`presences`、`start`、`stop`、`settle`、`publish`、`on`、`on_connected`、`on_disconnected`、`call`、`tool`、`signal`、`signal_source`、`declare_signal`、`register_pattern`、`pattern`、`ensure_connected`、`neighbors`、`connections`、`peer`、`peers`、`connected_peers`、`peer_manifest`、`fetch_manifest`。
4. 基类的默认实现是空操作，所以不注入语法糖的模式**可以**不覆写。

### 2.4 激活时机

Handler 由**注册表**在激活时实例化，用户**不应当**手动构造（`node.register_pattern` 的文档字符串把「与 Preset 启动路径一致」列为理由）。激活过程见 §3.6。

---

## 3. 路由契约

本节是模式层与协议层之间**唯一**的接口约定，**必须**与 `MSPProtocol._dispatch` 逐行对应。

### 3.1 三步判定顺序

收到任何信号，协议层**必须**按以下顺序判定，且**必须**在前一步命中时**立即返回**、不再继续：

**第 1 步 — 核心信号类型**

若 `sig.type` ∈ `{hello, ack, ping, pong, error}`，**必须**交给协议层自处理（`_dispatch_core`），**不得**查模式表。

> 这一条意味着：即使一个 `hello` 信号携带了 `pattern` 字段，也**不会**被路由到任何 Handler。核心信号类型是模式层的**禁区**。

**第 2 步 — 带 `pattern` 且已登记**

否则，若 `sig.pattern` 非空**且** `sig.pattern` 命中 `protocol.patterns`（即本节点已激活该模式的 Handler），**必须**调用该 Handler 的 `on_signal(protocol, peer_id, sig)`，然后返回。

`protocol.patterns` 是一个 `dict[str, PatternHandler]`，键为 `pattern_id`。

**第 3 步 — 默认核心分发**

否则（`sig.pattern` 为空，**或** `sig.pattern` 非空但未登记），**必须**交给 `_dispatch_core`。未知 `type` **必须**回 `error`，载荷 `code = -32600`、`message = "未知信号类型: <type>"`（`_reply_error` 会带上原信号的 `reqid`）。

### 3.2 判定流程图

```
                      收到 Signal
                           │
        ┌──────────────────┴──────────────────┐
        │ type ∈ {hello, ack, ping, pong,     │ 是
        │         error} ?                    ├──────▶ _dispatch_core（协议层自处理）
        └──────────────────┬──────────────────┘
                           │ 否
        ┌──────────────────┴──────────────────┐
        │ pattern 非空 且 pattern 已登记 ?     │ 是
        └──────────────────┬──────────────────┘──────▶ handler.on_signal(protocol, peer_id, sig)
                           │ 否
                           ▼
                    _dispatch_core
                    ├─ signal          → _on_signal（本地回调过滤）
                    ├─ tool_call       → _on_tool_call（独立线程执行）
                    ├─ tool_result     → _on_tool_result（唤醒 reqid 等待者）
                    ├─ manifest_update → _on_manifest_update
                    ├─ ping            → 回 pong
                    ├─ pong            → 忽略（last_seen 已在读循环更新）
                    ├─ error           → _on_error（记日志）
                    └─ 其它 type       → 回 error(code=-32600)
```

### 3.3 路由键的写入方

发信号的一方**必须**在构造信号时显式声明 `pattern`：

```python
protocol._send(peer_id, Signal.make(
    type=self.TOOL_CALL,          # 模式私有信号类型
    source=self._node.node_id,
    target=peer_id,
    reqid=reqid,
    payload={"tool": tool, "args": args},
).with_pattern(self.pattern_id))  # ← 路由键
```

`Signal.with_pattern(pattern)` 就地设置 `pattern` 字段并返回 `self`，便于链式调用。

**核心模式的信号不写 `pattern`**：`tool_call` / `tool_result` 的 `pattern` 为 `None`（见 [request-reply.md](patterns/request-reply.md)），`signal` 的 `pattern` 为 `None`（`publish` 不设置该字段，见 [publish-subscribe.md](patterns/publish-subscribe.md)）。它们因此稳定地走第 3 步。

### 3.4 未登记模式的行为（**必须**遵守）

1. **必须**：未知 `pattern` **不得**导致连接中断。第 2 步判定失败后**必须**继续走第 3 步。
2. **必须**：带未登记 `pattern` 的信号按第 3 步降级处理。若其 `type` 是已知核心类型，就按该类型处理（例如 `type="tool_call"` 且带未知 `pattern` 的信号**会**被当作普通工具调用执行）。
3. **必须**：未知 `type` 回 `error(code=-32600)`，`message` 形如 `未知信号类型: <type>`，且**不得**因此关闭连接。
4. **应当**：实现方对「收到未登记 `pattern` 的信号」记一条调试日志；参考实现当前**没有**记录，见 §10 的 G3。

> 注意第 3.4.2 条的一个后果：给 `tool_call` 加上一个**未登记**的 `pattern`，并不等于「拒绝对端」——它只是失去了模式层的特殊语义，仍会按核心语义执行。安全过滤**不得**依赖 `pattern` 字段（见 §9）。

### 3.5 `on_signal` 的运行线程与阻塞禁令

`_dispatch` 由 `_read_loop` 同步调用，而 `_read_loop` 是**该连接的唯一读线程**。因此：

- `on_signal` 中执行长耗时操作，**会**阻塞该连接后续所有消息的接收；
- 若长耗时操作本身还要等待对端回包（例如多轮模式的 `ask()`），**会**形成死锁——对端的回答正是被自己阻塞掉的那条消息。

所以任何需要执行工具、等待对端、或做阻塞 I/O 的 Handler **必须**：

```python
threading.Thread(target=self._run_tool, args=(...), daemon=True).start()
```

这一约定在 `msp/multi-round`（`_on_tool_call` → `_run_tool`）与协议核心（`_on_tool_call` → `_run_tool`）中一致，是本规范的**必须**级要求在模式层的同构表述。

### 3.6 激活路径

Handler 进入路由表有两条等价路径，**必须**都落到同一个激活动作：

| 路径 | 触发 | 行为 |
|---|---|---|
| Preset 启动 | `Preset.patterns` 中的每个 ID | 构造 `cls()` 并激活；核心模式 ID 跳过 |
| 运行时登记 | `node.register_pattern(pattern_id, metadata=None)` | 从 `PATTERN_REGISTRY` 取类，若存在且未激活则构造并激活 |

激活动作（`MSPNode._activate_pattern`）固定为三件事，顺序**必须**是：

1. `handler.install_api(node)` — 注入语法糖；
2. `node._patterns[handler.pattern_id] = handler` — 节点侧索引（`node.pattern(id)` 的查询源）；
3. `protocol.patterns[handler.pattern_id] = handler` — 协议层路由表。

第 1 步在第 3 步之前，是为了让 `install_api` 里挂的短名与公开方法在路由生效时已经可用。

---

## 4. 核心模式与可扩展模式

### 4.1 划分

| 类别 | 模式 ID | 实现位置 | `PATTERN_REGISTRY` 条目 |
|---|---|---|---|
| **核心模式** | `msp/request-reply` | 协议层（`MSPProtocol` 的 `call` / `_on_tool_call` / `_run_tool` / `_on_tool_result`） | **无** |
| **核心模式** | `msp/publish-subscribe` | 协议层（`MSPProtocol` 的 `publish` / `on` / `_on_signal`） | **无** |
| **可扩展模式** | `msp/multi-round` | 独立文件 `patterns/multi_round.py` | 有 |
| **可扩展模式** | `msp/task` | 独立文件 `patterns/task.py` | 有 |
| **规划中** | `msp/streaming` / `msp/callback-push` / `msp/async-polling` | 尚未实现 | 尚未登记 |

判定「是核心模式」的依据是常量集合，不是约定：

```python
CORE_PATTERNS = frozenset({"msp/request-reply", "msp/publish-subscribe"})
```

`MSPNode.__init__` 与 `register_pattern` **必须**用这个集合判定并跳过 Handler 实例化。因此 `protocol.patterns` 与 `node._patterns` 中**不会**出现核心模式的条目——这不是遗漏，而是核心模式不参与模式层路由的证据。

### 4.2 为什么这两个是核心

三个理由，每一个都指向**协议层状态**：

1. **信号路由依赖协议层**。`_dispatch` 本身就是协议层的函数；如果 request-reply / publish-subscribe 也走 `on_signal`，那么「收包 → 路由」的第 2 步会立刻命中它们，第 3 步的默认分发（含 `manifest_update`、`ping`）反而成为不可达代码。核心语义必须坐在路由**之下**，不能坐在路由**之上**。
2. **`reqid` 关联依赖协议层状态**。`pending_calls: dict[str, tuple[threading.Event, list]]` 是协议层字段，`_on_tool_result` 需要用它唤醒等待者。把它搬进 Handler 意味着连接断开时（`_handle_disconnect`）要跨层回调每个 Handler 去清理各自的等待表——把一个内聚的失效处理拆成 N 份。
3. **广播扇出依赖协议层状态**。`publish` 需要遍历 `connections: dict[str, Connection]` 并直接调用 `conn.send()`。Handler 只能通过 `protocol._send(peer_id, ...)` 逐个发；扇出循环、`ConnectionClosed` 处理与去重连接（`_finish_handshake` 的规范方向）都属于协议层。

另外有一条**兼容性**理由：`tool_call` / `tool_result` / `signal` / `manifest_update` 是 [README.md §5.1](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#51-核心信号类型signaltype) 冻结的核心信号类型。若把它们交给模式层，则「只用 request-reply 的最小实现」（互通的最低公分母）也必须加载模式层，抬高了下限。

### 4.3 `conflicts_with` 的语义

`conflicts_with: list[str]` 声明「本模式与被列出的模式**不得**同时激活」。

- 该属性的语义是**声明式**的：它**不得**被理解为「会自动关闭对方」。参考实现当前**不读取** `conflicts_with`（见 §10 的 G2），因此**不得**依赖运行时自动校验。
- 一个实现若在激活模式时读取 `conflicts_with` 并拒绝冲突组合，**必须**以明确错误终止启动，**不得**静默忽略其中一方。
- 两个模式若只共享信号类型名而语义不同（如 `msp/multi-round` 与 `msp/task` 都定义 `input_required` / `input_response`），**不构成**冲突——因为二者都用不同的 `pattern` 值路由，报文空间不重叠。

---

## 5. 模式如何取得协议层能力与 `install_api` 的推广

### 5.1 取得协议层能力

`on_signal` 的第一个形参就是 `MSPProtocol` 实例。Handler 通过它使用协议层能力：

| 能力 | 用法 | 性质 |
|---|---|---|
| 发包 | `protocol._send(peer_id, sig)` | **私有方法，但属于既定惯例** |
| 广播 | `protocol.publish(path, payload)` | 公开方法 |
| 本节点 ID | `protocol.node_id` | 公开属性 |
| 连接表查询 | `protocol.connections` | 公开属性 |

关于 `_send` 的下划线前缀，本规范如实写明：

> **`protocol._send()` 是私有方法，但在模式层中是既定惯例（established convention）。** `msp/multi-round` 与 `msp/task` 的全部定向发包都通过它完成；`protocol` 对象是 `on_signal` 的显式形参，正是为了把这一能力合法地交给 Handler。**不得**用「它是私有方法」为由要求模式层改用 `conn.send()`——那会绕过连接登记与 `RuntimeError("未连接到 X")` 的统一失败语义。

调用约定：

1. `_send(peer_id, sig)` 在**未连接**时抛 `RuntimeError(f"未连接到 {peer_id}")`，连接**刚好关闭**时抛 `ConnectionClosed`。Handler **应当**捕获这两者并记调试日志，**不得**让异常穿透到读循环（会触发 `_read_loop` 的 `except Exception` 分支，断开与对端的连接）。
2. 发信号时**必须**填 `source=protocol.node_id`；定向回包**应当**填 `target=<对端 node_id>`；需要关联的往返**必须**填 `reqid`。
3. Handler **不得**直接操作 `protocol.connections` 做删除/替换——连接生命周期的唯一权威是协议层。

### 5.2 `install_api` 的推广

`install_api` 是**任意层组件**的通用扩展点，不只是模式层：

| 层 | 实现该方法的组件 | 注入的语法糖 |
|---|---|---|
| 模式层 | `MultiRoundHandler` | `node.multiround` |
| 模式层 | `TaskHandler` | `node.task` |
| 发现层 | `ManualConnect` | `node.add_manual_source(...)`（运行时动态加发现源） |
| 宣告层 | 参考实现中暂无 | — |

注入点只有一处，代价约 4 行：

```python
def _install_layer_api(self, component) -> None:
    install = getattr(component, "install_api", None)
    if install is not None:
        install(self)
```

调用时机：`MSPNode.__init__` 在构造每个 discovery / presence 实例**之后立即**调用；模式层的 `install_api` 则由 `_activate_pattern` 调用（§3.6）。

规范条文：

1. 任意层组件**可以**定义 `install_api(node)`；定义了就**必须**接受且仅接受一个位置参数 `node`；
2. 组件**应当**在其中保存节点反引用（`self._node = node`）；
3. 挂到 `node` 上的名字**必须**唯一，且**不得**与 §2.3 列出的核心 API 冲突；
4. `install_api` **不得**在其中发起网络 I/O 或阻塞等待——它运行在 `MSPNode.__init__` 路径上。

---

## 6. `fallback_to` 与降级语义

### 6.1 属性语义

`fallback_to` 声明「当对端未宣告本模式时，本模式**应当**降级为哪个模式」。它**必须**是另一个已定义的 Pattern ID，且**不应当**形成环（`A → B → A`）。

### 6.2 方向判定

降级的触发条件是**对端能力清单**，不是本地配置：

1. 发送方**应当**先读取 `protocol.peer_manifests[peer_id]["patterns"]`（或 `node.peer(peer_id).supports(pattern_id)`）；
2. 若目标模式在列表中（或对端是 `FULL_PEER` 这类全模式预设）→ 用本模式；
3. 否则 → 用 `fallback_to` 指明的模式，或直接拒绝发起。

### 6.3 当前实现状态（如实）

**参考实现未实现自动降级。** 依据：

- `fallback_to` 在 `MultiRoundHandler`（`multi_round.py:56`）与 `TaskHandler`（`task.py:302`）上**各声明一次**（值均为 `"msp/request-reply"`），全代码库**没有任何读取点**；
- `MSPProtocol.call()` **不检查** `peer_manifests[peer_id]["patterns"]`，直接把 `tool_call` 发出去；
- `MSPNode.call()` 同样不检查；
- 对端未激活该模式时，信号按 [§3.4](#34-未登记模式的行为必须遵守) 降级到第 3 步的默认分发——**这恰好是 request-reply 的语义**，所以「预期中的降级」在核心模式方向上是**偶然成立**的，而不是被显式实现。

因此：

- **应当**：实现方在发起扩展模式交互前自行检查 `peer.supports(pattern_id)`，并自行选择降级或拒绝；
- **不得**：把「对端未宣告该模式」当作连接级错误；
- **可以**：实现自动降级，但一旦实现，**必须**在降级时保持 `reqid` 关联语义不变（降级只换报文形态，不换关联键的作用域）。

### 6.4 `Manifest` 侧的对应字段

对端支持的模式列表来自 `Manifest.patterns`（序列化为 `patterns: list[str]`）。注意 JSON 键名是 **snake_case 的 `patterns`**，而 `Manifest` 内部的多数字段序列化为 camelCase（`patternMetadata`、`inputSchema`、`mimeType`）。模式私有元数据住在 `patternMetadata: {pattern_id: dict}`，由 `Manifest.set_pattern_metadata()` 写入。

### 6.5 与其他降级路径的区别

「降级」在本规范里出现三次，语义不同，**不得**混用：

| 说法 | 触发条件 | 落点 | 级别 |
|---|---|---|---|
| `fallback_to` 降级 | 对端未宣告目标模式 | 换用另一套模式报文（发送方选择） | **应当** |
| 路由降级 | `pattern` 未在 `protocol.patterns` 中登记 | 走第 3 步默认核心分发（协议层自动） | **必须** |
| 传输降级 | 连接不可达 / 冷却中 | `PeerUnavailable` → `ToolResult(error=...)` | **必须** |

前两者只在「模式装配不全」时才有区别：`fallback_to` 是**主动换模式**，路由降级是**被动退回核心语义**。

---

## 7. 规划中的模式

本节三个模式状态为 🔵 **规划中**。按 [README.md §2](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#2-规范性用语) 的定义：**实现者可以不实现，但一旦实现必须符合条文**。

三个模式**共用**下列总则：

- 模式私有信号类型**必须**同时携带 `pattern` 字段（值为对应 `pattern_id`）才能被路由；
- 载荷字段**必须**逐字使用本节给出的键名；`Signal` 信封字段用 snake_case（`type` / `source` / `target` / `path` / `reqid` / `payload` / `timestamp` / `pattern`），`payload` 内部字段**应当**沿用 camelCase（与 `structuredContent`、`blobId`、`mimeType` 的既有风格一致），本节逐字段写明；
- 三种模式都**不得**新增核心信号类型；
- 三种模式都**必须**在 `Manifest.patterns` 中宣告后才能被对端发起；未宣告即发起时按 §6.2 判定降级（`msp/async-polling` 正是 `msp/streaming` 与 `msp/callback-push` 的兜底目标）。

### 7.1 `msp/streaming` — 分块流式传输

**用途**：把一次性的长结果拆成多个增量块推送，使接收方在结果完整之前就能消费（增量渲染、边下边用、进度感知）。

**私有信号类型**：`stream_start`（开启流）、`stream_chunk`（数据块）、`stream_end`（结束，携带终态摘要）、`stream_cancel`（双向，任一方请求取消，可选实现）。四个类型**必须**携带 `reqid` 与 `pattern="msp/streaming"`。

**载荷字段**（键名**必须**逐字一致）：

| 信号 | 字段 | 类型 | 必需 | 语义 |
|---|---|---|---|---|
| `stream_start` | `streamId` | `str` | **必须** | 流标识；与 `reqid` 并存——`reqid` 用于关联，`streamId` 用于日志与多流复用 |
| | `totalChunks` / `totalBytes` | `int \| null` | **可以** | 已知总量；未知时省略或 `null` |
| | `contentType` | `str` | **可以** | 载荷 MIME 类型，缺省 `application/octet-stream` |
| | `ordering` | `str` | **可以** | `"ordered"`（默认）或 `"unordered"`，声明块是否可乱序到达 |
| | `meta` | `object` | **可以** | 模式无关的附加元数据（如工具名、任务 ID） |
| `stream_chunk` | `seq` | `int` | **必须** | 块序号，从 `0` 起单调递增；`ordering="unordered"` 时仍**必须**给出，接收方据此重排 |
| | `data` | `str` | **必须** | 块内容；二进制**必须**按 Base64 编码 |
| | `encoding` | `str` | **可以** | `"utf-8"`（默认）或 `"base64"` |
| | `final` | `bool` | **可以** | 缺省 `false`；`true` 等价于随后 `stream_end` 的简写 |
| `stream_end` | `status` | `str` | **必须** | `"ok"` / `"canceled"` / `"error"` |
| | `chunks` / `bytes` | `int` | **可以** | 实际发出的块数 / 字节数 |
| | `checksum` | `str` | **可以** | 整体校验和（如 `sha256:<hex>`） |
| | `error` | `object` | **可以** | `status="error"` 时**必须**给出，形如 `{"code": int, "message": str}` |

`stream_chunk` 与 `stream_end` 的 `streamId` 同样**必须**给出，且与 `stream_start` 一致。

**消息流**：

```
 发送方                                接收方
   │ ── stream_start(reqid=R) ─────────▶ │  准备接收（注册 streamId）
   │ ── stream_chunk(seq=0) ───────────▶ │  消费块 0
   │ ── stream_chunk(seq=1) ───────────▶ │  消费块 1
   │        ⋮                            │
   │ ◀── stream_cancel(reqid=R) ──────── │  （可选）接收方要求停止
   │ ── stream_end(status="canceled") ─▶ │  发送方确认终止
   │ ── stream_end(status="ok") ───────▶ │  终态：流关闭，reqid 可回收
```

**终态**：每个流**必须**以恰好一个 `stream_end` 结束。收到终态后该 `reqid` 与 `streamId` **必须**被双方注销。

**错误**：

| 情形 | 处理 |
|---|---|
| 未知 `streamId` 的 `stream_chunk` | **必须**丢弃并记日志；**应当**回 `stream_cancel` |
| `seq` 重复 | **必须**以首个到达者为准，丢弃后来的 |
| `seq` 跳号 | `ordering="ordered"` 时**应当**等待重排窗口；超时后**必须**以 `status="error"` 结束 |
| 终态前连接断开 | **必须**置本地流为失败并释放资源，**不得**永久保留半成品 |
| 载荷校验失败 | **必须**以 `status="error"` 结束 |

**背压**：`streaming` **不得**假设发送方可以无界推送。接收方**可以**用 `stream_cancel` 施加粗粒度背压；实现**可以**定义细粒度流控（如窗口 `chunk_window` / `stream_ack`），但一旦定义**必须**在 `patternMetadata["msp/streaming"]` 中声明，并遵循 [README.md §1](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#1-修订历史) 的「追加」规则；发送方**不得**因对端处理慢而阻塞读循环——推送**必须**在自己的线程里进行。

**与大对象 `blob_ref` 的关系**：二者**不得**互相替代。

| 维度 | `msp/streaming` | `blob_ref` 内容块 |
|---|---|---|
| 用途 | 增量消费（边到边用、进度、增量渲染） | 大对象的**引用传递**，内容走独立通道按需取 |
| 是否承载完整数据 | 是（分块承载） | 否（只承载 `blobId` / `mimeType` / `size` / `checksum`） |
| 出现在哪里 | 独立信号流 | `tool_result.payload.content` 的一个块，`type="blob_ref"` |

需要**在传输过程中被消费**的用 `streaming`；只是**体积大、可延后**取用的用 `blob_ref`。`blob_ref` 的取值通道（`blob_chunk` 信号流）属于 [base-protocol.md](base-protocol.md) 的范畴，本页不定义其报文。

**互斥与降级**：`conflicts_with = []`（与 `msp/task` 的产物广播可以并存）；`fallback_to = "msp/request-reply"`，降级语义 = 「一次性把完整结果作为 `tool_result` 返回」。

### 7.2 `msp/callback-push` — 长任务回调式回传

**用途**：提交一个长任务后**不阻塞等待**，任务完成时由被委托方**主动推**一条回调信号给提交方（也可推给提交方指定的第三方观察者）。

**私有信号类型**：`callback_register`（注册回调）、`callback_ack`（接受或拒绝的回执）、`callback_push`（结果回传）、`callback_cancel`（撤销，可选实现）。四个类型**必须**携带 `reqid` 与 `pattern="msp/callback-push"`。

**载荷字段**：三个信号的 `callbackId` 均**必须**给出并互相回显。

| 信号 | 字段 | 类型 | 必需 | 语义 |
|---|---|---|---|---|
| `callback_register` | `callbackId` | `str` | **必须** | 本次回调的标识，由提交方生成 |
| | `topic` | `str` | **必须** | 逻辑主题，实现自定（可用 `node_id` 或 `task.<id>`） |
| | `deliverTo` | `str` | **可以** | 结果投递目标 `node_id`；省略时即注册方自身 |
| | `path` | `str` | **可以** | 投递方式为广播时指定 `signal.path` |
| | `expiresAt` | `float` | **可以** | Unix 时间戳，超过后注册**必须**失效 |
| | `expect` | `str` | **可以** | `"result"`（默认）或 `"progress"` |
| `callback_ack` | `callbackId` / `accepted` | `str` / `bool` | **必须** | 回显与是否接受 |
| | `ttl` | `float` | **可以** | 被委托方愿意保留注册的秒数 |
| | `reason` | `str` | **可以** | `accepted=false` 时**应当**给出 |
| `callback_push` | `state` | `str` | **必须** | `"progress"` / `"completed"` / `"failed"` / `"canceled"` |
| | `content` | `list` | **可以** | content 块列表，格式与 `tool_result.payload.content` 完全一致 |
| | `structuredContent` | `any` | **可以** | 结构化结果，格式与 `tool_result.payload.structuredContent` 一致 |
| | `error` | `str` | **可以** | 失败原因；`state="failed"` 时**应当**给出 |
| | `seq` | `int` | **可以** | `state="progress"` 时的进度序号 |

**消息流**：

```
 提交方                                被委托方
   │ ── callback_register(reqid=R) ────▶ │  登记 callbackId → (deliverTo, topic)
   │ ◀── callback_ack(accepted=true) ─── │  回执
   │                                     │  ……任务异步执行……
   │ ◀── callback_push(state=progress) ── │  （可选）进度
   │ ◀── callback_push(state=completed) ─│  终态
   │ ── callback_cancel(reqid=R) ──────▶ │  （可选）撤销
```

**终态**：`callback_push.state` ∈ `{completed, failed, canceled}` 之一**必须**是本次回调的最后一条推送；此后该 `callbackId` **必须**被双方注销。

**错误**：

| 情形 | 处理 |
|---|---|
| `callback_ack.accepted=false` | 提交方**必须**停止等待推送，并按 `fallback_to` 走显式轮询 |
| 注册过期（`expiresAt` 已过） | 被委托方**必须**丢弃该 `callbackId`；推送失败**不得**无限重试 |
| 推送目标不可达 | 被委托方**必须**丢弃该注册并记日志；**不得**阻塞任务线程 |
| 未知 `callbackId` 的 `callback_push` | 接收方**必须**丢弃并记日志 |
| 重复终态推送 | 接收方**必须**以首个终态为准 |

**互斥与降级**：`conflicts_with = []`（与 `msp/task` 可并用——`msp/task` 负责状态机与多观察者广播，本模式负责定向回传）；`fallback_to = "msp/async-polling"`，降级语义 = 「不注册回调，改为提交方按 `callbackId` 显式轮询」。

### 7.3 `msp/async-polling` — 显式轮询语义（互操作兜底）

**用途**：互操作兜底。当对端既不支持 `streaming` 也不支持 `callback-push` 时，用「提交 → 轮询 → 取结果」这一最朴素的语义完成长任务协作。它是三个规划模式中**能力最弱但最可移植**的一个，也是另外两者的兜底目标。

**私有信号类型**（七个，**必须**携带 `reqid` 与 `pattern="msp/async-polling"`）：`poll_submit` → `poll_submit_result`、`poll_status` → `poll_status_result`、`poll_fetch` → `poll_fetch_result`，以及可选的 `poll_cancel`。

**载荷字段**：

- `poll_submit`：`tool`（`str`，**必须**）、`args`（`object`，**可以**）、`jobId`（`str`，**可以**，省略时由执行方生成）、`ttl`（`float`，**可以**，作业保留秒数）。
- `poll_submit_result`：`jobId`（**必须**）、`state`（**必须**）、`accepted`（`bool`，**必须**）。
- `poll_status`：`jobId`（**必须**）。`poll_status_result`：`jobId`（**必须**）、`state`（**必须**）、`progress`（`float`，**可以**，`0.0`–`1.0`）、`eta`（`float`，**可以**）。
- `poll_fetch`：`jobId`（**必须**）、`offset`（`int`，**可以**，分片取结果时用）。`poll_fetch_result`：`jobId`（**必须**）、`state`（**必须**）、`content`（`list`，**可以**）、`structuredContent`（`any`，**可以**）、`error`（`str`，**可以**）。

**`state` 取值**（本模式私有，**不得**与其他模式的状态字符串混用）：`pending`（已接受，未开始）、`running`（执行中）、`completed`（**终态**，结果可 `poll_fetch`）、`failed`（**终态**）、`canceled`（**终态**）、`not_found`（**终态**，未知或已过期的 `jobId`）。

**消息流**：

```
 提交方                                执行方
   │ ── poll_submit(reqid=R1) ─────────▶ │  接受作业，返回 jobId
   │ ◀── poll_submit_result(jobId=J) ─── │  state=pending
   │ ── poll_status(reqid=R2, J) ──────▶ │
   │ ◀── poll_status_result(state=running)│
   │        ⋮  （提交方自定轮询间隔）      │
   │ ── poll_status(reqid=R3, J) ──────▶ │
   │ ◀── poll_status_result(state=completed)
   │ ── poll_fetch(reqid=R4, J) ───────▶ │
   │ ◀── poll_fetch_result(content=…) ── │  终态数据交付
```

**终态**：`poll_status_result.state` 或 `poll_fetch_result.state` 为终态之一时本次协作结束；执行方**可以**在 `ttl` 之后回收该 `jobId`，此后查询**必须**返回 `not_found`（而**不得**返回 `failed`）。

**错误**：

| 情形 | 处理 |
|---|---|
| 未知 / 过期 `jobId` | **必须**回对应结果信号并置 `state="not_found"`；**不得**回 `error` 信号 |
| 轮询过快 | 执行方**可以**回 `state="running"` 并附 `eta`；**不得**因此断开连接 |
| `poll_fetch` 在非终态调用 | **必须**回 `state=running` 且**不得**附带 `content` |
| 取消 | 协作式：**必须**置取消标志并尽快回 `state="canceled"`；**不得**承诺强杀执行线程 |

**互斥与降级**：`conflicts_with = []`；`fallback_to = None`——本模式是**兜底链的末端**，再往下只剩「用 `msp/request-reply` 同步等一个短工具」，那不属于本模式的定义范围（见 §6.2）。

### 7.4 三者的选择顺序（**应当**）

```
需要增量消费 ─────▶ msp/streaming ──（对端未宣告）──▶ msp/callback-push
   需要结果主动回传 ──▶ msp/callback-push ──（对端未宣告）──▶ msp/async-polling
       兜底 ──▶ msp/async-polling ──（对端未宣告）──▶ msp/request-reply
```

---

## 8. 模式登记

新增一个可扩展模式**必须**完成以下步骤（对应 [README.md §8](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#8-参与演进) 的演进顺序）：

| 步骤 | 动作 | 落点 |
|---|---|---|
| 1 | 在 [README.md §5.2](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#52-模式-id) 的模式 ID 表新增一行，附状态标记 | 规范 |
| 2 | 在本页 §7（规划中）或新增页（已实现）给出完整条文：信号类型、载荷字段、消息流、终态、错误、互斥、`fallback_to` | 规范 |
| 3 | 在 [schema.md](schema.md) 同步报文形态 | 规范 |
| 4 | 新建 `src/msp/patterns/<name>.py`，实现 `PatternHandler` 子类 | 实现 |
| 5 | 在 `PATTERN_REGISTRY` 增加一条 `"<pattern_id>": <HandlerClass>` | 实现 |
| 6 | 若需随预设启动，加入相应 `Preset.patterns`；否则用 `node.register_pattern(pattern_id)` 运行时登记 | 实现 |
| 7 | 补测试；若为不兼容变更，在修订历史新增修订号 | 实现 + 规范 |

约束：

- 第 4–5 步**必须**成对出现。只在注册表加条目而没有 Handler 文件会让 `PATTERN_REGISTRY` 导入失败。
- 模式 ID 使用 `msp/` 前缀时**必须**先走完第 1–3 步；第三方模式**必须**自带前缀。
- 模式私有信号类型**不得**与 [README.md §5.1](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#51-核心信号类型signaltype) 的九个核心类型重名；`msp/` 之外的模式**必须**为自己的类型加前缀（`acme_stream_start`），避免跨模式撞名。
- 模式**不得**要求修改 `_dispatch` 的判定顺序（§3.1）。

一个最小骨架：

```python
# src/msp/patterns/streaming.py
class StreamingHandler(PatternHandler):
    pattern_id = "msp/streaming"
    fallback_to = "msp/request-reply"

    def install_api(self, node) -> None:
        self._node = node          # 约定：保存反引用
        node.streaming = self      # 约定：挂短名（不得与核心 API 冲突）

    def on_signal(self, protocol, peer_id: str, sig: Signal) -> None:
        ...  # 按 sig.type 分派；重活交给独立线程
```

```python
# src/msp/patterns/__init__.py
PATTERN_REGISTRY["msp/streaming"] = StreamingHandler   # 新增一条注册表条目
```

**注意**：`msp/streaming` 等三个规划模式一旦落地，**必须**同时在 `PATTERN_REGISTRY` 中出现，**不得**被加入 `CORE_PATTERNS`——它们不依赖协议层状态，属于可扩展模式。

---

## 9. 安全考量

| # | 考量 | 条文 |
|---|---|---|
| 1 | **`pattern` 不是安全边界** | 路由契约规定未登记 `pattern` 的信号降级到默认分发（§3.4），攻击者可以省略或伪造 `pattern` 绕过模式层的任何自建检查。授权判定**必须**基于信号类型与载荷（如 `tool_call` 的 `payload.tool`），**不得**基于 `pattern` |
| 2 | **`type` 字段被多模式共享** | `msp/multi-round` 与 `msp/task` 都定义 `input_required`。**不得**用 `type` 单独判定语义，**必须**配合 `pattern`；**不得**认为 `type` 相同则载荷可互换 |
| 3 | **`install_api` 会往 `node` 上挂名字** | 覆盖核心 API（如 `node.call = ...`）会直接破坏节点行为（见 §2.3 命名禁令）。加载路径 `PATTERN_REGISTRY` 是**静态导入**，属供应链信任问题，不是运行时可被远端触发的漏洞 |
| 4 | **模式层与协议层同权** | Handler 通过 `protocol._send` 可对任意已连对端发信号（`msp/task` 的观察者广播即此类用法）。模式**必须**由节点运营者安装，**不得**支持对端远程注册模式 |
| 5 | **`streaming` 的资源耗尽面（🔵）** | 分块流把「一条大消息」拆成「N 条小消息」，接收方为每个未完成流保留缓冲区会引入内存放大攻击面。实现**必须**为每个 `streamId` 设资源上限，超限时以 `stream_end(status="error")` 结束（同一意图见 `ttl` 与 `expiresAt`） |
| 6 | **授权过滤的落点不在模式层** | 出站扇出的 `sub` 授权过滤属于协议层 `publish` 的循环（见 [publish-subscribe.md](patterns/publish-subscribe.md#8-安全考量)、[security.md](security.md#36-执行点只有两处)）。模式**不得**自行实现「谁能看」的策略，否则会出现多处策略漂移 |

---

## 10. 已知缺口

按「事实」而非「意图」列出，供实现者判断可依赖程度。

| # | 缺口 | 影响 | 依据 |
|---|---|---|---|
| G1 | `fallback_to` 无任何读取点，**自动降级未实现** | 发起扩展模式前必须自行检查 `peer.supports(pattern_id)`；否则报文发出去后按默认分发处理 | `multi_round.py:56` 与 `task.py:302` 各一处声明，全库零读取点 |
| G2 | `conflicts_with` 无任何读取点，**互斥无运行时校验** | 冲突组合可以同时激活，行为未定义 | 全代码库无读取点 |
| G3 | 未登记 `pattern` 的信号**静默降级**，无日志 | 模式装配错误难以定位（同一 `tool_call` 成功执行，但走的是核心路径而非模式路径） | `_dispatch` 第 2 步无 `else` 分支 |
| G4 | `protocol.patterns` 与 `node._patterns` 不含核心模式 | `node.pattern("msp/request-reply")` 返回 `None`；核心模式的 API 只能从 `node` 上取（`node.call` / `node.publish` / `node.on`） | `CORE_PATTERNS` 跳过逻辑 |
| G5 | 模式**能力协商只到「列举」层** | `Manifest.patterns` 会交换，但没有任何代码在发信号前检查对端是否宣告了该模式 | `_dispatch` 与 `call` 均不查清单 |
| G6 | 三个规划模式（`msp/streaming` / `msp/callback-push` / `msp/async-polling`）**未实现** | 本页 §7 的条文当前无法在参考实现上验证 | 无对应文件与注册表条目 |
| G7 | `install_api` 的短名冲突**无运行时检测** | `node.multiround = self` 这类赋值会静默覆盖既有属性 | `_install_layer_api` 只做 `getattr` 后调用 |
| G8 | `on_signal` 抛出异常会被 `_read_loop` 的 `except Exception` 捕获并**断开连接** | Handler 的局部 bug 会升级为连接级故障 | `_read_loop` 的 `logger.warning("读循环异常…")` + `_handle_disconnect` |

---

## 11. 参考实现映射

| 条文 | 源码文件与符号 |
|---|---|
| §2.1–2.3 `PatternHandler` 契约（`pattern_id` / `fallback_to` / `conflicts_with` / `on_signal` / `install_api`） | `src/msp/patterns/base.py` → `PatternHandler`（四个实现点：`patterns/multi_round.py`、`patterns/task.py`、`discovery/manual.py` 的 `install_api`） |
| §3.1 三步判定顺序与默认分发 | `src/msp/protocol/protocol.py` → `MSPProtocol._dispatch`、`_dispatch_core` |
| §3.1 未知类型回 `-32600` | `src/msp/protocol/protocol.py` → `_dispatch_core`（`else` 分支）、`_reply_error` |
| §3.3 路由键写入 | `src/msp/core/signal.py` → `Signal.with_pattern`；`patterns/multi_round.py` → `call_multiround` / `_ask` / `_reply_result` |
| §3.4 未登记模式降级 | `src/msp/protocol/protocol.py` → `_dispatch`（第 2 步无 `else`） |
| §3.5 独立线程执行 | `src/msp/protocol/protocol.py` → `_on_tool_call`；`patterns/multi_round.py` → `MultiRoundHandler._on_tool_call` |
| §3.6 / §8 激活与登记 | `src/msp/core/node.py` → `__init__`、`register_pattern`、`_activate_pattern`、`_install_layer_api`、`pattern`；`src/msp/patterns/__init__.py` → `PATTERN_REGISTRY`；`src/msp/core/preset.py` → `Preset.patterns` |
| §4.1 核心模式集合 | `src/msp/core/node.py` → `CORE_PATTERNS` |
| §4.2 `reqid` 与扇出状态 | `src/msp/protocol/protocol.py` → `pending_calls`、`connections`、`call`、`publish` |
| §5.1 使用私有 `_send` | `src/msp/protocol/protocol.py` → `_send`；`patterns/task.py` → 各 `_send` 调用点 |
| §6.3 无自动降级 | `src/msp/patterns/multi_round.py` → `MultiRoundHandler.fallback_to`；`src/msp/patterns/task.py` → `TaskHandler.fallback_to`（两处声明，均无读取点） |
| §6.4 清单侧字段 | `src/msp/core/manifest.py` → `Manifest.patterns`、`pattern_metadata`、`set_pattern_metadata`、`to_dict` |
| §7.1–7.3 三个规划模式 | 无（🔵 规划中，无对应文件与注册表条目） |
| §10 G7 / G8 | `src/msp/core/node.py` → `_install_layer_api`；`src/msp/protocol/protocol.py` → `_read_loop`、`_handle_disconnect` |
