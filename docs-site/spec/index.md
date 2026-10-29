# MSP 规范 — Model Sensing Protocol Specification

| | |
|---|---|
| **协议修订** | `2026-10-10` |
| **对应实现** | `msp-py` 0.1.0（Alpha） |
| **文档状态** | 草案 — 覆盖全部已实现层，并完整定义规划中的能力（逐条标注状态） |
| **规范性用语** | RFC 2119（见 [规范性用语](#2-规范性用语)） |

> **Everything is a node. Everything is a signal. Every layer is extensible.**

本目录是 MSP 的**规范**（normative）：它定义互操作所要求的行为——双方各自独立实现，按本规范实现即可互通。

规范之外还有两类文档，分工如下：

| 文档 | 回答什么 | 性质 |
|---|---|---|
| **本目录（`docs/spec/`）** | 「实现**必须**做什么才能互通」 | 规范性 |
| [设计文档](/design) | 「为什么这样设计、放弃了什么」 | 说明性 |
| [技术白皮书](https://github.com/hxh230802/MSP/blob/master/docs/whitepaper.md) | 「它解决什么问题、与 MCP/A2A 的关系」 | 说明性 |
| [README](https://github.com/hxh230802/MSP/blob/master/README.zh-CN.md) | 「怎么用」 | 教程性 |
| `src/msp/` | 参考实现本身 | 事实来源 |

**规范与实现的冲突处理**：当条文与参考实现不一致时，以本规范为准并记为缺陷；参考实现是规范的第一个实现，不是规范本身。

---

## 1. 修订历史

MSP 的协议修订号沿用 **ISO 日期**（`YYYY-MM-DD`），与 MCP 的修订策略一致：修订号标识**一组互操作的报文契约**，而不是某次代码发布。

| 修订 | 日期 | 变更 |
|---|---|---|
| `2026-10-10` | 2026-10-10 | 首个规范草案。冻结 `Signal` 信封、核心信号类型、握手与去重规则、错误码、模式路由契约、`Endpoint` 与声明文件格式、路径匹配算法、`msp/task` 与 `msp/multi-round` 报文；完整定义规划中的能力面、安全模型与 QUIC / DHT 扩展点。 |

### 版本化策略

1. **修订号变更**必须伴随[修订历史](#1-修订历史)新增一行；不带日期的改动只能落在说明性文字上。
2. **向后兼容的增补**（新增可选字段、新增模式 ID、新增信号类型）在同一修订内以「追加」形式给出，接收方**应当**忽略未知字段与未知信号类型所要求的语义（见 [宽容读取](#7-一致性)）。
3. **不兼容变更**（改字段语义、改匹配算法、改握手次序）**必须**发新修订号，且**必须**在修订历史中标注影响面。
4. **模式 ID 命名空间**：`msp/` 前缀由本规范保留；第三方模式**必须**使用自有前缀（如 `acme/streaming`），不得占用 `msp/`。

---

## 2. 规范性用语

本规范中的关键词按 RFC 2119 解释。中文条文使用下表左列，等价于右列的英文关键词；引用实现时两者可互换。

| 中文 | 英文 | 含义 |
|---|---|---|
| **必须** | MUST | 绝对要求。不满足即不符合本规范 |
| **不得** | MUST NOT | 绝对禁止 |
| **应当** | SHOULD | 除非有正当理由，否则需遵守；偏离时**应当**能说明理由 |
| **不应当** | SHOULD NOT | 除非有正当理由，否则需避免 |
| **可以** | MAY | 可选，实现可自由取舍 |

正文中**加粗**的关键词承担规范效力；未加粗的同类词（如「需要」「建议」）是叙述，不构成要求。

**状态标注**：每一页与每一节都带一个状态标记，读者据此判断条文能否在当前实现上验证。

| 标记 | 含义 |
|---|---|
| ✅ **已实现** | 参考实现已落地，条文可直接验证 |
| 🟡 **部分实现** | 已落地主路径，存在条文列明的已知缺口 |
| 🔵 **规划中** | 条文已完整定义，参考实现尚未落地；**实现者可以不实现**，但一旦实现**必须**符合条文 |

---

## 3. 规范结构

| 页 | 内容 | 状态 |
|---|---|---|
| [architecture.md](architecture.md) | 分层架构、四个核心概念、层间契约、Preset 与角色、能力协商 | ✅ 已实现 |
| [base-protocol.md](base-protocol.md) | `Signal` 信封、编解码、连接生命周期、握手与去重、心跳、`reqid` 关联、错误码 | ✅ 已实现 |
| [transports.md](transports.md) | 传输抽象、TCP / WebSocket / UDS / QUIC 分帧与地址格式 | ✅ 已实现（QUIC 🔵） |
| [discovery.md](discovery.md) | Discovery / Presence 契约、共享目录声明文件、租约 TTL、HTTP 注册表、DHT | ✅ 已实现（DHT 🔵） |
| [patterns.md](patterns.md) | 模式层契约、`pattern_id` 与路由、`fallback_to` / `conflicts_with`、`install_api`、规划中的模式 | ✅ 已实现 |
| [patterns/request-reply.md](patterns/request-reply.md) | 核心模式：`tool_call` / `tool_result`、`reqid` 关联、超时 | ✅ 已实现 |
| [patterns/publish-subscribe.md](patterns/publish-subscribe.md) | 核心模式：广播、路径语法、通配符匹配算法、本地过滤 | ✅ 已实现 |
| [patterns/multi-round.md](patterns/multi-round.md) | `msp/multi-round`：执行中追问、`input_required` / `input_response` | ✅ 已实现 |
| [patterns/task.md](patterns/task.md) | `msp/task`：任务状态机、产物、观察者广播、A2A 等价映射 | ✅ 已实现 |
| [capabilities.md](capabilities.md) | resources / prompts / sampling / elicitation / roots 的信号定义 | 🔵 规划中 |
| [security.md](security.md) | 信任边界、威胁模型、TLS、节点认证、授权（`grants`） | 🟡 部分实现 |
| [interop.md](interop.md) | MCP ⊆ MSP、`msp.mcp` 适配层、A2A 映射、JSON-RPC 2.0 语义对齐 | ✅ 已实现（stdio + Streamable HTTP 载体 + tools） |
| [schema.md](schema.md) | 数据模型参考：JSON 形态的完整字段定义 | ✅ 已实现 |

---

## 4. 术语表

| 术语 | 英文 | 定义 |
|---|---|---|
| **节点** | Node | 通讯参与方，具有全局唯一 `node_id`。不预设客户端/服务端角色 |
| **信号** | Signal | 通讯的最小数据原子；握手、订阅、工具调用、任务、心跳全部是它的实例 |
| **模式** | Pattern | 一类交互的语义集合（请求—响应、发布—订阅、多轮往返、任务委托…），以 `pattern_id` 标识 |
| **能力清单** | Manifest | 节点自述的声明：支持的模式、发布的路径、提供的工具/资源/提示、角色能力位 |
| **端点** | Endpoint | 节点的传输身份：`{transport_type, address, node_id}` |
| **路径** | Path | 信号的逻辑地址，点号分段（`notify.web.download`），支持 `*` / `**` 通配 |
| **发现** | Discovery | 「我怎么找到别人」：产出 `Endpoint` |
| **宣告** | Presence | 「别人怎么找到我」：把 `Endpoint` 写进某个共享通道 |
| **传输** | Transport | 只搬运字节的连接抽象，不感知消息语义 |
| **预设** | Preset | 一个角色所启用的发现 / 宣告 / 传输 / 模式 / 能力位的组合 |
| **邻居** | Neighbor | 已发现（未必已连接）的对端 |
| **对等端** | Peer | 邻居的只读聚合视图（端点 + 连接 + 能力清单） |
| **应答通道** | Reply channel | 由本节点发起、对端应答的交互路径；授权模型中默认放行 |

---

## 5. 规范常量速查

以下常量在所有页面中含义一致，各页不再重复定义。**它们是互操作契约的一部分，不得随意改动。**

### 5.1 核心信号类型（`Signal.type`）

核心信号类型共 **9 个**（下表 8 行，因 `ping` 与 `pong` 合为一行）。`ping` / `pong` 的 `payload` 为 `{}`；其余类型的载荷字段以各页定义为准。

| `type` | 方向 | 有 `reqid` | 语义 | 页 |
|---|---|---|---|---|
| `hello` | 发起方 → 接受方 | 否 | 握手请求，`payload.manifest` 携带能力清单 | [base-protocol](base-protocol.md#42-握手) |
| `ack` | 接受方 → 发起方 | 否 | 握手应答，`payload.manifest` 携带能力清单 | 同上 |
| `signal` | 任意 → 全部已连对端 | 否 | 发布一条数据信号，`path` + `payload` | [publish-subscribe](patterns/publish-subscribe.md) |
| `tool_call` | 调用方 → 被调方 | **是** | 工具调用请求，`payload.tool` / `payload.args` | [request-reply](patterns/request-reply.md) |
| `tool_result` | 被调方 → 调用方 | **是** | 工具调用结果，`payload.content` / `structuredContent` / `error` | 同上 |
| `manifest_update` | 任意 → 全部已连对端 | 否 | 能力清单推送，`payload.manifest` 携带**完整清单**（非增量） | [base-protocol](base-protocol.md#44-能力清单交换与更新) |
| `ping` / `pong` | 双向 | 否 | 心跳探活 | [base-protocol](base-protocol.md#45-心跳与失联判定) |
| `error` | 任意 | 视情况 | 错误通告，`payload.code` / `payload.message` | [base-protocol](base-protocol.md#6-错误处理) |

**🔵 规划中的核心信号类型**（条文见 [base-protocol.md §6.3–6.4](base-protocol.md#63-取消)）：

| `type` | 分类 | 有 `reqid` | 语义 |
|---|---|---|---|
| `cancel` | 请求 | **是** | 请求取消某次在途调用。协作式：**不**保证对端真的停下，也**不**免除对端的应答义务 |
| `progress` | 通知 | **是** | 进度上报，按调用方给出的 `progressToken` 关联；**不得**被当作可靠传输 |

模式可定义**模式私有信号类型**（如 `input_required`、`task_submit`）。它们与核心类型共用同一个 `type` 字段空间，但**必须**同时携带 `pattern` 字段以便路由；`msp/` 命名空间外的模式**必须**为自己的类型加前缀，避免跨模式撞名。

### 5.2 模式 ID

| `pattern_id` | 状态 | 说明 |
|---|---|---|
| `msp/request-reply` | ✅ 核心 | `call()` / `tool_call` / `tool_result` |
| `msp/publish-subscribe` | ✅ 核心 | `publish()` / `signal` + 接收方本地过滤 |
| `msp/multi-round` | ✅ 扩展 | 执行中追问 |
| `msp/task` | ✅ 扩展 | 任务状态机 + 产物 |
| `msp/streaming` | 🔵 规划 | `stream_start` / `stream_chunk` / `stream_end` |
| `msp/callback-push` | 🔵 规划 | 长任务回调式回传 |
| `msp/async-polling` | 🔵 规划 | 显式轮询语义（互操作兜底） |

`msp/request-reply` 与 `msp/publish-subscribe` 是**核心模式**：直接实现在协议层，因为信号路由、`reqid` 关联与广播扇出依赖协议层状态。其余为**可扩展模式**：一个独立文件 + 一个注册表条目，不改协议核心。

### 5.3 命名规范

| 对象 | 分隔符 | 格式 | 示例 |
|---|---|---|---|
| `node_id` | 无 | `[a-z0-9_-]+` | `file_monitor` |
| Signal path | `.` | `segment(.segment)*` | `notify.web.download` |
| Pattern ID | `/` | `[namespace/]name` | `msp/multi-round` |
| Tool name | 无 | `[a-z0-9_-]+` | `get_weather` |
| Task ID | 无 | 实现自定 | `task-3f2a…` |

**路径分层遵循「域优先」**：`<域>.<实体>.<动作>`，域在最前（`notify.web.download`，而非 `web.notify.download`）。域是稳定、面向功能的分类；实体是可变、面向实现的来源。域放最前，接收方用 `notify.**` 即可一劳永逸地捕获全部现有与未来通知。

Pattern ID 使用斜杠是**全局命名空间**需要（反向域名前缀），与 Signal path 的点号分层是两个不同概念，**不得**混用。

### 5.4 错误码

错误码取 JSON-RPC 2.0 的约定值，使工具调用子集在语义上可直接映射（见 [interop](interop.md#json-rpc-20-语义对齐)）。

| `code` | 名称 | 本规范中的用途 | 参考实现现状 |
|---|---|---|---|
| `-32600` | 无效请求 | 收到未知 `type` 时回 `error` | ✅ 核心发出（`_dispatch_core` 兜底分支，码为字面量） |
| `-32601` | 方法不存在 | 工具调用指向未注册工具 | 🟡 **核心未发出**：错误以字符串进 `tool_result.payload.error`（`未知工具: X`），不带 `code`；该码目前只出现在 `msp.mcp` 的 JSON-RPC 桥中 |
| `-32602` | 参数无效 | 参数不满足工具声明的 `inputSchema` | 🟡 **核心未发出**：核心不做运行时 schema 校验，参数不符表现为 `TypeError` → `payload.error` |
| `-32603` | 内部错误 | 工具执行中抛出异常 | 🟡 **核心未发出**：异常文本原样进 `payload.error`，不带 `code` |
| `-32000` ~ `-32099` | 实现自定义 | **授权拒绝**已用 `-32000`（见 [security](security.md#3-授权)）；仅当信号带 `reqid` 时回错，广播类静默丢弃；模式层尚未使用 | ✅ 已实现（`-32000`） |

**工具执行失败不在 `tool_result` 内携带 `code`**：它走「错误即值」通道（[request-reply §6.3](patterns/request-reply.md#63-工具侧的失败与错误码归属)）。因此实现方**不得**期待在 `payload` 中读到 `code`；把 `payload.error` 字符串映射回错误码是适配层（如 JSON-RPC 桥）的职责。

### 5.5 角色能力位

| 能力位 | 含义 | 交换方式 |
|---|---|---|
| `pub` | 本节点会发布信号 | `Manifest.capabilities` |
| `sub` | 本节点会订阅信号 | 同上 |
| `req` | 本节点会调用他人工具 | 同上 |
| `rep` | 本节点会应答他人调用 | 同上 |

能力位是**自述**（「我自称会什么」），与**授权**（「我允许你做什么」）严格分离。授权**不得**依赖对端自报，也**不得**随清单交换（见 [security](security.md#3-授权)）。

### 5.6 默认参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `settle_timeout` | `0.5` s | `start()` / `settle()` 等待在建拨号落地的上界 |
| `call` 超时 | `5.0` s | 未显式指定时 |
| `heartbeat_interval` | `15.0` s | PING 周期 |
| `heartbeat_timeout` | `45.0` s | 超过此值未收到任何消息即判定失联 |
| `connect_backoff` | `5.0` s | 连接失败后的冷却时长 |
| `renew_interval` | `10.0` s | 目录声明租约续期周期 |
| 声明有效期 `stale_after` | 见 [discovery](discovery.md#32-租约与-ttl) | 过期声明被丢弃 |
| `connect_policy` | `eager` | `eager` 发现即连；`lazy` 仅接受入站，按需拨号 |

---

## 6. 与其他协议的关系

| 关系 | 结论 | 页 |
|---|---|---|
| **MCP** | MCP ⊆ MSP：工具调用场景下 MCP 的行为可被行为保持地映射进 MSP；反之不成立 | [interop](interop.md#mcp--msp) |
| **A2A** | A2A 是一个协议栈而非一种模式；MSP 只搬其「任务语义」，落地为 `msp/task` | [patterns/task](patterns/task.md#9-与-a2a-的等价映射) |
| **JSON-RPC 2.0** | 编码层不采用其信封，但在工具调用子集上做**语义对齐**；互通靠可选桥，不改核心 | [interop](interop.md#json-rpc-20-语义对齐) |

---

## 7. 一致性

一个实现声称「符合 MSP 修订 `2026-10-10`」，**必须**满足：

1. **报文形态**：能解析并生成 `Signal` 信封（[base-protocol §2](base-protocol.md#2-signal-信封)），含未知字段的宽容处理。
2. **握手**：实现 HELLO/ACK 交换与能力清单交换（[base-protocol §4](base-protocol.md#4-连接生命周期)）。
3. **核心模式**：实现 `msp/request-reply` 与 `msp/publish-subscribe` 的全部条文。
4. **路由**：按 `Signal.pattern` 路由，未知模式**不得**导致连接中断（[patterns §3](patterns.md#3-路由契约)）。
5. **宽容读取**：对未识别的字段、信号类型、内容块类型、模式 ID，**不得**视为协议错误而断开连接（[base-protocol §2.3](base-protocol.md#23-宽容读取)）。
6. **可选的扩展**：可扩展模式、传输后端、发现机制、能力面与安全机制均为**可选**；不实现是合规的，实现则**必须**符合对应条文。

**互通的最低公分母**是：一条 TCP 连接 + `Signal` 信封 + `msp/request-reply`。任何两个只满足这一点的实现都能互相调用工具。

---

## 8. 参与演进

规范变更走「**先改唯一权威源、再改散文、最后改实现**」的顺序，并在 [修订历史](#1-修订历史) 留痕：

1. **改 [`schema/<修订>/msp.yaml`](https://github.com/hxh230802/MSP/blob/master/schema/2026-10-10/msp.yaml)** —— 数据模型的唯一权威源：字段名、类型、必填性、默认值、约束，以及 `Signal.type`（+`pattern`）→ payload 的绑定；
2. 在对应页面提出条文（含状态标记）——散文负责解释「为什么这样设计」，**不得**再抄一份字段清单（那正是漂移的来源）；
3. 重新生成 `schema/<修订>/msp.schema.json`（`tools/gen_schema.py`），并让 `tools/check_schema_drift.py` 的**三方对账**通过：权威源 ↔ 参考实现 ↔ 散文页；
4. 更新参考实现与测试；
5. 新增修订行，标注是追加还是破坏性变更。

> **为什么先改 YAML**：字段只在 YAML 里定义一次，`msp.schema.json`、本目录各页的字段表与 `tests/test_schema_source.py` 都由它派生或与它对账。MCP 用同样的形态（`schema.ts` 为源、JSON Schema 与文档为产物），只换了个宿主语言。

新增通讯模式**不需要**修订本规范的核心页：模式是可选扩展，只需在 [patterns.md](patterns.md#8-模式登记) 登记并在 [interop](interop.md) 说明与他者的映射关系。
