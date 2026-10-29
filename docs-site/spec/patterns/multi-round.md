# `msp/multi-round` — 执行中追问

| | |
|---|---|
| **协议修订** | `2026-10-10` |
| **模式 ID** | `msp/multi-round` |
| **状态标记** | ✅ **已实现**（主路径可验证）；§9 列出的边界为 🟡 **部分实现** |
| **降级目标** | `msp/request-reply`（`fallback_to`） |
| **规范性用语** | RFC 2119，见[规范索引](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#2-规范性用语) |
| **本页定义** | 被调方在一次 `tool_call` 的**同一个 `reqid` 内**多次向调用方索取补充信息，再给出最终结果 |

## 1. 概述

### 1.1 解决的工程问题

工具参数经常要等到**执行中**才能确定：订票工具直到要下单才发现缺出发日期，检索工具直到拼查询语句才发现缺时间范围。若没有本模式，双方只有两种笨办法：

1. 工具失败一次，把「缺少什么」编码进 `tool_result.payload.error`，调用方解析后再调一次——一次交互被拆成两次，服务端要重建上下文，`reqid` 变了，`ctx` 里的中间状态全丢。
2. 工具干脆把参数一次要全，逼调用方把所有细节塞进 `args`，哪怕其中一半用不上。

`msp/multi-round` 给第三种选择：**在同一次调用的 `reqid` 内就地补齐**。工具函数在独立线程里执行到一半，调用 `ctx.ask(...)` 阻塞等待；调用方收到追问、作答、回传；工具带着答案继续跑。被调方的执行栈、局部变量、已发出的中间副作用都还在原地。

### 1.2 与现有模式的关系

- 本模式是 `msp/request-reply` 的**超集**：起手报文仍是 `tool_call`，收尾报文仍是 `tool_result`，关联键仍是 `reqid`。区别只在于往返过程中**被调方可以反向插话**。
- 「多轮」不等于「有人参与」。作答方是调用方提供的 `input_fn`；它可以查本地配置、走默认值、按规则推导、读本地模型——**可以**完全没有人在回路里。
- 本模式只新增**两个**模式私有信号类型（`input_required` / `input_response`），核心 `SignalType` 零改动。协议层为此付出的代价，只有[模式路由](../patterns.md#3-路由契约)里的一条查表。

## 2. 契约

### 2.1 模式标识与降级

| 项 | 值 | 源码位置 |
|---|---|---|
| `pattern_id` | `"msp/multi-round"` | `MultiRoundHandler.pattern_id` |
| `fallback_to` | `"msp/request-reply"` | `MultiRoundHandler.fallback_to` |
| `conflicts_with` | `[]`（继承 `PatternHandler` 默认值，本模式未声明） | `PatternHandler.conflicts_with` |

**降级语义**：`fallback_to` 声明的意图是——当对端不支持本模式时，改用 `msp/request-reply` 重发（退化为一次普通工具调用，追问能力消失）。**当前参考实现不发生自动降级**：`fallback_to` 在全仓库只被声明、没有任何代码读取。但 `call_multiround()` 现在会**先建连再检查** `peer(peer_id).supports("msp/multi-round")`，对端未宣告本模式时立即抛 `RuntimeError`（不再发出去后靠总超时兜底，见 §12 G2）——**检查**已实现，**降级**仍未实现。

实现者**可以**实现自动降级，但一旦实现**必须**满足：降级前**不得**发出任何 `input_required`；降级后本次交互的报文形态**必须**完全符合 [`msp/request-reply`](./request-reply.md)（不得带 `pattern` 字段）；降级**应当**通过调用方显式可见的方式告知（如返回值或异常），而**不得**静默改变语义。

> 事实澄清：当对端没有注册本模式 handler 时，带 `pattern` 的 `tool_call` 会落到协议层的默认分支（[`_dispatch`](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) 第 3 步），被核心工具注册表当作普通工具调用处理。这不是规范意义上的降级，而是**无模式路由的兜底**：同名工具若只在模式自带注册表里注册过，核心表查不到，会回一个 `error` 为「未知工具: X」的 `tool_result`。见 §6.1。

### 2.2 信号类型

| 信号 `type` | 方向 | 有 `reqid` | 语义 |
|---|---|---|---|
| `tool_call` | 调用方 → 被调方 | **是** | 起手请求；与核心同名类型共用，靠 `pattern` 区分 |
| `input_required` | 被调方 → 调用方 | **是** | 追问；`reqid` 与起手 `tool_call` **必须**相同 |
| `input_response` | 调用方 → 被调方 | **是** | 应答；`reqid` **必须**与追问相同 |
| `tool_result` | 被调方 → 调用方 | **是** | 终止结果；`reqid` **必须**与起手相同 |

`input_required` / `input_response` 是本模式私有的 `type` 值。所有本模式信号**必须**携带 `pattern = "msp/multi-round"`——它是协议层的路由键（见 §6.1 与 [模式层契约](../patterns.md#3-路由契约)）。

### 2.3 线程与阻塞模型

| 侧 | 约束 | 理由 |
|---|---|---|
| 被调方 | **必须**在独立线程中执行工具函数 | 工具的 `ctx.ask()` 是阻塞调用；若在执行读循环的线程里跑，调用方回传的 `input_response` 永远读不到，必死锁 |
| 被调方 | **可以**在一次工具执行中多次调用 `ctx.ask()` | 每次调用生成一对 `reqid` 相同的新追问/应答 |
| 调用方 | 收到 `input_required` 时**应当**在收到它的线程之外完成阻塞式询问 | 参考实现在读循环线程内同步调用 `input_fn`；见 §9 |
| 两侧 | **不得**假定追问次数有上界 | 协议不设次数上限；调用方用总超时兜底 |

`ctx.ask(prompt, timeout=30.0)`：`prompt`（`str`，必填）原样进入 `input_required.payload.prompt`；`timeout`（`float`，默认 `30.0`）是单次追问的等待上界；返回 `input_response.payload.answer` 的原值；超时抛 `TimeoutError`（文案 `"等待客户端补充信息超时"`）。调用方的总超时由 `call_multiround(..., timeout=60.0)` 独立控制，与单次追问超时**不是**同一个值，**不得**互相推导。

## 3. 报文（逐信号）

信封字段的通用规则见 [`Signal` 信封](../base-protocol.md#2-signal-信封)。以下示例中，信封为 snake_case（`type` / `source` / `pattern` / `target` / `path` / `reqid` / `payload` / `timestamp`），`payload` 内部字段名逐字取自源码。

### 3.1 `tool_call`

| 字段 | 位置 | 类型 | 必填 | 值 |
|---|---|---|---|---|
| `type` | 信封 | string | **必须** | `"tool_call"` |
| `pattern` | 信封 | string | **必须** | `"msp/multi-round"` |
| `source` / `target` | 信封 | string | **必须** | 调用方 / 被调方 `node_id` |
| `reqid` | 信封 | string | **必须** | 本次交互的关联标识，贯穿全部四类报文 |
| `payload.tool` | 载荷 | string | **必须** | 工具名 |
| `payload.args` | 载荷 | object | **必须** | 工具实参；参考实现取不到时用 `{}` |

```json
{ "type": "tool_call", "source": "client_node", "pattern": "msp/multi-round", "target": "server_node",
  "path": null, "reqid": "mr-1", "payload": { "tool": "book_flight", "args": { "destination": "Paris" } } }
```

`reqid` 的生成方式属实现自由。参考实现按 handler 实例计数生成 `mr-<n>`（`n` 从 1 递增），与核心模式使用 `Signal.new_reqid()`（16 位十六进制随机串）不同。**应当**保证同一节点内并发交互的 `reqid` 互不相同。

### 3.2 `input_required`

| 字段 | 位置 | 类型 | 必填 | 值 |
|---|---|---|---|---|
| `type` | 信封 | string | **必须** | `"input_required"` |
| `pattern` | 信封 | string | **必须** | `"msp/multi-round"` |
| `source` / `target` | 信封 | string | **必须** | 被调方 / 调用方 `node_id` |
| `reqid` | 信封 | string | **必须** | 与起手 `tool_call` 相同 |
| `payload.prompt` | 载荷 | string | **必须** | 追问文案 |

```json
{ "type": "input_required", "source": "server_node", "pattern": "msp/multi-round", "target": "client_node",
  "path": null, "reqid": "mr-1", "payload": { "prompt": "出发日期？" } }
```

**载荷只有 `prompt` 一个字段。** 参数名、期望类型、取值范围、候选项、上下文片段在参考实现中**均不存在**；接收方**不得**假定存在，发送方若自行扩展**应当**新增字段而**不得**改变 `prompt` 的含义（宽容读取见[base-protocol §2.3](../base-protocol.md#23-宽容读取)）。接收方取不到 `prompt` 时**应当**按空串处理。

### 3.3 `input_response`

| 字段 | 位置 | 类型 | 必填 | 值 |
|---|---|---|---|---|
| `type` | 信封 | string | **必须** | `"input_response"` |
| `pattern` | 信封 | string | **必须** | `"msp/multi-round"` |
| `source` / `target` | 信封 | string | **必须** | 调用方 / 被调方 `node_id` |
| `reqid` | 信封 | string | **必须** | 与该次 `input_required` 相同 |
| `payload.answer` | 载荷 | any | **必须** | 应答值，任意 JSON 可序列化类型 |

```json
{ "type": "input_response", "source": "client_node", "pattern": "msp/multi-round", "target": "server_node",
  "path": null, "reqid": "mr-1", "payload": { "answer": "2026-10-15" } }
```

`answer` 的类型不受本规范约束：字符串、数字、布尔、对象、数组、`null` 均可，被调方**不得**假定其为标量。参考实现在 `input_fn` 抛异常时把 `answer` 置为 `{"error": "<异常文本>"}`——这是**实现约定而非协议语义**，被调方**不得**把它当作取消或超时的信号。

### 3.4 `tool_result`

| 字段 | 位置 | 类型 | 必填 | 值 |
|---|---|---|---|---|
| `type` | 信封 | string | **必须** | `"tool_result"` |
| `pattern` | 信封 | string | **必须** | `"msp/multi-round"` |
| `reqid` | 信封 | string | **必须** | 与起手 `tool_call` 相同 |
| `payload.content` | 载荷 | any | **必须** | 工具返回值的**原样值**；返回 falsy 值（`None` / `""` / `0` / `False` / `{}` / `[]`）时归一为 `[]` |
| `payload.error` | 载荷 | string | **必须** | 成功时为 `""`；失败时为异常文本 |

```json
{ "type": "tool_result", "source": "server_node", "pattern": "msp/multi-round", "target": "client_node",
  "path": null, "reqid": "mr-1",
  "payload": { "content": { "destination": "Paris", "date": "2026-10-15", "airline": "国航" }, "error": "" } }
```

与核心 [`msp/request-reply`](./request-reply.md) 的 `tool_result` 有**三处实质差异**，实现者**必须**按本模式的形态处理：① 本模式**不产出** `structuredContent`，返回值只出现在 `content` 里；② 本模式的 `content` 是工具返回值的**原样值**（可能是对象、字符串、数组；但 falsy 值会被 `content or []` 归一为 `[]`），**不是**规范化后的内容块数组（核心模式会先经 `_normalize_tool_result` 再写入 `content`）；③ 本模式**总是**同时携带 `content` 与 `error`，成功时 `error` 是空串，因此调用方**应当**判断 `error != ""`，而**不得**用字段是否存在来判断成败。

## 4. 消息流

### 4.1 正常路径：两次追问 + 最终结果（同一个 `reqid`）

```text
   调用方 (client_node)                                    被调方 (server_node)
        │ ① tool_call  reqid=mr-1  payload={tool:"book_flight",args:{…}}      │
        ├──────────────────────────────────────────────────────────────────────▶│
        │                                     读循环只做分发，起独立线程跑工具
        │                                     工具执行中，发现缺参数
        │ ② input_required  reqid=mr-1  payload={prompt:"出发日期？"}           │
        │◀──────────────────────────────────────────────────────────────────────┤
        │                                     ctx.ask("出发日期？") 阻塞，<=30s
        │ input_fn("出发日期？") → "2026-10-15"                                 │
        │ ③ input_response  reqid=mr-1  payload={answer:"2026-10-15"}           │
        ├──────────────────────────────────────────────────────────────────────▶│
        │                                     唤醒 ask()，工具继续执行
        │ ④ input_required  reqid=mr-1  payload={prompt:"偏好航空公司？"}       │
        │◀──────────────────────────────────────────────────────────────────────┤
        │                                     ctx.ask("偏好航空公司？") 阻塞
        │ ⑤ input_response  reqid=mr-1  payload={answer:"国航"}                 │
        ├──────────────────────────────────────────────────────────────────────▶│
        │                                     工具返回，工作线程结束
        │ ⑥ tool_result  reqid=mr-1  payload={content:{…},error:""}             │
        │◀──────────────────────────────────────────────────────────────────────┤
        │ 唤醒 call_multiround()，返回 content                                  │
        ▼                                                                       ▼
```

四个关键不变式：① ②③④⑤⑥ 的信封 `reqid` **必须**恒等于 ①；② 同一 `reqid` 只**必须**产生一个 `tool_result`；③ 追问与被调方的线程数无关，**可以**在同一线程内串行发生多次；④ 调用方无需宣告自己支持本模式，也无需预知追问次数。

### 4.2 错误路径对照

```text
  (a) 追问超时      被调方: ask() 抛 TimeoutError → tool_result{content:[],error:"等待客户端补充信息超时"}
  (b) 工具异常      被调方: tool_result{content:[],error:"<异常文本>"}
  (c) 未知工具      被调方: tool_result{content:[],error:"未知工具: <name>"}  ← 立即回，不起线程
  (d) 调用方总超时  调用方: TimeoutError（丢弃该 reqid 的等待表项）→ 之后到达的 input_required 被静默丢弃
  (e) 对端无 handler 对端: error{code:-32600,message:"未知信号类型: input_required"}（带原 reqid）
                    调用方: 不识别该 error，继续等到总超时
```

## 5. 数据与类型约定

| 概念 | 类型 | 约束 |
|---|---|---|
| 答案 | `Any` | 任意 JSON 可序列化值；`input_fn` 的返回值原样进入 `answer` |
| 追问文案 | `string` | 单段文本，不含结构化 schema |
| 工具返回值 | `Any` | 原样进入 `tool_result.payload.content`；falsy 值（`None` / `""` / `0` / `False` / `{}` / `[]`）→ `[]` |
| 错误文本 | `string` | 人类可读；本模式**不**定义数值错误码 |

本模式**不**定义新的错误码。工具执行失败走 `tool_result.payload.error`（错误即值），协议级失败沿用[错误码表](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#54-错误码)（如 `-32600`）。参数不符合工具声明的 `inputSchema` 时**应当**用 `-32602` 语义的工具失败表达，而不是发 `error` 信号。

## 6. 错误处理与边界

**6.1 对端不宣告 / 未激活本模式**——调用方**应当**在调用前检查 `peer(peer_id).supports("msp/multi-round")`；参考实现的 `call_multiround()` 现在**自己**做这件事：先 `ensure_connected()`，再查 `supports()`，未宣告即抛 `RuntimeError`（调用方仍**应当**自行检查以决定是否走降级路径）。对端若没有注册本模式 handler：带 `pattern` 的信号在路由表中查不到，落入协议层默认分支。`tool_call` 会被当作**普通工具调用**处理（可能误命中核心注册表里的同名工具）；`input_required` / `input_response` 则命中「未知信号类型」分支，回 `error`（`code = -32600`）。该 `error` 携带原 `reqid`，协议层 `_on_error` **会**按 `reqid` 唤醒等待中的调用并回 `ToolResult(error=...)`（原实现只记日志、必须等满总超时，见 §12 G3）。

**6.2 `input_required` 无人应答**——被调方 `ctx.ask()` 的等待表项只登记在**被调方本地**。调用方若丢弃了 `reqid` 对应的等待表项（总超时、进程退出、逻辑分支遗漏），到达的 `input_required` 会被静默忽略，**不**回 `input_response`；被调方只能等到单次追问超时。协议**不**定义「拒绝追问」这一报文；实现者若需要，**应当**用 `input_response.payload.answer = null` 表达「无答案」。

**6.3 超时**——单次追问（被调方 `ctx.ask`）默认 `30.0` s，触发后抛 `TimeoutError`、弹出表项，工具通常随即失败并回 `error`；整次调用（调用方 `call_multiround`）默认 `60.0` s，触发后抛 `TimeoutError`、弹出 `reqid` 表项，且**不**向对端发送取消。两者无约束关系：追问次数 × 单次超时**可以**超过整次超时。调用方**应当**令整次超时 ≥ 预期追问次数 × 单次追问超时；参考实现不做校验。

**6.4 连接断开**——被调方的应答类信号（`tool_result` / `input_response`）统一经 `_send()` 发出，捕获 `(RuntimeError, ConnectionClosed)` 并降级为日志；连接已断时该次结果丢失且**无**任何补偿，工具函数已产生的副作用不回滚，但**不会**再让异常从工作线程冒出（原实现会让工作线程异常退出，见 §12 G8）。调用方在等待中断开连接时，等待表项由协议层的断线清理唤醒（`ToolResult(error="连接断开")`）。本模式**不**定义断线重连后的续传。

**6.5 `reqid` 不匹配**——被调方 `_on_input_response` 按 `reqid` 查等待表项，查不到即静默丢弃；调用方 `_on_tool_result` / `_on_input_required` 同样按 `reqid` 查表，查不到即静默丢弃。~~**两侧都不校验来源 `node_id`**~~ ✅ **已修复**：两侧现在都按**连接身份**（而非可伪造的 `sig.source`）核对「这条应答是否来自我调用的那个对端」，不匹配即丢弃。这一条是必需的——参考实现的 `reqid` 是 `mr-1`、`mr-2` 这类**可预测**值，**不得**把它当作安全令牌（[security](../security.md) §3.10）。见 §8。

**6.6 重入与并发**——并发多次调用**可以**：每个调用有独立 `reqid`、独立的事件与结果槽。但**同一 `reqid` 内并发两次 `ctx.ask()` 不被支持**：等待表项以 `reqid` 为键、只有一个槽位。工具函数**不得**从多个线程同时对同一 `reqid` 调用 `ask()`；参考实现会检测到重入并抛 `RuntimeError`（原实现静默覆盖、前一次必然超时，见 §12 G6）。**重入危险**：`input_fn` 在调用方的读循环线程里执行，若 `input_fn` 内部再发起一次到**同一对端**的调用并等待其回复，回复永远读不到，双方互等至超时。

**6.7 回调异常**——`input_fn` 抛出的任何异常都会被调用方捕获，并转成 `answer = {"error": "<异常文本>"}` 后照常回传，**追问不会因此中断**；被调方**必须**自行判断该对象是否是「失败」约定。

### 6.8 与 MCP `elicitation` 的差异

| 维度 | MCP `elicitation` | `msp/multi-round` |
|---|---|---|
| 请求关联 | **另起一次反向请求**，有独立的请求标识，与原调用不共享 | 延续原调用的 `reqid`，全程同一个关联键 |
| 原调用状态 | 原调用是否仍在等待由应用层维持 | 原调用在被调方**原地阻塞**，执行栈不丢 |
| 追问次数 | 一次反向请求对应一次征询 | 同一 `reqid` 内**可以**无限次追问 |
| 载荷 | 带 JSON Schema 的受约束结构（字段名、类型、枚举） | 只有一段 `prompt` 文本，无 schema |
| 权限方向 | 约定由 server 向 client 征询 | 双向：只要一方持连接即可发起（此处由被调方发起） |
| 复用既有原语 | 需新增反向请求通道 | 复用 `tool_call` 的 `reqid` 关联，核心零改动 |

结论：`elicitation` 解决的是「服务端能不能问一句」，本模式解决的是「这一次调用的上下文能不能活着等到答案」。两者可共存；在 MSP 中如要表达 `elicitation` 语义，应作为独立能力面（见 [capabilities](../capabilities.md)）而不是复用本模式。

## 7. 规范条文汇总

**必须**：① 本模式的四类信号**必须**携带 `pattern = "msp/multi-round"`；② 一次交互内 `input_required`、`input_response`、`tool_result` 的 `reqid` **必须**与起手 `tool_call` 相同；③ 被调方**必须**在独立线程（或等价的非读循环执行体）中执行工具函数；④ `input_required.payload.prompt` 与 `input_response.payload.answer` **必须**存在；⑤ 同一 `reqid` 只**必须**产生一个 `tool_result`；⑥ 未识别的字段、信号类型**不得**导致连接中断（[宽容读取](../base-protocol.md#23-宽容读取)）。

**应当**：⑦ 调用方**应当**在调用前确认对端宣告了本模式；⑧ 调用方**应当**令整次超时覆盖预期的全部追问；⑨ 被调方**应当**把失败表达为 `tool_result.payload.error`，而不是 `error` 信号；⑩ 实现者若要跳过一次追问，**应当**回 `answer = null`，而不是不回。

**不得**：⑪ 调用方**不得**假定追问次数、`answer` 的类型或 `prompt` 的结构；⑫ 被调方**不得**在读循环线程内调用 `ctx.ask()`；⑬ `msp/` 命名空间外的模式**不得**复用 `input_required` / `input_response` 这两个 `type`；⑭ 降级实现**不得**静默改变已发出的语义（见 §2.1）。

**可以**：⑮ 实现**可以**不实现本模式；一旦实现**必须**符合本页条文。⑯ 实现**可以**在本页之外扩展 `input_required.payload` 的字段。

## 8. 安全考量

- **来源未校验**：两侧都只按 `reqid` 关联，不校验 `source`。参考实现的 `reqid` 可预测（`mr-<n>`），因此**应当**把「收到 `input_response`」视为**未经认证的输入**，绝**不得**把它当作授权、身份或金额这类高价值决策的唯一依据。实现者**应当**改用不可预测的 `reqid` 并校验来源节点。
- **追问即数据入口**：`answer` 会直接进入工具函数的控制流。工具**必须**按普通不可信输入校验它（长度、类型、取值范围），**不得**把它拼进命令、路径或查询而不做转义。
- **信息泄露**：`prompt` 由被调方控制，会被原样交给调用方的 `input_fn`。调用方**应当**把 `prompt` 当作不可信文本渲染或记录，避免注入本地日志格式或终端控制序列。
- **无授权层**：本模式不做任何授权判定；谁能调用工具由连接与部署策略决定，见 [security](../security.md)。

## 9. 已知缺口

以下路径在参考实现中**未处理**（状态计为 🟡 **部分实现**；规划中的补法标 🔵）：

| 编号 | 缺口 | 现状 |
|---|---|---|
| G1 | 自动降级未实现 | `fallback_to` 只声明不消费；对端不支持时既不降级也不报错，靠总超时兜底 |
| G2 | ~~调用方不检查对端能力、不自动建连~~ ✅ **已修复** | `call_multiround()` 现在先 `ensure_connected()` 再查 `peer.supports(pattern_id)`；对端未宣告本模式时立即 `RuntimeError`，初始请求发送失败也会清掉等待表并报错 |
| G3 | ~~`error` 信号不唤醒等待~~ ✅ **已修复** | 协议层 `_on_error` 现在按 `reqid` 唤醒等待中的调用（`ToolResult(error=...)`，含 `code`），不再等满总超时（task G11 同步修复） |
| G4 | 无取消机制 | 调用方超时后不发任何取消；被调方不知道对方已放弃，工具继续跑到自己超时 |
| G5 | `input_required` 载荷无结构 | 只有 `prompt` 文本，无参数名/类型/枚举/上下文；无法做机器可校验的追问 |
| G6 | ~~同一 `reqid` 内并发 `ask()` 会互相覆盖~~ ✅ **已修复** | 等待表仍以 `reqid` 为键、单槽位，但第二次 `ask()` 会显式抛 `RuntimeError`（调用方**不得**并发追问的约束由实现兜住了） |
| G7 | `input_fn` 跑在读循环线程 | 阻塞型 `input_fn` 会阻塞该连接的全部消息处理；重入同一对端会互等 |
| G8 | ~~发送端不捕获断线异常~~ ✅ **已修复** | `_reply_result()` / `input_response` 统一经 `_send()` 发送，捕获 `(RuntimeError, ConnectionClosed)` 降级为日志 |
| G9 | 来源 `node_id` 不校验 | 见 §8 |
| G10 | ~~`inspect.signature(func)` 在 try 之外~~ ✅ **已修复** | `_run_tool()` 的自省也在 `try` 内，不可自省的函数会回一条 `tool_result{error}` 而不是静默死亡 |
| G11 | 中途无进度通知 | 追问之外没有「还在跑」的心跳；长工具期间调用方只能凭连接存活判断 |
| G12 | 🔵 规划中：追问的结构化 schema | 若实现，**必须**新增独立字段，**不得**改变 `prompt` 的含义 |
| G13 | 🔵 规划中：模式内取消 | 若实现，**必须**在同一 `reqid` 内表达，且被调方**应当**在下一个可中断点响应 |

## 10. 参考实现映射

| 条文 | 源码文件与符号 |
|---|---|
| §2.1 模式标识 / 降级声明 / 无自动降级 | [`src/msp/patterns/multi_round.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/multi_round.py) `MultiRoundHandler.pattern_id` / `.fallback_to`；[`src/msp/patterns/base.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/base.py) `PatternHandler.fallback_to` |
| §2.2 私有信号类型常量 / `pattern` 路由键 | `multi_round.py` `MultiRoundHandler.INPUT_REQUIRED` / `.INPUT_RESPONSE` / `.TOOL_CALL` / `.TOOL_RESULT`；[`protocol.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._dispatch` |
| §2.3 独立线程执行工具 / `ctx.ask` 签名与阻塞 | `multi_round.py` `MultiRoundHandler._on_tool_call` / `._run_tool` / `_ask`；`RoundContext.ask` |
| §3.1–§3.4 四类报文的载荷 | `multi_round.py` `call_multiround`（`{"tool":…,"args":…}`）、`_ask`（`{"prompt":…}`）、`_on_input_required`（`{"answer":…}`）、`_reply_result`（`{"content":…,"error":…}`） |
| §3.4 与核心形态的差异 | `protocol.py` `_normalize_tool_result` / `MSPProtocol._run_tool`（核心路径） |
| §4 消息流 | `multi_round.py` 模块 docstring 时序图；端到端示例 [`src/examples/multi_round_demo.py`](https://github.com/hxh230802/MSP/blob/master/src/examples/multi_round_demo.py) |
| §6.1 兜底路由（未知类型回 `-32600`） | `protocol.py` `MSPProtocol._dispatch` / `._dispatch_core` |
| §6.7 回调异常转答案 | `multi_round.py` `_on_input_required` 的 `try/except` |
| §9 G6/G7/G9 | `multi_round.py` `_active_asks` / `_pending_calls` 的键与槽位设计 |
| 模式激活与语法糖 / 预设声明 | [`src/msp/core/node.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `MSPNode.register_pattern` / `._activate_pattern`；`multi_round.py` `install_api`；[`src/msp/core/preset.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/preset.py) `Preset.FULL_PEER` / `LOCAL_AI` / `CLOUD_SERVICE` |
