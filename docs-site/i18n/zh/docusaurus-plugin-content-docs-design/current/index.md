# MSP 协议设计文档

本文档记录 MSP 的设计决策与取舍（为什么这样设计），与 README（怎么用）互补。
架构总览见 [README.md](https://github.com/hxh230802/MSP/blob/master/README.md) 的「架构」章节。

## 设计原则

- **万物皆节点（Everything is a node）**：节点的身份、能力、状态统一为 `Manifest` + `Endpoint`。
- **万物皆信号（Everything is a signal）**：工具调用、广播、握手、心跳、状态更新，全部是 `Signal` 的实例，不同的只是 `type`。
- **每层皆可扩展（Every layer is extensible）**：`core` 之外的 discovery / presence / transport / patterns 全部可插拔，核心改动最小化。

## ProReAct：等待是订阅，不是行动

### 问题

传统 ReAct 循环是拉式、回合制：Observation 只来自工具返回值，所以「等待」这个非动作在循环里没有合法表达，只能伪装成动作——智能体要等一个异步任务完成（下载文件、推送构建、跑完作业）时，只能 `sleep(45)` 再检查，没完成就再 `sleep`、再检查。轮询不是策略，是被迫的表达：模型把「不行动」硬写成「行动」，token 与回合全耗在「什么都没发生」上。

### 决策

MSP 的信号广播把「等待」从循环里拿出来，交给协议层：智能体把「我对什么感兴趣」注册成本地回调（`on("notify.web.download", cb)`），然后挂起；状态真正变化时对端 `publish` 该路径、广播到所有已连节点，本地回调匹配后把智能体唤醒。等待从「行动」降格为「订阅」（本地声明兴趣），从主动轮询变为被动唤醒——这就是协议名里 "Sensing" 的落点。

### 边界

这不等于「ReAct 绝对做不到事件驱动」：给模型一个阻塞式 `wait_until(path)` 工具，或让环境把事件注入上下文，都能在 agent 层拼凑出等效效果。区别在责任的归属——感知在 ReAct 里是模型自己的责任（agent 层 workaround），在 MSP 里是协议层的一等原语。同一种能力，一个由模型负责，一个由协议负责。

## 命名规范

三种命名空间各司其职，避免语义混淆：

| 类型 | 分隔符 | 格式 | 例子 |
|---|---|---|---|
| Node ID | 无 | `[a-z0-9_-]+` | `file_monitor` |
| Signal path | `.` | `segment(.segment)*` | `system.file.modified` |
| Pattern ID | `/` | `[namespace/]name` | `msp/multi-round` |
| Tool name | 无 | `[a-z0-9_-]+` | `get_weather` |

### Signal path 的分层约定：域优先

Signal path 遵循 **`<域>.<实体>.<动作>`**，域在最前：

| 层级 | 含义 | 例子 |
|---|---|---|
| 域 | 稳定的功能分类 | `notify`, `system`, `ai`, `sensor` |
| 实体 | 信号的来源或主体 | `web`, `file`, `state`, `temperature` |
| 动作 | 具体发生了什么 | `download`, `modified`, `progress` |

- **域优先**：`notify.web.download` 而非 `web.notify.download`。域是稳定、
  面向功能的分类，实体是可变、面向实现的来源。把域放最前，接收方用
  `notify.**` 即可一劳永逸地捕获所有现有和未来的通知，不因新增一个来源
  而修改过滤规则。
- 通配符 `*` / `**` 以域为锚点分段匹配（见下一节）。
- Pattern ID 用斜杠是全局命名空间需要（反向域名前缀），与 Signal path 的
  点号分层是两个不同概念，永不混用。

## 通配符过滤（本地回调）

Signal path 的精确匹配之外，本地回调 `on()` 支持两种通配符（只在模式末尾）：

| 模式 | 语义 | 例子 |
|---|---|---|
| 精确 | `path == pattern` | `ai.state` 只匹配 `ai.state` |
| `*` | 恰好一段 | `ai.*` 匹配 `ai.state`，不匹配 `ai.state.sub` |
| `**` | 零或多段 | `system.**` 匹配 `system` 及其下任意层 |

实现见 `protocol/matcher.py`：`pattern_matches(pattern, path)` 纯函数。广播模型
下没有订阅表——`publish` 把信号发给所有已连对端，接收方用 `on()` 注册的模式做
本地匹配，命中的回调才触发。协议线上格式零改动：通配符就是 `on()` 模式里的
一个字符串。

### 应用场景：虚拟总线

通配符过滤让「中间件」「聚合器」成为普通节点，无需中心 broker：

- 通知优化软件 `on("notify.**")`，任何按约定前缀 `notify.*` 发布的信号自动被接收；
- 日志聚合接收 `log.**`、监控面板接收 `metric.**`、权限审计接收 `auth.**`；
- 每个中间件是独立节点，接收命名空间、转换后转发，是 Unix 管道哲学在信号层的再现。

### 未来扩展：节点通配（二维匹配）

当前只实现路径通配。节点维度（`@node.on(node="*", path="notify.**")`）作为
下一步：在 `on()` 模式里加节点维度，本地回调按 `sig.source` 做节点过滤，形成
「节点 × 路径」二维匹配（MQTT / Redis Pub/Sub 都没有的能力）。广播已经把信号
送到每个节点，这一步纯属本地过滤，无需改动协议层。

## 与 JSON-RPC 2.0 的关系

**结论：MSP 在编码层不采用 JSON-RPC 信封，但在「工具调用」这一子集上做 JSON-RPC 2.0 语义对齐；互通靠可选的 `Signal ↔ JSON-RPC` 桥，不改核心。**

### 背景

JSON-RPC 2.0 只定义信封：请求 `{jsonrpc, method, params, id}`、响应 `{jsonrpc, result|error, id}`、通知（无 `id`）。它不定义发现、发布订阅、能力协商、传输——这些恰是 MSP 的核心。而 MCP（Model Context Protocol）的消息层正是 JSON-RPC 2.0，这是 MSP 值得考虑对齐的唯一外部理由。

### 重叠范围

MSP 的 `Signal` 里只有 request-reply 模式与 JSON-RPC 语义同构：

| MSP Signal | JSON-RPC 2.0 |
|---|---|
| `reqid` | `id` |
| `payload.tool` | `method` |
| `payload.args` | `params` |
| `payload.content` / `payload.structuredContent` | `result` |
| `payload.error` | `error.message`（`error.code` 取约定值，如内部错误 `-32603`、未知工具 `-32601`） |
| `type: "tool_call"` | request（有 `id`） |
| `type: "tool_result"` | response |

其余信号超出 JSON-RPC 范围：

- `SIGNAL`（信号广播）—— JSON-RPC 无发布订阅语义；
- `input_required` / `input_response`（多轮往返）—— 需要服务器反向向客户端发请求，JSON-RPC 单向模型表达不了；
- `HELLO/ACK`、`MANIFEST_UPDATE`、`PING/PONG` —— MSP 自有握手 / 能力 / 探活；
- `pattern` / `source` / `target` / `path` —— JSON-RPC 信封没有对应字段，只能塞进 `params`。

### 决策：不全面遵守，只做语义对齐

**不全面遵守**的理由：

1. **单向 vs 全双工**：JSON-RPC 是单向 request → response；MSP 是双方都能主动发消息的全双工协议。
2. **信封不匹配**：`Signal` 的 `pattern` 路由、`path`、`source/target` 是 MSP 的一等公民，压进 `method/params` 会丢语义或绕弯。
3. **迁移成本**：全面迁移要改 `_encode/_decode`、`Signal`、所有 pattern 的 `on_signal`，破坏「Everything is a signal」的统一性，收益却只覆盖约 20% 的消息。

**语义对齐**的做法（零代码）：声明上表的映射——「MSP 的 `tool_call` 即 JSON-RPC request，`tool_result` 即 JSON-RPC result/error」。MSP 的工具调用因此在语义上就是 JSON-RPC 2.0 兼容的。

### 互通的钩子：可选 codec 桥

若将来需要与 MCP / JSON-RPC 生态直接互通，做一个 `Signal ↔ JSON-RPC` 转换器，挂在 transport 之上、与 transport 一样可插拔，而不是改 `core`。互通是可选能力，核心保持统一 `Signal` 信封。

## 任务模式（msp/task）与 A2A 等价映射

**结论：A2A 不是「一种模式」而是「一个协议栈」；MSP 只搬 A2A 真正新增的「任务语义」，落地为 `msp/task` 模式，交互复用现有原语。**

### 问题

A2A（Agent2Agent）解决「agent 把一整段任务委托给另一个 agent」：任务状态机（submitted→working→input-required→completed/failed/canceled）+ 产物（Artifact）。MSP 已有 request-reply / pubsub / multi-round，缺的正是「任务生命周期」这一抽象。能否让 MSP 原生跑出等价 A2A 的任务语义？

### 决策

实现 `msp/task` 模式：把 A2A 的任务语义拆成信号（定义在模式内部，不污染核心 `SignalType`），只新增「状态机 + 产物」这一层：

| A2A | msp/task |
|---|---|
| `message/send` | `task_submit` → `task_submit_result`（阻塞到「接受」，不等到完成） |
| `message/stream`（SSE） | `task_status` / `task_artifact` / `task_result` 流 |
| `tasks/get` | `task_query` → `task_query_result` |
| `tasks/cancel` | `task_cancel` → `task_cancel_result` |
| `input-required` 态 | `ctx.ask()`（`input_required` / `input_response`，复用 multi-round 的 ask 机制） |
| TaskState | state 字符串 1:1 |
| Artifact + Part | `Artifact(name, description, parts=[content 块])`（复用 content.py） |
| `contextId` | 可选 `context_id` 透传 |
| Agent Card | `Manifest.pattern_metadata["msp/task"]`（未来 adapter 按需投影成 A2A card） |
| webhook 推送（单订阅者） | **观察者广播**：额外 publish 到 `task.<id>.<kind>`，任何节点 `on("task.**")` 旁观 |

### 取舍

1. **submit 非阻塞**：`submit()` 只阻塞到「接受」（拿回 task_id + submitted 态），与 A2A `message/send` 返回非终态 Task 一致；等完成用 `handle.wait()`（另有 `submit_and_wait` 糖）。阻塞到完成是反模式：任务可能跑几小时，客户端不该傻等。
2. **取消是协作式**：置 cancel_event + 立即发终态，worker 后续 emit 全部 no-op；不强行杀线程（Python 限制）。
3. **多观察者是 A2A 没有的能力**：A2A 的 SSE/webhook 都是单订阅者；MSP 的 pubsub 天然让第三方节点旁观任务进度，这是相对 A2A 的差异化点。
4. **input-required 复用 multi-round 的 ask 机制**：不重造；任务模式内部再次定义同名信号（pattern 不同，路由不冲突）。
5. **A2A 是协议栈而非模式**：本模式只搬 A2A 的「任务语义」；对接 A2A 生态的 HTTP/JSON-RPC 适配器是下一步，本模式是其地基。

## 工具输入 schema：签名自省与零硬依赖

### 问题

工具参数需要对外宣告描述与约束（类似 C# 的 `<param>` 注释），且 schema 校验迟早要做，约束应一并抽取。

### 决策

`schema_from_func` 从函数签名自动生成 JSON Schema，缺省生成、显式传入时以传入为准。参数描述与约束双兼容：

| 写法 | 提取内容 |
|---|---|
| `Annotated[str, "城市名"]` | `description` |
| `Annotated[int, Field(ge=0, le=100)]` | `ge` / `le` / `gt` / `lt` / `min_length` / `max_length` / `pattern` |
| `enum.Enum` 子类 | JSON `enum`（取 `.value`，与 pydantic / FastAPI 一致） |

两个实现要点：

1. **`get_type_hints(func, include_extras=True)`**：默认的 `get_type_hints` 会剥掉 `Annotated` 的元数据，必须显式开 `include_extras`。
2. **零硬依赖的 Pydantic 兼容**：不 `import pydantic`，用 duck-typing `type(meta).__name__ == "FieldInfo"` 识别 `Field`，用户装不装 pydantic 都能跑。项目唯一第三方依赖仍是 `watchdog`。

### 取舍

- `Optional[Literal]` / `Optional[Enum]` 的内层 schema 无 `type` 键，用 `anyOf` 表达可空，避免非法的 `{"type": null}`。
- 自省结果当前只用于对外宣告，不参与运行时校验；校验留到将来，约束字段已备好。

## Peer 视图

### 问题

一个邻居的信息散落在多处：`Endpoint` 在节点层，`Connection`、能力清单在协议层。想「访问邻居的所有信息」需要跨层拼凑。

### 决策

引入 `Peer`，把散落的信息聚合为一个只读对象：

- **视图而非存储**：`Peer` 不持有状态，每次属性访问都从所属节点实时读取；对端更新清单或断开后，同一个 `Peer` 对象立即反映最新状态，无需同步副本。
- **只查询，不操作**：`call` 仍放在节点上；`publish` 是广播、不面向单个对端，故不属于 `Peer`。
- **宽容未知对端**：查询一个未知 peer 返回 `None` / `[]` / `False`，不抛异常。

API：`peer.endpoint` / `peer.manifest`（返回副本）/ `peer.connection` / `peer.is_discovered` / `peer.is_connected` / `peer.tools()` / `peer.signals()` / `peer.patterns()` / `peer.supports(pattern_id)` / `peer.has_tool(name)` / `peer.has_signal(path)`。

## 对等端故障：错误即值、疑似死亡冷却与目录租约

### 问题

P2P 里对端随时可能不可达（崩溃、重启、断网）。「对端没了」是常态，不是异常；`call()` 若抛异常会直接打断调用方程序。同时需要一个机制区分「暂时连不上」与「真的死了」，并自动清理死节点。

### 决策

三条机制各司其职：

1. **错误即值**：`node.call()` 对端不可达（`PeerUnavailable`）、未知节点（`UnknownPeer`）、超时、中途断连，一律返回 `ToolResult(error=...)`，不抛异常打断调用方；只有程序性错误才 raise，`unwrap()` 显式抛 `ToolError`。
2. **疑似死亡 = 软冷却，不删邻居**：连接失败在 `_unavailable` 记 `now + connect_backoff`，冷却期内快速失败、不再重拨；成功则清除。**不删 `_neighbors`**——`DirectoryScan` 按声明 hash 去重，声明文件还在就不会重新发现，硬删会永久失去一个只是暂时失败的对端。
3. **目录租约 + TTL = 硬清理**：`DirectoryWrite` 周期性刷新 `timestamp`（租约）；`DirectoryScan` 丢弃超过 `stale_after` 的声明。崩溃节点不再续约 → 声明过期 → 从邻居表自然消失。

### 取舍

- **软标记与硬清理分离**：连接失败是「疑似」，声明过期才是「确认」，两个时间尺度互不干扰。
- 缺失 `timestamp` 的旧声明视为永不过期（向后兼容既有文件格式）。
- 握手读超时**已补**（原缺口）：`MSPProtocol.handshake_timeout`（默认 10 s，可经节点 `config` 覆盖）配合 `Connection.set_read_timeout()`；对端 accept 了 TCP 却永不回 ACK 时，握手以 `ConnectionClosed` 结束并关闭连接，不再永久阻塞拨号线程。

## 启动时序：settle（默认等建连落地）

### 问题

`start()` 里各层的时序是混的：传输 `listen` 是同步的，宣告 `announce` 是同步的，
**发现也是同步的**（`watch()` 会先跑一次全量扫描），但 eager 的拨号在后台线程里。
于是 `start()` 返回时的状态是「邻居已知、连接未必在」：紧接着 `publish()` 会扇出到
空的连接集合——广播模型下这既不是异常也不是错误码，而是**静默丢失**；紧接着
`call()` 则靠 `ensure_connected()` 现场兜底（能连上，但把首次调用的延迟推给了调用方）。

对使用者来说，这意味着「`start()` 之后要不要再 sleep 一下」变成了必须靠经验回答的
问题。测试里遍地 `wait_until(lambda: "a" in node.connections())`，就是这个问题的外部症状。

### 决策

`start(settle=True, settle_timeout=0.5)`：启动完成后等一次「发现驱动的在建拨号全部
落地（成功或失败）」，返回是否在超时前稳定；另提供独立的 `node.settle(timeout)`。

三条性质是刻意的：

1. **默认开启**：成功路径上拨号通常几十毫秒就落地，settle 立即返回，几乎没有额外
   成本；只有连不上的对端才会耗尽超时。默认关等于把这个坑留给每个调用方。
2. **只等待，不发起**：`settle()` 从不调用 `ensure_connected()`，它等的只是「已经有人
   在做的连接」。所以 `connect_policy="lazy"` 下它是 no-op（没有在建拨号，立即返回
   `True`），**绝不会把 lazy 节点变成 eager**——settle 与 `connect_policy` 正交。
3. **登记先于起线程**：`_on_endpoint` 在起拨号线程**之前**同步把 peer 计入「在建」
   集合，线程 `finally` 里注销并唤醒。若反过来在 `ensure_connected()` 里登记，settle
   可能赶在拨号线程被调度之前看到空集合，把「还没开始」误判成「已经稳定」——默认
   开启的保证就成了假的。

### 取舍

- **不是「网络就绪」的完整承诺**：边界明确——只覆盖发现驱动的拨号，不含 `call()` /
  `fetch_manifest()` / `msp/task` 自己发起的建连；也不保证连上 `start()` 之后才
  announce 的节点。
- **不按策略分支**：没有写成「eager 才 settle」。lazy 下自动 no-op 更可预测：调用方
  不需要知道自己的 preset 是哪种，也不会出现「换个 preset 语义就变」。
- **超时是上界不是错误**：`False` 只表示仍有拨号在飞，节点照常可用。握手读超时（默认 10 s，
  见上节）在这里表现为该次拨号较快失败并进入冷却，而不是让 `call()` 永久卡死。
- **不做「至少连上 N 个」**：这类要求会把「对端未就绪」升级成启动失败，与「错误即值」
  的容错取向冲突；需要强保证时，使用方应在 settle 之后自己检查 `connections()`。

## 扩展钩子（install_api）

### 问题

想要「运行时动态添加发现源」这类语法糖，又不愿为核心加一行改动。

### 决策

任意层组件可定义 `install_api(node)`；`MSPNode` 在构造完组件后调用它（若存在），组件即可往 node 上挂便捷方法，而不改核心。代价是核心约 4 行（`_install_layer_api`）。

- 通讯模式用它挂 `node.multiround`；
- 手动发现用它挂 `node.add_manual_source(...)`（运行时动态加发现源）。

```python
node.start()
node.add_manual_source("http://registry2:8080/nodes")  # 运行时动态加发现源
```

### 取舍

「核心零改动」与「语法糖」不可兼得时，选少量核心改动（约 4 行）换取任意层注入 API 的能力。

## UDS 传输（本机）

### 问题

本机自组网默认走回环 TCP。回环 TCP 有协议栈开销，本机多进程通信可以用更轻的 Unix Domain Socket。

### 决策

`UDSTransport`：字节流走 `AF_UNIX`，复用 `TCPConnection` 的 4 字节长度前缀分帧（零新分帧逻辑）。地址是文件路径（默认临时目录 `msp-<pid>-<rand>.sock`），与共享目录发现天然契合。`Preset.LOCAL_AI_UDS` 即 `LOCAL_AI` 换 UDS 传输。

### 取舍

- **仅 Linux/macOS**：Windows 的 Python 未暴露 `socket.AF_UNIX`，`listen()` / `connect()` 抛 `RuntimeError`；Windows 上继续用 TCP。
- socket 文件在进程退出后不自动删除：`listen()` 先清理残留（只删 `stat.S_ISSOCK` 类型的文件，防误删普通文件），`close()` 再 `unlink`。
- 权限收紧到 `0o600`（仅本用户可连），与安全模型「本机同用户全量信任」一致。

## 安全模型

### 结论：信任边界 = 传输可达，认证 ≠ 授权

MSP 的安全模型一句话：**信任边界就是传输的边界**——谁能连上来，谁就在信任域内。协议层因此不内置 TLS / 认证 / 授权逻辑，安全由部署形态决定，而不是由每一条消息自己决定。

但「连上来」之后还要分两层：**认证**（你是谁）和**授权**（你能做什么）。认证 ≠ 授权——证书只能证明「你是 node_b」，不能证明「node_b 有权调 `rm -rf` 工具」。

### 威胁模型

三类攻击者，对应三层对策：

| 攻击者 | 能干什么 | 对策 |
|---|---|---|
| 链路上的窃听/篡改者 | 读、改、重放消息 | TLS 加密 |
| 未经认证就连接进来的节点 | 冒充任意 node_id，混入发现、搅乱去重、白嫖广播 | 节点认证 |
| 已认证但不可信的节点 | 调未开放的工具、publish 触发副作用、偷看广播 | 授权 |

### 本机自组网：权限集合相等，无需认证

MSP 面向的第一类场景是本机自组织网络：同一台机器上的一组进程 / 节点通过 localhost 互联，各自独立编组、共享发现注册表、互相广播。

在这种形态下，做认证没有意义，因为**每个节点的权限集合相等**：

- 所有节点跑在**同一个 OS 用户**之下，文件系统、网络端口、环境变量、进程信号的可达权限完全相同；
- 一个节点能读到的、能调用的、能写到的，另一个节点同样能读到、调用、写到；
- 加密通道（TLS）保护的也是「传输途中」的机密性，而 localhost 回环不经过不可信的网络段，没有中间人可拦。

所以本机场景跳过 TLS 与节点认证：**认证一个和你权限相同的对端，等于认证你自己**——不增加任何真实的安全收益，只增加握手复杂度和部署成本。

### 跨机时：安全随传输走

安全模型是「随传输走」的，而不是「随协议走」的。跨机暴露是**显式开启、默认关闭**的模式：节点默认只监听 localhost，谁要跨机、谁自己去开 `0.0.0.0` 监听，并同时配好下面这套。

当传输从 localhost 换成真实的网络（`TCPTransport` 监听 `0.0.0.0`、或未来加 UDP / QUIC），信任边界随之扩大，此时必须在**传输层之上、协议核心不动**的前提下补上：

1. **TLS**：加密 + 服务器身份校验，防窃听与中间人。
2. **节点认证**：连接建立后校验对端身份，防未授权节点混入发现注册表或监听敏感命名空间。两种取法：**mTLS**（证书 CN/SAN = node_id，适合已有 PKI 的机房），或**签名 HELLO**（节点用 Ed25519 私钥签自己的 manifest，node_id 绑定公钥，靠显式 pin 密钥 / TOFU + 人工确认，更贴合 P2P、免 PKI 负担）。默认倾向后者。
3. **身份绑定**：HELLO 里声明的 `node_id` 必须与 TLS / 密钥身份一致，不一致就断开；否则冒充 node_id 能搅乱 node_id 排序去重和发现注册表。
4. **授权**：见下一节。认证只解决「你是谁」，授权才解决「你能做什么」。

这些都挂在「可插拔的传输包装」或「握手前置校验」上，与 `core` 的解耦方式同 JSON-RPC 桥、发现源一致——**协议核心继续只认 `Signal`，安全是传输与握手阶段的责任**。

### 授权：默认只留应答通道（设计已定稿，实现待排期）

**授权与能力分离**：能力位（`pub` / `sub` / `req` / `rep`）在 manifest 里，是「我自称会什么」；授权（grants）在本地 Preset 里，是「我允许你对端做什么」——授权绝不依赖对端自报，也不随 manifest 交换。

授权表声明在 Preset，与 `capabilities` / `connect_policy` 同款「预设」风格：

```python
# Preset（本地策略，不随 manifest 交换）
grants = {
    # 未列明的任何对端：默认只留应答通道
    "*":      {"req": [],            "pub": False, "sub": False, "rep": True},
    # 逐 peer 覆盖
    "node_b": {"req": True,          "pub": ["notify.**"], "sub": ["metric.**"], "rep": True},
    "node_c": {"req": ["read_file"], "pub": False, "sub": False, "rep": True},
}
```

四个动作对应四类信号：

| 动作 | 语义 | 授权主体 | 匹配方式 | 默认 |
|---|---|---|---|---|
| `req` | 允许它调我的工具 | 工具名列表 | 精确匹配（`True` = 全部） | `[]`：一个都不给 |
| `pub` | 允许它的 publish 触发我的 `on()` | path 模式 | 复用 `pattern_matches` | `False` |
| `sub` | 允许它收我的广播 | path 模式 | 复用 `pattern_matches` | `False` |
| `rep` | 允许它的应答（`tool_result`）进来 | 布尔 | 不分工具 | `True` |

**`rep` 与前三个不是一类。** `req` / `pub` / `sub` 是**对它的限制**——关掉就是不许它主动对我做什么；`rep` 是**我留给自己的通道**——由我发起、它应答的交互（`call()` 的返回值）默认放行。所以「默认 rep-only」的准确含义是：**默认状态下对端在我面前只能当应答方——我不能靠它主动，但我随时能靠它**。把 `rep` 显式写成 `True`，是为了让这个默认姿态在表里看得见，也避免实现时把「应答」误当成「请求」一并拒掉。

**默认值**：`"*"` 即网络对端的默认姿态——`req` 空白名单（什么都不暴露，显式加一个工具名才开放一个）、`pub` 拒绝（它的 publish 进不了 `on()`）、`sub` 拒绝（广播不发给它）、`rep` 放行。本机（loopback / UDS 同用户）整张表绕过、全量信任，只有跨机对端走这张表。

**执行点只有两处，core 仍只认 `Signal`**：

- 入站：`_dispatch(peer_id, sig)` 最前面查授权——`tool_call` 查 `req`、`signal` 查 `pub`、`tool_result` 查 `rep`，不通过直接丢（可回 `ERROR`）。
- 出站：`publish()` 的扇出循环里，每个对端查 `sub`，未授权的跳过。

**与广播的张力**：`sub` 授权是发送侧的扇出过滤——「广播 = 全发」与「不让未授权者看」在这里冲突。它和已删除的订阅表形状相似但性质不同：订阅表是「谁**想**要」（带宽优化），`sub` 授权是「谁**能**看」（安全），故按安全需要加回 per-peer 过滤，不掺带宽优化。

### 一句话对照

| 部署形态 | 信任边界 | 需要什么 |
|---|---|---|
| localhost 自组网 | 同一 OS 用户 | 无需 TLS / 认证 / 授权 |
| 跨机 / 公网 | 网络可达范围 | TLS + 节点认证 + 授权（默认只留应答通道） |

## 信任边界：把「对端输入」与「本地状态」分层

**问题**（一次针对合并后代码的风险审查）：三条独立的 SEV-1 指向同一个根因——对端自报的东西直接进入控制流。

- **授权对模式私有信号兜底放行**：`authorized()` 只查 `tool_call` / `signal` / `tool_result`，其余一律 `return True`。于是任何新起的信号类型名自动获得「免授权」地位：`task_submit` 在 `req=[]`（默认只留应答通道）下照样执行任务函数。实测——`req` 全拒时普通工具调用被正确拒绝，`task_submit` 却跑通并把产物回了回来。规范当时把「模式私有信号的授权归属」记为**未定义**并要求实现在模式层自行收紧，而实现没有做。
- **可选能力的失败被放在致命路径上**：`task_store` 按 UTF-8 文本读，坏字节抛 `UnicodeDecodeError`，而它在**节点构造期**被调用 → 一行坏数据把节点**永久**钉死（每次重启都复现，且没有任何代码路径会再去修那一行）。同一模块的 docstring 还写着「坏行跳过，不因为一行坏数据丢掉整个文件」——代码与自己的承诺相反。
- **不可序列化的产物杀死 worker**：序列化异常先在落盘处抛，随后在终态落盘处**再抛一次且无人接住** → daemon 线程死亡、任务永远停在非终态、提交方永远等不到 `task_result`（只能等满超时）。

**决策**

1. **授权默认拒绝**（`security.md` §3.9）：核心三类型照旧查表，连接机制类显式豁免，**其余一切模式私有信号必须由注册的模式自己声明归属**（`PatternHandler.authorize`，默认实现返回 `False`）。新增模式或新增信号类型时，忘记归类的后果是「被拒绝」而不是「被放行」。
2. **来源校验按连接身份，不按自报字段**（§3.10）：`sig.source` 是对端自报的，`peer_id` 是握手后由本地连接确定的事实。**读方向与写方向必须对称**——原先 `task_query` / `task_cancel` 校验了 `client_id`，而 `task_status` / `task_artifact` / `task_result` 完全不校验发送方，于是第三方可以伪造他人任务的终态与产物。
3. **可选能力的失败不得致命**：持久化默认关闭，因此它的任何失败只降级为「不持久化 + 告警」——不拒绝启动、不杀死 worker、不改变任务语义。状态以内存为准，磁盘只是尽力而为。
4. **外来输入在入口处归一**（对端清单、授权表）：类型不对就当没有，而不是让类型错误在运行期以 `AttributeError` 的形式变成一次断连、或以 `TypeError` 的形式让清单更新静默冻结。

**取舍**

- **归一与兜底两处都做**：入口归一（握手 / 更新 / 构造）负责语义正确，消费点兜底（`Peer.tools()` 之类）负责「不被搞崩」。两处都做是刻意的——注入路径不止一条。
- **产物不可序列化选择提前报错**（任务随即 `failed`），不静默替换成文本：失败也是终态，提交方拿得到；静默降级会让「产物少了内容」无人知晓。
- **没有改** `mr-<n>` 这个可预测的 `reqid`：来源校验已经堵住跨对端注入（只有被调用的那个对端能应答），而改 reqid 生成会触碰既有报文与测试，收益不足。规范仍要求「不得把 `reqid` 当作安全令牌」。
- **没有动**本机对端整表绕过：同一 OS 用户下权限本就相等，绕过「授权」没有意义。跨机才是授权表存在的理由，也是这次修复的目标场景。

**验证**：`tests/test_risk_fixes.py`，24 个用例，修复前全红。其中 5 个是「不得改变既有行为」的护栏——本机对端仍整表绕过、`req` 白名单命中仍放行、未知信号类型仍回 `-32600`、执行者的正常回执仍被接受。

## 能力面：resources / prompts / sampling（设计，暂未实现）

### 背景：MCP 的能力面

MCP 在工具（tools）之外还有三类能力，加两类通知：

- **resources**：server 把上下文数据以资源（URI → 内容）暴露给 client，client 可 `read`（读）与 `subscribe`（订阅变更，变更时 server 推 `resources/updated`）。让模型不只靠工具，还能「读」到文件、数据库记录等上下文。
- **prompts**：server 预定义可复用提示模板（名字 + 参数），client `get` 时由 server 渲染出完整 prompt。把「怎么写提示」的知识从 client 搬到 server。
- **sampling**：反向能力。server 在处理中需要「让模型生成一段」（如 agent 的子任务推理），向 client 发请求，client 用背后的 LLM 生成后返回。主从反转：server 成为能力请求方，client（LLM 宿主）成为提供方。
- **elicitation**：server 需要用户决策 / 输入，向 client 征询。与 MSP 的 multi-round（`input_required` / `input_response`）同构。
- **roots**：client 单向声明自己的 filesystem roots，server 据此决定可访问哪些路径。

### MSP 映射：全部是信号

「Everything is a signal」意味着这三类能力不是三套机制，而是几组新 SignalType：

| MCP 操作 | MSP 信号 | 方向 |
|---|---|---|
| `resources/read` | `resource_read` → `resource_content` | client→server 请求 / 响应 |
| `resources/subscribe` | `resource_subscribe` / `resource_unsubscribe` → `resource_updated` | 订阅 + 变更通知 |
| `prompts/get` | `prompt_get` → `prompt_content` | client→server 请求 / 响应 |
| `sampling/createMessage` | `sampling_request` → `sampling_result` | server→client 反向请求 |
| `elicitation/create` | `elicitation_request` → `elicitation_result` | server→client 反向请求 |
| `roots/list` | `roots_list` → `roots` / `roots_changed` | client→server 通知 |

### 三个关键取舍

1. **清单即列表，省掉 list 往返**：MCP 的 `resources/list`、`prompts/list` 要额外请求；MSP 的 `resources` / `prompts` 已经住在 Manifest 里，握手 + `MANIFEST_UPDATE` 就完成了「列出」。所以不设 list 信号，只有 read / get。
2. **反向能力是全双工的天然优势**：MCP 基于单向 JSON-RPC，sampling 要 client 与 server 互换角色；MSP 双方都能主动发信号，`sampling_request` 只是「方向反过来的 tool_call」，reqid 关联同构，无需角色翻转。
3. **资源订阅与路径过滤是两维**：信号按 path（点分层）广播、接收方本地 `on()` 过滤，资源按 URI 订阅。两者维度不同，不强行把 URI 塞进 path，单独用 `resource_subscribe`。

### 现状与补法

`Manifest` 已经声明了这些能力的「位」：`resources` / `prompts` 的 descriptor，以及 `clientCapabilities.sampling / elicitation / roots` 三个布尔位。缺的是对应的 SignalType 与协议操作——补法是给 `_dispatch_core` 加分支（与 `tool_call` 同构）、node 层加 `@node.resource(...)`、`@node.prompt(...)`、`node.sample(peer, ...)` 等 API。在补上之前，对端拿到清单会「看到许诺但用不了」，所以这些声明当前仅作预留。

## 远端工具视图：把对端的 schema 变成本地函数

### 问题

调用一个远端工具的代码只有三行。真正的摩擦在**之前**：必须先 `fetch_manifest()`，再人肉读 `inputSchema`，才知道工具叫什么、参数叫什么、哪个必填。写错参数名的代价尤其高——它不会在本地报错，而是绕过网络变成对端返回的一条字符串（`__init__() got an unexpected keyword argument 'city'`），既没有堆栈也没有位置，只能肉眼比对清单。

而这份 schema 本来就在手上：`ToolDescriptor.inputSchema` 随握手交换。所以这里**不需要**代码生成步骤，也不需要新增任何线上字段——gRPC 要 `.proto`、OpenAPI 要 spec 文件，MSP 的 IDL 已经在协议里了。

### 决策

`peer.t`：把 `inputSchema` 投影成 `inspect.Signature` 与惰性可调用代理（`core/remote_tools.py`）。三条刻意的约束：

1. **挂在自己的命名空间下，不直接挂 `Peer` 上。** `Peer` 已有 12 个成员（`tools` / `signals` / `manifest` / `node_id` …），而工具名文法 `[a-z0-9_-]+` 完全可能撞上；`__getattr__` 只在属性找不到时触发，所以直接挂会**静默**返回错的东西，连检测机会都没有。子命名空间把保留名从 12 个降到 5 个，撞名工具仍可用 `t[...]` / `t.tool(...)` 访问。
2. **属性访问是纯的。** 建连与调用推迟到**调用那一刻**；否则 `hasattr` / `dir` / 调试器展开对象都会触发网络 I/O，而 `Peer` 的契约是「查询未知对端返回空值、不抛异常、无副作用」。
3. **不新增错误语义开关。** 默认返回 `ToolResult`（错误即值），要抛异常用既有的 `unwrap()`。加一个 `on_error="raise"` 等于在便利函数里悄悄推翻规范的头条决定；复用已有契约则不可能与规范冲突。

签名映射遵守「认不出就退化为 `Any`，绝不猜」：没有 `properties` 键 → 签名未知（关键字透传，这样 `**kwargs` 式工具也能调）；`properties: {}` → 严格无参；参数名不是合法标识符或是关键字 → **不静默改名**，只列进 `unrepresentable` 与 `conflicts()`。必填参数进位置参数位（保持清单顺序），可选参数一律 keyword-only——这样「可选参数排在必填之前」不会触发 Python 的 `non-default argument follows default argument`，也不必为了排序而重排清单。

### 取舍

- **签名质量的上界是 `schema_from_func` 的保真度。** 它当前不产出 `default`（可选参数显示为 `<optional>` 而不是真实默认值），且 pydantic v2 下 `Field(ge=…)` 会静默丢失。本模块只做忠实降级，不去补偿——补偿等于在客户端编造提供方没声明的约束。反过来看，这个功能把 `inputSchema` 从「只用于宣告」推成了**承重结构**，也就把「修生成器」变成了有动机的事。
- **返回值仍是 `Any`。** `ToolDescriptor.outputTypes` 恒为空，返回值没有 schema；完整类型化要先把输出侧补上。
- **不做的事**：不解析 `$ref`、不取远端引用（没有 SSRF 面）、不生成 `.py` 文件、不用 `exec`（对端 schema 是不可信输入）、不缓存——视图随取随弃，工具名与签名实时从 `Peer` 读，所以对端 `manifest_update` 之后立刻生效。
- **不给超时参数**：所有关键字参数原样发给对端，因此没有保留字；需要自定义超时直接用 `node.call(peer, tool, args, timeout=...)`。
- **规范只加了一条**：`inputSchema` 是对外契约的一部分（request-reply §7.2）。JSON Schema → 宿主语言的映射**不进规范**——它是客户端选择，不在线上，不构成互操作面。这条边界是刻意的：上一轮和 MCP 对比时，唯一守住的就是「线格式不膨胀」。
