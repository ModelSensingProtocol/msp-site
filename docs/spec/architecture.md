# 架构 — Architecture

> **协议修订** `2026-10-10` ｜ **状态** ✅ 已实现（QUIC / DHT 扩展点为 🔵 规划中）
>
> 本页定义 MSP 的整体形状：**分层与层间契约**、**四个核心概念**、**三个正交扩展轴**、**角色与 Preset**、**能力协商**、**连接策略与启动时序**、**Peer 视图**与**扩展钩子**。它对应 MCP 规范的 *Architecture* 页——先讲清部件与边界，再进入报文细节。

---

## 1. 概述

MSP 的架构由一句话决定：**把「交流方式」从协议核心里赶出去，做成可插拔的模式。**

由此产生五层结构，以及四条**窄到只有一个数据结构**的层间契约：

```text
┌─────────────────────────────────────────────────────────────────┐
│ 应用层      MSPNode                                             │
│   @node.tool · @node.signal_source · @node.on · node.publish    │
│   node.call · node.ensure_connected · node.register_pattern     │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ 模式层      PatternHandler（pattern_id / fallback_to /          │
│             conflicts_with / on_signal / install_api）          │
│   Request-Reply · PubSub · MultiRound · Task                    │
│   Streaming · CallbackPush · AsyncPolling         （🔵 规划中）  │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ 协议层      MSPProtocol                                         │
│   核心信号 HELLO·ACK·PING·PONG·ERROR                            │
│   路由     _dispatch → 命中 pattern 交 handler，否则核心分发      │
│   连接管理 connections · peer_manifests · pending_calls         │
│   编解码   _encode(Signal) → bytes · _decode(bytes) → dict      │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ 传输层      TransportRegistry                                   │
│   TCPTransport · WebSocketTransport · UDSTransport              │
│   QUICTransport                                   （🔵 规划中）  │
│   统一接口 Connection.send(bytes) / receive() → bytes           │
│   只收发字节 · 不感知消息语义                                     │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ 发现层 / 宣告层（两者正交，自由组合）                              │
│   Discovery：DirectoryScan · ManualConnect ·（🔵）DHT            │
│   Presence ：DirectoryWrite · ManualAdvertise ·（🔵）DHT         │
│   统一契约 Endpoint = { transport_type, address, node_id }       │
└─────────────────────────────────────────────────────────────────┘
```

### 层间契约

| 边界 | 契约 | 效果 |
|---|---|---|
| 发现 → 传输 | 只传 `Endpoint` | 换发现机制不改传输 |
| 传输 → 协议 | 只传 `bytes` | 加传输后端不改协议 |
| 协议 → 模式 | 只传 `Signal` + 按 `pattern` 路由 | 加通讯模式不改协议 |
| 模式 → 应用 | 通过 `install_api(node)` 注入语法糖 | 加模式不改 `MSPNode` |

**这四条契约是 MSP「每层皆可扩展」的全部机制。** 每一层都只依赖下层的**一个数据结构**，不认识下层的实现细节。

### 各层**不得**做的事

| 层 | **不得** |
|---|---|
| 传输层 | 解析报文内容、理解 `type`／`pattern`、做重连或去重 |
| 协议层 | 理解任何具体模式的语义、认识工具名或路径含义、内置 TLS／认证／授权逻辑 |
| 模式层 | 绕过协议层直接收发字节、修改 `Signal` 信封字段语义 |
| 发现层 | 建立连接、假设对端一定可达（发现只产出候选端点） |

