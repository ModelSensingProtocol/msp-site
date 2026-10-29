# Transports

| | |
|---|---|
| **Protocol revision** | `2026-10-10` |
| **Status markers** | ✅ implemented (TCP / WebSocket / UDS); 🔵 planned (QUIC) |
| **Defined on this page** | The byte-moving contract of the transport layer (`Transport` / `Connection` / `ConnectionClosed`), backend registration and selection (`TransportRegistry`), the framing and address formats of each backend, and the complete normative provisions for QUIC. |

## 1. Overview

The transport layer is the lowest layer of MSP: it **only moves bytes**. It establishes connections, sends and receives bytes, and handles framing — nothing else. It does not parse `Signal`, does not take part in handshake semantics, does not inspect the capability manifest, and does not know the peer's `node_id`. This division of labour is a hard boundary: once the transport layer starts understanding message semantics, a new backend has to reimplement the protocol logic all over again, and the layer's replaceability disappears (for the reasoning see [the design document](/design)).

| Role | Defined in | Responsibility |
|---|---|---|
| `Connection` | [base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/base.py) | One established connection: `send(bytes)` / `receive() -> bytes` / `close()` |
| `ConnectionClosed` | same as above | The signal that "this connection can no longer be used" |
| `Transport` | same as above | The backend of one transport protocol: `listen` / `accept` / `connect` / `close` |
| `TransportRegistry` | [registry.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/registry.py) | Backend table; selects a backend by `Endpoint.transport_type` |

| `transport_type` | Implementation | Address form | Status |
|---|---|---|---|
| `tcp` | [tcp.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/tcp.py) | `{"host": str, "port": int}` | ✅ implemented |
| `websocket` | [websocket.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/websocket.py) | `{"url": "ws://host:port/path"}` | ✅ implemented |
| `uds` | [uds.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/uds.py) | `{"path": "/path/to.sock"}` | ✅ implemented (Linux/macOS only) |
| `quic` | none | `{"host": str, "port": int, …}` (see §3.6) | 🔵 planned |

The relationship between the transport layer and discovery / presence is described in [discovery.md](./discovery.md): that layer produces `Endpoint`, and this layer consumes its `transport_type` and `address`.

## 2. Contract

### 2.1 `Connection`

```
send(data: bytes) -> None
receive() -> bytes
close() -> None            # idempotent
```

- `send(data)` **MUST** send `data` as **one complete message**; framing details (length prefix, frame header) are handled by the implementation.
- `receive()` **MUST** return the payload of **exactly one** complete message, **MUST NOT** return the length prefix or frame header, and **MUST NOT** glue two adjacent messages together.
- `receive()` is a blocking call: when there is no data it **MUST** wait, and **MUST NOT** return `b""` to mean "no data yet". The empty byte string `b""` is a **valid message** (zero-length payload), not an error signal.
- When the connection can no longer be used (peer closed, local end closed, OS-level error, frame length over the limit), `send` / `receive` **MUST** raise `ConnectionClosed`; the implementation **SHOULD** make a best effort to close the underlying socket before raising.
- `close()` **MUST** be idempotent: repeated calls raise no error and throw no exception.
- `send` **SHOULD** be safe to call concurrently from multiple threads (the reference implementation uses `_send_lock` so that the bytes of a single message are not interleaved). `receive()` does **not** guarantee concurrency safety: **MUST NOT** call `receive()` on the same `Connection` from several threads at the same time.

### 2.2 `Transport`

```
listen(address: dict) -> dict
accept() -> Connection
connect(address: dict) -> Connection
close() -> None            # idempotent
```

- `listen(address)` **MUST** start listening and return the address actually in effect, always in this form:

```json
{
  "transport_type": "tcp",
  "address": {"host": "127.0.0.1", "port": 45678}
}
```

  Note that this is not an `Endpoint`: it has no `node_id`, and the outer object carries an extra `transport_type` key. A node takes `info["address"]` to construct an `Endpoint`.
- `listen({})` **MUST** work: `TransportRegistry.listen_all()` always calls `listen` with an empty dictionary, so every backend **MUST** define defaults for `host` / `port` / `path`. The returned address **SHOULD** differ from the input (with `port=0` it returns the real port assigned by the kernel).
- `accept()` **MUST** block until an inbound connection arrives; the caller loops on it in a dedicated thread or coroutine. Calling it before `listen()` **MUST** raise `RuntimeError`.
- `connect(address)` **MUST** raise `ConnectionError` on failure and **MUST NOT** raise `ConnectionClosed` (the former means "did not connect", the latter means "connected and then dropped"). The connect timeout **SHOULD** have a default (10 s in the reference implementation) and **MUST NOT** wait indefinitely.
- `accept()` **MUST NOT** perform the MSP-layer handshake (HELLO/ACK belong to the protocol layer). The only exception is the WebSocket **HTTP Upgrade handshake** — that is the transport layer's own frame negotiation.
- `close()` **MUST** be idempotent and release the listening resources. The reference implementation does **not** specify whether it wakes a blocked `accept()` in another thread; **MUST NOT** rely on that behaviour (see §9).

