# MSP Specification — Model Sensing Protocol Specification

| | |
|---|---|
| **Protocol revision** | `2026-10-10` |
| **Corresponding implementation** | `msp-py` 0.1.0 (Alpha) |
| **Document status** | Draft — covers every implemented layer and fully defines the planned capabilities (each provision carries a status marker) |
| **Normative language** | RFC 2119 (see [Normative language](#2-normative-language)) |

> **Everything is a node. Everything is a signal. Every layer is extensible.**

This directory is the MSP **specification** (normative): it defines the behaviour that interoperability requires — two parties implementing independently can interoperate simply by implementing this specification.

Outside the specification there are two further classes of document, with the following division of labour:

| Document | What it answers | Nature |
|---|---|---|
| **This directory (`docs/spec/`)** | "What an implementation **MUST** do in order to interoperate" | Normative |
| [Design document](/design) | "Why it is designed this way, and what was given up" | Explanatory |
| [Technical whitepaper](https://github.com/hxh230802/MSP/blob/master/docs/whitepaper.md) | "What problem it solves, and how it relates to MCP/A2A" | Explanatory |
| [README](https://github.com/hxh230802/MSP/blob/master/README.zh-CN.md) | "How to use it" | Tutorial |
| `src/msp/` | The reference implementation itself | Source of truth |

**Handling conflicts between specification and implementation**: where a provision disagrees with the reference implementation, this specification prevails and the disagreement is recorded as a defect; the reference implementation is the first implementation of the specification, not the specification itself.

---

## 1. Revision history

MSP protocol revision numbers follow an **ISO date** (`YYYY-MM-DD`), consistent with MCP's revision policy: a revision number identifies **a set of interoperable message contracts**, not a particular code release.

| Revision | Date | Changes |
|---|---|---|
| `2026-10-10` | 2026-10-10 | First specification draft. Freezes the `Signal` envelope, the core signal types, the handshake and deduplication rules, the error codes, the pattern routing contract, the `Endpoint` and declaration file formats, the path matching algorithm, and the `msp/task` and `msp/multi-round` messages; fully defines the planned capability surface, the security model and the QUIC / DHT extension points. |

### Versioning policy

1. A **revision number change** **MUST** be accompanied by a new row in the [revision history](#1-revision-history); a change without a date may land on explanatory prose only.
2. **Backwards-compatible additions** (a new optional field, a new pattern ID, a new signal type) are given within the same revision in "append" form, and the receiver **SHOULD** ignore unknown fields and the semantics that unknown signal types require (see [Lenient reading](#7-conformance)).
3. **Incompatible changes** (changing field semantics, changing the matching algorithm, changing the handshake order) **MUST** get a new revision number, and **MUST** have their extent of impact marked in the revision history.
4. **Pattern ID namespace**: the `msp/` prefix is reserved by this specification; third-party patterns **MUST** use a prefix of their own (such as `acme/streaming`) and **MUST NOT** occupy `msp/`.

---

## 2. Normative language

Keywords in this specification are interpreted per RFC 2119. Chinese provisions use the left column of the table below, equivalent to the English keywords in the right column; the two forms may be cited interchangeably when implementing.

| Chinese | English | Meaning |
|---|---|---|
| **必须** | MUST | Absolute requirement. Failing it means non-conformance with this specification |
| **不得** | MUST NOT | Absolute prohibition |
| **应当** | SHOULD | To be followed unless a valid reason exists; a deviation **SHOULD** be justifiable |
| **不应当** | SHOULD NOT | To be avoided unless a valid reason exists |
| **可以** | MAY | Optional; an implementation may choose freely |

Only **bold** keywords in the body text carry normative force; unbolded words of the same kind (such as "needs to" and "it is advisable") are prose and constitute no requirement.

**Status markers**: every page and every section carries a status marker, from which the reader judges whether the provisions can be verified against the current implementation.

| Marker | Meaning |
|---|---|
| ✅ **Implemented** | Landed in the reference implementation; the provisions can be verified directly |
| 🟡 **Partially implemented** | The main path has landed, with the known gaps listed in the provisions |
| 🔵 **Planned** | The provisions are fully defined but not yet landed in the reference implementation; an implementer **MAY** leave them unimplemented, but once implemented they **MUST** comply with the provisions |

---

## 3. Specification structure

| Page | Content | Status |
|---|---|---|
| [architecture.md](architecture.md) | Layered architecture, the four core concepts, inter-layer contracts, Preset and roles, capability negotiation | ✅ Implemented |
| [base-protocol.md](base-protocol.md) | `Signal` envelope, encoding and decoding, connection lifecycle, handshake and deduplication, heartbeat, `reqid` correlation, error codes | ✅ Implemented |
| [transports.md](transports.md) | Transport abstraction, TCP / WebSocket / UDS / QUIC framing and address formats | ✅ Implemented (QUIC 🔵) |
| [discovery.md](discovery.md) | Discovery / Presence contract, shared directory declaration file, lease TTL, HTTP registry, DHT | ✅ Implemented (DHT 🔵) |
| [patterns.md](patterns.md) | Pattern layer contract, `pattern_id` and routing, `fallback_to` / `conflicts_with`, `install_api`, planned patterns | ✅ Implemented |
| [patterns/request-reply.md](patterns/request-reply.md) | Core pattern: `tool_call` / `tool_result`, `reqid` correlation, timeouts | ✅ Implemented |
| [patterns/publish-subscribe.md](patterns/publish-subscribe.md) | Core pattern: broadcast, path syntax, wildcard matching algorithm, local filtering | ✅ Implemented |
| [patterns/multi-round.md](patterns/multi-round.md) | `msp/multi-round`: follow-up questions during execution, `input_required` / `input_response` | ✅ Implemented |
| [patterns/task.md](patterns/task.md) | `msp/task`: task state machine, artifacts, observer broadcast, A2A equivalence mapping | ✅ Implemented |
| [capabilities.md](capabilities.md) | Signal definitions for resources / prompts / sampling / elicitation / roots | 🔵 Planned |
| [security.md](security.md) | Trust boundary, threat model, TLS, node authentication, authorization (`grants`) | 🟡 Partially implemented |
| [interop.md](interop.md) | MCP ⊆ MSP, the `msp.mcp` adapter layer, A2A mapping, JSON-RPC 2.0 semantic alignment | ✅ Implemented (stdio + Streamable HTTP carrier + tools) |
| [schema.md](schema.md) | Data model reference: complete field definitions in JSON form | ✅ Implemented |

---

## 4. Glossary

| Term | English | Definition |
|---|---|---|
| **Node** | node | A communication participant with a globally unique `node_id`. No client or server role is presupposed |
| **Signal** | signal | The smallest data atom of communication; handshakes, subscriptions, tool calls, tasks and heartbeats are all instances of it |
| **Pattern** | pattern | The semantic set of one class of interaction (request/reply, publish/subscribe, multi-round exchange, task delegation…), identified by `pattern_id` |
| **Manifest** | manifest | The declaration a node makes about itself: supported patterns, published paths, offered tools/resources/prompts, role capability bits |
| **Endpoint** | endpoint | The transport identity of a node: `{transport_type, address, node_id}` |
| **Path** | path | The logical address of a signal, segmented by dots (`notify.web.download`), supporting `*` / `**` wildcards |
| **Discovery** | discovery | "How do I find others": produces an `Endpoint` |
| **Presence** | presence | "How do others find me": writes the `Endpoint` into some shared channel |
| **Transport** | transport | A connection abstraction that only moves bytes, with no awareness of message semantics |
| **Preset** | preset | The combination of discovery / presence / transport / pattern / capability bits enabled for a role |
| **Neighbour** | neighbour | A peer that has been discovered (not necessarily connected) |
| **Peer** | peer | A read-only aggregate view of a neighbour (endpoint + connection + manifest) |
| **Reply channel** | reply channel | An interaction path initiated by this node to which the peer replies; allowed by default in the authorization model |

---

## 5. Specification constants at a glance

The constants below mean the same thing on every page, and the individual pages do not define them again. **They are part of the interoperability contract and MUST NOT be changed at will.**

### 5.1 Core signal types (`Signal.type`)

There are **9** core signal types in total (8 rows in the table below, because `ping` and `pong` share one row). The `payload` of `ping` / `pong` is `{}`; for the remaining types the payload fields are as defined on their respective pages.

| `type` | Direction | Has `reqid` | Semantics | Page |
|---|---|---|---|---|
| `hello` | Initiator → Acceptor | No | Handshake request; `payload.manifest` carries the manifest | [base-protocol](base-protocol.md#42-handshake) |
| `ack` | Acceptor → Initiator | No | Handshake reply; `payload.manifest` carries the manifest | Same as above |
| `signal` | Any → all connected peers | No | Publish one data signal, `path` + `payload` | [publish-subscribe](patterns/publish-subscribe.md) |
| `tool_call` | Caller → callee | **Yes** | Tool call request, `payload.tool` / `payload.args` | [request-reply](patterns/request-reply.md) |
| `tool_result` | Callee → caller | **Yes** | Tool call result, `payload.content` / `structuredContent` / `error` | Same as above |
| `manifest_update` | Any → all connected peers | No | Manifest push; `payload.manifest` carries the **complete manifest** (not a delta) | [base-protocol](base-protocol.md#44-manifest-exchange-and-update) |
| `ping` / `pong` | Both directions | No | Heartbeat liveness probe | [base-protocol](base-protocol.md#45-heartbeat-and-liveness-loss-detection) |
| `error` | Any | As applicable | Error notification, `payload.code` / `payload.message` | [base-protocol](base-protocol.md#6-error-handling) |

**🔵 Planned core signal types** (provisions in [base-protocol.md §6.3–6.4](base-protocol.md#63-cancellation)):

| `type` | Category | Has `reqid` | Semantics |
|---|---|---|---|
| `cancel` | Request | **Yes** | Requests cancellation of an in-flight call. Cooperative: it does **not** guarantee that the peer actually stops, and does **not** relieve the peer of the duty to reply |
| `progress` | Notification | **Yes** | Progress report, correlated by the `progressToken` supplied by the caller; **MUST NOT** be treated as a reliable transport |

A pattern may define **pattern-private signal types** (such as `input_required`, `task_submit`). They share the same `type` field space with the core types, but **MUST** also carry a `pattern` field so that they can be routed; a pattern outside the `msp/` namespace **MUST** prefix its own types, to avoid name collisions across patterns.

### 5.2 Pattern IDs

| `pattern_id` | Status | Description |
|---|---|---|
| `msp/request-reply` | ✅ Core | `call()` / `tool_call` / `tool_result` |
| `msp/publish-subscribe` | ✅ Core | `publish()` / `signal` + local filtering at the receiver |
| `msp/multi-round` | ✅ Extension | Follow-up questions during execution |
| `msp/task` | ✅ Extension | Task state machine + artifacts |
| `msp/streaming` | 🔵 Planned | `stream_start` / `stream_chunk` / `stream_end` |
| `msp/callback-push` | 🔵 Planned | Callback-style delivery for long tasks |
| `msp/async-polling` | 🔵 Planned | Explicit polling semantics (interoperability fallback) |

`msp/request-reply` and `msp/publish-subscribe` are **core patterns**: implemented directly in the protocol layer, because signal routing, `reqid` correlation and broadcast fan-out depend on protocol-layer state. The rest are **extensible patterns**: one standalone file plus one registry entry, without touching the protocol core.

### 5.3 Naming rules

| Object | Separator | Format | Example |
|---|---|---|---|
| `node_id` | none | `[a-z0-9_-]+` | `file_monitor` |
| Signal path | `.` | `segment(.segment)*` | `notify.web.download` |
| Pattern ID | `/` | `[namespace/]name` | `msp/multi-round` |
| Tool name | none | `[a-z0-9_-]+` | `get_weather` |
| Task ID | none | implementation-defined | `task-3f2a…` |

**Path layering follows "domain first"**: `<domain>.<entity>.<action>`, with the domain in front (`notify.web.download`, not `web.notify.download`). The domain is the stable, function-oriented classification; the entity is the variable, implementation-oriented source. With the domain in front, a receiver can capture every existing and future notification once and for all with `notify.**`.

Using a slash in a Pattern ID is a requirement of the **global namespace** (a reverse-domain prefix) and is a different concept from the dot layering of a Signal path; the two **MUST NOT** be mixed.

### 5.4 Error codes

Error codes take JSON-RPC 2.0's conventional values, so that the tool-call subset maps directly in semantics (see [interop](interop.md#json-rpc-20-semantic-alignment)).

| `code` | Name | Use in this specification | Reference implementation status |
|---|---|---|---|
| `-32600` | Invalid request | Returns `error` on an unknown `type` | ✅ Emitted by the core (fallback branch of `_dispatch_core`, code as a literal) |
| `-32601` | Method not found | A tool call names an unregistered tool | 🟡 **Not emitted by the core**: the error goes as a string into `tool_result.payload.error` (`Unknown tool: X`), without a `code`; the code currently appears only in the JSON-RPC bridge of `msp.mcp` |
| `-32602` | Invalid params | Arguments do not satisfy the tool's declared `inputSchema` | 🟡 **Not emitted by the core**: the core performs no runtime schema validation; mismatched arguments surface as a `TypeError` → `payload.error` |
| `-32603` | Internal error | An exception is thrown during tool execution | 🟡 **Not emitted by the core**: the exception text goes verbatim into `payload.error`, without a `code` |
| `-32000` ~ `-32099` | Implementation-defined | **Authorization denial** already uses `-32000` (see [security](security.md#3-authorization)); an error is returned only when the signal carries a `reqid`, while broadcasts are dropped silently; the pattern layer does not use them yet | ✅ Implemented (`-32000`) |

**Tool execution failure does not carry a `code` inside `tool_result`**: it travels the "error as value" channel ([request-reply §6.3](patterns/request-reply.md#63-failures-on-the-tool-side-and-error-code-ownership)). An implementation therefore **MUST NOT** expect to read a `code` in the `payload`; mapping the `payload.error` string back to an error code is the job of the adapter layer (such as a JSON-RPC bridge).

### 5.5 Role capability bits

| Capability bit | Meaning | How it is exchanged |
|---|---|---|
| `pub` | This node publishes signals | `Manifest.capabilities` |
| `sub` | This node subscribes to signals | Same as above |
| `req` | This node calls other nodes' tools | Same as above |
| `rep` | This node replies to other nodes' calls | Same as above |

Capability bits are **self-description** ("what I claim to be able to do"), strictly separated from **authorization** ("what I allow you to do"). Authorization **MUST NOT** rely on the peer's self-report, and **MUST NOT** be exchanged with the manifest (see [security](security.md#3-authorization)).

### 5.6 Default parameters

| Parameter | Default | Description |
|---|---|---|
| `settle_timeout` | `0.5` s | Upper bound for `start()` / `settle()` to wait for in-flight dials to land |
| `call` timeout | `5.0` s | When not specified explicitly |
| `heartbeat_interval` | `15.0` s | PING period |
| `heartbeat_timeout` | `45.0` s | No message received for longer than this counts as liveness loss |
| `connect_backoff` | `5.0` s | Cooldown after a failed connection |
| `renew_interval` | `10.0` s | Renewal period of the directory declaration lease |
| Declaration lifetime `stale_after` | See [discovery](discovery.md#32-lease-and-ttl) | Expired declarations are dropped |
| `connect_policy` | `eager` | `eager` connects on discovery; `lazy` accepts inbound only and dials on demand |

---

## 6. Relationship to other protocols

| Relationship | Conclusion | Page |
|---|---|---|
| **MCP** | MCP ⊆ MSP: in the tool-call scenario, MCP's behaviour can be mapped into MSP behaviour-preservingly; the converse does not hold | [interop](interop.md#mcp--msp) |
| **A2A** | A2A is a protocol stack rather than a pattern; MSP carries over only its "task semantics", landed as `msp/task` | [patterns/task](patterns/task.md#9-equivalence-mapping-to-a2a) |
| **JSON-RPC 2.0** | The encoding layer does not adopt its envelope, but performs **semantic alignment** on the tool-call subset; interoperation relies on an optional bridge and does not change the core | [interop](interop.md#json-rpc-20-semantic-alignment) |

---

## 7. Conformance

An implementation that claims to conform to MSP revision `2026-10-10` **MUST** satisfy:

1. **Message shape**: it can parse and produce the `Signal` envelope ([base-protocol §2](base-protocol.md#2-the-signal-envelope)), including lenient handling of unknown fields.
2. **Handshake**: it implements the HELLO/ACK exchange and the manifest exchange ([base-protocol §4](base-protocol.md#4-connection-lifecycle)).
3. **Core patterns**: it implements every provision of `msp/request-reply` and `msp/publish-subscribe`.
4. **Routing**: it routes by `Signal.pattern`, and an unknown pattern **MUST NOT** terminate the connection ([patterns §3](patterns.md#3-routing-contract)).
5. **Lenient reading**: for unrecognized fields, signal types, content block types and pattern IDs, it **MUST NOT** treat them as protocol errors and drop the connection ([base-protocol §2.3](base-protocol.md#23-lenient-reading)).
6. **Optional extensions**: extensible patterns, transport backends, discovery mechanisms, the capability surface and security mechanisms are all **optional**; not implementing them is conformant, whereas implementing them **MUST** comply with the corresponding provisions.

The **lowest common denominator for interoperability** is: one TCP connection + the `Signal` envelope + `msp/request-reply`. Any two implementations that satisfy only this much can call each other's tools.

---

## 8. Taking part in evolution

Specification changes follow the order "**change the single authoritative source first, then the prose, then the implementation**", and leave a trace in the [revision history](#1-revision-history):

1. **Change [`schema/<revision>/msp.yaml`](https://github.com/hxh230802/MSP/blob/master/schema/2026-10-10/msp.yaml)** — the single authoritative source of the data model: field names, types, required-ness, defaults, constraints, and the binding of `Signal.type` (+`pattern`) → payload;
2. propose the provision on the corresponding page (with its status marker) — the prose explains "why it is designed this way" and **MUST NOT** copy the field list again (that is exactly where drift comes from);
3. regenerate `schema/<revision>/msp.schema.json` (`tools/gen_schema.py`), and make the **three-way reconciliation** of `tools/check_schema_drift.py` pass: authoritative source ↔ reference implementation ↔ prose pages;
4. update the reference implementation and the tests;
5. add a revision row, marking whether the change is additive or breaking.

> **Why the YAML comes first**: fields are defined only once, in the YAML, and `msp.schema.json`, the field tables on every page of this directory and `tests/test_schema_source.py` are all derived from it or reconciled against it. MCP uses the same shape (`schema.ts` as the source, JSON Schema and documentation as the products); only the host language differs.

Adding a communication pattern **does not need** an amendment to the core pages of this specification: a pattern is an optional extension, so it suffices to register it in [patterns.md](patterns.md#8-pattern-registration) and describe its mapping to other protocols in [interop](interop.md).