协议层**不认识工具、路径、任务**，只认识 `Signal` 与 `pattern` —— 这是「协议核心极小」能够成立的原因，也是第三方实现只需理解 [base-protocol.md](base-protocol.md) 与 [patterns.md §3](patterns.md#3-路由契约) 即可互通的原因。

---

## 2. 四个核心概念

| 概念 | 定义 | 规范出处 |
|---|---|---|
| **节点** Node | 通讯参与方，具有全局唯一 `node_id`。**不预设**客户端／服务端角色——一个节点**可以**同时发布、订阅、提供工具、调用工具 | [§5](#5-角色与-preset) |
| **信号** Signal | 通讯的最小数据原子。所有交互的统一载体，仅以 `type` 区分 | [base-protocol.md §2](base-protocol.md#2-signal-信封) |
| **端点** Endpoint | 节点的传输身份 `{transport_type, address, node_id}`。发现层产出它，传输层据它建连 | [discovery.md](discovery.md#51-endpoint) |
| **路径** Path | 信号的逻辑地址，点号分段（`notify.web.download`），支持 `*` / `**` 通配 | [publish-subscribe.md](patterns/publish-subscribe.md#3-路径语法) |

三条设计原则是这四个概念的直接推论，也是本规范的解读框架：

> **Everything is a node.** 工具、模型、传感器、宿主程序、远端服务，都是节点，地位对等。
> **Everything is a signal.** 握手、订阅、工具调用、任务、心跳，都是信号，只有 `type` 不同。
> **Every layer is extensible.** 发现、宣告、传输、模式，每一层都可插拔，不触碰核心。

---

## 3. 三个正交扩展轴

「扩展」在 MSP 里是三件互不相关的事，**各自独立**——换一种发现机制不改协议层，加一种传输后端不改协议层，加一种通讯模式同样不改协议层：

| 轴 | 扩展单位 | 接入方式 | 参考实现代价 |
|---|---|---|---|
| **发现 / 宣告** | 一个 `Discovery` / `Presence` 实现 | 注册进 `DISCOVERY_REGISTRY` / `PRESENCE_REGISTRY`，在 Preset 里点名 | 0 行核心改动 |
| **传输** | 一个 `Transport` 实现 | 注册进 `TRANSPORT_REGISTRY`，在 Preset 里点名 | 0 行核心改动 |
| **模式** | 一个 `PatternHandler` 实现 | 注册进 `PATTERN_REGISTRY`，在 Preset 里点名；协议层按 `pattern` 查表路由 | 0 行核心改动 |

**「核心改动 ≤ 60 行」是这套架构的验收标准。** 参考实现中，让模式层得以零改动扩展的全部代价，是协议层里的**一次查表**（[patterns.md §3](patterns.md#3-路由契约)）；让任意层都能注入语法糖的全部代价，是 `_install_layer_api` 的约 4 行（[§11](#11-扩展钩子-install_api)）。

新增一种通讯模式**不需要**修订本规范的核心页：模式是可选扩展，只需在 [patterns.md §7](patterns.md#8-模式登记) 登记，并说明与他者的映射关系。

---

## 4. 发现与宣告：两个正交接口

发现与宣告是**两个方向相反、彼此独立**的接口，**不得**被合并成一个「节点管理」抽象：

| 接口 | 回答的问题 | 产物 / 输入 |
|---|---|---|
| **Discovery** | 「我怎么找到别人」 | 产出 `Endpoint` |
| **Presence** | 「别人怎么找到我」 | 消费 `Endpoint`，写进某个共享通道 |

```python
class Discovery(ABC):
    def list_endpoints(self) -> list[Endpoint]: ...        # 初始全量扫描
    def watch(self, on_add, on_remove) -> None: ...        # 动态产出端点

class Presence(ABC):
    def announce(self, endpoint: Endpoint) -> None: ...     # 宣告自己
    def withdraw(self, node_id: str) -> None: ...           # 撤销宣告
    def update(self, endpoint: Endpoint) -> None: ...       # 更新端点
```

**正交的含义**：一个节点**可以**只发现不宣告（观察者）、只宣告不发现（纯服务方）、或两者都做（完全对等）。这四种组合直接对应 [§5](#5-角色与-preset) 的预设表。

两层的统一契约是 **`Endpoint`**：`transport_type` 决定用哪个传输后端，`address` 的具体结构随后端变化（[transports.md](transports.md#32-地址格式)），`node_id` 在手动发现时**可以**为空（尚未知对端身份）。

**发现只产出候选，不保证可达。** 一个端点出现在共享目录里**不**意味着对端在监听、**不**意味着握手会成功。可达性是连接时才知道的事实。因此发现层**不得**触发任何阻塞行为，拨号必须异步（[§8](#8-连接策略与-settle)）。

详细条文（共享目录声明文件格式、事件 + 轮询双机制、租约 TTL、HTTP 注册表、DHT）见 [discovery.md](discovery.md)。

---

## 5. 角色与 Preset

### 5.1 角色是组合，不是硬编码

一个节点启用哪些发现、宣告、传输与模式，取决于它的角色。MSP 用 **`Preset`** 声明这四类资源：

| 字段 | 含义 |
|---|---|
| `discovery` | 启用哪些发现机制 |
| `presence` | 启用哪些宣告机制 |
| `transports` | 启用哪些传输后端 |
| `patterns` | 启用哪些通讯模式 |
| `primary_transport` | 对外宣告哪个后端（决定 `Endpoint.transport_type`） |
| `capabilities` | 角色能力位（`pub` / `sub` / `req` / `rep`） |
| `connect_policy` | 发现时的连接策略：`eager`（发现即连）/ `lazy`（只接受，按需拨号） |

**角色不是协议机制。** 经典协议里的「客户端／服务端」在 MSP 里只是上表在不同维度上的取值组合：

| 经典角色 | 在 MSP 里是 |
|---|---|
| MCP 服务端 | 宣告工具、不发现对端，仅启用 `msp/request-reply`（≈ `CLOUD_SERVICE`） |
| MCP 客户端 | 发现工具节点、不宣告工具，仅启用 `msp/request-reply` |
| A2A 智能体 | 既发现又宣告、既提供也调用工具，启用 `msp/multi-round` / `msp/task`（≈ `FULL_PEER`） |

MCP 的 client／server 是**不对称**的组合（一端只服务、一端只调用），A2A 的 agent 是**对称**的组合。MSP 不预设任何一端，把取值权留给节点本身——因此**一个 MSP 节点可以同时扮演 MCP 服务端、MCP 客户端与 A2A 智能体**，而在角色固化的协议里这需要分别维护三个组件。

### 5.2 内置预设

| 预设 | discovery | presence | transports | patterns | capabilities | connect_policy |
|---|---|---|---|---|---|---|
| `LOCAL_TOOL` | — | directory | tcp | 核心二模式 | `pub` `rep` | lazy |
| `LOCAL_TOOL_ADVANCED` | — | directory | tcp | 核心 + 多轮 + 任务 | `pub` `rep` | lazy |
| `LOCAL_AI` | directory | directory | tcp | 核心 + 多轮 + 任务 | `pub` `sub` `req` `rep` | eager |
| `LOCAL_AI_UDS` | directory | directory | uds | 核心 + 多轮 + 任务 | `pub` `sub` `req` `rep` | eager |
| `CLOUD_SERVICE` | — | directory | tcp | 核心 + 多轮 + 任务 | `pub` `rep` | lazy |
| `OBSERVER` | directory | — | tcp | 发布—订阅 | `sub` | eager |
| `FULL_PEER` | directory | directory | tcp | 核心 + 多轮 + 任务 | `pub` `sub` `req` `rep` | eager |
| `MANUAL_PEER` | manual | manual | websocket | 核心二模式 | `pub` `sub` `req` `rep` | eager |

「核心二模式」= `msp/request-reply` + `msp/publish-subscribe`。

规范条文：

1. 未指定预设时，节点**必须**使用 `FULL_PEER`。
2. `primary_transport` **必须**在 `transports` 中；否则节点启动**必须**失败并报错，**不得**静默降级到其它后端。
3. Preset 中列出的名称**必须**已在对应注册表中注册；未注册即启动失败。
4. 预设**可以**被覆盖：在同一节点上**可以**运行时追加（见 [§5.3](#53-运行时调整)）。
5. `LOCAL_AI_UDS` **仅**在支持 `AF_UNIX` 的平台可用（[transports.md](transports.md#33-uds平台限制权限与残留清理)）。

### 5.3 运行时调整

| 操作 | 效果 |
|---|---|
| `node.register_pattern(pattern_id, metadata=None)` | 声明一个模式：写入 `Manifest.patterns`（与 `pattern_metadata`），若注册表中有对应 handler 则自动实例化并激活；运行中即时推送清单 |
| `node.add_manual_source(...)` | 由手动发现的 `install_api` 注入，运行时动态追加发现源 |

规范条文：`register_pattern` **必须**是幂等的（重复声明不产生副作用）；节点运行中调用时**必须**立即推送清单（[base-protocol.md §4.4](base-protocol.md#44-能力清单交换与更新)）。

---

## 6. 能力协商

### 6.1 握手即协商

能力清单（`Manifest`）在**握手时**交换，因此双方**在建连前**就知道彼此支持哪些通讯模式、提供哪些工具、会发布哪些路径：

```text
   node_a                                         node_b
     │  ── hello {manifest: {patterns: [...],      │
     │            tools: [...], signals: [...]}} ─► │
     │                                             │  比对 patterns：
     │                                             │  · 交集 = 可用的交流方式
     │                                             │  · 缺失 = 需要降级或放弃
     │  ◄──────── ack {manifest: {...}} ────────── │
     │  同样比对                                    │
     ▼                                             ▼
```

**这比「先连接、再试探」更高效**，也为模式降级（`fallback_to`）提供了信息基础：调用方在发出请求前就能判断「对方是否支持 `msp/multi-round`」，而不必发出去等一个失败。

规范条文：

1. 双方**必须**在握手报文中携带**完整**的能力清单（不是增量）。
2. 清单**必须**包含该节点已启用的全部模式 ID（`patterns`）。
3. 节点**不得**在未宣告某模式的情况下使用该模式的信号类型。收到此类信号时按宽容读取处理（[base-protocol.md §2.3](base-protocol.md#23-宽容读取)）。
4. 清单**可以**包含尚未实现的能力声明——但这会使对端「看到许诺但用不了」。实现**应当**只宣告自己真正实现的能力（[capabilities.md §现状](capabilities.md)对当前实现正是此状态）。

### 6.2 能力位与授权是两回事

| | 存放位置 | 语义 | 可交换 |
|---|---|---|---|
| **能力位** `pub` / `sub` / `req` / `rep` | `Manifest.capabilities` | 「我自称会什么」 | ✅ 随清单交换 |
| **授权** `grants` | 本地 `Preset` | 「我允许你做什么」 | ❌ **不得**交换 |

**授权绝不依赖对端自报。** 一个节点宣称自己有 `req` 能力，**不**意味着别人必须接受它的调用。详见 [security.md §授权](security.md#3-授权)。

### 6.3 模式元数据

`Manifest.pattern_metadata` 允许模式挂载**自己定义**的元数据（键为 `pattern_id`）：

```json
"patternMetadata": {
  "msp/task": { "name": "...", "skills": [ ... ] }
}
```

规范条文：Manifest 核心**不感知、不校验**该字段的内容，原样随清单交换。格式由各模式自己定义（`msp/task` 用它承载 A2A 的 Agent Card 投影，见 [task.md](patterns/task.md#62-agent-card-投影)）。

---

## 7. `Peer`：邻居的只读视图

一个邻居的信息天然散落在多处：`Endpoint` 在节点层，`Connection` 与能力清单在协议层。`Peer` 把它们聚合为一个对象。

**`Peer` 是视图而非存储**：不持有任何状态，每次属性访问都从所属节点实时读取。对端更新清单或断开后，**同一个 `Peer` 对象立即反映最新状态**——没有副本要同步。因此 `Peer` 对象可以随意创建和丢弃。

| 成员 | 类型 | 未发现 / 未连接时 |
|---|---|---|
| `endpoint` | `Endpoint \| None` | `None` |
| `manifest` | `dict \| None`（**浅拷贝**） | `None` |
| `connection` | `Connection \| None` | `None` |
| `is_discovered` | bool | `False` |
| `is_connected` | bool | `False` |
| `tools()` / `signals()` / `patterns()` | `list` | `[]` |
| `supports(pattern_id)` | bool | `False` |
| `has_tool(name)` / `has_signal(path)` | bool | `False` |

规范条文：

1. **只查询，不操作。** `call` 仍放在节点上；`publish` 是广播、不面向单个对端，故**不属于** `Peer`。
2. **宽容未知对端。** 查询未知 `peer_id` **必须**返回 `None` / `[]` / `False`，**不得**抛异常。
3. `manifest` **必须**返回副本，修改返回值**不得**污染节点内部状态。
4. 视图的枚举 API：`node.peers()`（全部已知邻居，含未连接）、`node.connected_peers()`（仅已连接），均按 `node_id` 排序。

---

## 8. 连接策略与 `settle`

### 8.1 `connect_policy`

| 策略 | 发现时的行为 | 连接时机 |
|---|---|---|
| `eager` | 发现即异步拨号 | 发现时 |
| `lazy` | 只记入邻居表 | 首次 `call()` / `fetch_manifest()` 时（`ensure_connected`） |

**两种策略都必须保证同一件事**：任何需要连接的用户 API **必须**在内部调用 `ensure_connected(peer_id)` 兜底，使「邻居已知但未连接」不会变成调用方的负担。

**并发建连必须去重**：每个对端一把连接锁，避免多个线程同时触发重复拨号（重复连接会被对端去重，但代价是一次无谓的握手与冷却记录，见 [base-protocol.md §4.3](base-protocol.md#43-重复连接去重)）。

### 8.2 对等端故障：错误即值、软冷却、不删邻居

对端随时可能不可达（崩溃、重启、断网）。「对端没了」是**常态，不是异常**：

| 机制 | 解决什么 | 规定 |
|---|---|---|
| **错误即值** | 对端没了不该打断调用方程序 | `call()` 对不可达／未知／超时／中途断连一律返回 `ToolResult(error=...)`，**不得**抛异常 |
| **疑似死亡 = 软冷却** | 区分「暂时连不上」与「真死了」 | 连接失败记 `now + connect_backoff`，冷却期内快速失败不再重拨；成功即清除 |
| **不删邻居** | 硬删会让只是暂时失败的对端永久消失 | 连接失败**不得**从邻居表移除该对端 |
| **目录租约 + TTL = 硬清理** | 自动清理真正死掉的节点 | 宣告方周期续租，发现方丢弃过期声明（[discovery.md](discovery.md#32-租约与-ttl)） |

**软标记与硬清理分离**：连接失败是「疑似」，声明过期才是「确认」，两个时间尺度互不干扰。这是 MSP 处理对端故障的核心取舍，任何实现都**应当**保持这一分离，否则会退化成「一次网络抖动就永久失去一个对端」。

### 8.3 启动时序与 `settle`

**问题**：`start()` 里各层的时序是混的——传输监听是同步的，宣告是同步的，**发现也是同步的**（`watch()` 先跑一次全量扫描），但 `eager` 的拨号在后台线程里。于是 `start()` 返回时的状态是「**邻居已知、连接未必在**」：

- 紧接着 `publish()` 会扇出到**空的连接集合**——广播模型下这既不是异常也不是错误码，而是**静默丢失**；
- 紧接着 `call()` 靠 `ensure_connected()` 现场兜底（能连上，但把首次调用的延迟推给调用方）。

对使用者来说，这意味着「`start()` 之后要不要再 sleep 一下」变成了必须靠经验回答的问题。测试里遍地 `wait_until(lambda: "a" in node.connections())` 就是这个问题的外部症状。

**决策**：`start(settle=True, settle_timeout=0.5)` —— 启动完成后等一次「发现驱动的在建拨号全部落地（成功或失败）」，返回是否在超时前稳定；另提供独立的 `node.settle(timeout)`。

```python
node.start()                          # settle=True 默认：返回时发现驱动的拨号已落地
ok = node.start(settle_timeout=1.0)   # 自定义上界；False 表示仍有拨号在飞
node.start(settle=False)              # 纯非阻塞：连接在后台形成
node.settle(0.5)                      # 或单独等待；返回是否在超时前稳定
```

三条性质是**刻意**的：

1. **默认开启**：成功路径上拨号通常几十毫秒落地，`settle` 立即返回，几乎无额外成本；只有连不上的对端才会耗尽超时。默认关等于把这个坑留给每个调用方。
2. **只等待，不发起**：`settle()` **从不**调用 `ensure_connected()`。它等的只是「已经有人在做」的连接。因此 `connect_policy="lazy"` 下它是 **no-op**（没有在建拨号，立即返回 `True`），**绝不会**把 lazy 节点变成 eager——`settle` 与 `connect_policy` 正交。
3. **登记先于起线程**：发现回调**必须**在起拨号线程**之前**同步把该对端计入「在建」集合，线程在 `finally` 里注销并唤醒。若反过来在拨号线程内部登记，`settle` 可能赶在拨号线程被调度之前看到空集合，把「还没开始」误判成「已经稳定」——默认开启的保证就成了假的。

**边界（诚实版本）**：

- **只覆盖发现驱动的拨号**：`call()` / `fetch_manifest()` / `msp/task` 自己发起的建连**不在**计数内。
- **不承诺「连上所有未来节点」**：`start()` 返回之后才 announce 的节点走正常发现路径。
- **超时是上界不是错误**：`False` 只表示仍有拨号在飞，节点照常可用。
- **不做「至少连上 N 个」**：这类要求会把「对端未就绪」升级成启动失败，与「错误即值」的容错取向冲突。需要强保证时，使用方**应当**在 `settle` 之后自行检查 `connections()`。

---

## 9. 启动与停止顺序

`start()` **必须**按以下顺序执行（顺序本身是契约的一部分）：

```text
  1. 传输层 listen_all()            所有后端开始监听
  2. 确定对外端点                    primary_transport → Endpoint
  3. 写入 manifest                   合并 Preset 的模式与能力位 → push_manifest
  4. 宣告层 announce(endpoint)       别人现在可以发现我了
  5. 发现层 watch(on_add, on_remove) 同步跑一次全量扫描 → 邻居入表
  6. 各传输后端启动 accept 循环
  7. 启动全部 signal_source 生成器线程
  8. settle（默认 0.5 s）
```

**第 3 步必须先于第 4 步**：能力清单在**握手时**交换，而握手由对方发起——若宣告先于清单就绪，一个反应快的对端可能在清单写入前拨进来，双方就会交换到一份不完整的能力清单。

`stop()` **必须**逆序执行：撤销宣告 → 停止发现 → 关闭协议层（关闭全部连接、唤醒全部在途请求）→ 关闭传输层。未启动的节点调用 `stop()` **不得**报错（构造期已启动的心跳线程仍需停止）。

---

## 10. 节点 API 面的分工

| 类别 | API | 说明 |
|---|---|---|
| 声明能力 | `declare_signal(path, schema, description)`、`signal_source(path)` / `signal(path)`、`tool(name, description, input_schema)`、`register_pattern(id, metadata)` | 写入 `Manifest` 并推送 |
| 注册回调 | `on(path)`、`on_connected(cb)`、`on_disconnected(cb)` | `path=None` 匹配全部；支持 `*` / `**` |
| 交互 | `publish(path, payload)`、`call(peer, tool, args, timeout)` | 见两个核心模式页 |
| 连接 | `ensure_connected(peer)`、`settle(timeout)`、`start(...)`、`stop()` | |
| 查询 | `neighbors()`、`connections()`、`peer(id)`、`peers()`、`connected_peers()`、`peer_manifest(id)`、`fetch_manifest(id)`、`pattern(id)` | `peer_manifest` 只读缓存、不触发连接；`fetch_manifest` 会触发连接 |

**设计约束**：`node.call()` 是**唯一**会对 `Peer` 做动作的 API，且它留在节点上而不是 `Peer` 上——`Peer` 保持纯查询（[§7](#7-peer邻居的只读视图)）。

---

## 11. 扩展钩子 `install_api`

**问题**：想要「运行时动态添加发现源」这类语法糖，又不愿为核心加一行改动。

**决策**：任意层组件**可以**定义 `install_api(node)`；`MSPNode` 在构造完组件后调用它（若存在），组件即可往 node 上挂便捷方法，而不改核心：

```python
node.start()
node.add_manual_source("http://registry2:8080/nodes")  # 运行时动态加发现源
```

- 通讯模式用它挂 `node.multiround`、`node.task`；
- 手动发现用它挂 `node.add_manual_source(...)`。

**约定**（`PatternHandler.install_api` 的契约，同样适用于 discovery / presence）：

1. 保存 `self._node = node` 作为反引用，供自身公开方法内部使用，避免用户手动传 `protocol` / `node_id`；
2. 挂到 node 上的短名**必须**唯一，**不得**与核心 API 冲突；
3. `install_api` **不应当**做重活（不建立连接、不启动线程）。

**代价**：核心约 4 行（`_install_layer_api`）。「核心零改动」与「语法糖」不可兼得时，选少量核心改动换取任意层注入 API 的能力。

---

## 12. 规范条文汇总

**必须**（MUST）：

1. 层间**必须**只通过四条契约传递数据（`Endpoint` / `bytes` / `Signal`+`pattern` / `install_api`）。
2. 传输层**不得**解析报文内容；协议层**不得**理解具体模式语义。
3. `Discovery` 与 `Presence` **必须**保持为两个独立接口。
4. 未指定 Preset 时**必须**使用 `FULL_PEER`；`primary_transport` **必须**属于 `transports`，否则启动失败。
5. 双方**必须**在握手中交换**完整**能力清单，包含全部已启用模式 ID。
6. 节点**不得**在未宣告某模式的情况下使用该模式的信号类型。
7. 授权**不得**随清单交换，**不得**依赖对端自报。
8. 任何需要连接的用户 API **必须**内部调用 `ensure_connected()` 兜底。
9. 同一对端的并发建连**必须**被去重（每对端一把锁）。
10. `call()` **不得**因对端不可达／超时／断开而抛异常，**必须**返回错误值。
11. 连接失败**不得**从邻居表移除对端；只有声明过期才清理。
12. `start()` **必须**按 [§9](#9-启动与停止顺序) 的顺序执行，清单写入先于宣告。
13. `settle()` **不得**发起连接；`connect_policy="lazy"` 下**必须**是 no-op。
14. 「在建拨号」**必须**在起线程**之前**登记。
15. `Peer` **必须**是纯查询视图，未知对端返回空值而非抛异常。

**应当**（SHOULD）：

16. 实现**应当**只宣告自己真正实现的能力。
17. 新扩展**应当**只改注册表与 Preset，不改核心。
18. 需要强连接保证时，使用方**应当**在 `settle` 之后自行检查 `connections()`。

---

## 13. 已知缺口

| # | 缺口 | 后果 |
|---|---|---|
| 1 | 无「网络就绪」的完整承诺 | `settle` 只覆盖发现驱动的拨号；`call` / `fetch_manifest` / `msp/task` 发起的建连不计入 |
| 2 | `lazy` 节点不参与 `settle` | 在 lazy 节点上 `settle()` 恒为 `True`，不能用作「已连上对端」的判据 |
| 3 | 发现 `on_remove` 只删邻居表，不断开连接 | 对端撤下宣告后，已建立的连接靠心跳失联才断开（最长 `heartbeat_timeout`） |
| 4 | 无中央注册表的一致性保证 | 多注册表源并存时，同一 `node_id` 的不同端点**可以**同时存在于邻居表（后到者覆盖，见 `_on_endpoint`） |
| 5 | 能力清单无「未实现」标记 | 见 [§6.1 第 4 条](#61-握手即协商)：对端会看到许诺但用不了的条目 |
| 6 | 无拓扑感知 | 广播扇出不做带宽优化，`N` 个对端即 `N` 次发送（这是刻意的取舍，不是缺陷；见 [publish-subscribe.md §安全考量](patterns/publish-subscribe.md#8-安全考量)） |
| 7 | 无节点身份持久化 | `node_id` 由使用方自行保证唯一；协议不提供分配或冲突检测 |

---

## 14. 参考实现映射

| 条文 | 源码 | 符号 |
|---|---|---|
| 五层组装 | `src/msp/core/node.py` | `MSPNode.__init__`、`_activate_pattern`、`_install_layer_api` |
| 注册表 | 同上 | `DISCOVERY_REGISTRY`、`PRESENCE_REGISTRY`、`TRANSPORT_REGISTRY`、`CORE_PATTERNS` |
| 启动 / 停止顺序 | 同上 | `start`、`stop`、`_accept_loop`、`_run_signal_source` |
| 连接策略与冷却 | 同上 | `_on_endpoint`、`ensure_connected`、`_eager_connect`、`_unavailable`、`connect_backoff` |
| `settle` | 同上 | `settle`、`_connecting`、`_settle_cv` |
| 错误即值 | 同上 | `MSPNode.call`、`PeerUnavailable`、`UnknownPeer` |
| Peer 视图 | `src/msp/core/peer.py` | `Peer` 全篇 |
| Preset | `src/msp/core/preset.py` | `Preset` 及 8 个内置预设 |
| 能力清单 | `src/msp/core/manifest.py` | `Manifest`、`set_pattern_metadata` |
| 发现契约 | `src/msp/discovery/base.py` | `Discovery`、`Endpoint` |
| 宣告契约 | `src/msp/presence/base.py` | `Presence` |
| 模式契约 | `src/msp/patterns/base.py` | `PatternHandler` |
| 模式注册表 | `src/msp/patterns/__init__.py` | `PATTERN_REGISTRY` |
| 分层原则的完整论证 | `docs/DESIGN.md` | 全篇 |

---

**另见**：[base-protocol.md](base-protocol.md)（报文层）｜[transports.md](transports.md)｜[discovery.md](discovery.md)｜[patterns.md](patterns.md)｜[security.md](security.md)（信任边界与授权）｜[interop.md](interop.md)（角色映射）