### 2.3 `TransportRegistry`

| Method | Semantics |
|---|---|
| `register(transport_type, transport)` | Register a backend; when the same `transport_type` is registered again, the later registration wins |
| `has` / `get` | Check whether a backend is registered / fetch a backend |
| `items()` | Iterate `(transport_type, transport)` |
| `listen_all() -> dict` | Call `listen({})` on every backend in registration order, returning `{transport_type: listen info}` |
| `connect(endpoint) -> Connection` | Select the backend by `endpoint.transport_type` and call `transport.connect(endpoint.address)` |
| `close_all() -> None` | Close the backends one by one; an error from a single backend is swallowed and logged at debug level, and **MUST NOT** abort the remaining backends |

- **Backend selection rule**: `Endpoint.transport_type` **MUST** exactly match the key used at `register` time (case-sensitive); when nothing matches it **MUST** raise `UnsupportedTransport`, and the error message **SHOULD** list every currently registered type.
- The registry does **not** validate that the address matches the backend: with `transport_type` `tcp` and an `address` missing `host`, the error comes from the backend (`KeyError`), not from the registry.
- A node announces **only** one endpoint to the outside, namely `Preset.primary_transport`; the other backends still `listen` as usual, but their addresses do **not** go into any declaration file. So "one node, many backends" is currently meaningful only on the side being connected to; the peer has no way to learn the secondary addresses.
- The registry does **not** understand message semantics and does **not** hold `Connection` objects: the connection lifecycle belongs to the protocol layer.

## 3. Messages and formats

### 3.1 Framing

TCP and UDS are both byte streams without message boundaries, so they share the same length-prefix framing; UDS reuses `TCPConnection` directly and is byte-for-byte identical to TCP. WebSocket has its own frame boundaries and does not use this section's format (see §3.5).

```
 0        1        2        3        4                      4+N
 +--------+--------+--------+--------+----------------------+
 | len[0] | len[1] | len[2] | len[3] |  payload (N = len)   |
 +--------+--------+--------+--------+----------------------+
 |<--- 4-byte big-endian length ---->|<-- N-byte payload -->|
```

- **Byte order**: big-endian (network byte order), `len.to_bytes(4, "big")` / `int.from_bytes(header, "big")`. **MUST NOT** use little-endian.
- **Length semantics**: `len` = number of payload bytes, **not** including the 4-byte header itself; the total frame length is always `4 + len`.
- **Limit**: `MAX_MESSAGE_SIZE = 16 * 1024 * 1024` (16 MiB = 16777216 bytes). When the receiving side reads `len > 16777216` it **MUST** close the connection and raise `ConnectionClosed` (to prevent "a peer declaring a huge length to exhaust memory"). `len == 16777216` is valid.
- **Zero-length frame**: when `len == 0` the receiving side returns `b""` directly without reading any payload bytes; the upper layer **MUST** accept a message with an empty payload.
- **Coalescing**: the sending side issues one `sendall(header + payload)` and the receiving side splits by length; frames that arrive back to back are returned one after another and **MUST NOT** be merged.
- **Partial frames**: the receiving side loops on `recv` until it has the required number of bytes (`_recv_exact`). When fewer than 4 header bytes or fewer than `len` payload bytes have arrived it **MUST** keep blocking and **MUST NOT** return the bytes received so far.
- **Write mutual exclusion**: the sending side takes a lock so that one message's bytes are written contiguously and are not interleaved with another message's.
- **Asymmetry**: the limit check runs on the receiving side only. The sending side does **not** validate `len`; a message above 16 MiB is disconnected by the peer with `ConnectionClosed`.

### 3.2 Address formats

