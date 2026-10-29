# 发现与宣告 — Discovery and Presence

| | |
|---|---|
| **协议修订** | `2026-10-10` |
| **状态标记** | ✅ 已实现（共享目录、手动注册表）；🔵 规划中（DHT） |
| **本页定义** | `Discovery` 与 `Presence` 两个正交接口的契约、`Endpoint` 的结构、共享目录声明文件的精确格式与租约语义、手动注册表（文件 / HTTP）的报文形态与轮询规则、运行时注入发现源的钩子，以及 DHT 的完整规划条文。 |

## 1. 概述

发现层回答「我怎么找到别人」，宣告层回答「别人怎么找到我」。两者是**两个正交接口**，不是一件事的两半：一个节点可以只有发现（旁观者），也可以只有宣告（只提供能力、不主动找别人），也可以两者都有。

| 接口 | 输入 | 输出 | 参考实现 |
|---|---|---|---|
| `Discovery` | 共享通道（目录 / 注册表 / DHT） | `Endpoint` | [directory.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/directory.py) `DirectoryScan`、[manual.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/manual.py) `ManualConnect` |
| `Presence` | `Endpoint` | 共享通道里的一条声明 | [directory.py](https://github.com/hxh230802/MSP/blob/master/src/msp/presence/directory.py) `DirectoryWrite`、[manual.py](https://github.com/hxh230802/MSP/blob/master/src/msp/presence/manual.py) `ManualAdvertise` |

两者的公共数据单位是 `Endpoint`：发现产出它，宣告消费它，传输层（见 [transports.md](./transports.md)）按它的 `transport_type` 选后端。节点层（[core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py)）只依赖这两个接口，不感知具体机制。

| 组成 | 参考实现键 | 状态 |
|---|---|---|
| 共享目录发现 | `directory` / `DirectoryScan` | ✅ 已实现 |
| 共享目录宣告 | `directory` / `DirectoryWrite` | ✅ 已实现 |
| 手动注册表发现 | `manual` / `ManualConnect` | ✅ 已实现 |
| 手动注册表宣告 | `manual` / `ManualAdvertise` | ✅ 已实现 |
| DHT 发现 + 宣告 | `dht`（规划） | 🔵 规划中 |

## 2. 契约

### 2.1 `Discovery`

```
list_endpoints() -> list[Endpoint]
watch(on_add: Callable[[Endpoint], None],
      on_remove: Callable[[str], None] | None = None) -> None
stop() -> None
```

- `list_endpoints()` **必须**返回当前已知的全部端点，用于启动时的初始快照；**不得**因为某一条声明损坏而整体失败（跳过坏条目即可）。
- `watch(on_add, on_remove)` **必须**在返回前完成至少一次全量扫描，使调用方在 `watch()` 返回时已能看到既有邻居（参考实现先同步 `_full_scan()` / `_scan()`，再起后台线程）。
- `on_add` **必须**在「发现新端点」与「已发现端点的声明发生变化」两种情况下被调用；`on_remove` 的参数**必须**是 `node_id` 字符串，**不得**是 `Endpoint`。
- `on_remove=None` **必须**被容忍；发现源**不得**把本节点自己当作邻居（`self_node_id` 对应的声明**必须**被跳过）。
- 回调**可以**在任意线程被调用（文件事件线程、轮询线程），实现**不得**假设它运行在调用 `watch()` 的线程上；回调方**应当**把耗时工作移出回调（参考实现的 `node._on_endpoint` 自己起拨号线程）。
- `stop()` **必须**幂等，**应当**在一个轮询周期内返回，且**不得**在返回后再触发新回调。
- 抽象基类只声明了 `list_endpoints` 与 `watch`；`stop()` 是**约定方法**（两个已实现机制都提供，`MSPNode.stop()` 以鸭子类型调用），见 §9-12。

### 2.2 `Presence`

```
announce(endpoint: Endpoint) -> None
withdraw(node_id: str) -> None
update(endpoint: Endpoint) -> None      # 默认实现 = withdraw + announce
```

- `announce` **必须**要求 `endpoint.node_id` 非空。
- `withdraw(node_id)` **必须**幂等：声明不存在时不报错（参考实现吞掉 `FileNotFoundError`）。
- `update` **可以**被覆写为更高效的增量更新；两个已实现机制都覆写为「直接覆写」，**不**先删后写。
- 宣告**不得**产出或修改 `Endpoint` 的语义（**不**得补全 `node_id`、**不**得改写 `address`），只做序列化与写入；**不得**读取共享通道里其他节点的声明——读取是 `Discovery` 的职责。
- `announce` 失败**必须**显式抛出（宣告应 fail-fast）：声明写不进去意味着本节点不可被发现，静默失败会让故障难以定位。

### 2.3 两个接口的正交性

| 组合 | 含义 | 预设示例 |
|---|---|---|
| 只有 `Discovery` | 只找别人、不宣告自己 | `OBSERVER`（只订阅信号） |
| 只有 `Presence` | 只被找到、不主动找别人（accept-only） | `LOCAL_TOOL`、`CLOUD_SERVICE` |
| 两者都有 | 全对等 | `FULL_PEER`、`LOCAL_AI`、`MANUAL_PEER` |

一个节点**可以**启用多个发现机制与多个宣告机制（`Preset.discovery` / `Preset.presence` 是集合）。多个发现源指向同一个 `node_id` 时，**最后被处理的源生效**（参考实现按源顺序覆盖字典），实现**应当**在文档中说明该优先级。

`DirectoryScan` 的构造函数会主动创建 `nodes_dir`：纯扫描节点（无宣告层）也需要目录存在，否则文件事件监听无法挂载。

### 2.4 运行时注入发现源（`install_api`）

任意层组件**可以**定义 `install_api(node)`；`MSPNode` 在构造完该组件后立即调用它（若存在），组件即可往节点上挂便捷方法，而无需改动核心。

- 唯一实现该钩子的发现组件是 `ManualConnect`：它挂上

```
node.add_manual_source(source: str) -> None
```

- `source` 的取值规则与构造参数相同（文件路径 / `file://` / `http(s)://`，见 §3.3）；该调用**必须**在 `start()` 之前与之后都能工作：`start()` 之前调用只登记，`watch()` 时统一扫描；`start()` 之后调用**必须**立即追加扫描一次，失败**应当**只记日志而不中断节点。
- 参考实现中 `DirectoryScan` / `DirectoryWrite` / `ManualAdvertise` **未**实现 `install_api`（见 §9-12）。

## 3. 报文与格式

### 3.1 共享目录声明文件

每个节点把自己的声明写成「目录里一个文件」，其他节点扫描该目录。这是本机场景的零配置机制。

- **存放位置**：`nodes_dir`，默认 `~/.msp/nodes`（构造时 `os.path.expanduser`）。
- **文件名规则**：`{self_node_id}.json`——文件名取**宣告方自己的** node_id，与 `announce(endpoint)` 传入的 `endpoint.node_id` 无关。
- **原子写入**：**必须**先写同目录下的临时文件 `{self_node_id}.json.tmp`，再 `os.replace` 覆盖目标。临时文件名**不得**以 `.json` 结尾，否则扫描方会把半个文件当成声明（扫描与事件过滤都以 `.json` 后缀判定）。
- **文件内容**（逐字，`json.dump(..., ensure_ascii=False, indent=2)`，写入后无换行尾随）：

```json
{
  "node_id": "node_a",
  "endpoint": {
    "transport_type": "tcp",
    "address": {
      "host": "127.0.0.1",
      "port": 45678
    }
  },
  "timestamp": 1712345678.0
}
```

- 字段语义：`node_id` 为宣告方标识；`endpoint.transport_type` / `endpoint.address` 直接来自 `Endpoint`（形态见 [transports.md §3.2](./transports.md#32-地址格式)）；`timestamp` 是 Unix epoch 秒（float），即**租约**（见 §3.2）。
- **读取宽容性**：扫描方**必须**忽略未识别的顶层与嵌套字段（**可以**追加字段而不发新修订）；缺 `node_id`、缺 `endpoint`、JSON 解析失败、文件不可读时**必须**跳过该文件，**不得**因此中断扫描。
- **以谁为准**：`node_id` 以**文件内容**为准（用于产出 `Endpoint` 与去重）；文件**删除**事件只能从**文件名**推断 `node_id`（去掉 `.json` 后缀），因此实现**应当**保持二者一致——手工放置的文件若改名，删除通知可能指向错误标识（见 §9-5）。
- 声明**不得**携带工具/能力清单：能力清单只在握手时交换（见 [base-protocol.md](./base-protocol.md)），发现阶段只暴露端点。

### 3.2 租约与 TTL

`timestamp` 是租约而非元数据：未按时续租的声明**必须**被视为「节点已死」并从发现结果中剔除。

| 参数 | 默认值 | 归属 | 含义 |
|---|---|---|---|
| `renew_interval` | `10.0` s | `DirectoryWrite` | 续租周期（重写 `timestamp` 的间隔） |
| `stale_after` | `30.0` s | `DirectoryScan` | 过期阈值：`now - timestamp > stale_after` 即过期 |
| `poll_interval` | `30.0` s | `DirectoryScan`（`ManualConnect` 为 `5.0` s；`DirectoryWrite` 无此参数） | 周期性全量重扫的间隔 |

规则：

- 过期判定**必须**严格大于：`now - timestamp > stale_after` 才过期，恰好等于阈值时仍有效。
- `timestamp` 缺失（`null` 或字段不存在）时**必须**视为**永不过期**——这是对旧声明与手写声明的向后兼容，使其不参与租约淘汰。
- 过期或损坏的声明在扫描中**必须**等同「不存在」：既**不得**产出 `Endpoint`，**也**必须**触发 `on_remove`（这是「硬清理」：崩溃节点的邻居条目被删除，而不是被标记为可疑）。
- 宣告方**必须**保证 `renew_interval < stale_after`（默认 10 s < 30 s），否则自己的声明会周期性过期。
- 时间**必须**取自本机时钟。跨机的网络文件系统上，宣告方与扫描方的时钟偏差会直接表现为误判（见 §9-7）。
- 崩溃节点的消失延迟上界是 `stale_after + poll_interval`（默认 60 s）：过期要靠下一次扫描才被发现，事件通道不会通知「声明变旧」。

### 3.3 手动注册表（本地文件 / HTTP）

跨机 / 云端场景不依赖文件事件，而是从一个「共享注册表」读取端点列表。注册表是**单载体多节点**：一个文件或一个 URL 承载多条声明。

**载体选择**（`source` 参数的解析规则，`nodes_dir` 默认为 `~/.msp/nodes`）：

| `source` | 载体 | 说明 |
|---|---|---|
| `None` | 文件 | `{nodes_dir}/manual_peers.json` |
| `file://<path>` | 文件 | 剥掉 `file://` 前缀后再 `expanduser` |
| 裸路径 | 文件 | 直接 `expanduser` |
| `http://…` / `https://…` | HTTP | `base_url = source.rstrip("/")`，两种 scheme 走同一实现 |

**条目格式**（JSON 数组，条目字段与声明文件一致）：

```json
[
  {
    "node_id": "node_a",
    "endpoint": {"transport_type": "tcp", "address": {"host": "127.0.0.1", "port": 45678}},
    "timestamp": 1712345678.0
  }
]
```

- 文件载体读取：文件不存在、JSON 非法、无读权限或顶层不是数组时**必须**返回空列表，**不得**抛异常。
- 文件载体写入：**必须**「读—改—写」并原子替换（同目录 `{path}.tmp` + `os.replace`），**不得**就地追加。
- `upsert(entry)` **必须**按 `node_id` 替换已有条目（存在时替换、不存在时追加）；`remove(node_id)` **必须**移除该条目的全部出现。一个 `node_id` 在注册表中**应当**至多出现一次。
- 文件载体的 `timestamp` **当前不参与任何过期判定**：`ManualConnect` 只按条目内容 hash 去重，从不读 `timestamp`。因此条目**不会**自动过期，宣告方若不 `withdraw`，僵尸条目会永久残留（见 §9-8）。

**HTTP 注册表报文**（实现自定的部分已标注）：

| 操作 | 请求 | 期望响应 |
|---|---|---|
| 读取全部条目 | `GET {base_url}` | 2xx + JSON 数组（**必须**是数组；非数组或解析失败视为空） |
| 上报 / 更新 | `PUT {base_url}/{node_id}`，`Content-Type: application/json`，body 为**整条条目** JSON | 任意 2xx；响应体被忽略 |
| 撤销 | `DELETE {base_url}/{node_id}` | 任意 2xx；响应体被忽略 |

- 超时**必须**有界（参考实现三处均为 5 s）；**不得**无限等待。`node_id` **不**做 URL 编码，其字符集受索引约束为 `[a-z0-9_-]+`，因此可安全直接拼进路径。
- 读取失败**必须**降级为空结果（网络抖动不应让发现层崩溃）；上报与撤销失败**必须**抛出（由 `urllib` 在 4xx/5xx 时抛 `HTTPError`）。
- **实现自定**（源码未规定）：鉴权方式（请求中**没有**任何认证头）、并发控制（**没有** `ETag` / `If-Match`，两个节点同时 upsert 存在丢失更新）、分页与增量拉取（每次全量 GET）、错误响应体格式、`POST` 语义、缓存头、TLS 证书校验策略（使用 `urllib` 默认上下文）。

### 3.4 DHT 记录（🔵 规划中）

**实现者可以不实现，但一旦实现**必须**符合本条。**

- **定位**：去中心化的广域发现，替代集中式 HTTP 注册表（注册表只能是单点）。DHT 同时充当发现与宣告通道：宣告方 `put` 记录，发现方 `get` 记录。
- **键的设计**：记录键**必须**是 `SHA-256(UTF-8("msp/dht/1:" + node_id))`（32 字节摘要，直接作为 Kademlia 键空间中的 ID）。**不得**用明文 `node_id` 当键——那会让整张表可按名称枚举。
- **记录形态**（前三个字段与共享目录声明**逐字相同**，复用同一解析器与 `Endpoint` 映射）：

```json
{
  "node_id": "node_a",
  "endpoint": {"transport_type": "quic", "address": {"host": "203.0.113.7", "port": 4433}},
  "timestamp": 1712345678.0,
  "expires_at": 1712349278.0,
  "public_key": "<base64(Ed25519 公钥, 32 字节)>",
  "signature": "<base64(Ed25519 签名)>"
}
```

- `expires_at` **必须**满足 `timestamp < expires_at <= timestamp + TTL`；TTL **应当**在 300–3600 s 之间。
- `signature` **必须**由 `public_key` 对「`node_id` / `endpoint` / `timestamp` / `expires_at` 四字段的规范化 JSON」签名，规范化规则与去重一致：`json.dumps(..., sort_keys=True)` 且无多余空白，UTF-8 编码；**不得**把 `signature` 自身纳入签名范围。
- **注册流程**：宣告方对 `record_key` 执行 `put`，副本数 `k = 20`；每 `renew_interval`（或 TTL 的 1/3，取较小者）重新发布一次；`withdraw` 时对最近节点发 `delete`。中间节点**必须**先验签再存储或转发，**不得**转发未签名记录。
- **查找流程**：请求方对 `record_key` 执行 `get`，**应当**采用迭代式查找（并行 α = 3 条路径），得到记录集合后逐条验签与检查 `expires_at`，通过者映射为 `Endpoint` 并经 `on_add` 上报。结果**应当**缓存 `min(TTL, 60 s)`，**不得**每个 `poll_interval` 都打全网。
- **失效与租约**：`expires_at <= now` 的记录**必须**被丢弃并触发 `on_remove(node_id)`；存储节点**不得**在 `expires_at` 之后继续服务该记录。重发布频率低于 TTL 会造成记录提前消失（与目录租约同构的失效语义）。
- **与 `Endpoint` 的映射**：`node_id` → `Endpoint.node_id`，`endpoint.transport_type` → `Endpoint.transport_type`，`endpoint.address` → `Endpoint.address`；其余字段（`expires_at` / `public_key` / `signature`）**不得**泄漏进 `Endpoint`。
- **与 Registry 的接入方式**：注册为 `DISCOVERY_REGISTRY["dht"] = DHTDiscovery`、`PRESENCE_REGISTRY["dht"] = DHTAdvertise`；参数经 `config` 透传，例如 `config={"discovery": {"dht": {"bootstrap": [{"host": "h", "port": 6881}], "ttl": 600}}}`。节点在 `Preset.discovery` / `presence` 加入 `"dht"` 即可启用，核心无需改动。单条记录**应当** ≤ 4096 字节，实现**应当**限制单次查找的跳数与并发，避免把发现层变成放大攻击面。

## 4. 消息流

### 4.1 共享目录：announce → scan → dial

```
节点 A（宣告方）              文件系统 ~/.msp/nodes/            节点 B（扫描方）
  | start()                                                       | start()
  |  listen_all() -> 得到 A 的监听地址                             |  listen_all()
  |  Endpoint(A)                                                   |
  |  DirectoryWrite.announce(Endpoint(A))                          |
  |   写 A.json.tmp（json.dump indent=2）                          |
  |   os.replace(A.json.tmp, A.json) ------> [A.json]              |
  |   启动续租线程（每 renew_interval=10 s 重写 timestamp）         |
  |                                                               |  DirectoryScan.watch(on_add, on_remove)
  |                                                               |   1) _full_scan() 同步扫一遍：listdir -> 只看 *.json
  |                                                               |      _read_declaration：坏文件/过期 -> 跳过
  |                                                               |      跳过 self_node_id、缺 node_id、缺 endpoint
  |                                                               |      hash(json.dumps(decl, sort_keys=True)) 去重
  |                                                               |   2) 起事件线程 + poll_loop（poll_interval=30 s）
  |<==== on_add(Endpoint(A)) ===== node._on_endpoint()：          |
  |                               _neighbors["a"] = Endpoint，     |
  |                               connect_policy=eager -> 异步拨号  |
  |<================ TCP / UDS / WebSocket 连接 + HELLO / ACK =====|
  | stop() -> DirectoryWrite.withdraw("a") -> unlink A.json        |
  |                                                               |  事件或轮询发现 A.json 消失
  |                                                               |  -> on_remove("a") -> _neighbors.pop("a")
```

注意两条通道的分工：`watchdog` 文件事件负责**实时**，周期轮询负责**兜底**（看门狗失效、事件丢失、跨文件系统时仍能收敛）。轮询**不得**被省略——它是唯一有保证的发现路径。

### 4.2 租约续期与过期清理

```
t=0    A 写声明，timestamp=T0，续租线程启动
t=10   A 续租 -> timestamp=T10（t=20 再续一次 -> T20）
t=25   A 崩溃（SIGKILL，来不及 withdraw，文件仍在）
t=30   B 扫描：now-T20 = 10，不大于 stale_after(30) -> 仍有效
t=55   B 扫描：now-T20 = 35 > 30 -> _read_declaration 返回 None
       -> A 不在本次 current_nodes 中，而 _known 里仍记着 A
       -> 判定「消失」-> on_remove("a")（硬清理）-> _neighbors.pop("a")
       消失延迟上界 = stale_after + poll_interval（默认 60 s）
```

### 4.3 手动注册表：轮询与上报

```
节点 A（ManualAdvertise）        注册中心（文件 / HTTP）        节点 B（ManualConnect）
  | announce(Ep)                                                  |
  |  PUT /nodes/a {node_id, endpoint, timestamp} ---------------->|  存储 a
  |  （没有续租线程：timestamp 只在 announce/update 时写一次）     |
  |                                                              | 轮询（poll_interval=5 s）：GET /nodes -> [ {...} ]
  |                                                              |  _to_endpoint：跳过自己、校验字段
  |                                                              |  hash(entry) 去重 -> on_add
  |                                                              |  条目在所有源中都消失 -> on_remove
  | stop(): withdraw("a") -> DELETE /nodes/a ------------------->|  删除 a
```

`list_endpoints()` 与轮询共用同一套解析（`_to_endpoint`），因此启动快照与运行期增量不会出现字段校验不一致。

### 4.4 DHT：注册与查找（🔵 规划中）

```
宣告方 A                                            请求方 B
  | key = SHA256("msp/dht/1:a")                        |
  | 签名记录（Ed25519）                                |
  |-- put(key, record) 迭代收敛到 k=20 个最近节点 --->  |  DHT 网络
  |   每 TTL/3 或 renew_interval 重发布                |
  |                                                   |-- get(key) 迭代查找（α=3）-->|
  |                                                   |<-- 记录集合（多副本）--------|
  |                                                   |   逐条验签 + 检查 expires_at -> Endpoint -> on_add
  |                                                   |   缓存 min(TTL, 60 s)
  | withdraw(): delete(key) ------------------------->|
  |                                                   | expires_at 到期 -> on_remove
```

## 5. 数据类型

### 5.1 `Endpoint`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `transport_type` | `str` | 是 | 传输后端标识：`tcp` / `websocket` / `uds` / `quic`（见 [transports.md §3.2](./transports.md#32-地址格式)） |
| `address` | `dict` | 是 | 地址，结构随 `transport_type` 变化 |
| `node_id` | `str \| None` | 否（默认 `None`） | 手动发现时可能还不知道对端身份 |

- 各后端的 `address` 形态：`tcp` → `{"host": str, "port": int}`；`websocket` → `{"url": "ws://host:port/path"}`；`uds` → `{"path": str}`；`quic` → `{"host": str, "port": int, …}`（🔵）。
- **去重键**：`(transport_type, tuple(sorted(address.items())))`——同 `transport_type` + 同 `address` 视为同一端点，与 `node_id` 无关。
- `node_id` 为 `None` 的 `Endpoint` **可以**存在（手工填入的地址），但**不得**由共享目录 / 注册表机制产出（这两种机制都要求声明里带 `node_id`）。
- `address` 的值**应当**可哈希：`address_key()` 本身不会抛错（`sorted` 只比较键），但它的**返回值**在用作 `set` / `dict` 键时，含嵌套 `dict` / `list` 的 `address` 会抛 `TypeError`（见 §9-15）。

### 5.2 发现与宣告的实现参数

| 组件 | 构造参数（默认值） |
|---|---|
| `DirectoryScan` | `self_node_id`（必填）、`nodes_dir="~/.msp/nodes"`、`poll_interval=30.0`、`stale_after=30.0` |
| `DirectoryWrite` | `self_node_id`（必填）、`nodes_dir="~/.msp/nodes"`、`renew_interval=10.0` |
| `ManualConnect` | `self_node_id`（必填）、`nodes_dir="~/.msp/nodes"`、`source=None`、`poll_interval=5.0` |
| `ManualAdvertise` | `self_node_id`（必填）、`nodes_dir="~/.msp/nodes"`、`source=None`（同 `ManualSource` 的解析规则） |

注册表名（`Preset.discovery` / `Preset.presence` 中使用的键）：`DIRECTORY` 机制为 `"directory"`，手动机制为 `"manual"`（`DISCOVERY_REGISTRY` / `PRESENCE_REGISTRY` 的键）。`config` 按层分组透传，例如 `config={"presence": {"manual": {"source": "http://registry:8080/nodes"}}}`。

### 5.3 声明与注册表条目字段

| 字段 | 类型 | 免检规则（发现方） |
|---|---|---|
| `node_id` | `str` | 缺失 / 空 / 等于 `self_node_id` → 跳过 |
| `endpoint` | `dict` | 缺失 → 跳过 |
| `endpoint.transport_type` | `str` | 注册表载体**必须**有（缺失或类型不对时按「声明损坏」逐条跳过，见 §6；不再由传输层报错） |
| `endpoint.address` | `dict` | 同上 |
| `timestamp` | `float`（epoch 秒） | 共享目录：缺失视为永不过期；手动注册表：忽略 |

`timestamp` 在两种机制里的**效力不同**（租约 vs 装饰性字段），实现**不得**把手动注册表的 `timestamp` 当作 TTL。

## 6. 错误处理与边界

| 场景 | 行为 |
|---|---|
| 声明文件不存在 / 无权限 / JSON 非法 | 跳过（视为不存在），**不得**抛出；不触发 `on_remove`（除非它此前在 `_known` 中） |
| 声明缺 `node_id` 或 `endpoint` | 跳过 |
| 声明属于自己 | 跳过，**不得**通知 |
| 声明过期（`now - timestamp > stale_after`） | 视为不存在；若此前已知则触发 `on_remove(node_id)` |
| 轮询扫描抛异常 / 文件事件线程挂载失败 | 轮询记 warning 后继续（**不得**终止轮询线程）；事件线程异常未被捕获（见 §9-13），只剩轮询兜底 |
| `stop()` 被重复调用 / 观察者尚未创建 | 幂等；观察者创建竞态可能导致线程泄漏（见 §9-13） |
| `withdraw` 时声明文件不存在 | 吞掉 `FileNotFoundError`，不报错 |
| 注册表文件顶层不是数组 | 视为空 |
| HTTP `GET` 失败 / 超时 / 返回非 JSON | 视为空结果，不抛出 |
| HTTP `PUT` / `DELETE` 失败（4xx/5xx/网络错误） | 抛出（宣告 fail-fast） |
| 同一 `node_id` 出现在多个源 | 最后一次处理的条目生效；`list_endpoints()` 会返回重复条目，轮询则去重 |
| `add_manual_source` 后立即扫描失败 | 记 warning，不中断节点 |

## 7. 规范条文汇总（MUST/SHOULD 清单）

1. `Discovery.watch()` **必须**在返回前完成一次全量扫描。
2. `on_remove` 的参数**必须**是 `node_id`；**不得**是 `Endpoint`。
3. 发现源**必须**跳过 `self_node_id`；`Discovery.stop()` **必须**幂等且**不得**在返回后触发新回调。
4. `Presence.announce` **必须**要求非空 `node_id`；`withdraw` **必须**幂等。
5. 宣告**不得**读取共享通道中其他节点的声明；发现**不得**写入共享通道。
6. `announce` 失败**必须**显式抛出；发现侧读取失败**必须**降级为「视为不存在」。
7. 声明文件**必须**采用 §3.1 的字段与 `{self_node_id}.json` 命名，并**必须**原子写入；临时文件名**不得**以 `.json` 结尾。
8. 发现方**必须**忽略未知字段；**不得**因单条声明损坏而中断扫描。
9. 续租**必须**满足 `renew_interval < stale_after`（默认 10 s < 30 s）。
10. 过期判定**必须**为 `now - timestamp > stale_after`（严格大于）；缺失 `timestamp` **必须**视为永不过期。
11. 过期声明**必须**触发 `on_remove`（硬清理），**不得**仅标记为可疑。
12. 周期轮询**不得**被省略，它是唯一有保证的发现路径；文件事件只是时延优化。
13. 手动注册表条目**必须**遵循 §3.3 的字段；文件载体写入**必须**原子替换。
14. HTTP `GET` **必须**把「非数组 / 非 2xx / 解析失败」降级为空结果；超时**必须**有界。
15. DHT（🔵）**必须**用哈希键、**必须**验签后才接受或转发记录、`expires_at` 到期**必须**丢弃。
16. 运行时新增的发现源**应当**复用与构造参数相同的 `source` 解析规则。

## 8. 安全考量

- **声明可伪造**：任何能写 `nodes_dir` 的进程都能宣告任意 `node_id`，`node_id` 与进程身份之间**没有**绑定。发现层的信任边界等于「共享通道的可写性」；这与 [security.md](./security.md) 的结论一致：认证不在发现层，而在连接建立之后。
- **目录权限未收口**：`nodes_dir` 以默认 umask 创建，实现**不**显式设置权限。因此同机其他用户可能读到声明——泄漏面只有端点与 `node_id`（不含工具与能力清单，那是握手时才交换的）。UDS 的 `0o600` 是**连接**层的收口，不是声明文件的收口。声明文件还持续暴露「本机有哪些节点在跑」，续租与轮询频率会泄漏节点活动（默认 10 s / 30 s）。
- **HTTP 注册表可投毒**：注册表是明文、无鉴权、无完整性校验的单一信任点，能改注册表就能把发现方引向任意端点。因此在公网使用**必须**配合 TLS 与鉴权（见 §3.3「实现自定」），**不应当**把注册表直接暴露到不可信网络。
- **DHT 的额外威胁**：Sybil / Eclipse（攻击者包住某个键的邻域即可回答伪造的邻居列表）——缓解手段是记录签名 + 多路径查找 + 结果交叉验证；**不得**信任未签名记录。键哈希只隐藏 `node_id` 的明文，记录本体仍包含端点地址，因此 DHT 上的宣告**应当**视为公开信息。UDP 传输**必须**防止放大（响应**不得**大于请求）。
- **拒绝服务面**：发现回调会触发拨号（`connect_policy=eager`），恶意声明可以持续注入新 `node_id` 制造连接尝试与线程。节点层的 `connect_backoff`（默认 5 s）只对已失败的对端起冷却，不限制新标识的数量。

## 9. 已知缺口

1. **原子写入不会被事件通道看见**：`os.replace` 在同一目录内是 rename，Linux 上 `watchdog` 把配对的重命名合并成 `FileMovedEvent` 并派发到 `on_moved`，而事件处理器只实现了 `on_created` / `on_modified` / `on_deleted`。因此**新节点的首次宣告只能等下一次轮询（默认 30 s）才被发现**，事件机制对这一主路径并不生效；`withdraw` 的 unlink 反而能实时触发。手工就地修改（打开既有 `.json` 写入）可以实时触发。
2. **续租会把去重打回原形**：去重键是 `hash(json.dumps(decl, sort_keys=True))`，其中包含每次都变的 `timestamp`。因此续租后每次扫描都会重新触发 `on_add`（默认每 30 s 一次）——幂等依赖节点层的 `_neighbors` 覆盖与协议层「已连接则直接返回」，而不是发现层去重。
3. ~~**续租无法重启**~~ ✅ **已修复**：`DirectoryWrite.withdraw()` 现在复位停止事件与续租线程句柄，再次 `announce` / `update` 会重新启动续租（幂等由 `is_alive()` 保证）。
4. 🟡 **`withdraw` 仍忽略 `node_id` 参数**：路径恒为 `{self_node_id}.json`，传入别的 `node_id` 也会删自己的声明。**已修复的一半**：`announce` 写入的内容恒用 `self_node_id`，因此不再产出「文件名与内容 node_id 不同」的声明（`endpoint.node_id` 不一致时记 warning）。
5. **删除通知以文件名推断身份**：`_handle_file_removed` 直接 `basename[:-5]`，若文件被改名或内容与文件名不一致，`on_remove` 会指向错误的 `node_id`（而新增路径以内容为准）。
6. **硬删邻居 vs 软冷却**：`on_remove` 会**立即**从 `_neighbors` 删除条目（与 [DESIGN.md](/design) 一致：连接失败是软冷却、声明过期才是硬清理）。但连接失败记录的冷却时间戳 `_unavailable` **不**随 `on_remove` 清除，因此「崩溃→快速重启→重新发现」的节点在 `connect_backoff`（5 s）内会先吃到一次快速失败，且该表只增不减。
7. **过期时间尺度偏紧**：`renew_interval=10 s`、`stale_after=30 s`、`poll_interval=30 s`，意味着一次 > 30 s 的 GC 停顿或调度饥饿就会让健康节点被误判为死亡（假阳性），而真死亡的消失延迟上界是 60 s。跨机网络盘场景还叠加时钟偏差问题（租约完全依赖双方本机时钟）。
8. **手动注册表没有过期机制**（**按设计，非缺陷**）：`ManualAdvertise` 不续租、`ManualConnect` 不读 `timestamp`，条目永不自动过期——§3.4 与 §10 明确要求实现**不得**把手动注册表的 `timestamp` 当作 TTL，撤销依赖显式 `withdraw`；宣告方崩溃而未撤销时会留下僵尸端点。
9. **手动注册表无并发控制**：文件载体是读—改—写，两个进程同时 upsert 会丢失更新；HTTP 载体同样无 `ETag`。
10. ~~**文件载体对裸文件名不健壮**~~ ✅ **已修复**：仅当 `dirname` 非空时才 `makedirs`，`source` 为裸文件名时写出正常。
11. **`list_endpoints()` 会返回重复端点**：同一 `node_id` 出现在多个源时按源顺序全部返回，而轮询路径以「最后一个源生效」去重，两条路径的语义不一致。
12. **抽象基类不声明 `stop()` 与 `install_api`**：`Discovery` 只声明 `list_endpoints` / `watch`，`stop()` 与 `install_api(node)` 全靠约定与鸭子类型；`DirectoryScan` / `DirectoryWrite` / `ManualAdvertise` 未实现 `install_api`，因此「运行时动态改宣告目标」目前没有钩子。
13. ~~**事件观察者线程无异常处理且存在 stop 竞态**~~ ✅ **已修复**：观察者的「登记 + 启动」放入 `_lock` 临界区，`stop()` 只可能看到「未登记」（无泄漏）或「已登记且已启动」（停得掉）；`schedule()` 失败降级为 warning（只剩轮询）。修复前 `stop()` 可能漏掉一个已创建的非守护 Observer 线程，导致进程无法退出。
14. **`stop()` 不等待在途扫描**：停止瞬间正在执行的回调仍会到达；`ManualConnect.stop()` 后轮询线程最多再存活 `poll_interval + 5 s`（HTTP 超时）。
15. **`Endpoint.address_key()` 的返回值要求地址值可哈希**：调用它本身不会抛错（`sorted` 只比较互不相同的键），但把返回值用作 `set` / `dict` 键时，`address` 含嵌套 `dict` / `list`（QUIC 的 `bootstrap` 列表式地址）会抛 `TypeError`。该方法当前无调用点，故无实际触发路径。
16. **声明读取无大小上限**：`_read_declaration` 用 `json.load` 整文件读入，畸大的文件会长时间占用扫描线程。
17. **DHT 未实现**：`DISCOVERY_REGISTRY` / `PRESENCE_REGISTRY` 中没有 `dht` 条目。
18. ~~**坏声明让扫描整体失败**~~ ✅ **已修复**：原实现在三处直接下标 `ep_data["transport_type"]`，声明缺字段即抛 `KeyError`，且 `watch()` 的首次全量扫描不在 `try` 内，异常直穿 `node.start()`——**违反 §6「不得因单条声明损坏而整体失败」**。现统一经 `_endpoint_of()` 校验 `node_id` / `endpoint` / `transport_type` / `address` 的存在性与类型，逐条跳过。
19. ~~**坏声明不触发硬清理**~~ ✅ **已修复**：事件通道遇到损坏声明时按「文件已消失」处理，满足 §3.2「损坏或过期的声明**必须**触发 `on_remove`」。
20. ~~**合法 JSON 但非对象 / `timestamp` 非数字**~~ ✅ **已修复**：前者等同损坏（返回 `None`，此前抛 `AttributeError`）；后者按「无租约」处理，与「缺失 `timestamp` 视为永不过期」同口径。
21. ~~**手动注册表的非对象条目**~~ ✅ **已修复**：`ManualSource.read()` 过滤非对象元素，`ManualConnect._to_endpoint()` 校验字段类型；此前 `["x"]` 会让扫描与 `upsert()` 抛 `AttributeError`（同层两路径容错不一致）。
22. ~~**`Presence.announce` 的 node_id 非空 MUST 无实现**~~ ✅ **已修复**：`presence/base.py` 的 `require_node_id()` 在 `DirectoryWrite` / `ManualAdvertise` 的 `announce()` 里 fail-fast（`ValueError`）；此前 `DirectoryWrite` 会写出 `"node_id": null`，`ManualAdvertise` 会静默替换成 `self_node_id`。

## 10. 参考实现映射

| 条文 / 契约 | 源码文件与符号 |
|---|---|
| `Discovery` 抽象接口（`list_endpoints` / `watch`） | [discovery/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/base.py) `Discovery` |
| `Endpoint` 字段与 `address_key()` | [discovery/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/base.py) `Endpoint` |
| `Presence` 抽象接口（`announce` / `withdraw` / `update` 默认实现） | [presence/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/presence/base.py) `Presence` |
| 声明文件路径、`_declaration` 字段、原子写入、续租、withdraw；`_declaration_path` 恒用 `self_node_id` | [presence/directory.py](https://github.com/hxh230802/MSP/blob/master/src/msp/presence/directory.py) `DirectoryWrite` |
| 扫描、事件 + 轮询、hash 去重、过期判定 | [discovery/directory.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/directory.py) `DirectoryScan._full_scan` / `_poll_loop` / `_read_declaration` |
| 事件处理器（只实现 created / modified / deleted）、删除事件以文件名推断 node_id | [discovery/directory.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/directory.py) `_DirectoryHandler` / `_handle_file_removed` |
| 手动发现轮询、`add_source`、`install_api` | [discovery/manual.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/manual.py) `ManualConnect` |
| 手动宣告 upsert / remove | [presence/manual.py](https://github.com/hxh230802/MSP/blob/master/src/msp/presence/manual.py) `ManualAdvertise` |
| `file://` / 裸路径 / `http(s)://` 载体解析、原子写、HTTP `GET` / `PUT` / `DELETE` 与 5 s 超时 | [utils/manual_source.py](https://github.com/hxh230802/MSP/blob/master/src/msp/utils/manual_source.py) `ManualSource` |
| 注册表名与组件实例化、`config` 透传 | [core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `DISCOVERY_REGISTRY` / `PRESENCE_REGISTRY` |
| `install_api` 钩子调用点 | [core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `_install_layer_api` |
| 发现回调、邻居表、`on_remove` 硬删、eager 拨号、软冷却与硬清理的分工 | [core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `_on_endpoint` / `_on_endpoint_removed` / `_eager_connect` / `_unavailable`、[DESIGN.md](/design) |
| 预设中的发现 / 宣告组合 | [core/preset.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/preset.py) `Preset.OBSERVER` / `LOCAL_TOOL` / `MANUAL_PEER` |

相关页面：[transports.md](./transports.md)（`Endpoint` 的消费方）· [base-protocol.md](./base-protocol.md)（握手交换能力清单）· [security.md](./security.md)（信任边界与认证）· [architecture.md](./architecture.md)（分层架构）· [patterns.md](./patterns.md)（`install_api` 的另一类使用者）。
