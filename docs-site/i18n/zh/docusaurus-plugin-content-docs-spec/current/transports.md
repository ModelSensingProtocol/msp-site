# 传输层 — Transports

| | |
|---|---|
| **协议修订** | `2026-10-10` |
| **状态标记** | ✅ 已实现（TCP / WebSocket / UDS）；🔵 规划中（QUIC） |
| **本页定义** | 传输层的字节搬运契约（`Transport` / `Connection` / `ConnectionClosed`）、后端注册与选择（`TransportRegistry`）、各后端的分帧格式与地址格式，以及 QUIC 的完整规划条文。 |

## 1. 概述

传输层是 MSP 的最底层：它**只搬运字节**。它建立连接、收发字节、处理分帧，除此之外什么都不知道——不解析 `Signal`、不参与握手语义、不检查能力清单、不知道对端 `node_id`。这一分工是硬边界：一旦传输层开始理解消息语义，新增后端就要重实现一遍协议逻辑，层的可替换性随之消失（理由见[设计文档](/design)）。

| 角色 | 定义位置 | 职责 |
|---|---|---|
| `Connection` | [base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/base.py) | 一条已建立的连接：`send(bytes)` / `receive() -> bytes` / `close()` |
| `ConnectionClosed` | 同上 | 「这条连接不能再用」的信号 |
| `Transport` | 同上 | 一种传输协议的后端：`listen` / `accept` / `connect` / `close` |
| `TransportRegistry` | [registry.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/registry.py) | 后端表，按 `Endpoint.transport_type` 选择后端 |

| `transport_type` | 实现 | 地址形态 | 状态 |
|---|---|---|---|
| `tcp` | [tcp.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/tcp.py) | `{"host": str, "port": int}` | ✅ 已实现 |
| `websocket` | [websocket.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/websocket.py) | `{"url": "ws://host:port/path"}` | ✅ 已实现 |
| `uds` | [uds.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/uds.py) | `{"path": "/path/to.sock"}` | ✅ 已实现（仅 Linux/macOS） |
| `quic` | 无 | `{"host": str, "port": int, …}`（见 §3.6） | 🔵 规划中 |

传输层与「发现 / 宣告」的关系见 [discovery.md](./discovery.md)：那一层产出 `Endpoint`，本层消费其 `transport_type` 与 `address`。

## 2. 契约

### 2.1 `Connection`

```
send(data: bytes) -> None
receive() -> bytes
close() -> None            # 幂等
```

- `send(data)` **必须**把 `data` 作为**一条完整消息**发出，分帧细节（长度前缀、帧头）由实现处理。
- `receive()` **必须**返回**恰好一条**完整消息的负载，**不得**返回长度前缀或帧头，**不得**把两条相邻消息粘在一起返回。
- `receive()` 是阻塞调用：无数据时**必须**等待，**不得**返回 `b""` 表示「暂无数据」。空字节串 `b""` 是一条**合法消息**（零长负载），不是错误信号。
- 连接不可再用时（对端关闭、本端已关闭、OS 层错误、帧长超限），`send` / `receive` **必须**抛出 `ConnectionClosed`；实现**应当**在抛出前尽力关闭底层 socket。
- `close()` **必须**幂等：重复调用不报错、不抛异常。
- `send` **应当**可被多个线程并发调用（参考实现用 `_send_lock` 保证单条消息的字节不被交错）。`receive()` **不**保证并发安全：**不得**在多个线程中同时 `receive()` 同一条 `Connection`。

### 2.2 `Transport`

```
listen(address: dict) -> dict
accept() -> Connection
connect(address: dict) -> Connection
close() -> None            # 幂等
```

- `listen(address)` **必须**开始监听并返回实际生效的地址，形态固定为：

```json
{
  "transport_type": "tcp",
  "address": {"host": "127.0.0.1", "port": 45678}
}
```

  注意这不是 `Endpoint`：它没有 `node_id`，且外层多一个 `transport_type` 键。节点用法是取 `info["address"]` 去构造 `Endpoint`。