| `transport_type` | `listen` input keys (defaults) | External `address` form | Outbound connection requirement |
|---|---|---|---|
| `tcp` | `host` (`"127.0.0.1"`), `port` (`0`) | `{"host": str, "port": int}` | `host` and `port` **MUST** be present |
| `websocket` | `host` (`"127.0.0.1"`), `port` (`0`), `path` (`"/msp"`) | `{"url": "ws://<host>:<port><path>"}` | `url` **MUST** be present and start with `ws://` |
| `uds` | `path` (`<tempdir>/msp-<pid>-<8 hex digits>.sock`) | `{"path": str}` | `path` **MUST** be present |
| `quic` | see §3.6 | see §3.6 | see §3.6 |

TCP listening parameters: `SO_REUSEADDR` is set when the socket is created, `listen(128)` is called, and the listening address is taken from the actual result of `getsockname()`. The address family is fixed to `AF_INET`; IPv6 literals are **not** supported (`::1` fails on a family mismatch). WebSocket listening parameters are in §3.4, UDS in §3.3.

The `connect` timeout for TCP/UDS defaults to **10 s** and is **not** exposed through the `address` dictionary — `TransportRegistry.connect` passes only `endpoint.address`, so the caller **MUST NOT** expect to adjust the timeout through address fields. On a successful connection the socket is switched back to blocking mode (the read loop needs it).

### 3.3 UDS: platform limits, permissions and stale-socket cleanup

