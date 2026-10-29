# Base Protocol

> **Specification revision** `2026-10-10` ｜ **Status** ✅ Implemented (`cancel` / `progress` are 🔵 Planned)
>
> This page defines the message layer of MSP: the **unified `Signal` envelope**, **JSON / UTF-8 encoding and decoding**, the **connection lifecycle** (handshake, capability exchange, heartbeat, close), **request/reply correlation** (`reqid`) and **error handling**. It corresponds to the *Base Protocol* of the MCP specification — any behaviour that does not belong to a specific pattern is defined here.

---

## 1. Overview

MSP has exactly one kind of message: `Signal`.

Handshakes, heartbeats, broadcasts, tool calls, task states and error notifications are all instances of `Signal`; **only the `type` field differs**. That is the whole meaning of "Everything is a signal" at the message layer, and it is also where the boundary lies for a third party implementing this protocol independently: **understanding this page plus [pattern routing](patterns.md#3-routing-contract) is enough to implement an interoperable node.**

The message layer defines no interaction semantics. It does four things only:

1. **Encapsulation** — put every interaction into the same envelope ([§2](#2-the-signal-envelope));
2. **Encoding and decoding** — envelope ↔ bytes ([§3](#3-encoding-and-decoding));
3. **Maintaining the connection** — establish, handshake, deduplicate, probe liveness, close ([§4](#4-connection-lifecycle));
4. **Correlating requests with responses** — use `reqid` to match a response back to its request ([§5](#5-requestreply-correlation-reqid)).

Everything else (how tools are called, how signals are broadcast, how tasks are delegated) is defined by the **pattern layer**, and the protocol layer knows nothing about it ([patterns.md](patterns.md)).

---

## 2. The `Signal` envelope

### 2.1 Fields

| Field | Type | Required | Default | Semantics |
|---|---|---|---|---|
| `type` | string | **MUST** | — | Signal type. Core types are listed in [§2.2](#22-core-signal-types); a pattern may define private types |
| `source` | string | **MUST** | — | Sender `node_id`. **MUST** match the `node_id` declared in the connection handshake ([§4.3](#43-duplicate-connection-deduplication)) |
| `pattern` | string \| null | Optional | `null` | **Routing key**: which communication pattern this signal belongs to. If a registered pattern matches, the signal is handed to that pattern; otherwise the default core dispatch applies |
| `target` | string \| null | Optional | `null` | Target `node_id`. Filled in for point-to-point interaction; **MUST NOT** be filled in for a broadcast (`signal`) |
| `path` | string \| null | Optional | `null` | Logical path, used for publish/subscribe ([publish-subscribe](patterns/publish-subscribe.md)). **MUST** conform to [§2.4](#24-path-syntax) |
| `reqid` | string \| null | Optional | `null` | Request ID, used to correlate a response back to its request ([§5](#5-requestreply-correlation-reqid)) |
| `payload` | object | Optional | `{}` | Payload. Its semantics are decided jointly by `type` + `pattern` |
| `timestamp` | number | Optional | The sender's current time | Send time, Unix seconds (floating point) |

**The `pattern` field is a central design point of MSP.** It encodes "which communication pattern this signal belongs to" explicitly into the signal itself, so dispatch at the protocol layer needs only one decision — "look up the table by `pattern` and route" — and **does not need to understand the semantics of any specific pattern**. This is why the pattern layer can be extended with zero change, and it is the fundamental difference at the envelope layer between MSP and protocols that use a single `method` string to serve as both routing key and name (such as JSON-RPC).

### 2.2 Core signal types

The following 9 types (`ping` / `pong` count as one each) are **handled by the protocol layer itself**. Their **ownership** is decided by `pattern`: a message with an empty `pattern` takes the core path of the protocol layer, and its semantics and payload are frozen by this specification and **MUST NOT** be rewritten by a pattern; **a message of the same name that carries a non-empty `pattern` is not on the core path**, and is defined by that pattern itself (see "Pattern-private types" below, and the instance in [multi-round.md](patterns/multi-round.md) — it uses `tool_call` / `tool_result` as its own message types, with a payload that differs slightly from the core).

| `type` | Category | Has `reqid` | Description |
|---|---|---|---|
| `hello` | request | No | Handshake request; `payload.manifest` carries the manifest |
| `ack` | response | No | Handshake reply; `payload.manifest` carries the manifest |
| `ping` | request | No | Liveness probe request |
| `pong` | response | No | Liveness probe reply |
| `signal` | notification | No | Publish one data signal: `path` + `payload` |
| `tool_call` | request | **Yes** | Tool call request: `payload.tool` / `payload.args` |
| `tool_result` | response | **Yes** | Tool call result: `payload.content` / `payload.structuredContent` / `payload.error` |
| `manifest_update` | notification | No | Manifest push: `payload.manifest` |
| `error` | notification | As applicable | Error notification: `payload.code` / `payload.message`; when it replies to a request it **SHOULD** fill in that request's `reqid` |

**Category rules** (isomorphic to MCP's requests / responses / notifications trichotomy):

- `reqid` empty → **notification**: one-way; the receiver **MUST NOT** send a response to it;
- `reqid` non-empty and the type is a request type → **request**: the receiver **MUST** eventually send the corresponding response or an `error`;
- `reqid` non-empty and the type is a response type → **response**: used only to wake the caller that is waiting.

The reference implementation states the current criteria through two predicates, `is_request()` / `is_response()`: request types = `tool_call` / `hello` / `ping`; response types = `tool_result` / `ack` / `pong`. Note that they **are criteria, not mechanism** — routing does not depend on these two predicates.

**Pattern-private types**: a pattern **MAY** define its own signal types (such as `input_required`, `task_submit`). There are three rules:

1. It **MUST** carry a non-empty `pattern` as well; otherwise the receiver has no way to route it;
2. It **MAY** reuse the **name** of a core type (`msp/multi-round` reuses `tool_call` / `tool_result`), but the message **MUST** carry this pattern's `pattern`, and the shape of its `payload` **is defined by that pattern** — so on reading a message with `type="tool_result"` an implementation **MUST** first decide from `pattern` which semantic path it belongs to, and **MUST NOT** apply the core payload table unconditionally;
3. The `msp/` prefix namespace is reserved by this specification. Third-party patterns **MUST** add their own prefix to their types, to avoid name collisions across patterns — because two patterns with different `pattern` values **MAY** safely use a type of the same name (the routing key differs, see [patterns.md §3](patterns.md#3-routing-contract)).

### 2.3 Lenient reading

The MSP envelope **MUST** be processed as a "lenient reading" (Postel's principle); this is the precondition for interoperability:

| Situation | What **MUST** happen |
|---|---|
| An undefined field appears | Ignore it; **MUST NOT** report an error |
| `pattern` points at an unregistered pattern | Treat it as having no `pattern` and take the default core dispatch; **MUST NOT** drop the connection |
| `type` has an unknown value | **SHOULD** reply with `error` (`code` = `-32600`), filling in the original `reqid`; **MUST NOT** drop the connection |
| A content block of unknown type | Pass it through to the upper layer unchanged ([schema.md](schema.md#content-blocks-contentblock)) |
| `payload` is missing a field | The missing field takes that type's default value; **MUST NOT** crash because a field is missing |

**Forbidden behaviour**: closing a connection because of a content problem in any **single message**. Connections are closed only by a transport error, by heartbeat liveness loss or by deduplication arbitration ([§4](#4-connection-lifecycle)). The reason: a message error is an application-layer problem, whereas the connection is a resource shared by the whole node; tearing down the entire connection over one bad message would also break other patterns and in-flight requests on that peer.

### 2.4 Path syntax

`path` **MUST** conform to the following grammar:

```text
path    = segment ( "." segment )*
segment = 1*( ALPHA / DIGIT / "_" / "-" )
```

**Layering convention: domain first** — `<domain>.<entity>.<action>`, with the domain first.

| Level | Meaning | Example |
|---|---|---|
| domain | stable, function-oriented classification | `notify`, `system`, `ai`, `sensor` |
| entity | where the signal comes from, or what it is about | `web`, `file`, `state`, `temperature` |
| action | what actually happened | `download`, `modified`, `progress` |

`notify.web.download` (rather than `web.notify.download`): the domain is a stable, function-oriented classification, while the entity is a variable, implementation-oriented source. With the domain first, a receiver can capture all present and future notifications once and for all with `notify.**`, without changing its filter rules when a new source appears.

**`path` and `pattern` are two different concepts** and **MUST NOT** be confused: `path` is the logical address of a signal (a dot-separated hierarchy), while `pattern` is a pattern identifier (a slash-separated global namespace, such as `msp/multi-round`).

---

## 3. Encoding and decoding

### 3.1 Wire format

`Signal` **MUST** be encoded as a **UTF-8-encoded JSON object**:

```python
# encode (reference implementation protocol._encode)
json.dumps(signal.to_dict(), ensure_ascii=False).encode("utf-8")
```

This yields three normative requirements:

1. **Field names use snake_case** (the keys of `to_dict()` are the on-wire field names). This is where the two naming schemes part ways with the camelCase inside `Manifest`: **the envelope is snake, while the manifest and the inside of `payload` are mostly camel** ([schema.md](schema.md#type-notation-conventions)).
2. **Non-ASCII characters are sent as raw UTF-8 bytes** and **MUST NOT** be escaped as `\uXXXX`. The receiver **MUST** decode as UTF-8. This lets packet captures and logs be read directly for Chinese payloads.
3. **`payload` MUST be a JSON object** (it may hold arbitrarily nested values) and **MUST NOT** be an array or a scalar. When an array has to be sent, wrap it in a key.

**One message, one frame**: an envelope **MUST NOT** be split across several transport frames, and a transport frame **MUST NOT** contain several envelopes — framing is the transport layer's job ([transports.md](transports.md#31-framing)). **MUST NOT** compress `payload` separately; large objects go through `blob_ref` to a dedicated channel ([schema.md](schema.md#content-blocks-contentblock)).

### 3.2 The semantic boundary of `timestamp`

`timestamp` is a reading of the **sender's local clock**, used for observation and diagnosis.

- It **SHOULD** be filled in; the receiver **MAY** ignore it.
- It **MUST NOT** be used for causal ordering, deduplication, idempotency decisions or timeout computation — different nodes' clocks are **not guaranteed** to be synchronised, and may have an arbitrary offset across machines.
- A scenario that needs a freshness judgement (such as declaration expiry) measures the locally observed interval with the **receiver's own clock**, rather than comparing absolute `timestamp` values ([discovery.md](discovery.md#32-lease-and-ttl)).

---

## 4. Connection lifecycle

### 4.1 State machine

```text
   ┌──────────┐  open TCP/WS/UDS link   ┌─────────────┐
   │  Idle    │ ──────────────────────► │ Connected   │
   └──────────┘                         │ (unbound)   │
                                        └──────┬──────┘
                        ┌──────────────────────┴──────────────────────┐
                        │ Dialer: send HELLO, wait for ACK            │
                        │ Acceptor: wait HELLO, record manifest, ACK  │
                        └──────────────────────┬──────────────────────┘
                                               ▼
                                        ┌─────────────┐
        ┌──── dedup drops one ◄──────── │  Handshake  │ ────► heartbeat PING/PONG
        │                               │  (active)   │
        ▼                               └──────┬──────┘
  ┌──────────┐ transport error / peer silent / │
  │  Closed  │ ◄──── stop() / peer closed ─────┘
  └──────────┘
        │
        └──► cleanup: connections / peer_manifests / _last_seen
              wake every in-flight request on that peer with ToolResult(error="connection closed")
              fire on_disconnected(peer_id)
```

### 4.2 Handshake

The handshake is a **two-way capability exchange**: right after the connection is established, both sides exchange their capability manifests. It **MUST** be the first pair of messages after the connection is established; any other message **MUST NOT** be sent before the handshake.

```text
  Dialer                                      Acceptor
      │                                          │
      │  ── hello  {payload.manifest} ─────────► │
      │                                          │  record peer_manifests[peer]
      │                                          │  start read loop
      │  ◄──────── ack  {payload.manifest} ───── │
      │                                          │
      │  record peer_manifests[peer]             │
      │  start read loop                         │
      ▼                                          ▼
```

Normative provisions:

1. The initiator **MUST** open the handshake with `hello`, and `payload.manifest` **MUST** be the sender's current manifest ([schema.md](schema.md#manifest)).
2. The acceptor **MUST** first check that the first message is `hello`; if it is not, it **MUST** close the connection. The reference implementation raises an error here and closes.
3. If the acceptor accepts the connection, it **MUST** reply with `ack`, carrying its own manifest in the same way.
4. Both sides **MUST** consider the peer usable only after the peer's manifest has arrived (`peer.manifest` non-empty).
5. `hello` / `ack` **MUST** declare the sender's `node_id` in `source`; that value then becomes the peer identity of this connection (`peer_id`).
6. The handshake **MUST NOT** carry a `reqid` (the capability exchange is a connection-level event, not a request/reply).

### 4.3 Duplicate-connection deduplication

**Why it is needed**: discovery is **symmetric** — while A discovers B, B discovers A, so both may dial each other at the same time, and two connections then exist between the same pair of nodes. Two connections cause duplicated broadcast delivery and split request state, so they **MUST** be arbitrated down to one.

**Arbitration rules**:

1. **The first connection is registered unconditionally**, whatever its direction. Direction arbitration takes effect only when "a connection for the same `peer_id` already exists".
2. When a connection already exists, the lexicographic order of `node_id` decides the **canonical direction**: the side with the smaller `node_id` **MUST** be the initiator (dialer).
   ```python
   canonical_is_outbound = (self.node_id < peer_id)
   ```
3. If an incoming connection matches the canonical direction → it **replaces** the old connection, and the old connection is closed (that is, the "smaller ID dials" connection wins).
4. If an incoming connection does not match the canonical direction → the **new** connection is closed and the old one is kept.

**A consequence to note (acceptor's view)**: for an **inbound** connection judged to be in the non-canonical direction, the acceptor closes it directly and **does not reply `ack`**.

**A consequence to note (initiator's view)**: the initiator therefore sees a **connection close** on `receive()`, not an explicit error message. The reference implementation classifies it as "peer unreachable" and writes a connection cooldown (`connect_backoff`, 5 s by default).

**This is existing behaviour, not a suggested implementation**: two nodes that dial each other simultaneously will still end up connected (the canonical connection in the other direction gets established), but **the discarded dial leaves behind a harmless cooldown record**. An implementer that adopts a different deduplication algorithm (for example keeping one by an agreed rule after the connection is established, and **closing the loser gracefully with an error**) **MUST** ensure: in a steady state there is only one active connection between the same pair of nodes, and both sides agree on "which one is kept" — otherwise each side keeps one connection, and broadcasts are delivered twice in a split state.

**Self-protection on disconnect**: when the read loop ends it reports a disconnect, but it **MUST** check "is the connection currently registered still this one of mine". If that connection has already been replaced by a new one, it **MUST NOT** clear the state — otherwise the disconnect of the old connection would wrongly delete the state of the new one.

### 4.4 Manifest exchange and update

| Occasion | Mechanism |
|---|---|
| Connection established | `payload.manifest` of `hello` / `ack` |
| Change while running | `manifest_update`, broadcast to all connected peers |
| Cached lookup | The node's locally stored `peer_manifests[peer_id]` |

Normative provisions:

1. `Manifest.version` **MUST** increase monotonically ([schema.md](schema.md#manifest-changes-and-version)). Any operation that changes the content of the manifest **MUST** increment it.
2. On receiving `manifest_update`, the receiver **MUST** replace its local copy only when `new_version > current_version`; otherwise it **MUST** discard the update. This keeps out-of-order pushes from rolling the state back.
3. `manifest_update` **MUST NOT** carry a `reqid` and **MUST NOT** require a reply; capability synchronisation is a one-way, best-effort notification.
4. A node **MUST NOT** assume that the peer has received a `manifest_update` it sent. When strong synchronisation is needed, use a tool call or a fresh handshake as the reference point.

### 4.5 Heartbeat and liveness-loss detection

| Parameter | Default | Meaning |
|---|---|---|
| `heartbeat_interval` | `15.0` s | PING period of the heartbeat thread |
| `heartbeat_timeout` | `45.0` s | No message of **any** kind received for longer than this counts as liveness loss |

```text
  every 15 s                    every connected peer
     │   ── ping {target: peer} ────────► │
     │  ◄─────────── pong ─────────────── │
     │                                    │
  every 15 s, check _last_seen:
     now - last_seen(peer) > 45 s  →  liveness loss, close the connection
```

Normative provisions:

1. A node **SHOULD** send `ping` periodically (with `target` pointing at a specific peer).
2. On receiving `ping` it **MUST** reply with `pong`, and `pong.target` **MUST** be `ping.source`.
3. **The liveness criterion is "the arrival of any message", not "receipt of `pong`".** The reference implementation refreshes `last_seen` whenever **any** message arrives in the read loop. This means an implementation that keeps publishing signals but never answers pong can survive — lenient treatment; it is not a violation.
4. After liveness loss is detected, the connection **MUST** be closed and the cleanup of [§4.6](#46-close-and-cleanup) performed; it **SHOULD** be logged.
5. The heartbeat **MUST NOT** be used as a judgement of "peer application health" — it only judges whether the link still works. A peer stuck in a long task will still answer pong.

### 4.6 Close and cleanup

When a connection closes (transport error, heartbeat liveness loss, `stop()`, or the peer closing), the following **MUST** be done atomically:

1. remove the peer from `connections`;
2. remove its manifest from `peer_manifests`;
3. remove its record from `_last_seen`;
4. **wake every in-flight request on that peer** and return a `ToolResult(error=...)` — **MUST NOT** leave the caller blocked for ever;
5. fire the `on_disconnected(peer_id)` callback;
6. close the underlying connection.

**Item 4 is the most important item in this section.** It is "error as value" showing up at the connection layer ([request-reply.md §6](patterns/request-reply.md#61-errors-as-values)): the disappearance of a peer is a **value**, not an exception, and the caller **MUST** be able to receive it and keep running.

**When a node stops** (`stop()`), the same cleanup as for closing a single connection **MUST** be applied to every connection; in addition it **MUST** stop the heartbeat thread, withdraw its announcements and close every listening socket.

---

## 5. Request/reply correlation (`reqid`)

### 5.1 Generation and lifetime

| Item | Provision |
|---|---|
| Generated by | **the side that initiates the request** |
| Format | A 16-character lowercase hexadecimal string (`uuid4().hex[:16]`), such as `"3f2a91c0d4e8b7a5"` |
| Uniqueness | **MUST NOT** be reused **within the lifetime of the same connection** |
| Reply obligation | The receiver **MUST** fill the `reqid` back in, unchanged, in the response |
| Deregistration | The initiator **MUST** deregister locally when the response arrives, on timeout, or when the connection breaks |
| Timeout | The initiator's responsibility; `5.0` s by default. On timeout it **MUST** deregister and **MUST** return an error value to the caller |

### 5.2 Correlation rules

```text
  Caller                                        Callee
     │                                             │
     │   1. reqid = newly generated                │
     │   2. pending_calls[reqid] = (event, slot)   │
     │   ── tool_call {reqid, payload} ──────────► │
     │                                             │  3. run concurrently (separate thread)
     │                                             │  4. write the result back
     │  ◄─────────── tool_result {reqid} ───────── │
     │   5. match by reqid → write slot → wake     │
     │   6. deregister, return ToolResult          │
     ▼                                             ▼
```

Normative provisions:

1. Responses **MUST** be matched by `reqid` and **MUST NOT** be matched in order of arrival — a connection **MAY** carry any number of concurrent in-flight requests, and their responses **MAY** come back out of order.
2. On receiving a response with an **unknown** `reqid`, the receiver **MUST** drop it silently (it **SHOULD** log it). Typical causes are that the request has already timed out and been deregistered, or that the process has just restarted. It **MUST NOT** break the connection or return an error because of this.
3. `reqid` **MUST NOT** be used on `hello` / `ack` / `ping` / `pong` / `signal` / `manifest_update` — these are notifications or connection-level interactions. `error` **MAY** carry a `reqid` to indicate which request it replies to.
4. A pattern **MAY** introduce its own correlation identifier (such as `msp/task`'s `taskId`), but **any interaction that reuses request/reply semantics SHOULD reuse `reqid`** — the follow-up questions of both `msp/multi-round` and `msp/task` carrying the same `reqid` throughout is exactly this point ([multi-round.md](patterns/multi-round.md)).

---

## 6. Error handling

### 6.1 Two error channels

MSP deliberately distinguishes **protocol-level failures** from **tool execution failures**:

| Channel | Carrier | Used for |
|---|---|---|
| Error as value | `tool_result.payload.error` | Tool execution failure, peer unreachable, timeout, disconnection midway |
| `error` signal | `payload.code` + `payload.message` | Protocol-level failure: unknown signal type, invalid arguments, internal error |

**The dividing line**: whether the error is an expected result of **one particular call**. If yes → `tool_result` (the caller gets a value and the program continues); if not (the message as a whole cannot be processed) → the `error` signal.

### 6.2 The `error` signal

```json
{
  "type": "error",
  "source": "node_a",
  "pattern": null,
  "target": "node_b",
  "path": null,
  "reqid": "3f2a91c0d4e8b7a5",
  "payload": { "code": -32600, "message": "unknown signal type: foo" },
  "timestamp": 1791321600.123
}
```

Normative provisions:

1. When replying to a request, `error` **SHOULD** fill in that request's `reqid`.
2. `error` **MUST** carry `payload.code` (an integer) and `payload.message` (a string).
3. On receiving `error`, the receiver **MUST** log it; it **MUST NOT** retry automatically — retry policy belongs to the caller or the pattern layer, and the protocol layer does not do it on their behalf.
4. Error codes take the conventional values of JSON-RPC 2.0, so that the tool-call subset maps directly ([interop.md](interop.md#json-rpc-20-semantic-alignment)):

| `code` | Name | Where it appears |
|---|---|---|
| `-32600` | invalid request | An unknown `type` was received |
| `-32601` | method not found | A tool call points at an unregistered tool |
| `-32602` | invalid params | The arguments do not satisfy the declared `inputSchema` |
| `-32603` | internal error | An exception was thrown during tool execution |
| `-32000` ~ `-32099` | implementation-defined | Reserved for the pattern layer; **SHOULD** be documented in the implementation's documentation |

### 6.3 Cancellation

> **Status**: 🔵 Planned. The protocol layer currently has **no** cancellation mechanism. An implementer **MAY** leave it unimplemented, but once implemented it **MUST** comply with the following provisions.

A new core signal, `cancel`:

| Field | Value |
|---|---|
| `type` | `"cancel"` |
| `target` | **MUST** be the executor of the request being cancelled |
| `reqid` | **MUST** be the ID of the request being cancelled |
| `payload.reason` | Optional, string, a human-readable reason for cancelling |

Normative provisions:

1. Cancellation is **cooperative**: the receiver **SHOULD** stop work as soon as it can, but **MAY** finish the current uninterruptible step before stopping.
2. Cancellation **MUST NOT** be relied upon for correctness — the sender **MUST NOT** assume that the peer has received `cancel`, and **MUST NOT** assume that the peer has stopped.
3. After receiving `cancel`, the receiver **MUST** still send the **terminal response** of that request (a `tool_result` carrying an `error`, or the terminal `task_result` of `msp/task`). In other words: **cancellation changes the result, not the obligation to answer.**
4. For a `cancel` with an unknown `reqid`, the receiver **MUST** ignore it silently.
5. Cancellation in `msp/task` does not go through this signal; it uses the pattern's own `task_cancel` ([task.md](patterns/task.md#8-cancellation)).

### 6.4 Progress

> **Status**: 🔵 Planned.

A new core signal, `progress`:

| Field | Value |
|---|---|
| `type` | `"progress"` |
| `reqid` | **MUST** be the ID of the request being tracked |
| `payload.progressToken` | **MUST**, string, given by the initiator in the request's `payload.progressToken` |
| `payload.progress` | **MUST**, number, the amount completed |
| `payload.total` | Optional, number, the total amount; absent means the total is unknown |

Normative provisions:

1. `progress` is a **notification**: the receiver **MUST NOT** reply to it.
2. `payload.progress` for the same `progressToken` **MUST** be monotonically non-decreasing; the receiver **SHOULD** ignore any message that moves progress backwards.
3. If the initiator did not give a `progressToken` in the request, the executor **MUST NOT** send progress — progress without an identifier cannot be correlated.
4. `progress` **MAY** be dropped or coalesced; it **MUST NOT** be treated as a reliable transport.
5. By default progress does **not** enter the model context; whether to expose it to the model is the host's decision.

### 6.5 Timeouts

> **Status**: 🟡 Partially implemented.

Currently only the **caller-side** timeout is implemented: `call(timeout=5.0)` deregisters locally on timeout and returns `ToolResult(error=...)`.

**Known gaps**: the protocol has **no** notion of a server-side deadline — `tool_call` carries no deadline, so the callee **cannot** know that the caller has given up, and work still running will not be stopped automatically. The remedy is: ① introduce `cancel` ([§6.3](#63-cancellation)); ② or add an optional `payload.deadline` to the request, agreed to be an absolute time on the **sender's clock**, advisory only and **MUST NOT** be treated as a hard constraint (clocks across machines are not synchronised).

---

## 7. Summary of normative provisions

**MUST**:

1. Every message **MUST** be a `Signal` envelope, encoded as a UTF-8 JSON object.
2. `type` and `source` **MUST** be present; `source` **MUST** match the `node_id` declared during the handshake.
3. After a connection is established, the `hello` / `ack` handshake **MUST** complete first, before any other message is exchanged.
4. In a steady state there **MUST** be only one active connection between the same pair of nodes ([§4.3](#43-duplicate-connection-deduplication)).
5. `Manifest.version` **MUST** increase monotonically; only a newer version is accepted.
6. `reqid` **MUST NOT** be reused within a connection; a response **MUST** carry back the `reqid` unchanged.
7. Responses **MUST** be matched by `reqid`, and **MUST NOT** be matched in order of arrival.
8. When a connection closes, every in-flight request on that peer **MUST** be woken with an error value.
9. On receiving `ping`, a node **MUST** reply with `pong`.
10. On receiving an unknown `type`, a node **SHOULD** reply with `error` (`-32600`); it **MUST NOT** break the connection because of it.
11. Unknown fields, unknown patterns and unknown content blocks **MUST** be treated leniently.
12. `payload` **MUST** be a JSON object.

**MUST NOT**:

13. **MUST NOT** close a connection over a semantic problem in one message.
14. **MUST NOT** use `timestamp` for ordering, deduplication or timeout computation.
15. **MUST NOT** carry notification-type messages with a `reqid`.
16. **MUST NOT** set `target` on a `signal` broadcast.
17. On receiving `error`, **MUST NOT** retry automatically.
18. The `msp/` prefix **MUST NOT** be taken by third-party patterns.

**SHOULD**:

19. `manifest_update` **SHOULD** be pushed as soon as possible after a capability change.
20. Liveness loss **SHOULD** be judged by "the arrival of any message", not by `pong` alone.
21. A response or `cancel` with an unknown `reqid` **SHOULD** be ignored silently and logged.

---

## 8. Security considerations

1. **`source` is not trustworthy.** `source` is a field the sender **reports about itself**. The protocol layer currently **does not check** it against the identity established by the connection handshake (because the trust boundary simply is the reach of the transport, see [security.md](security.md#22-threat-model)). A cross-machine deployment **MUST** bind identities during the handshake; otherwise any node that can connect can impersonate an arbitrary `node_id` and disturb deduplication and the discovery registry.
2. **`reqid` is a local identifier, not an authorization credential.** Holding a certain `reqid` **MUST NOT** be taken as proof of the right to receive that response; who may receive a response is decided by the connection identity.
3. **`manifest` is self-description, not a promise.** A node **MAY** announce tools in its manifest that it does not actually implement. Security decisions **MUST NOT** rely on the peer's manifest; they **MUST** rely on the local authorization table ([security.md](security.md#3-authorization)).
4. **`payload` has no size limit.** The protocol layer sets no message ceiling; implementations **SHOULD** impose a limit in the transport layer or before decoding, otherwise a single oversized frame can exhaust memory.
5. **`error.message` may leak internal information** (such as exception text). Implementations **SHOULD** separate "the error text shown to others" from "the error text written to the log".
6. **A heartbeat is not proof of liveness.** A heartbeat reflects the link only; a compromised node that still answers pong is indistinguishable at the protocol layer from a healthy one.

---

## 9. Known gaps

| # | Gap | Consequence | Remedy |
|---|---|---|---|
| 1 | ~~no read timeout during the handshake~~ ✅ **Fixed** | When a peer accepted the TCP connection but never sent `ack`, the initiator's `receive()` used to **block that thread for ever** | `Connection.set_read_timeout()` + `MSPProtocol.handshake_timeout` (10 s by default, overridable through the node `config`): on timeout it ends with `ConnectionClosed`, closes the connection and counts as unreachable |
| 2 | No cancellation mechanism | After the caller times out and gives up, the callee's work runs to the end, burning compute for nothing | Implement `cancel` ([§6.3](#63-cancellation)) |
| 3 | No progress reporting | A long task is a black box to the caller, which can only poll — exactly the shape this protocol sets out to remove | Implement `progress` ([§6.4](#64-progress)) |
| 4 | No backpressure / flow control | When `send()` blocks on a slow peer it holds up the broadcast fan-out loop | Add a send-queue ceiling and a drop policy in the transport layer; or introduce window negotiation |
| 5 | No message size ceiling | Oversized frames create a memory risk | Set a limit before decoding and reply with `error` |
| 6 | No server-side deadline | See [§6.5](#65-timeouts) | Design it together with `cancel` |
| 7 | Dedup drops a connection without replying `ack` | The initiator can only infer failure from the connection close, and a harmless cooldown record is left behind | Reply with an `error` explaining why, before closing |
| 8 | `error` carries no structured detail | The caller can read only a string | `payload.data` carries structured detail (isomorphic to MCP's `error.data`) |
| 9 | The one-shot `stream`/`blob` channel is undefined | Large objects can only be embedded as Base64, inflating them by 33% | `blob_ref` + `msp/streaming` ([patterns.md §6](patterns.md#7-planned-patterns)) |

---

## 10. Reference implementation map

| Provision | Source file | Symbol |
|---|---|---|
| `Signal` envelope | `src/msp/core/signal.py` | `Signal`, `Signal.make`, `to_dict` / `from_dict`, `is_request` / `is_response` |
| Signal type constants | `src/msp/core/signal.py` | `SignalType` |
| Encoding and decoding | `src/msp/protocol/protocol.py` | `_encode`, `_decode` |
| Handshake | Same as above | `handshake_outbound`, `handshake_inbound` |
| Deduplication arbitration | Same as above | `_finish_handshake` |
| Manifest push and version check | Same as above | `push_manifest`, `_on_manifest_update` |
| Dispatch and lenient reading | Same as above | `_dispatch`, `_dispatch_core`, `_reply_error` |
| Heartbeat and liveness loss | Same as above | `_heartbeat_loop`, `_last_seen`, `heartbeat_interval` / `heartbeat_timeout` |
| Close and cleanup | Same as above | `_handle_disconnect`, `stop` |
| `reqid` correlation | Same as above | `pending_calls`, `call`, `_on_tool_result` |
| Timeout | Same as above | `call(timeout=...)` |
| Error as value | `src/msp/core/node.py` | The `except` branches of `MSPNode.call`, `PeerUnavailable`, `UnknownPeer` |
| Error value carriers | `src/msp/core/content.py` | `ToolResult`, `ToolError` |

---

**See also**: [architecture.md](architecture.md) (layering and roles) ｜ [patterns.md](patterns.md) (pattern routing) ｜ [transports.md](transports.md) (framing) ｜ [schema.md](schema.md) (authoritative field definitions) ｜ [interop.md](interop.md) (the mapping to JSON-RPC)