- `listen({})` **必须**可用：`TransportRegistry.listen_all()` 恒以空字典调用 `listen`，因此每个后端**必须**为 `host` / `port` / `path` 定义默认值。返回的地址**应当**与输入不同（`port=0` 时返回内核分配的真实端口）。
- `accept()` **必须**阻塞直到有一条入站连接到达，调用方在独立线程或协程中循环调用它；`listen()` 之前调用**必须**抛 `RuntimeError`。
- `connect(address)` 失败时**必须**抛 `ConnectionError`，**不得**抛 `ConnectionClosed`（前者表示「没连上」，后者表示「连上了又断了」）。连接超时**应当**有默认值（参考实现为 10 s），**不得**无限等待。
- `accept()` **不得**执行 MSP 层握手（HELLO/ACK 属于协议层）。唯一例外是 WebSocket 的 **HTTP Upgrade 握手**——那是传输层自身的帧协商。
- `close()` **必须**幂等并释放监听资源。参考实现**未**规定它是否唤醒另一个线程中阻塞的 `accept()`；**不得**依赖该行为（见 §9）。

### 2.3 `TransportRegistry`

| 方法 | 语义 |
|---|---|
| `register(transport_type, transport)` | 注册后端；同一 `transport_type` 重复注册时后注册者生效 |
| `has` / `get` | 查询是否已注册 / 取后端 |
| `items()` | 迭代 `(transport_type, transport)` |
| `listen_all() -> dict` | 按注册顺序对所有后端调用 `listen({})`，返回 `{transport_type: 监听信息}` |
| `connect(endpoint) -> Connection` | 按 `endpoint.transport_type` 选后端，调用 `transport.connect(endpoint.address)` |
| `close_all() -> None` | 逐个关闭后端；单个后端抛错被吞掉并记 debug 日志，**不得**中断其余后端 |

- **后端选择规则**：`Endpoint.transport_type` **必须**精确匹配 `register` 时使用的键（区分大小写）；无匹配时**必须**抛 `UnsupportedTransport`，错误消息**应当**列出当前已注册的全部类型。
- Registry **不**校验地址与后端是否匹配：`transport_type` 为 `tcp` 而 `address` 缺 `host` 时，错误来自后端（`KeyError`），不是 Registry。
- 节点对外宣告的端点**只有** `Preset.primary_transport` 一个；其余后端照常 `listen`，但地址**不**进任何声明文件。因此「一个节点多后端」当前只在被连接方有意义，对端无从得知次要地址。
- Registry **不**感知消息语义、**不**持有 `Connection`：连接的生命周期归协议层。

## 3. 报文与格式

### 3.1 分帧

TCP 与 UDS 都是字节流，没有消息边界，因此共用同一套长度前缀分帧；UDS 直接复用 `TCPConnection`，与 TCP 逐字节一致。WebSocket 自带帧边界，不使用本节格式（见 §3.5）。

```
 0        1        2        3        4                      4+N
 +--------+--------+--------+--------+----------------------+
 | len[0] | len[1] | len[2] | len[3] |  payload（N = len）  |
 +--------+--------+--------+--------+----------------------+
 |<------- 4 字节大端无符号长度 ---->|<----- N 字节负载 --->|
```

- **字节序**：大端（网络字节序），`len.to_bytes(4, "big")` / `int.from_bytes(header, "big")`。**不得**使用小端。
- **长度语义**：`len` = 负载字节数，**不包含** 4 字节头自身；整帧长度恒为 `4 + len`。
- **上限**：`MAX_MESSAGE_SIZE = 16 * 1024 * 1024`（16 MiB = 16777216 字节）。接收侧读到 `len > 16777216` 时**必须**关闭连接并抛 `ConnectionClosed`（防「对端声明超大长度导致内存耗尽」）。`len == 16777216` 合法。
- **零长帧**：`len == 0` 时接收侧直接返回 `b""`，不再读取负载字节；上层**必须**能接受一条空负载的消息。
- **粘包**：发送侧一次 `sendall(header + payload)`，接收侧按长度切分；先后到达的多个帧依次返回，**不得**合并。
- **半包**：接收侧循环 `recv` 直到凑满所需字节数（`_recv_exact`）。头部不足 4 字节或负载不足 `len` 字节时**必须**继续阻塞等待，**不得**按「已收到的部分」返回。
- **写入互斥**：发送侧加锁，保证一条消息的字节连续写入，不与另一条消息交错。
- **不对称**：上限检查只在接收侧执行。发送侧**不**校验 `len`，超过 16 MiB 的消息会被对端以 `ConnectionClosed` 断开。

### 3.2 地址格式

| `transport_type` | `listen` 输入键（默认值） | `address` 对外形态 | 出站连接要求 |
|---|---|---|---|
| `tcp` | `host`（`"127.0.0.1"`）、`port`（`0`） | `{"host": str, "port": int}` | `host` 与 `port` **必须**存在 |
| `websocket` | `host`（`"127.0.0.1"`）、`port`（`0`）、`path`（`"/msp"`） | `{"url": "ws://<host>:<port><path>"}` | `url` **必须**存在且以 `ws://` 开头 |
| `uds` | `path`（`<tempdir>/msp-<pid>-<8 位十六进制>.sock`） | `{"path": str}` | `path` **必须**存在 |
| `quic` | 见 §3.6 | 见 §3.6 | 见 §3.6 |