- **Platform limit**: Unix domain sockets are available on Linux/macOS only. CPython on Windows does **not** expose `socket.AF_UNIX`, and `listen()` / `connect()` raise `RuntimeError` before any socket call is made (the message states that Unix domain sockets are available on Linux/macOS only and points at switching to TCP). An implementation **MUST NOT** silently fall back to another transport on a platform without `AF_UNIX`: a fallback would change the `transport_type` and the address form in the declaration, and the peer would have no way to know.
- **Default socket path rule**: `os.path.join(tempfile.gettempdir(), f"msp-{os.getpid()}-{os.urandom(4).hex()}.sock")`, i.e. `<tempdir>/msp-<pid>-<8 hex digits>.sock`; `address` **MAY** specify `path` explicitly. `listen` returns `{"transport_type": "uds", "address": {"path": <actual path>}}`. The address is a filesystem path, so it fits naturally with shared-directory discovery (see [discovery.md](./discovery.md)).
- **Permissions**: after `bind` it **MUST** run `chmod(path, 0o600)` so that the socket is connectable only by this user. A `chmod` failure is ignored (harmless on read-only filesystems and similar), but permissions **MUST NOT** be relaxed because of it.
- **Stale socket file cleanup**: after a process crashes the kernel does not delete the socket file, and a plain `bind` fails because the path already exists. So `listen()` **MUST** clean up stale files before `bind`: `os.unlink(path)` only when `os.stat(path)` succeeds **and** `stat.S_ISSOCK(mode)` is true; **MUST NOT** delete non-socket files (to avoid destroying user data).
- **close semantics**: `close()` **MUST** be idempotent; after closing the listening socket it unlinks the path it recorded and clears the record. Re-listening on the same path is therefore a routine operation ([test_uds.py](https://github.com/hxh230802/MSP/blob/master/tests/test_uds.py) covers this behaviour).
- **Framing**: byte-for-byte identical to TCP (§3.1); the reference implementation reuses `TCPConnection` directly and does **not** introduce a second framing implementation.
- **Connect timeout**: `connect` defaults to 10 s; an `AF_UNIX` connection usually completes immediately, so the timeout is only a backstop.

### 3.4 WebSocket handshake (RFC 6455 subset)

Client request (verbatim):

```
GET /msp HTTP/1.1
Host: 127.0.0.1:45678
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: <base64(16 random bytes)>
Sec-WebSocket-Version: 13

```

Server response (verbatim, `accept = base64(SHA1(key + GUID))`):

```
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <accept>

```

- The handshake magic value is `GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"`.
- The client **MUST** verify that the status line contains ` 101 ` and **MUST** verify that `Sec-WebSocket-Accept` equals the value it computed itself; a mismatch raises `ConnectionError`.
- The server **MUST** require `Sec-WebSocket-Key` and raises `ConnectionError` when it is absent; the reference implementation does **not** validate the request method or path, nor `Sec-WebSocket-Version` (see §9).
- The HTTP header read limit is **64 KiB**, exceeding it raises `ConnectionError`, and EOF during the read raises `ConnectionClosed`.
- The handshake may read bytes of the first frame; the implementation **MUST** buffer those bytes for the subsequent `receive()` to consume first and **MUST NOT** discard them (otherwise the first frame is lost).

### 3.5 WebSocket frames

```
 0                   1                   2                   3
 +-+-+-+-+-------+-+-------------+-------------------------------+
 |F|R|R|R|opcode |M| Payload len |  Extended payload length ...  |
 |I|S|S|S| (4b)  |A|     (7b)    |  (16/64b, len=126/127 only)   |
 |N|V|V|V|       |S|             |                               |
 +-+-+-+-+-------+-+-------------+ - - - - - - - - - - - - - - - +
 |  Masking key (4B when MASK=1) |       Payload data ...        |
 +---------------------------------------------------------------+
```

- The sending side sends **binary frames** only (`FIN=1`, `opcode=0x2`).
- Length encoding: `len < 126` writes the 7-bit value directly; `126 <= len < 65536` writes `126` + 2 bytes big-endian; otherwise `127` + 8 bytes big-endian.
- **Masking**: frames sent by the client **MUST** be masked (`MASK=1`, a 4-byte random key, payload XORed with `key[i % 4]`); frames sent by the server **MUST NOT** be masked. The receiving side decides whether to unmask from the `MASK` bit in the frame header.
- **Fragmentation**: a `0x1`/`0x2` frame with `FIN=0` opens a fragment buffer, subsequent `opcode=0x0` (continuation) frames append to it, and the whole message is returned to the upper layer only at `FIN=1`; an orphan continuation **SHOULD** be ignored.
- **Control frames** are consumed inside `receive()` and **MUST NOT** be returned to the upper layer: `0x8` (close) → send a close frame back on a best-effort basis, then raise `ConnectionClosed`; `0x9` (ping) → reply with `pong` (`0xA`) echoing the payload, then continue reading; `0xA` (pong) → ignore. An unknown opcode **SHOULD** be ignored rather than disconnect.
- **Limit**: `MAX_MESSAGE_SIZE = 16 * 1024 * 1024`, but the check applies to the **single-frame** length; the **total length after fragment reassembly has no limit** (see §9).
- **Text frames**: the payload of a `0x1` frame is returned as a message as-is (**no** UTF-8 validation, **no** transcoding); an implementation **SHOULD NOT** rely on text-frame semantics.
- **Differences from TCP**: ① message boundaries come from frames, so no length prefix is needed; ② there are symmetric ping/pong and close frames (TCP/UDS have none and can rely only on an upper-layer heartbeat); ③ there is an HTTP Upgrade handshake with a 64 KiB header limit; ④ server and client sending behaviour is asymmetric (masking). **In common**: both have ordered, reliable byte-stream semantics, the `Connection` interface is identical, and neither uses `b""` in `receive()` to mean "no data yet".

### 3.6 QUIC (🔵 planned)

An implementer **MAY** leave this unimplemented, but once implemented it **MUST** conform to this provision.

- **`transport_type`**: `"quic"`, registered in `TransportRegistry` (consistent with the reserved `# "quic": QUICTransport` in [core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py)).
- **Version / ALPN**: **MUST** use QUIC v1 (RFC 9000) with ALPN `"msp/1"`; **MUST NOT** reuse HTTP/3's `"h3"`.
- **1-RTT and 0-RTT**: the first connection **MUST** perform the full 1-RTT handshake (TLS 1.3). After caching a valid session ticket, the client **MAY** send the first MSP message together with the ClientHello using **0-RTT early data**. 0-RTT data **MUST** satisfy the idempotence requirement — signals with side effects such as `tool_call` **MUST NOT** be placed in 0-RTT, and only `hello` **SHOULD** go there. When the server rejects 0-RTT, the client **MUST** fall back to 1-RTT and resend, and **MUST NOT** treat "0-RTT rejected" as a connection failure.
- **Address format**:

```json
{
  "host": "127.0.0.1",
  "port": 4433,
  "alpn": "msp/1",
  "early_data": false,
  "max_streams": 8
}
```

  | Field | Type | Default | Semantics |
  |---|---|---|---|
  | `host` | str | `"127.0.0.1"` | Host |
  | `port` | int | `0` (listen); required for connect | Port; `0` means allocate dynamically and write the value back |
  | `alpn` | str | `"msp/1"` | ALPN identifier; any value other than `msp/1` **MUST** be rejected |
  | `early_data` | bool | `false` | Whether 0-RTT is allowed |
  | `max_streams` | int | `8` | Upper bound on concurrent bidirectional streams this end accepts from the peer |

  Unknown fields **MUST** be ignored (lenient reading), consistent with the field policy in [base-protocol.md](./base-protocol.md).
- **Framing and stream reuse**: one `Connection` **MUST** be bound to **one** long-lived bidirectional stream, carrying **byte-for-byte the same** 4-byte big-endian length-prefixed frames as TCP/UDS (§3.1), so that `TransportRegistry`, the protocol layer and `MAX_MESSAGE_SIZE` all remain unchanged. Concurrency **MAY** be achieved by opening new streams, but **MUST NOT** split the message of a single `send()` across several streams — the "exactly one complete message" semantics of `receive()` do not change with the transport.
- **Congestion control**: **MUST** use congestion control at least equivalent to TCP NewReno (CUBIC or BBR) and **MUST NOT** send without a rate limit; stream-level and connection-level flow control **MUST** both be in effect.
- **Connection migration**: the connection identity **MUST** be based on the Connection ID rather than the `(host, port)` 4-tuple; after a client changes networks it **SHOULD** keep using the same connection and **MUST NOT** discard the established MSP session state because of it.
- **Differences from TCP**: ① multiple streams within one connection with no head-of-line blocking (each stream retransmits independently); ② encryption and authentication are built in (TLS 1.3 sits inside QUIC, so there is **no** WebSocket-style stage of "plaintext Upgrade first, encryption afterwards"); ③ 0-RTT and connection migration are supported; ④ it runs over UDP, so packet loss and MTU need explicit handling (PMTU discovery); ⑤ the server **MAY** serve QUIC and TCP on the same port at once (implementation-defined).
- **Lifecycle**: the semantics of `listen` / `accept` / `connect` / `close` are fully consistent with the `Transport` contract (§2.2); `accept()` blocks until an inbound connection completes the QUIC handshake.
- **Migration path**: change `Preset.transports` from `{"tcp"}` to `{"quic"}` (or keep both), point `primary_transport` at `"quic"`, and no other layer needs to change — this is the direct payoff of "the transport layer only moves bytes".

## 4. Message flows

### 4.1 TCP outbound connection and framing

```
Client (TransportRegistry)                    Server (Transport)
        |                                             |
        |-- connect({"host","port"}) ---------------->|  socket(AF_INET, SOCK_STREAM)
        |   sock.settimeout(10.0)                     |  SO_REUSEADDR + bind + listen(128)
        |   sock.connect((host, port))                |
        |   sock.settimeout(None)                     |
        |<------------------- Connection -------------|  (blocking accept() returns Connection)
        |                                             |
        |-- send(b"HELLO...") -->[00 00 00 1D][HELLO] |  _recv_exact(4) -> len=29
        |                                             |  _recv_exact(29)  -> payload
        |<-- receive() <---------[00 00 00 1A][ACK..] |
        |-- close() --> shutdown(SHUT_RDWR) + close() |
```

The difference from WebSocket: TCP has **no** transport-layer handshake, and the `Connection` returned by `accept()` is usable immediately; the MSP-layer HELLO/ACK is then completed by the protocol layer.

### 4.2 UDS lifecycle (including stale cleanup)

```
Process A                                          Process B
  | listen({"path": P})                                    |
  |   _require_af_unix()  -> RuntimeError if no AF_UNIX    |
  |   _unlink_stale(P): stat(P) is S_ISSOCK ? unlink(P)    |
  |   bind(P) ; chmod(P, 0o600) ; listen(128)              |
  |   returns {"transport_type":"uds","address":{"path":P}}|
  |<--------------- connect({"path": P}) ------------------|
  | accept() -> TCPConnection (4-byte length prefix)       |
  | close() -> server.close() ; _unlink_stale(P)           |
  |            (socket file removed; path can be reused)   |
```

### 4.3 WebSocket handshake and leftover first-frame bytes

```
Client                                              Server
  |-- GET /msp HTTP/1.1 ... Sec-WebSocket-Key: K -->|  _read_http_headers (<=64 KiB, 10 s timeout)
  |                                                 |  accept = base64(SHA1(K + GUID))
  |<-- HTTP/1.1 101 ... Sec-WebSocket-Accept -------|  may read first-frame bytes too -> leftover
  |   leftover in _buf; _recv_exact reads it first  |
  |-- send(b"...") --> [0x82][0x80|len][mask][data]|  server sends frames unmasked
```

### 4.4 QUIC 0-RTT (🔵 planned)

```
Client                                              Server
  |  (first connection: 1-RTT)                        |
  |-- Initial(ClientHello, alpn="msp/1") ------------>|
  |<-- Initial(ServerHello) + Handshake + 1-RTT ------|
  |<-- NewSessionTicket (cached for next 0-RTT) ------|
  |  (reconnect: early_data=true)                     |
  |-- Initial(ClientHello, early_data) + 0-RTT ------>|  idempotent signals only; SHOULD be hello only
  |<-- 1-RTT done; 0-RTT rejected -> resend on 1-RTT -|
```

## 5. Data types

| Type / symbol | Definition | Notes |
|---|---|---|
| `Connection` | Abstract class, `send` / `receive` / `close` | The only interface for moving bytes |
| `ConnectionClosed` | `Exception` subclass | "This connection can no longer be used"; **not** used for "did not connect" |
| `Transport` | Abstract class, `listen` / `accept` / `connect` / `close` | The backend of one protocol |
| `TransportRegistry` | Concrete class | Backend table + dispatch by `Endpoint.transport_type` |
| `UnsupportedTransport` | `Exception` subclass | No matching backend |
| `TCPConnection` | `Connection` implementation | 4-byte big-endian length-prefix framing; **reused by UDS** |
| `WebSocketConnection` | `Connection` implementation | RFC 6455 frame codec + fragment reassembly |
| `UDSTransport` | `Transport` implementation | `AF_UNIX`, Linux/macOS only |
| `MAX_MESSAGE_SIZE` | `16 * 1024 * 1024` | TCP/UDS and WebSocket share the same constant value |
| `TCPConnection.HEADER_SIZE` | `4` | Number of length-prefix bytes |
| WebSocket `GUID` | `258EAFA5-E914-47DA-95CA-C5AB0DC85B11` | RFC 6455 handshake magic value |
| WebSocket opcode | `0x0` CONT / `0x1` TEXT / `0x2` BINARY / `0x8` CLOSE / `0x9` PING / `0xA` PONG | Sending uses `0x2` only |

Example `listen_all()` return value:

```json
{
  "tcp":       {"transport_type": "tcp",       "address": {"host": "127.0.0.1", "port": 45678}},
  "websocket": {"transport_type": "websocket", "address": {"url": "ws://127.0.0.1:45679/msp"}},
  "uds":       {"transport_type": "uds",       "address": {"path": "/tmp/msp-1234-9a3f0c11.sock"}}
}
```

The field definitions and deduplication rules of `Endpoint` are in [discovery.md §5](./discovery.md#5-data-types).

## 6. Error handling and boundaries

| Scenario | Raised | Connection closed |
|---|---|---|
| `send` / `receive` on an already closed connection | `ConnectionClosed` | Already closed |
| OS error during `send` / `receive` | `ConnectionClosed` | Yes (`close()` first) |
| Peer EOF (0 bytes read) | `ConnectionClosed` | **No** (see §9) |
| Receiving side `len > 16 MiB` | `ConnectionClosed` | Yes |
| WebSocket single frame `len > 16 MiB` | `ConnectionClosed` | Yes |
| WebSocket close frame received | `ConnectionClosed` | Closed after replying with a close frame |
| `connect` failure / timeout | `ConnectionError` | Yes (`sock.close()`) |
| `accept()` before `listen()` | `RuntimeError("listen() not called")` | No connection |
| UDS `listen()` / `connect()` on a platform without `AF_UNIX` | `RuntimeError` | No connection |
| WebSocket `connect` with a non-`ws://` URL | `ValueError` | No connection (parsing precedes connecting) |
| WebSocket status line not 101 / Accept mismatch | `ConnectionError` | Yes |
| Server receives a request without `Sec-WebSocket-Key` | `ConnectionError` | Yes (`sock.close()` inside `accept()`) |
| HTTP headers exceed 64 KiB | `ConnectionError` | Yes |
| EOF during the handshake | `ConnectionClosed` | Yes |
| `Registry.connect` with an unregistered type | `UnsupportedTransport` | No connection |

Boundary values: `len == 0` is a valid empty message; `len == 16777216` is valid; `len == 16777217` disconnects. In WebSocket, `126` and `127` are **extended length markers**, not the length itself.

## 7. Summary of normative provisions (MUST/SHOULD list)

1. `Connection.receive()` **MUST** return the payload of exactly one complete message and **MUST NOT** return framing headers.
2. A `Connection` **MUST** use `ConnectionClosed` uniformly for "no longer usable"; `close()` **MUST** be idempotent.
3. `Transport.listen({})` **MUST** work and return the actual listening address (form in §2.2).
4. `Transport.connect` **MUST** raise `ConnectionError` on failure and **MUST NOT** raise `ConnectionClosed`.
5. The transport layer **MUST NOT** parse `Signal`, **MUST NOT** take part in the MSP-layer handshake, and **MUST NOT** make any decision based on `node_id`.
6. TCP/UDS framing **MUST** use a 4-byte **big-endian** length prefix, and `len` **MUST NOT** include the length field itself.
7. The receiving side **MUST** disconnect and raise `ConnectionClosed` when `len > 16777216`.
8. The receiving side **MUST NOT** return partial data for a partial frame and **MUST** block until it has the whole frame.
9. The sending side **SHOULD** lock the byte writes of one message and **MUST NOT** let the bytes of two messages interleave.
10. `TransportRegistry` **MUST** select the backend exactly by `Endpoint.transport_type`, raising `UnsupportedTransport` when nothing matches.
11. `TransportRegistry.listen_all()` **MUST** call each backend's `listen` with an empty dictionary.
12. `TransportRegistry.close_all()` **MUST NOT** abort the shutdown of the remaining backends because one backend failed.
13. WebSocket client frames **MUST** be masked and server frames **MUST NOT** be masked; the client **MUST** validate `Sec-WebSocket-Accept`.
14. WebSocket control frames **SHOULD** be handled inside `receive()` and **MUST NOT** be returned to the upper layer; bytes read in excess during the handshake **MUST NOT** be discarded.
15. The UDS socket file permissions **MUST** be tightened to `0o600`; cleanup of a stale file **MUST** first confirm `stat.S_ISSOCK` and **MUST NOT** delete a regular file.
16. UDS on a platform without `socket.AF_UNIX` **MUST** fail explicitly (`RuntimeError`) and **MUST NOT** silently degrade to another transport.
17. A QUIC (🔵) implementation **MUST** use ALPN `"msp/1"`, **MUST** reuse the 4-byte length-prefix frame, and **MUST NOT** send signals with side effects in 0-RTT.

## 8. Security considerations

- **Which layer TLS sits at**: TLS **MUST** terminate **inside the transport backend** — that is, above the socket and below `Connection`; `TransportRegistry`, the protocol layer and the pattern layer **MUST NOT** be aware of TLS and **MUST NOT** rely on the identity TLS provides for routing decisions. The semantics of identity (certificate CN/SAN, or the binding between a signed HELLO and `node_id`) belong to [security.md](./security.md); this layer provides nothing but a byte pipe.
- **Current state**: the reference implementation has **no** TLS. WebSocket supports `ws://` only (plaintext); `wss://` is rejected by `_parse_url`; TCP and UDS are unencrypted as well. The trust boundary of the current version is therefore "whoever can connect".
- **Listening surface**: TCP/WebSocket bind to `127.0.0.1` by default. Changing that to `0.0.0.0` or a public address widens the trust domain to the whole reachable network — before TLS and node authentication are in place, that **SHOULD NOT** be done.
- **UDS permissions**: `0o600` makes the socket connectable only by this user, consistent with the model of "full trust among processes of the same user on this machine". It blocks other users on the same machine only; it does **not** provide authentication: any process under the same user can still connect and impersonate any `node_id`.
- **Resource-exhaustion protection**: the 16 MiB limit is the only built-in memory protection; it applies on the receiving side only and, for WebSocket, is judged per frame (see §9). A UDP-based QUIC **MUST** additionally handle amplification attacks (the server **MUST NOT** send more than 3 times the request size before address validation).
- **The plaintext transport of the HTTP registry** and the forgeability of declaration files are discovery-layer security issues; see [discovery.md §8](./discovery.md#8-security-considerations).

## 9. Known gaps

1. ~~**No read timeout on the MSP-layer handshake**~~ ✅ **Fixed**: `Connection` gained `set_read_timeout(timeout)` (implemented for TCP / UDS / WebSocket; the base class defaults to an empty implementation, so third-party backends are unaffected), and the protocol-layer handshake bounds `receive()` with `handshake_timeout` (10 s by default) and restores blocking mode as soon as the read finishes; a timeout ends in `ConnectionClosed` and closes the connection.
2. **The WebSocket HTTP handshake runs synchronously in the accept-loop thread**: each backend has a single accept thread, so a slow client (occupying up to the 10 s handshake timeout) stops that backend from accepting new connections in the meantime.
3. **The WebSocket server does not validate the request method, path or `Sec-WebSocket-Version`**: any HTTP request carrying `Sec-WebSocket-Key` is upgraded.
4. **The server does not enforce client masking**: RFC 6455 requires client frames to be masked, but the implementation decides unmasking from the frame header and does not report an error when it receives an unmasked frame.
5. **WebSocket fragment reassembly has no total-length limit**: the 16 MiB limit is judged per frame, and accumulating several frames can exceed it (memory-exhaustion risk).
6. **The sending side does not validate the limit**: `send` on TCP/UDS/WebSocket never checks `MAX_MESSAGE_SIZE`; an oversized message only causes a disconnect at the peer.
7. **The EOF path neither sets `_closed` nor closes the socket**: `_recv_exact` raises `ConnectionClosed` directly on EOF, while `receive()` only catches `OSError`, so that path neither changes state nor calls `close()`; the caller **MUST** call `close()` itself, and a repeated `receive()` raises `ConnectionClosed` again.
8. **UDS is Linux/macOS only**: Python on Windows does not expose `socket.AF_UNIX`, so `listen()` / `connect()` raise `RuntimeError`; `accept()` performs no platform check and only reports `RuntimeError("listen() not called")`.
9. **The UDS path length is not validated**: Linux's `sun_path` is about 108 bytes, so a long temporary directory plus a long `node_id` makes `bind` fail (`OSError`), and the error message does not point at the real cause.
10. **`_unlink_stale` uses `os.stat` (following symbolic links)**: a symbolic link pointing at a socket is unlinked (deleting the link itself) — this is the exception to the "delete only `S_ISSOCK`" guard.
11. **`UDSTransport.close()` unlinks the recorded path** even when the file at that path has already been recreated by another process.
12. **`TransportRegistry` has no rollback and no warning**: an error from any backend's `listen` in `listen_all()` aborts the whole procedure and the backends that already listened are not rolled back and closed; registering the same type twice silently overwrites; there is no `unregister`; `_endpoints` has no public accessor.
13. **IPv4 only**: every backend creates an `AF_INET` socket and does not support IPv6.
14. **WebSocket implements no extension negotiation**: no `permessage-deflate`, no subprotocols, no `wss://`.
15. **QUIC is not implemented**: `TRANSPORT_REGISTRY` holds a commented-out placeholder only.
16. **Only `primary_transport` reaches the declaration**: a multi-backend node exposes a single address to the outside, and the remaining backends are effectively undiscoverable.
17. **`close()` does not guarantee waking a blocked `accept()`**: the behaviour of a thread blocked in `accept()` after the listening socket is closed is undefined, and the accept loop exits via the node's run flag and exception branches.

## 10. Reference implementation map

| Provision / contract | Source file and symbols |
|---|---|
| `Connection.send` / `receive` / `close`, `ConnectionClosed`, `Transport` | [base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/base.py) |
| `register` / `has` / `get` / `items` / `listen_all` / `connect` / `close_all` / `UnsupportedTransport` | [registry.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/registry.py) |
| 4-byte big-endian length-prefix framing, 16 MiB limit, `_send_lock` | [tcp.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/tcp.py) `TCPConnection`, `MAX_MESSAGE_SIZE` |
| TCP `listen` / `accept` / `connect(timeout=10.0)` / `close` | [tcp.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/tcp.py) `TCPTransport` |
| WebSocket handshake (client / server) | [websocket.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/websocket.py) `_client_handshake` / `_server_handshake` / `GUID` |
| WebSocket frame codec, masking, fragmentation, control frames | [websocket.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/websocket.py) `_make_frame` / `_read_frame` / `receive` |
| WebSocket URL parsing, HTTP header limit | [websocket.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/websocket.py) `_parse_url` / `_read_http_headers` |
| UDS platform limit | [uds.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/uds.py) `_AF_UNIX_AVAILABLE` / `_require_af_unix` |
| UDS default path, `0o600`, stale cleanup, unlink on close | [uds.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/uds.py) `listen` / `_unlink_stale` / `close` |
| Registry contents (`tcp` / `websocket` / `uds`, `quic` placeholder) | [node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `TRANSPORT_REGISTRY` |
| `primary_transport` decides the announced endpoint | [node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `MSPNode.start` |
| One accept-loop thread per backend | [node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `_accept_loop` / `_accept_loop_for` |
| `Endpoint` shape and `address_key()` | [discovery/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/base.py) `Endpoint` |
| TCP / UDS / WebSocket round-trips, large messages, re-listening on the same path | [test_uds.py](https://github.com/hxh230802/MSP/blob/master/tests/test_uds.py), [test_websocket.py](https://github.com/hxh230802/MSP/blob/master/tests/test_websocket.py) |

Related pages: [base-protocol.md](./base-protocol.md) (`Signal` envelope and handshake) · [discovery.md](./discovery.md) (producer of `Endpoint`) · [security.md](./security.md) (TLS, authentication and authorization) · [architecture.md](./architecture.md) (layered architecture and inter-layer contracts).
