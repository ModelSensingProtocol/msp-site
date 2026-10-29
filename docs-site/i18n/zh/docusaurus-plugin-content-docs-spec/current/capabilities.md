# MSP 规范 — 能力面：resources / prompts / sampling / elicitation / roots

| | |
|---|---|
| **协议修订** | `2026-10-10` |
| **状态** | 🔵 **规划中** — 报文已完整定义，参考实现尚未落地 |
| **上游依据** | [../DESIGN.md](/design)「能力面：resources / prompts / sampling」、[../whitepaper.md](https://github.com/hxh230802/MSP/blob/master/docs/whitepaper.md) §5 |
| **本页定义** | MCP 能力面（resources / prompts / sampling / elicitation / roots）到 MSP 信号的完整映射、报文形态、消息流、错误归属与安全条文 |

本页把 MCP 在工具之外的能力面翻译成 MSP 信号。全部条文标 🔵：**实现者可以不实现，但一旦实现必须符合条文**。

## 1. 概述

### 1.1 范围

MCP（Model Context Protocol）在 tools 之外还有五组能力。按「Everything is a signal」（[README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §4），它们在 MSP 里不是五套机制，而是几组新的 `Signal.type`：

| MCP 能力 | 解决的问题 | MSP 落点 |
|---|---|---|
| resources | 对端把上下文数据以 URI 暴露出来，本端按需读取 | `resource_read` / `resource_content`；订阅侧 `resource_subscribe` / `resource_unsubscribe` / `resource_updated` |
| prompts | 对端预定义可复用提示模板，本端取值后由对端渲染 | `prompt_get` / `prompt_content` |
| sampling | 本端执行中需要「让某个模型生成一段」，向持有 LLM 的对端发反向请求 | `sampling_request` / `sampling_result` |
| elicitation | 本端需要用户决策或输入，向持有用户界面的对端征询 | `elicitation_request` / `elicitation_result` |
| roots | 一个节点单向声明自己允许被访问的文件系统根，供对端裁剪范围 | `roots_list` / `roots` / `roots_changed` |

MCP 的 `*/list` 往返（`resources/list`、`prompts/list`、`resources/templates/list`）在 MSP 中**没有**对应信号，见 §2.2。

### 1.2 与索引和信封的关系

本页定义的是一个**规划中的新能力面**：它**不属于**任何已注册的模式（[README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.2 的模式表保持不变），也不改变 [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.1 已冻结的核心信号类型。

- **信号命名**：本页的 `type` 取值逐字取自 [../DESIGN.md](/design) 的映射表，一律为裸 snake_case；`msp/` 前缀是**模式 ID** 与第三方模式私有信号类型的命名空间（[README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §1.4、§5.3、[base-protocol](base-protocol.md) §2.2），**不**出现在本页的 `type` 取值里。
- **路由**：本页全部信号**不携带** `pattern`（`pattern = null`），由协议层的默认核心分发处理，论证见 §3.1。
- **与 `cancel` / `progress` 的关系**：核心已在 [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.1 把二者列为 🔵 规划中的核心信号（条文见 [base-protocol](base-protocol.md) §6.3–6.4）。本页不重复定义其报文，只声明两条交互：请求方**可以**用 `cancel` 取消在途的 `resource_read` / `sampling_request` / `elicitation_request`（按被取消请求的 `reqid` 关联，协作式，且不免除应答义务）；执行方在请求方给出 `payload.progressToken` 时**可以**用 `progress` 上报进度。
- **与索引的差异**：本页的信号类型**尚未**进入 [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.1 的表。并入核心表**必须**走 README §8 的演进流程并新增修订行；本页不修改索引。

实现收到本页未识别的信号类型时，**不得**断开连接，**应当**按 [base-protocol](base-protocol.md) §2.3 宽容读取处理；参考实现的现有行为是回 `error`（`code = -32600`，见 §9.1）。

### 1.3 内容承载

资源内容、提示消息与采样结果一律复用 [../src/msp/core/content.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) 的内容块（§5.1），不新造数据类型。

## 2. 映射与契约

### 2.1 MSP 映射表

下表与 [../DESIGN.md](/design)「MSP 映射：全部是信号」逐行一致：

| MCP 操作 | MSP 信号 | 方向 |
|---|---|---|
| `resources/read` | `resource_read` → `resource_content` | 读取方 → 资源持有方 请求 / 应答 |
| `resources/subscribe` | `resource_subscribe` / `resource_unsubscribe` → `resource_updated` | 订阅方 → 资源持有方 请求；持有方 → 订阅方 通知 |
| `prompts/get` | `prompt_get` → `prompt_content` | 调用方 → 提示持有方 请求 / 应答 |
| `sampling/createMessage` | `sampling_request` → `sampling_result` | 生成请求方 → 生成提供方 反向请求 / 应答 |
| `elicitation/create` | `elicitation_request` → `elicitation_result` | 征询方 → 用户宿主 反向请求 / 应答 |
| `roots/list` | `roots_list` → `roots` / `roots_changed` | 询问方 → roots 宿主 请求 / 应答；宿主 → 全部已连对端 通知 |

「反向」指请求方是 MCP 里的 server 角色；MSP 不预设角色，方向由能力声明决定（§2.3）。

### 2.2 取舍一：清单即列表，省掉 `list` 往返

MCP 的「列出有什么」是一次额外往返：`resources/list`（可带 `cursor` 分页）、`prompts/list`、`resources/templates/list`。MSP 不设这些信号，因为清单本身就是列表：① `Manifest.resources` / `Manifest.prompts` 的 `ResourceDescriptor`（`uri` / `name` / `description` / `mimeType` / `subscribable`）与 `PromptDescriptor`（`name` / `description` / `arguments`）**必须**随 HELLO / ACK 交换（[base-protocol](base-protocol.md) §4.4）；② 清单变化时 `manifest_update` 推送新清单，接收方按 `version` 丢弃过期项；③ 于是「列出」是握手与推送的**副产品**。本页只定义 read / get 这类**取值**操作，其入参（`uri` / `name`）**必须**来自对端清单，取值方**应当**先做本地校验，避免用取值请求探测清单。

两条推论：收到清单中不存在的 `uri` / `name` 时，持有方**应当**在应答载荷的 `error` 字段说明失败，**不应当**当作协议错误（§6.1）；MCP 的 `resources/templates/list`（URI 模板）**没有**对应物——`ResourceDescriptor` 没有模板字段，需要模板语义时**必须**按 [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §8 追加清单字段与新修订号，**不得**在本修订内私自扩展 `uri` 语法。分页同理：MSP 清单交换没有 `cursor` / `nextCursor`，**应当**一次性给出完整清单（§9.3）。

### 2.3 取舍二：反向能力是全双工的天然优势

展开 [../DESIGN.md](/design)「三个关键取舍」的第 2 条。MCP 里 sampling / elicitation 之所以是「反转」，原因是**角色**：`initialize` 把两端固化为 client 与 server，client 在自己的 `capabilities` 里声明 `sampling` / `elicitation` / `roots`，于是「请求生成」「征询用户」必须由 server 侧发起、client 侧应答，能力位挂在 client 上。MSP 没有这种角色固化：双方都能主动发信号，`sampling_request` 与 `tool_call` 在协议层完全同构——同一条连接、同一个 `reqid` 关联机制（[base-protocol](base-protocol.md) §5）、同一套超时规则，差别只有 `type`、方向与载荷形状。因此**不**需要「角色翻转」机制，也**不**需要在握手时确认谁是 client；但能力位仍然必需（§2.5），且同一份实现**可以**既提供工具（`rep`）又请求生成（`clientCapabilities.sampling = true`）。

注意：**方向不是理由**。JSON-RPC 2.0 只定义单条消息的形状，不限制哪一方发起；MSP 与它的差别在信封字段，不在方向（见 [interop](interop.md#json-rpc-20-语义对齐)）。

### 2.4 取舍三：资源订阅与路径过滤是两个维度

展开 [../DESIGN.md](/design)「三个关键取舍」的第 3 条。MSP 已有发布—订阅：`publish(path, payload)` 把 `signal` 扇出到全部已连对端，接收方用 `node.on(path)` 做本地通配匹配（[patterns/publish-subscribe](patterns/publish-subscribe.md)、[../src/msp/protocol/matcher.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/matcher.py)）。一个自然的想法是让资源变更也走这条路，于是「订阅资源」退化为「订阅某个 path」。本页**不**采用，因为两个维度不同：路径过滤的寻址单位是 path（点号分段、域优先，[base-protocol](base-protocol.md) §2.4），匹配方式是发送方广播 + 接收方本地 `*` / `**` 过滤，扇出到全部已连对端；资源订阅的寻址单位是 URI（`file://`、`db://`，含 `/`、`:`、`.`），匹配方式是请求—确认式点对点订阅、持有方维护订阅表，只扇出给订阅了该 URI 的对端。

把 URI 塞进 path 会让 path 不再承担「域优先的功能分类」，且需要为 `/`、`:`、`.` 设计转义，破坏 [base-protocol](base-protocol.md) §2.4 的文法（`segment = 1*( ALPHA / DIGIT / "_" / "-" )`，`/` 与 `:` 都不合法）。所以单设 `resource_subscribe`，寻址单位是 URI。两者**可以**并存：持有方**可以**在资源变更时额外 `publish` 一条路径信号供旁观者使用，但 `resource_updated` **不得**依赖它，订阅方也**不得**用路径过滤代替订阅声明。

### 2.5 能力声明与授权

能力声明是自述（「我自称会什么」），与授权（「我允许你做什么」）严格分离（[README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.5）。因此：提供方**必须**把可读取的资源与可渲染的提示声明进 `Manifest`，未声明的 `uri` / `name` **不得**被取值成功；`subscribable = false` 的资源**不得**被订阅成功；声明**不得**作为授权依据（接收方**不得**因对端声明了某能力就放宽本地授权，发送方也**不得**因对端声明了 `clientCapabilities.sampling = true` 就认定对方一定响应）；收到未声明能力位的请求时，接收方**应当**回 `error`（`code = -32601`，§6.2），与「调用未注册工具」同构。授权见 [security](security.md)。

## 3. 报文

### 3.1 共同规则

本页全部信号使用 [base-protocol](base-protocol.md) §2 的 `Signal` 信封，字段级条文以该页为准。**`pattern` 取值**：本页全部信号的 `pattern` **必须**为 `null`（或缺省），即它们**不属于任何模式**。理由：① [../DESIGN.md](/design) 的补法明确是「给 `_dispatch_core` 加分支（与 `tool_call` 同构）」，而 `_dispatch` 只把**带 `pattern`** 的信号交给模式处理器（[../src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._dispatch`），其余走 `_dispatch_core`；[base-protocol](base-protocol.md) §2.1 也把 `pattern` 默认值定为 `null`。② 这五组能力的**声明**已经住在 `Manifest` 里（`resources` / `prompts` descriptor 与 `clientCapabilities` 三个布尔位），再引入模式 ID 会让同一件事在两处声明。③ 每个信号都是形状固定的一次性操作，不构成「一类交互的语义集合」（[README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §4 对「模式」的定义）；先例是 `tool_call` / `tool_result`——它们是核心类型，而 `msp/multi-round` 在需要时用**同一** `type` 加 `pattern` 覆盖路由。④ 因此本页的信号既不是 [base-protocol](base-protocol.md) §2.2 那 9 个核心类型（索引表 8 行，因 `ping` / `pong` 合并为一行），也不是「模式私有类型」（后者**必须**携带非空 `pattern`），而是规划中能力面的**追加类型**，按 [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §1.2 第 2 条的增补规则给出。

其余共同条文：

- `source` **必须**是发送方自己的 `node_id`；`target` 上，请求与响应**必须**填接收方的 `node_id`（定向单播），`roots_changed` **必须**为 `null`（广播给全部已连对端，与 `signal` 一致）。接收方收到 `target` 非空且不等于自身 `node_id` 的信号时**应当**忽略（现有核心分支不检查 `target`，本条为新增条文）。
- `path` **必须**为 `null`：本页信号**不得**用 `path` 承载 URI。
- `reqid`：请求与响应**必须**携带，且响应的 `reqid` **必须**原样回填请求值；`reqid` **必须**是发送方在本次连接生命周期内唯一的非空字符串；`resource_updated`（`event = "changed"`）与 `roots_changed` 是通知，**不得**携带 `reqid`。分类规则与 [base-protocol](base-protocol.md) §2.2 一致：`reqid` 为空即通知，接收方**不得**为之应答。
- 请求**可以**携带 `payload.progressToken`（string），供执行方用核心 `progress` 上报进度（[base-protocol](base-protocol.md) §6.4）。

信号总表（分类按 [base-protocol](base-protocol.md) §2.2 的三分法）：

| `type` | 分类 | 有 `reqid` | 方向 |
|---|---|---|---|
| `resource_read` | 请求 | 是 | 读取方 → 资源持有方 |
| `resource_content` | 响应 | 是 | 资源持有方 → 读取方 |
| `resource_subscribe` / `resource_unsubscribe` | 请求 | 是 | 订阅方 → 资源持有方 |
| `resource_updated` | 响应（`subscribed` / `unsubscribed`）/ 通知（`changed`） | 前者是，后者否 | 资源持有方 → 订阅方 |
| `prompt_get` | 请求 | 是 | 调用方 → 提示持有方 |
| `prompt_content` | 响应 | 是 | 提示持有方 → 调用方 |
| `sampling_request` / `sampling_result` | 请求 / 响应 | 是 | 生成请求方 ↔ 生成提供方（反向） |
| `elicitation_request` / `elicitation_result` | 请求 / 响应 | 是 | 征询方 ↔ 用户宿主（反向） |
| `roots_list` / `roots` | 请求 / 响应 | 是 | 询问方 ↔ roots 宿主 |
| `roots_changed` | 通知 | 否 | roots 宿主 → 全部已连对端 |

一次请求的线格式（信封字段名与 [base-protocol](base-protocol.md) §2.1 一致）：

```json
{"type": "resource_read", "source": "agent_a", "pattern": null, "target": "file_monitor",
 "path": null, "reqid": "9f2c1ab34d5e6078", "payload": {"uri": "file:///tmp/report.md"},
 "timestamp": 1786000000.0}
```

### 3.2 `resource_read` / `resource_content`

| 信号 | 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `resource_read` | `payload.uri` | string | 是 | **必须**是对端清单中已声明的 `ResourceDescriptor.uri` |
| `resource_content` | `payload.uri` | string | 是 | 回填请求的 `uri` |
| `resource_content` | `payload.content` | array&lt;ContentBlock&gt; | 是 | **可以**为空数组；块类型见 §5.1 |
| `resource_content` | `payload.mimeType` | string | 否 | 与清单 `mimeType` 一致时**可以**省略 |
| `resource_content` | `payload.error` | string | 否 | 非空表示读取失败；此时 `content` **应当**为空数组 |

失败形态：`payload.error` 非空（错误即值，§6.1）。二进制资源**应当**用 `resource` 块内嵌（小对象）或 `blob_ref`（大对象，§5.2）；**不得**在 `resource_content` 里内联超出接收方缓冲上限的字节。

### 3.3 `resource_subscribe` / `resource_unsubscribe` / `resource_updated`

订阅、退订都是请求；接受与否用**同一条** `resource_updated` 确认，用 `event` 区分三种事件，从而不为一个空 ACK 增加信号类型。

| 信号 | 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `resource_subscribe` | `payload.uri` | string | 是 | **必须**指向 `subscribable = true` 的资源 |
| `resource_subscribe` | `payload.ttl` | number | 否 | 订阅存活秒数；缺省表示持续到连接断开或显式退订 |
| `resource_unsubscribe` | `payload.uri` | string | 是 | 退订目标 |
| `resource_updated` | `payload.uri` | string | 是 | 被订阅资源的 URI |
| `resource_updated` | `payload.event` | string | 是 | `"subscribed"` / `"changed"` / `"unsubscribed"` |
| `resource_updated` | `payload.content` | array&lt;ContentBlock&gt; | 视 `event` | `subscribed` 与 `changed` **必须**携带；`unsubscribed` **不得**携带 |
| `resource_updated` | `payload.version` | integer | 否 | 资源版本号，单调不减，用于检测乱序与丢失 |

确认与变更的线格式（信封同 §3.1）：

```json
// 订阅确认（响应，reqid = 请求的 reqid）
{"type": "resource_updated", "source": "file_monitor", "target": "agent_a",
 "reqid": "5b1e77c0a9d34f21",
 "payload": {"uri": "file:///tmp/report.md", "event": "subscribed",
             "content": [{"type": "text", "text": "# Report\n..."}], "version": 7}}
// 变更通知（通知，reqid 缺省）
{"type": "resource_updated", "source": "file_monitor", "target": "agent_a",
 "payload": {"uri": "file:///tmp/report.md", "event": "changed",
             "content": [{"type": "text", "text": "# Report\n... (v8)"}], "version": 8}}
```

条文：持有方接受订阅时**必须**立即以同一 `reqid` 回 `event = "subscribed"` 作为确认与初始快照，拒绝时**必须**回 `error`（§6.2）**不得**沉默；接受退订时**必须**以同一 `reqid` 回 `event = "unsubscribed"`，此后**不得**再向该对端发送该 `uri` 的任何 `resource_updated`；变更通知**不得**携带 `reqid`，`version` 不单调时接收方**应当**按最新值覆盖而**不得**视为协议错误；连接断开时该连接上的全部订阅**必须**失效，重连后**必须**重新订阅（订阅是连接级状态，不随 `Manifest` 交换）；`ttl` 到期时持有方**应当**停止推送并**可以**静默停止；`ttl` **不得**被用作授权。

### 3.4 `prompt_get` / `prompt_content`

| 信号 | 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `prompt_get` | `payload.name` | string | 是 | **必须**是 `Manifest.prompts` 中已声明的 `PromptDescriptor.name` |
| `prompt_get` | `payload.arguments` | object | 否 | 键为 `PromptDescriptor.arguments[].name`，值为 string |
| `prompt_content` | `payload.name` | string | 是 | 回填请求的 `name` |
| `prompt_content` | `payload.messages` | array&lt;object&gt; | 是 | 元素为 `{"role": "user"\|"assistant", "content": ContentBlock}`；**可以**为空数组 |
| `prompt_content` | `payload.description` / `payload.error` | string | 否 | 渲染后的说明（缺省沿用清单值）/ 非空表示渲染失败，此时 `messages` **应当**为空数组 |

`arguments` 不满足清单声明的参数时，持有方**应当**在 `error` 里说明（而不是协议错误）。渲染是提供方职责，调用方**不得**假设渲染结果与清单描述逐字一致。

### 3.5 `sampling_request` / `sampling_result`

`sampling_request.payload`（字段名与 MCP `sampling/createMessage` 对齐，便于互通）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `messages` | array&lt;object&gt; | 是 | 元素为 `{"role": "user"\|"assistant", "content": ContentBlock}` |
| `systemPrompt` | string | 否 | 系统提示 |
| `includeContext` | string | 否 | `"none"` / `"thisServer"` / `"allServers"`（MCP 语义；实现**可以**忽略并视为 `"none"`） |
| `modelPreferences` | object | 否 | `{"hints": [{"name": string}], "costPriority", "speedPriority", "intelligencePriority"}`，优先级取 0~1 |
| `maxTokens` / `temperature` / `stopSequences` | integer / number / array&lt;string&gt; | 否 | 生成上限、采样温度、停止串 |
| `metadata` | object | 否 | 实现自定义元数据 |
| `progressToken` | string | 否 | 进度标识（§3.1） |

`sampling_result.payload`：`role`（string，**必须**为 `"assistant"`）、`content`（ContentBlock，单块，与 MCP `CreateMessageResult.content` 一致）、`model`（string，实际使用的模型标识，供请求方记账与复现）、`stopReason`（string，可选，如 `"endTurn"` / `"maxTokens"`）、`error`（string，可选，非空表示宿主拒绝或生成失败）。**`error` 为空时 `role` / `content` / `model` 必须存在；`error` 非空时三者应当省略。** 宿主**可以**拒绝（额度、隐私、策略），但拒绝**必须**通过 `error` 字段或 `error` 信号表达，**不得**沉默丢弃。

### 3.6 `elicitation_request` / `elicitation_result`

| 信号 | 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `elicitation_request` | `payload.message` | string | 是 | 向用户呈现的问题文本；**必须**按不可信输入处理（§8） |
| `elicitation_request` | `payload.requestedSchema` | object | 是 | 受限 JSON Schema：`type` **必须**为 `"object"`；`properties` 的值**必须**是原始类型或 `enum`；`required` 为属性名数组 |
| `elicitation_result` | `payload.action` | string | 是 | `"accept"` / `"decline"` / `"cancel"` |
| `elicitation_result` | `payload.content` | object | 视 `action` | `action = "accept"` 时**必须**存在且**必须**满足 `requestedSchema`；其余取值**不得**携带 |

`action = "decline"` / `"cancel"` 是**成功应答**而非错误：请求已被正确处理，只是用户不同意或撤回了操作。宿主**不得**为这两种取值发送 `error` 信号。

### 3.7 `roots_list` / `roots` / `roots_changed`

`roots_list.payload` 为空对象 `{}`（保留以承载未来扩展）。`roots` 与 `roots_changed` 的 `payload.roots` **必须**是数组，元素为 `{"uri": string, "name": string}`：`uri` **必须**是绝对 URI，`name` **可以**为空串。

方向说明：[../DESIGN.md](/design) 该行标注为「client→server 通知」，那是按 MCP 的 client / server 角色描述的。MSP 不预设角色（[README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §4），本页改用可判定的表述：roots 由**声明了 `clientCapabilities.roots = true` 的节点**（下称 roots 宿主）持有；`roots_list` 由任何已连对端发给宿主；`roots`、`roots_changed` 由宿主发出。这与 MCP 中「server 向 client 请求 roots」的形状一致。

条文：宿主**应当**在接受握手后主动发送一次 `roots_changed`（无 `reqid`，`target = null`）；roots 变化时**必须**发送 `roots_changed`；询问方收到后**应当**以最新值覆盖本地缓存，**不得**因为 `roots` 与 `roots_changed` 不一致而断开连接；收到 `roots_list` 但自身 `clientCapabilities.roots = false` 时**必须**回 `error`（`code = -32601`）；`roots` **不得**被当作访问控制——它是**声明**不是授权，接收方**不得**因为某个路径不在 `roots` 里就认为对端允许访问其余路径（[README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.5）。

## 4. 消息流

### 4.1 资源订阅 + 变更通知

```text
 agent_a（订阅方）                        file_monitor（资源持有方）
   │ HELLO / ACK：交换 Manifest              │
   │ ← resources[file:///tmp/report.md]      │
   │    .subscribable = true                 │
   │ ─ resource_subscribe ─────────────────▶ │ reqid=r1 {uri, ttl}
   │                                         │ 登记订阅表
   │ ◀ resource_updated ──────────────────── │ reqid=r1 event=subscribed
   │   {uri, event:"subscribed", content:[…]}│ 确认 + 初始快照
   │                       （文件被写入）     │
   │ ◀ resource_updated ──────────────────── │ 无 reqid event=changed
   │   {uri, event:"changed", version:8}     │
   │ ─ resource_unsubscribe ───────────────▶ │ reqid=r2 {uri}
   │ ◀ resource_updated ──────────────────── │ reqid=r2 event=unsubscribed
   │ （此后不再收到该 uri 的任何更新）        │
```

### 4.2 反向 sampling 请求

```text
 worker（生成请求方）                    llm_host（生成提供方）
   │ HELLO / ACK：清单里                    │
   │ clientCapabilities.sampling = true     │
   │ ─ sampling_request ──────────────────▶ │ reqid=s1
   │   {messages, systemPrompt, maxTokens}  │ 交给本机 LLM
   │ ◀ sampling_result ───────────────────  │ reqid=s1
   │   {role:"assistant", content, model}   │
   │ （宿主拒绝：payload.error 非空，        │
   │   或 error 信号 -32601）               │
   │ 与 tool_call 同构：同一连接、同一 reqid  │
   │ 关联、同一超时规则，方向相反而已。       │
```

### 4.3 elicitation 与取消

`elicitation` 的消息流与 §4.2 同构，只是把 `sampling_request` / `sampling_result` 换成 `elicitation_request` / `elicitation_result`，且 `action = "decline"` / `"cancel"` 属成功应答。二者与核心 `cancel` / `progress`（[base-protocol](base-protocol.md) §6.3–6.4）的组合如下：

```text
 agent_a（请求方）                     file_monitor（执行方）
   │ ─ resource_read ───────────────▶ │ reqid=r3 {uri:"file:///big.bin",
   │                                  │            progressToken:"p-num-1"}
   │ ◀ progress ───────────────────── │ reqid=r3（通知，不得应答）
   │   {progressToken, progress:40, total:100}
   │ ─ cancel ──────────────────────▶ │ reqid=r3 {reason:"用户取消"}
   │ ◀ resource_content ──────────── │ reqid=r3 终态 {uri, content:[],
   │                                  │   error:"已取消"}——取消改变的是结果，
   │                                  │   不是「是否应答」的义务
```

## 5. 数据类型

### 5.1 内容块

资源内容、`prompt_content.messages[].content`、`sampling_request.messages[].content` 与 `sampling_result.content` **必须**使用 [../src/msp/core/content.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) 中已定义的内容块类型：

| `type` | 关键字段 | 用途 |
|---|---|---|
| `text` | `text`（必填）、`annotations`（可选） | 文本资源与提示 |
| `image` / `audio` | `data`（Base64，必填）、`mimeType`（必填） | 图片 / 音频 |
| `resource` | `resource: {uri, mimeType, text?, blob?}` | 内嵌文本或二进制资源 |
| `resource_link` | `uri`、`name`、`mimeType`、`description` | 只给引用，内容由接收方自行取值 |
| `blob_ref` | `blobId`、`mimeType`、`size`、`checksum` | MSP 扩展：指向独立 blob 通道（§5.2） |

接收方遇到未知块类型时**必须**原样保留（宽容读取，[base-protocol](base-protocol.md) §2.3；`block_from_dict()` 的行为），**不得**视为协议错误。

### 5.2 `blob_ref` 与大对象

`resource` 块把字节内嵌进信号，受传输分帧与内存限制。超过实现自定阈值（**应当**在文档中声明，例如 1 MiB）的资源**应当**改用 `blob_ref`：`blob_ref` 只携带 `blobId` / `mimeType` / `size` / `checksum`，字节走独立的 blob 信号流（`msp/streaming` 规划中，见 [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.2）；`checksum` **应当**是全量内容的摘要，接收方取回后**应当**校验；`blobId` **必须**在当前连接内唯一；收到 `blob_ref` 但未实现 blob 通道时，接收方**应当**回 `resource_content.payload.error` 说明失败，**不得**静默丢弃。

### 5.3 Manifest 声明槽

| 声明槽 | 源码形态 | 本页用法 |
|---|---|---|
| `Manifest.resources` | `array<ResourceDescriptor>`，序列化键 `resources` | 「列出有什么」的唯一来源；`subscribable` 决定是否可订阅 |
| `Manifest.prompts` | `array<PromptDescriptor>`，序列化键 `prompts` | 同上；`arguments` 描述 `prompt_get` 的入参 |
| `Manifest.clientCapabilities.sampling` | 布尔，序列化键 `clientCapabilities.sampling` | 是否接受 `sampling_request` |
| `Manifest.clientCapabilities.elicitation` | 布尔，序列化键 `clientCapabilities.elicitation` | 是否接受 `elicitation_request` |
| `Manifest.clientCapabilities.roots` | 布尔，序列化键 `clientCapabilities.roots` | 是否持有并宣告 roots |

这三个客户端能力位在源码中已存在（`supports_sampling` / `supports_elicitation` / `supports_roots`，序列化为 `clientCapabilities`），但 [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.5 的「角色能力位」表只列出 `pub` / `sub` / `req` / `rep`，**未**收录它们。本页因此把三者记为「源码已存在的声明槽」，**不**改动索引、也**不**把新语义塞进 `pub`/`sub`/`req`/`rep`（差异见 §9.3）。

## 6. 错误处理

### 6.1 两条失败通道

沿用 [base-protocol](base-protocol.md) §6.1：**错误即值**指请求已被正确解析、已路由到正确的提供方，业务上失败（URI 不存在、资源不可订阅、提示名不存在、参数不满足声明、生成失败）时，在**应答信号**的 `payload.error` 里放字符串，`reqid` 不变，**不得**再发 `error` 信号；**协议层失败**（未实现该信号、`reqid` 缺失、`payload` 不是对象、未声明该能力位）则发 `error` 信号，`payload` 为 `{"code": <int>, "message": <string>}`（[base-protocol](base-protocol.md) §6.2）。`elicitation_result.action` 取 `decline` / `cancel` 属于成功，**不得**走任一失败通道（§3.6）。

### 6.2 错误码归属

| 失败情形 | 通道 | `code` / 字段 |
|---|---|---|
| 收到未实现的能力面信号类型，或 `reqid` 缺失、`payload` 不是对象 | `error` 信号 | `-32600` |
| 本节点未声明该能力（清单无 `resources` / `prompts`，或对应 `clientCapabilities` 位为 `false`） | `error` 信号 | `-32601`（与「调用未注册工具」同构） |
| `uri` / `name` 不在对端清单中，或资源 `subscribable = false` | 应答载荷 `error` | 无 `code` |
| `prompt_get.arguments` 不满足 `PromptDescriptor.arguments`，或 `elicitation_result.content` 不满足 `requestedSchema` | 应答载荷 `error` | 无 `code` |
| 提供方在渲染 / 生成应答时抛出未预期异常 | `error` 信号 | `-32603` |
| 未在超时内收到应答 | 本地超时（实现自定异常） | **不得**发送 `error` |
| `target` 非空且不是本节点 | 忽略并记日志 | **不得**回 `error`（避免环回） |
| 收到未知 `reqid` 的 `cancel` | 静默忽略（[base-protocol](base-protocol.md) §6.3） | — |

`-32000` ~ `-32099` 保留给模式层（[README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.4）。本页信号不携带 `pattern`，**不得**使用该区间；收到该区间的 `error` 时**应当**原样透传给上层而不是改写（见 [interop](interop.md) 的桥接降级策略）。

### 6.3 超时、取消与进度

未显式指定时，请求方**应当**沿用 `call` 的默认超时 `5.0` s（[README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.6）；`sampling_request` 与 `elicitation_request` 依赖模型或人，**应当**使用更长的超时，但本页**不**冻结该值（`msp/multi-round` 的 `ctx.ask()` 用 `30.0` s 作为参考，它不在 [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.6 的冻结默认参数表内，实现**可以**自定）。请求方超时后**必须**丢弃该 `reqid` 的迟到应答，**不得**把它当作下一条请求的结果；协议**没有**服务端截止时间的概念（[base-protocol](base-protocol.md) §6.5），执行方**不一定**知道调用方已放弃。显式取消**必须**使用核心 `cancel` 信号（协作式、按被取消请求的 `reqid` 关联、收到后**仍必须**发送终态响应），本页信号**不得**自定义取消报文，`msp/task` 的取消走模式自己的 `task_cancel`。执行方在请求携带 `payload.progressToken` 时**可以**用核心 `progress` 上报进度，**不得**把 `progress` 当作可靠传输。

### 6.4 与 `msp/multi-round` 的关系

`elicitation_request` / `elicitation_result` 与 `msp/multi-round` 的 `input_required` / `input_response` 都能达到「追问」的效果，但语义不同（逐信号差异另见 [patterns/multi-round](patterns/multi-round.md) §6.8）：

| | `msp/multi-round` | `elicitation_request` |
|---|---|---|
| 请求标识 | **必须**沿用原 `tool_call` 的 `reqid`，整段交互一个 `reqid` | 自己新开一个 `reqid`，不延续原调用 |
| 触发位置 | 只在一次工具调用的执行过程中（`ctx.ask()`） | 任何时刻，包括没有工具调用时 |
| 前提 | 对端**必须**激活 `msp/multi-round` 模式（`pattern` 字段） | 对端**必须**声明 `clientCapabilities.elicitation = true` |
| 载荷 | `{"prompt": string}` / `{"answer": 任意 JSON}` | `{message, requestedSchema}` / `{action, content}`，`content` 可被机器校验 |
| 声明位置 | `Manifest.patterns` | `Manifest.clientCapabilities.elicitation` |

选择依据：追问属于「**这一次工具调用**缺参数」时**应当**用 `msp/multi-round`（同一 `reqid`，调用方有 `input_fn` 参与，失败降级目标是 `msp/request-reply`）；需要**脱离工具调用**向用户提问（执行前策略确认、选择资源范围），或对端没有激活 `msp/multi-round` 时**应当**用 `elicitation_request`；需要结构化、可校验的答案时**应当**用 `elicitation_request`（`content` 受 `requestedSchema` 约束，而 multi-round 的 `answer` 只是任意 JSON）；需要模型**生成**内容而不是向人提问时，两个都**不得**使用，**必须**用 `sampling_request`。

## 7. 规范条文汇总（MUST/SHOULD 清单）

**必须**：① 全部信号的 `pattern` 为 `null`，`source` 为发送方 `node_id`，请求与响应携带 `reqid` 且响应原样回填（§3.1）；② `resource_read` 的 `uri` 来自对端清单，`resource_content` 携带 `uri` 与 `content`（§3.2）；③ 订阅被接受时立即回 `event = "subscribed"` 并带初始快照，被拒绝时回 `error`（§3.3）；④ 退订被接受时回 `event = "unsubscribed"`，此后不再推送该 URI（§3.3）；⑤ `event = "changed"` 的 `resource_updated` 与 `roots_changed` 不带 `reqid`，`unsubscribed` 不带 `content`（§3.1、§3.3）；⑥ 连接断开时该连接上的订阅全部失效，重连后重新订阅（§3.3）；⑦ 收到 `roots_list` 而自身 `clientCapabilities.roots = false` 时回 `-32601`（§3.7）；⑧ `requestedSchema` 的 `type` 为 `"object"`、`properties` 的值为原始类型或 `enum`（§3.6）；⑨ 能力面失败按 §6.1 走对应通道，不得两者并用；⑩ 未知块类型与未识别的信号类型不得被视为协议错误或导致断开（§5.1、§1.2）；⑪ 取消使用核心 `cancel`，收到后仍发送终态响应（§6.3）。

**应当**：⑫ 取值前本地校验 `uri` / `name` 是否在对端清单中（§2.2）；⑬ `blob_ref` 的 `checksum` 存在并在取回后校验，大对象阈值在实现文档中声明（§5.2）；⑭ sampling / elicitation 的超时长于 `call` 默认值，超时后丢弃迟到应答（§6.3）；⑮ roots 宿主在握手后主动发一次 `roots_changed`（§3.7）。

**不得**：⑯ 用 `path` 承载 URI（§3.1）；⑰ 把 `roots` 或 `ResourceDescriptor.subscribable` 当作授权依据（§2.5、§3.7）；⑱ 使用 `-32000` ~ `-32099` 错误码区间（§6.2）；⑲ 把 `ttl` / `maxTokens` 等载荷字段用作访问控制（§3.3）。

**可以**：⑳ 资源变更时额外 `publish` 一条路径信号，但 `resource_updated` 不得依赖它（§2.4）；㉑ 忽略 `includeContext` 并视为 `"none"`（§3.5）；㉒ `ttl` 到期时静默停止推送（§3.3）；㉓ 请求携带 `payload.progressToken`，执行方用 `progress` 上报进度（§3.1、§6.3）。

## 8. 安全考量

信任边界是传输可达范围，认证不等于授权（[security](security.md)）。

1. **数据外泄面**：`resource_read` 与 `resource_subscribe` 让对端持续或按需获取本机数据。提供方**必须**在授权层按 URI 前缀做判定，**不得**只依据清单声明（清单是自述）；订阅是**持续**数据流，**应当**默认短 `ttl` 并可即时退订。
2. **提示注入面**：`prompt_content.messages` 的文本会进入请求方的模型上下文，请求方**应当**把它标注为外部不可信内容，**不得**当作系统指令执行。
3. **反向生成面**：`sampling_request` 把**对端的提示词**送进本机 LLM，存在提示注入与额度滥用风险。宿主**必须**能拒绝，并**应当**按来源节点做策略判定；宿主**不得**因为 `source` 自报的身份就放宽策略（[README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.5）。
4. **面向人的征询面**：`elicitation_request.message` 是外部不可信文本，宿主**必须**在呈现时标明来源 `sig.source`；`requestedSchema` **不得**用于构造可执行动作（例如「输入要执行的命令」），只**应当**用于结构化选项。
5. **roots 与扇出面的误用**：任何把 `roots` 当作白名单或黑名单的实现都偏离 §3.7 的条文；`roots_changed` 广播给全部已连对端，订阅表按对端维护，二者都有放大风险。实现**应当**对订阅数量、单条 `content` 体积、单位时间推送次数设上限，超限时**应当**回 `error` 而不是静默降级。

## 9. 已知缺口

### 9.1 现状

现状**必须**明确：`Manifest` 已经声明了这些能力的「位」，但协议层没有任何对应操作，因此对端拿到清单会**看到许诺但用不了**。

| 事实 | 源码位置 |
|---|---|
| `Manifest.resources` / `Manifest.prompts` 字段与 `add_resource()` / `add_prompt()` 已存在，并随 `to_dict()` 交换 | [../src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `ResourceDescriptor` / `PromptDescriptor` / `Manifest.add_resource` / `Manifest.add_prompt` / `Manifest.to_dict` |
| 客户端能力位已存在并序列化为 `clientCapabilities` | 同上，`Manifest.supports_sampling` / `supports_elicitation` / `supports_roots` |
| 清单推送与差分已可用 | [../src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol.push_manifest()` / `_on_manifest_update()`；差分 `Manifest.diff()` / `Manifest.apply_diff()` 已写好但未被协议层使用 |
| **没有**任何本页信号类型 | [../src/msp/core/signal.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/signal.py) `SignalType` 只有 `hello` / `ack` / `signal` / `tool_call` / `tool_result` / `manifest_update` / `ping` / `pong` / `error` |
| **没有**任何本页分发分支 | [../src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._dispatch_core()` 无对应 `elif`；本页信号落到 `else`，被回 `error`（`-32600`「未知信号类型」） |
| **没有** node 层 API | [../src/msp/core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) 无 `resource()` / `prompt()` / `sample()` / `elicit()` / `roots()`，只有 `tool()` / `on()` / `publish()` / `call()` |
| 本页信号**尚未**进入 [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.1 的核心信号类型表 | 索引 §5.1 目前只收录 9 个已实现核心类型（表 8 行）与 🔵 的 `cancel` / `progress` |

### 9.2 补法

1. 在 `SignalType` 追加本页 §3.1 总表列出的 14 个类型名（与唯一权威源 `schema/2026-10-10/msp.yaml` 的条目数一致）。
2. 在 `MSPProtocol._dispatch_core()` 追加分支，与 `tool_call` / `tool_result` **同构**：请求分支解析 `payload`、按 `reqid` 关联，响应分支唤醒等待方。所有可能耗时的操作（资源读取、提示渲染、模型生成、向人征询）**必须**在独立线程执行，**不得**在读循环线程里同步执行——理由与 `MSPProtocol._on_tool_call()` 的注释一致：慢操作会阻塞该连接的消息接收，且操作内部若回调对端会死锁。
3. 在 `MSPNode` 层追加装饰器与方法：`@node.resource(uri, ...)`、`@node.prompt(name, ...)`、`node.read_resource(peer, uri)`、`node.get_prompt(peer, name, arguments)`、`node.subscribe_resource(peer, uri)`、`node.sample(peer, ...)`、`node.elicit(peer, ...)`、`node.set_roots([...])`，以及接收侧的 `node.on_resource_updated(...)`。这些名字是**规划 API**，不构成规范常量；条文只约束 §3 的报文形态。
4. 复用既有能力，不新造：内容块用 `core/content.py` 与 `block_from_dict()`；结果规范化可复用 `_normalize_tool_result()`；请求—应答的等待/唤醒结构可参照 `MultiRoundHandler` 的 `_pending_calls` / `_active_asks`；取消与进度直接复用核心 `cancel` / `progress`（[base-protocol](base-protocol.md) §6.3–6.4），**不得**为能力面另造一套。

### 9.3 缺口清单

| # | 缺口 | 状态 | 影响 |
|---|---|---|---|
| 1 | 本页全部信号在参考实现中不存在，收到即回 `-32600` | 🔵 | 清单已宣告、操作不可用（§9.1） |
| 2 | 本页信号类型未进入 [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.1 核心信号表 | 索引缺口 | 并入核心表**必须**走 README §8，本页不修改索引 |
| 3 | `clientCapabilities` 三个能力位不在 [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.5 的冻结能力位表中 | 索引缺口 | 本页只把它们记为源码已有声明槽，未改动索引 |
| 4 | 无 URI 模板（MCP `resources/templates/list`）对应物 | 🔵 | 动态 URI 需走规范演进流程（§2.2） |
| 5 | 清单交换无分页 | 🔵 | 规模大时单条 `manifest_update` 很大；`Manifest.diff()` 已写好但 `push_manifest()` 发送的是**完整清单**，未被协议层用于增量 |
| 6 | 订阅与 roots 都是连接级状态；且无服务端截止时间 | 设计选择 / 🔵 | 断线重连后必须重新订阅；调用方超时后执行方不一定知道，只能靠 `cancel` 协作式停止（[base-protocol](base-protocol.md) §6.5） |
| 7 | blob 通道（`msp/streaming`）规划中 | 🔵 | `blob_ref` 只能指向尚未落地的通道 |
| 8 | MCP 适配层只实现 stdio + tools | 🔵 | MCP 的 resources / prompts / sampling 与本页信号之间暂无转换器（见 [interop](interop.md)） |

## 10. 参考实现映射

| 条文 | 状态 | 源码文件与符号 |
|---|---|---|
| §2.1 映射表、§3 全部报文 | 🔵 未实现 | 规划落点为 `src/msp/core/signal.py` `SignalType` 与 `src/msp/protocol/protocol.py` `MSPProtocol._dispatch_core` |
| §3.1 信封字段；`pattern` 为 `null` 时走默认分发、未知信号回 `-32600`、`target` 现状不检查；定向发送与广播 | ✅ / 🔵 | [../src/msp/core/signal.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/signal.py) `Signal` / `Signal.make` / `Signal.to_dict` / `Signal.from_dict` / `Signal.new_reqid`；[../src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._dispatch`（第 3 步）、`_dispatch_core` 的 `else` 分支、`_reply_error`、`_send`、`publish` |
| §5.1 内容块与结果规范化（可复用） | ✅ | [../src/msp/core/content.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) `TextContent` / `ImageContent` / `AudioContent` / `EmbeddedResource` / `ResourceLink` / `BlobRef` / `block_from_dict` / `blocks_from_list`；`_normalize_tool_result` |
| §5.2 `blob_ref` 与 blob 通道 | 🔵 | 同上 `BlobRef`；blob 通道未实现 |
| §5.3 清单声明槽 | ✅（仅声明与交换） | [../src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `ResourceDescriptor` / `PromptDescriptor` / `Manifest.add_resource` / `add_prompt` / `to_dict`（`clientCapabilities`）/ `from_dict` |
| §2.2 清单推送与版本过滤 / 清单差分 | ✅ / 🟡 | `MSPProtocol.push_manifest` / `_on_manifest_update`；`Manifest.diff` / `apply_diff`（未被协议层使用） |
| §2.4 路径通配过滤 | ✅ | [../src/msp/protocol/matcher.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/matcher.py) `pattern_matches`；[../src/msp/core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `MSPNode.on` |
| §6.3 工作线程执行、取消 / 进度；§6.4 同 `reqid` 追问 | ✅ 可复用 / 🔵 | `MSPProtocol._on_tool_call` / `_run_tool`；[../src/msp/patterns/multi_round.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/multi_round.py) `MultiRoundHandler._run_tool` / `INPUT_REQUIRED` / `INPUT_RESPONSE` / `RoundContext.ask` / `call_multiround`；`cancel` / `progress` 见 [base-protocol](base-protocol.md) §6.3–6.4 |
| §9.2 node 层 API | 🔵 未实现 | [../src/msp/core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) 现有 `tool` / `on` / `publish` / `call` / `pattern` |