TCP 监听参数：建 socket 时设置 `SO_REUSEADDR`，`listen(128)`，监听地址取 `getsockname()` 的实际结果。地址族固定为 `AF_INET`，**不**支持 IPv6 字面量（`::1` 会因族不匹配失败）。WebSocket 监听参数见 §3.4，UDS 见 §3.3。

TCP/UDS 的 `connect` 超时默认 **10 s**，且**不**经 `address` 字典暴露——`TransportRegistry.connect` 只传 `endpoint.address`，调用方**不得**指望通过地址字段调整超时。连接成功后 socket 被设回阻塞模式（读循环需要）。

### 3.3 UDS：平台限制、权限与残留清理

- **平台限制**：Unix Domain Socket 仅 Linux/macOS 可用。Windows 的 CPython **未**暴露 `socket.AF_UNIX`，`listen()` / `connect()` 在进入任何 socket 调用之前就抛 `RuntimeError`（消息指明「Unix Domain Socket 仅 Linux/macOS 可用」并指向改用 TCP）。实现**不得**在无 `AF_UNIX` 的平台静默降级为别的传输：降级会改变声明里的 `transport_type` 与地址形态，对端无从得知。
- **默认 socket 路径规则**：`os.path.join(tempfile.gettempdir(), f"msp-{os.getpid()}-{os.urandom(4).hex()}.sock")`，即 `<tempdir>/msp-<pid>-<8 位十六进制>.sock`；`address` **可以**显式指定 `path`。`listen` 返回 `{"transport_type": "uds", "address": {"path": <实际路径>}}`。地址就是文件系统路径，因此与共享目录发现天然契合（见 [discovery.md](./discovery.md)）。
- **权限**：`bind` 之后**必须** `chmod(path, 0o600)`，使 socket 只对本用户可连。`chmod` 失败被忽略（只读文件系统等场景下无害），但**不得**因此放宽权限。
- **残留 socket 文件清理**：进程崩溃后 socket 文件不会被内核删除，直接 `bind` 会因路径已存在而失败。因此 `listen()` **必须**在 `bind` 之前清理残留：`os.stat(path)` 成功**且** `stat.S_ISSOCK(mode)` 为真时才 `os.unlink(path)`；**不得**删除非 socket 文件（防误删用户数据）。
- **close 语义**：`close()` **必须**幂等；关闭监听 socket 后 unlink 自己记录的路径并清空记录。因此在同一路径上重新监听是常态操作（[test_uds.py](https://github.com/hxh230802/MSP/blob/master/tests/test_uds.py) 覆盖该行为）。
- **分帧**：与 TCP 逐字节相同（§3.1），参考实现直接复用 `TCPConnection`，**不**引入第二套分帧逻辑。
- **连接超时**：`connect` 默认 10 s；`AF_UNIX` 连接通常立即完成，超时只用于兜底。

### 3.4 WebSocket 握手（RFC 6455 子集）

客户端请求（逐字）：

```
GET /msp HTTP/1.1
Host: 127.0.0.1:45678
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: <base64(16 随机字节)>
Sec-WebSocket-Version: 13

```

服务端应答（逐字，`accept = base64(SHA1(key + GUID))`）：

```
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <accept>

```

- 握手魔数 `GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"`。
- 客户端**必须**校验状态行含 ` 101 `，并**必须**校验 `Sec-WebSocket-Accept` 等于自己算出的值；不符时抛 `ConnectionError`。
- 服务端**必须**要求存在 `Sec-WebSocket-Key`，缺失时抛 `ConnectionError`；参考实现**不**校验请求方法与路径，也**不**校验 `Sec-WebSocket-Version`（见 §9）。
- HTTP 头读取上限 **64 KiB**，超出抛 `ConnectionError`；读取中遇 EOF 抛 `ConnectionClosed`。
- 握手时可能多读到首帧字节，实现**必须**缓存这部分字节供随后的 `receive()` 优先消费，**不得**丢弃（否则丢首帧）。

### 3.5 WebSocket 帧

```
 0                   1                   2                   3
 +-+-+-+-+-------+-+-------------+-------------------------------+
 |F|R|R|R|opcode |M| Payload len |  Extended payload length ...  |
 |I|S|S|S| (4b)  |A|     (7b)    |  (16/64b, 仅当 len=126/127)   |
 |N|V|V|V|       |S|             |                               |
 +-+-+-+-+-------+-+-------------+ - - - - - - - - - - - - - - - +
 |  Masking key（4 字节，仅当 MASK=1）  |       Payload data ...   |
 +---------------------------------------------------------------+
```

- 发送侧只发**二进制帧**（`FIN=1`，`opcode=0x2`）。
- 长度编码：`len < 126` 直接写 7 位；`126 <= len < 65536` 写 `126` + 2 字节大端；否则写 `127` + 8 字节大端。
- **掩码**：客户端发出的帧**必须**带掩码（`MASK=1`，4 字节随机 key，负载按 `key[i % 4]` 异或）；服务端发出的帧**必须**不带掩码。接收侧按帧头 `MASK` 位决定是否解掩码。
- **分片**：`FIN=0` 的 `0x1`/`0x2` 帧开启分片缓冲，后续 `opcode=0x0`（continuation）帧追加，直到 `FIN=1` 才把整条消息返回给上层；孤立的 continuation **应当**被忽略。
- **控制帧**在 `receive()` 内部消化、**不得**返回给上层：`0x8`（close）→ 尽力回一个 close 帧后抛 `ConnectionClosed`；`0x9`（ping）→ 原样回 `pong`（`0xA`）后继续读；`0xA`（pong）→ 忽略。未知 opcode **应当**忽略而非断开。
- **上限**：`MAX_MESSAGE_SIZE = 16 * 1024 * 1024`，但校验发生在**单帧**长度上；分片重组后的**总长没有上限**（见 §9）。
- **文本帧**：`0x1` 帧的负载被当作一条消息原样返回（**不**做 UTF-8 校验、**不**转码）；实现**不应当**依赖文本帧语义。
- **与 TCP 的差异**：① 消息边界由帧提供，无需长度前缀；② 有对称的 ping/pong 与 close 帧（TCP/UDS 没有，只能靠上层心跳）；③ 有 HTTP Upgrade 握手与 64 KiB 头上限；④ 服务端与客户端发送行为不对称（掩码）。**共同点**：都是有序可靠的字节流语义，`Connection` 接口完全一致，`receive()` 都不以 `b""` 表示「暂无数据」。

### 3.6 QUIC（🔵 规划中）

**实现者可以不实现，但一旦实现**必须**符合本条。**

- **`transport_type`**：`"quic"`，注册进 `TransportRegistry`（与 [core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) 中预留的 `# "quic": QUICTransport` 一致）。
- **版本 / ALPN**：**必须**使用 QUIC v1（RFC 9000），ALPN 为 `"msp/1"`；**不得**复用 HTTP/3 的 `"h3"`。
- **1-RTT 与 0-RTT**：首次连接**必须**走完整 1-RTT 握手（TLS 1.3）。客户端缓存到有效 session ticket 后**可以**用 **0-RTT early data** 把首条 MSP 消息随 ClientHello 发出。0-RTT 数据**必须**满足幂等要求——**不得**把 `tool_call` 这类有副作用的信号放进 0-RTT，**应当**只放 `hello`。服务端拒绝 0-RTT 时，客户端**必须**回退到 1-RTT 重发，**不得**把「0-RTT 被拒」当作连接失败。
- **地址格式**：

```json
{
  "host": "127.0.0.1",
  "port": 4433,
  "alpn": "msp/1",
  "early_data": false,
  "max_streams": 8
}
```

  | 字段 | 类型 | 默认值 | 语义 |
  |---|---|---|---|
  | `host` | str | `"127.0.0.1"` | 主机 |
  | `port` | int | `0`（listen）；connect 必填 | 端口；`0` 表示动态分配并回填 |
  | `alpn` | str | `"msp/1"` | ALPN 标识；取值不是 `msp/1` 时**必须**拒绝 |
  | `early_data` | bool | `false` | 是否允许 0-RTT |
  | `max_streams` | int | `8` | 本端允许的对端并发双向流上限 |

  未知字段**必须**被忽略（宽容读取），与 [base-protocol.md](./base-protocol.md) 的字段策略一致。
- **分帧与流复用**：一条 `Connection` **必须**绑定**一条**长期存在的双向流，其上复用与 TCP/UDS **逐字节相同**的 4 字节大端长度前缀帧（§3.1），使 `TransportRegistry`、协议层与 `MAX_MESSAGE_SIZE` 全部零改动。并发**可以**通过开新流实现，但**不得**把一条 `send()` 的消息拆分到多条流上——`receive()` 的「恰好一条完整消息」语义不因传输而改变。
- **拥塞控制**：**必须**使用至少与 TCP NewReno 等价的拥塞控制（CUBIC 或 BBR），**不得**无限速发送；流级与连接级流控**必须**同时生效。
- **连接迁移**：连接标识**必须**基于 Connection ID 而非 `(host, port)` 四元组；客户端换网后**应当**继续使用同一连接，**不得**因此丢弃已建立的 MSP 会话状态。
- **与 TCP 的差异**：① 单连接内多流、无队头阻塞（每条流独立重传）；② 加密与认证内建（TLS 1.3 在 QUIC 内部，**不**存在「先明文 Upgrade 再加密」的 WebSocket 式阶段）；③ 支持 0-RTT 与连接迁移；④ 基于 UDP，需显式处理丢包与 MTU（PMTU 探测）；⑤ 服务端**可以**在同一端口同时服务 QUIC 与 TCP（实现自定）。
- **生命周期**：`listen` / `accept` / `connect` / `close` 语义与 `Transport` 契约完全一致（§2.2）；`accept()` 阻塞直到入站连接完成 QUIC 握手。
- **迁移路径**：把 `Preset.transports` 从 `{"tcp"}` 换成 `{"quic"}`（或并存），`primary_transport` 指向 `"quic"`，其余各层无需改动——这正是「传输层只搬字节」的直接收益。

## 4. 消息流

### 4.1 TCP 出站连接与分帧

```
Client (TransportRegistry)                    Server (Transport)
        |                                             |
        |-- connect({"host","port"}) ---------------->|  socket(AF_INET, SOCK_STREAM)
        |   sock.settimeout(10.0)                     |  SO_REUSEADDR + bind + listen(128)
        |   sock.connect((host, port))                |
        |   sock.settimeout(None)                     |
        |<------------------- Connection -------------|  （阻塞 accept() 返回 Connection）
        |                                             |
        |-- send(b"HELLO...") -->[00 00 00 1D][HELLO] |  _recv_exact(4) -> len=29
        |                                             |  _recv_exact(29)  -> payload
        |<-- receive() <---------[00 00 00 1A][ACK..] |
        |-- close() --> shutdown(SHUT_RDWR) + close() |
```

与 WebSocket 的差别：TCP **没有**传输层握手，`accept()` 返回的 `Connection` 立刻可用；MSP 层 HELLO/ACK 随后由协议层完成。

### 4.2 UDS 生命周期（含残留清理）

```
进程 A                                                   进程 B
  | listen({"path": P})                                    |
  |   _require_af_unix()  -> 无 AF_UNIX 则 RuntimeError    |
  |   _unlink_stale(P): stat(P) 是 S_ISSOCK ? unlink(P)    |
  |   bind(P) ; chmod(P, 0o600) ; listen(128)              |
  |   返回 {"transport_type":"uds","address":{"path":P}}   |
  |<--------------- connect({"path": P}) ------------------|
  | accept() -> TCPConnection（复用 4 字节长度前缀分帧）   |
  | close() -> server.close() ; _unlink_stale(P)           |
  |            （socket 文件被删除，同路径可再次 listen）  |
```

### 4.3 WebSocket 握手与首帧残留

```
Client                                              Server
  |-- GET /msp HTTP/1.1 ... Sec-WebSocket-Key: K -->|  _read_http_headers（<=64 KiB, 10 s 超时）
  |                                                 |  accept = base64(SHA1(K + GUID))
  |<-- HTTP/1.1 101 ... Sec-WebSocket-Accept ------|  可能同时读到首帧字节 -> leftover
  |   leftover 存入 _buf；随后 _recv_exact 优先消费 |
  |-- send(b"...") --> [0x82][0x80|len][mask][data]|  服务端发帧不加掩码
```

### 4.4 QUIC 0-RTT（🔵 规划中）

```
Client                                              Server
  |  （首次连接：1-RTT）                              |
  |-- Initial(ClientHello, alpn="msp/1") ------------>|
  |<-- Initial(ServerHello) + Handshake + 1-RTT ------|
  |<-- NewSessionTicket（缓存，供下次 0-RTT）---------|
  |  （再次连接：early_data=true）                     |
  |-- Initial(ClientHello, early_data) + 0-RTT ------>|  仅接受幂等信号（应当只有 hello）
  |<-- 1-RTT 完成；0-RTT 被拒时回退 1-RTT 重发 --------|
```

## 5. 数据类型

| 类型 / 符号 | 定义 | 说明 |
|---|---|---|
| `Connection` | 抽象类，`send` / `receive` / `close` | 字节搬运的唯一接口 |
| `ConnectionClosed` | `Exception` 子类 | 「这条连接不可再用」；**不**用于表示「没连上」 |
| `Transport` | 抽象类，`listen` / `accept` / `connect` / `close` | 一种协议的后端 |
| `TransportRegistry` | 具体类 | 后端表 + 按 `Endpoint.transport_type` 派发 |
| `UnsupportedTransport` | `Exception` 子类 | 没有匹配的后端 |
| `TCPConnection` | `Connection` 实现 | 4 字节大端长度前缀分帧；**被 UDS 复用** |
| `WebSocketConnection` | `Connection` 实现 | RFC 6455 帧编解码 + 分片重组 |
| `UDSTransport` | `Transport` 实现 | `AF_UNIX`，仅 Linux/macOS |
| `MAX_MESSAGE_SIZE` | `16 * 1024 * 1024` | TCP/UDS 与 WebSocket 共用同一常量值 |
| `TCPConnection.HEADER_SIZE` | `4` | 长度前缀字节数 |
| WebSocket `GUID` | `258EAFA5-E914-47DA-95CA-C5AB0DC85B11` | RFC 6455 握手魔数 |
| WebSocket opcode | `0x0` CONT / `0x1` TEXT / `0x2` BINARY / `0x8` CLOSE / `0x9` PING / `0xA` PONG | 发送只用 `0x2` |

`listen_all()` 返回值示例：

```json
{
  "tcp":       {"transport_type": "tcp",       "address": {"host": "127.0.0.1", "port": 45678}},
  "websocket": {"transport_type": "websocket", "address": {"url": "ws://127.0.0.1:45679/msp"}},
  "uds":       {"transport_type": "uds",       "address": {"path": "/tmp/msp-1234-9a3f0c11.sock"}}
}
```

`Endpoint` 的字段定义与去重规则见 [discovery.md §5](./discovery.md#5-数据类型)。

## 6. 错误处理与边界

| 场景 | 抛出 | 是否关闭连接 |
|---|---|---|
| `send` / `receive` 于已关闭连接 | `ConnectionClosed` | 已是关闭态 |
| `send` / `receive` 时 OS 错误 | `ConnectionClosed` | 是（先 `close()`） |
| 对端 EOF（读到 0 字节） | `ConnectionClosed` | **否**（见 §9） |
| 接收侧 `len > 16 MiB` | `ConnectionClosed` | 是 |
| WebSocket 单帧 `len > 16 MiB` | `ConnectionClosed` | 是 |
| WebSocket 收到 close 帧 | `ConnectionClosed` | 回 close 帧后关闭 |
| `connect` 失败 / 超时 | `ConnectionError` | 是（`sock.close()`） |
| `accept()` 于 `listen()` 之前 | `RuntimeError("listen() 未调用")` | 无连接 |
| UDS 在无 `AF_UNIX` 平台调 `listen()` / `connect()` | `RuntimeError` | 无连接 |
| WebSocket `connect` 传入非 `ws://` URL | `ValueError` | 无连接（解析先于连接） |
| WebSocket 状态行非 101 / Accept 不匹配 | `ConnectionError` | 是 |
| 服务端收到无 `Sec-WebSocket-Key` 的请求 | `ConnectionError` | 是（`accept()` 内 `sock.close()`） |
| HTTP 头超过 64 KiB | `ConnectionError` | 是 |
| 握手期间 EOF | `ConnectionClosed` | 是 |
| `Registry.connect` 遇未注册类型 | `UnsupportedTransport` | 无连接 |

边界取值：`len == 0` 是合法空消息；`len == 16777216` 合法；`len == 16777217` 断开。WebSocket 的 `126` 与 `127` 是**扩展长度标记**，不是长度本身。

## 7. 规范条文汇总（MUST/SHOULD 清单）

1. `Connection.receive()` **必须**返回恰好一条完整消息的负载，**不得**返回分帧头。
2. `Connection` **必须**用 `ConnectionClosed` 统一表示「不可再用」；`close()` **必须**幂等。
3. `Transport.listen({})` **必须**可用并返回实际监听地址（形态见 §2.2）。
4. `Transport.connect` 失败**必须**抛 `ConnectionError`，**不得**抛 `ConnectionClosed`。
5. 传输层**不得**解析 `Signal`、**不得**参与 MSP 层握手、**不得**依据 `node_id` 做任何判断。
6. TCP/UDS 分帧**必须**使用 4 字节**大端**长度前缀，`len` **不得**包含长度字段自身。
7. 接收侧 `len > 16777216` 时**必须**断开并抛 `ConnectionClosed`。
8. 接收侧**不得**因半包返回部分数据，**必须**阻塞至凑满整帧。
9. 发送侧**应当**为一条消息的字节写入加锁，**不得**让两条消息的字节交错。
10. `TransportRegistry` **必须**按 `Endpoint.transport_type` 精确选择后端，无匹配时抛 `UnsupportedTransport`。
11. `TransportRegistry.listen_all()` **必须**以空字典调用每个后端的 `listen`。
12. `TransportRegistry.close_all()` **不得**因单个后端失败而中断其余后端的关闭。
13. WebSocket 客户端帧**必须**带掩码、服务端帧**必须**不带掩码；客户端**必须**校验 `Sec-WebSocket-Accept`。
14. WebSocket 控制帧**应当**在 `receive()` 内部处理，**不得**返回给上层；握手多读到的字节**不得**丢弃。
15. UDS 的 socket 文件权限**必须**收紧为 `0o600`；清理残留时**必须**先确认 `stat.S_ISSOCK`，**不得**删除普通文件。
16. UDS 在无 `socket.AF_UNIX` 的平台**必须**显式失败（`RuntimeError`），**不得**静默降级成别的传输。
17. QUIC（🔵）实现**必须**使用 ALPN `"msp/1"`、**必须**复用 4 字节长度前缀帧、**不得**在 0-RTT 中发送有副作用的信号。

## 8. 安全考量

- **TLS 挂在哪一层**：TLS **必须**终结在**传输后端内部**——即 socket 之上、`Connection` 之下；`TransportRegistry`、协议层与模式层**不得**感知 TLS 的存在，也**不得**依赖 TLS 提供的身份做路由判断。身份的语义（证书 CN/SAN 或签名 HELLO 与 `node_id` 的绑定）属于 [security.md](./security.md) 的范围，本层只提供字节管道。
- **现状**：参考实现**没有** TLS。WebSocket 只支持 `ws://`（明文），`wss://` 会被 `_parse_url` 拒绝；TCP 与 UDS 也没有加密。因此当前版本的信任边界就是「谁能连上来」。
- **监听面**：TCP/WebSocket 默认绑定 `127.0.0.1`。改成 `0.0.0.0` 或公网地址会把信任域扩大到整个可达网络——在 TLS 与节点认证就位之前，**不应当**这样做。
- **UDS 权限**：`0o600` 使 socket 只对本用户可连，与「本机同用户全量信任」的模型一致。它只挡住同机其它用户，**不**提供认证：同一用户下的任意进程仍可连上并冒充任意 `node_id`。
- **资源耗尽防护**：16 MiB 上限是唯一内建的内存保护；它只在接收侧生效，且对 WebSocket 只按单帧判定（见 §9）。UDP 化的 QUIC 还**必须**额外处理放大攻击（服务端**不得**在地址验证前发送超过 3 倍请求体积的数据）。
- **HTTP 注册表的明文传输**与声明文件的可伪造性属于发现层的安全问题，见 [discovery.md §8](./discovery.md#8-安全考量)。

## 9. 已知缺口

1. ~~**MSP 层握手无读超时**~~ ✅ **已修复**：`Connection` 增加 `set_read_timeout(timeout)`（TCP / UDS / WebSocket 已实现；基类默认空实现，第三方后端不受影响），协议层握手用 `handshake_timeout`（默认 10 s）约束 `receive()`，读完立即恢复阻塞模式；超时以 `ConnectionClosed` 结束并关闭连接。
2. **WebSocket HTTP 握手在 accept 循环线程内同步执行**：每个后端只有一个接受线程，慢客户端（最多占满 10 s 握手超时）会让该后端在此期间停止接受新连接。
3. **WebSocket 服务端不校验请求方法、路径与 `Sec-WebSocket-Version`**：任何带 `Sec-WebSocket-Key` 的 HTTP 请求都会被升级。
4. **服务端不强制客户端掩码**：RFC 6455 要求客户端帧带掩码，实现按帧头决定是否解掩码，收到未掩码帧不报错。
5. **WebSocket 分片重组无总长上限**：16 MiB 上限按单帧判定，多帧累加可以超过该上限（内存耗尽风险）。
6. **发送侧不校验上限**：TCP/UDS/WebSocket 的 `send` 都不检查 `MAX_MESSAGE_SIZE`，超长消息只会在对端造成断开。
7. **EOF 路径不置 `_closed`、不关闭 socket**：`_recv_exact` 遇 EOF 直接抛 `ConnectionClosed`，而 `receive()` 只捕获 `OSError`，因此该路径既不改状态也不 `close()`；调用方**必须**自行 `close()`，重复 `receive()` 会重复抛 `ConnectionClosed`。
8. **UDS 仅 Linux/macOS**：Windows 的 Python 未暴露 `socket.AF_UNIX`，`listen()` / `connect()` 抛 `RuntimeError`；`accept()` 不做平台检查，只报 `RuntimeError("listen() 未调用")`。
9. **UDS 路径长度未校验**：Linux `sun_path` 约 108 字节，长临时目录 + 长 `node_id` 会 `bind` 失败（`OSError`），错误信息不指向真正原因。
10. **`_unlink_stale` 用 `os.stat`（跟随符号链接）**：指向 socket 的符号链接会被 unlink（删掉链接本身）——这是「只删 `S_ISSOCK`」防线的例外情形。
11. **`UDSTransport.close()` 会 unlink 记录下来的路径**，即使该路径上的文件已被另一个进程重建。
12. **`TransportRegistry` 无回滚、无告警**：`listen_all()` 中任一后端 `listen` 抛错会中断整个过程，先前已监听的后端不回滚关闭；重复 `register` 同一类型静默覆盖；没有 `unregister`；`_endpoints` 无公开访问器。
13. **仅 IPv4**：所有后端都建 `AF_INET` socket，不支持 IPv6。
14. **WebSocket 未实现扩展协商**：无 `permessage-deflate`、无子协议、无 `wss://`。
15. **QUIC 未实现**：`TRANSPORT_REGISTRY` 中只有注释占位。
16. **只有 `primary_transport` 进入声明**：多后端节点对外只暴露一个地址，其余后端实际不可被发现。
17. **`close()` 不保证唤醒阻塞中的 `accept()`**：关闭监听 socket 后阻塞在 `accept()` 的线程行为未定义，接受循环靠节点运行标志与异常分支退出。

## 10. 参考实现映射

| 条文 / 契约 | 源码文件与符号 |
|---|---|
| `Connection.send` / `receive` / `close`、`ConnectionClosed`、`Transport` | [base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/base.py) |
| `register` / `has` / `get` / `items` / `listen_all` / `connect` / `close_all` / `UnsupportedTransport` | [registry.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/registry.py) |
| 4 字节大端长度前缀分帧、16 MiB 上限、`_send_lock` | [tcp.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/tcp.py) `TCPConnection`、`MAX_MESSAGE_SIZE` |
| TCP `listen` / `accept` / `connect(timeout=10.0)` / `close` | [tcp.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/tcp.py) `TCPTransport` |
| WebSocket 握手（客户端 / 服务端） | [websocket.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/websocket.py) `_client_handshake` / `_server_handshake` / `GUID` |
| WebSocket 帧编解码、掩码、分片、控制帧 | [websocket.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/websocket.py) `_make_frame` / `_read_frame` / `receive` |
| WebSocket 地址解析、HTTP 头上限 | [websocket.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/websocket.py) `_parse_url` / `_read_http_headers` |
| UDS 平台限制 | [uds.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/uds.py) `_AF_UNIX_AVAILABLE` / `_require_af_unix` |
| UDS 默认路径、`0o600`、残留清理、close 时 unlink | [uds.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/uds.py) `listen` / `_unlink_stale` / `close` |
| 后端注册表内容（`tcp` / `websocket` / `uds`，`quic` 占位） | [node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `TRANSPORT_REGISTRY` |
| `primary_transport` 决定对外宣告的端点 | [node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `MSPNode.start` |
| 每个后端一个接受循环线程 | [node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `_accept_loop` / `_accept_loop_for` |
| `Endpoint` 形态与 `address_key()` | [discovery/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/base.py) `Endpoint` |
| TCP / UDS / WebSocket 往返、大消息、同路径重新监听 | [test_uds.py](https://github.com/hxh230802/MSP/blob/master/tests/test_uds.py)、[test_websocket.py](https://github.com/hxh230802/MSP/blob/master/tests/test_websocket.py) |

相关页面：[base-protocol.md](./base-protocol.md)（`Signal` 信封与握手）· [discovery.md](./discovery.md)（`Endpoint` 的产出方）· [security.md](./security.md)（TLS、认证与授权）· [architecture.md](./architecture.md)（分层架构与层间契约）。
