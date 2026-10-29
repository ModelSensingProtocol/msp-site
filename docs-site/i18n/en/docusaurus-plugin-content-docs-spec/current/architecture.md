# Architecture

> **Protocol revision** `2026-10-10` | **Status** ✅ implemented (the QUIC / DHT extension points are 🔵 planned)
>
> This page defines the overall shape of MSP: **the layers and the contracts between them**, **the four core concepts**, **the three orthogonal extension axes**, **roles and presets**, **capability negotiation**, **connection policy and startup timing**, **the Peer view** and **the extension hooks**. It corresponds to the *Architecture* page of the MCP specification — the components and boundaries first, then the message details.

---

## 1. Overview

The MSP architecture is decided by one sentence: **drive the "way of communicating" out of the protocol core and make it a pluggable pattern.**

From that follow a five-layer structure, and four inter-layer contracts **narrow enough to be a single data structure**:

```text
┌─────────────────────────────────────────────────────────────────┐
│ Application layer   MSPNode                                     │
│   @node.tool · @node.signal_source · @node.on · node.publish    │
│   node.call · node.ensure_connected · node.register_pattern     │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Pattern layer       PatternHandler (pattern_id / fallback_to /  │
│                     conflicts_with / on_signal / install_api)   │
│   Request-Reply · PubSub · MultiRound · Task                    │
│   Streaming · CallbackPush · AsyncPolling          (🔵 planned)  │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Protocol layer      MSPProtocol                                 │
│   core signals  HELLO·ACK·PING·PONG·ERROR                       │
│   routing       _dispatch → pattern hit → handler, else core    │
│   conn. mgmt    connections · peer_manifests · pending_calls    │
│   codec         _encode(Signal) → bytes · _decode(bytes) → dict │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Transport layer     TransportRegistry                           │
│   TCPTransport · WebSocketTransport · UDSTransport              │
│   QUICTransport                                   (🔵 planned)   │
│   unified interface Connection.send(bytes) / receive() → bytes  │
│   sends and receives bytes only · unaware of message semantics  │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Discovery / presence layer (orthogonal, freely combinable)      │
│   Discovery: DirectoryScan · ManualConnect · (🔵) DHT            │
│   Presence : DirectoryWrite · ManualAdvertise · (🔵) DHT         │
│   contract  Endpoint = { transport_type, address, node_id }     │
└─────────────────────────────────────────────────────────────────┘
```

### Inter-layer contracts

| Boundary | Contract | Effect |
|---|---|---|
| discovery → transport | only `Endpoint` is passed | changing the discovery mechanism does not change the transport |
| transport → protocol | only `bytes` is passed | adding a transport backend does not change the protocol |
| protocol → pattern | only `Signal` is passed, routed by `pattern` | adding a communication pattern does not change the protocol |
| pattern → application | syntax sugar injected through `install_api(node)` | adding a pattern does not change `MSPNode` |

**These four contracts are the entire mechanism behind "every layer is extensible" in MSP.** Each layer depends on **one data structure** of the layer below, and knows nothing about that layer's implementation details.

### What each layer **MUST NOT** do

| Layer | **MUST NOT** |
|---|---|
| transport layer | parse message content, understand `type` / `pattern`, do reconnection or deduplication |
| protocol layer | understand the semantics of any concrete pattern, know tool names or what a path means, build in TLS / authentication / authorization logic |
| pattern layer | bypass the protocol layer and send or receive bytes directly, change the semantics of `Signal` envelope fields |
| discovery layer | establish connections, assume the peer is necessarily reachable (discovery only produces candidate endpoints) |

The protocol layer **does not know tools, paths or tasks**; it knows only `Signal` and `pattern` — this is why "a tiny protocol core" can hold, and why a third-party implementation needs to understand only [base-protocol.md](base-protocol.md) and [patterns.md §3](patterns.md#3-routing-contract) to interoperate.

---

## 2. The four core concepts

| Concept | Definition | Normative source |
|---|---|---|
| **Node** | A communication participant with a globally unique `node_id`. It **does not presuppose** a client / server role — a node **MAY** publish, subscribe, provide tools and call tools at the same time | [§5](#5-roles-and-presets) |
| **Signal** | The smallest data atom of communication. The unified carrier of every interaction, distinguished only by `type` | [base-protocol.md §2](base-protocol.md#2-the-signal-envelope) |
| **Endpoint** | The transport identity of a node, `{transport_type, address, node_id}`. The discovery layer produces it, the transport layer connects to it | [discovery.md](discovery.md#51-endpoint) |
| **Path** | The logical address of a signal, in dot-separated segments (`notify.web.download`), supporting `*` / `**` wildcards | [publish-subscribe.md](patterns/publish-subscribe.md#3-path-syntax) |

The three design principles are direct corollaries of these four concepts, and also the interpretative frame of this specification:

> **Everything is a node.** Tools, models, sensors, host programs and remote services are all nodes, on equal footing.
> **Everything is a signal.** Handshakes, subscriptions, tool calls, tasks and heartbeats are all signals, differing only in `type`.
> **Every layer is extensible.** Discovery, presence, transport and pattern are all pluggable, without touching the core.

---

## 3. The three orthogonal extension axes

In MSP, "extension" is three unrelated things, **each of them independent** — changing the discovery mechanism does not change the protocol layer, adding a transport backend does not change the protocol layer, and adding a communication pattern likewise does not change the protocol layer:

| Axis | Unit of extension | How to plug in | Cost in the reference implementation |
|---|---|---|---|
| **discovery / presence** | one `Discovery` / `Presence` implementation | register it in `DISCOVERY_REGISTRY` / `PRESENCE_REGISTRY`, name it in the preset | 0 lines of core changes |
| **transport** | one `Transport` implementation | register it in `TRANSPORT_REGISTRY`, name it in the preset | 0 lines of core changes |
| **pattern** | one `PatternHandler` implementation | register it in `PATTERN_REGISTRY`, name it in the preset; the protocol layer routes by looking `pattern` up in a table | 0 lines of core changes |

**"Core changes ≤ 60 lines" is the acceptance criterion of this architecture.** In the reference implementation, the whole cost of making the pattern layer extensible with zero changes is **one table lookup** in the protocol layer ([patterns.md §3](patterns.md#3-routing-contract)); the whole cost of letting any layer inject syntax sugar is about 4 lines in `_install_layer_api` ([§11](#11-the-extension-hook-install_api)).

Adding a communication pattern **does not need** a revision of the core pages of this specification: a pattern is an optional extension, it only needs to be registered in [patterns.md §7](patterns.md#8-pattern-registration) with a statement of its mapping to the others.

---

## 4. Discovery and presence: two orthogonal interfaces

Discovery and presence are **two interfaces pointing in opposite directions and independent of each other**, and **MUST NOT** be merged into a single "node management" abstraction:

| Interface | Question it answers | Artifact / input |
|---|---|---|
| **Discovery** | "How do I find others" | produces `Endpoint` |
| **Presence** | "How do others find me" | consumes `Endpoint`, writes it into some shared channel |

```python
class Discovery(ABC):
    def list_endpoints(self) -> list[Endpoint]: ...        # full initial scan
    def watch(self, on_add, on_remove) -> None: ...        # produce endpoints dynamically

class Presence(ABC):
    def announce(self, endpoint: Endpoint) -> None: ...     # announce itself
    def withdraw(self, node_id: str) -> None: ...           # withdraw the announce
    def update(self, endpoint: Endpoint) -> None: ...       # update the endpoint
```

**What orthogonality means**: a node **MAY** only discover and not announce (an observer), only announce and not discover (a pure service provider), or do both (a full peer). These four combinations correspond directly to the preset table in [§5](#5-roles-and-presets).

The unified contract of the two layers is **`Endpoint`**: `transport_type` decides which transport backend to use, the concrete structure of `address` varies with the backend ([transports.md](transports.md#32-address-formats)), and `node_id` **MAY** be empty during manual discovery (the peer's identity is not yet known).

**Discovery only produces candidates; it does not guarantee reachability.** An endpoint appearing in a shared directory does **not** mean the peer is listening, and does **not** mean the handshake will succeed. Reachability is a fact known only when connecting. The discovery layer therefore **MUST NOT** trigger any blocking behaviour, and dialling **MUST** be asynchronous ([§8](#8-connection-policy-and-settle)).

Detailed provisions (shared directory declaration file format, the event + polling dual mechanism, lease TTL, HTTP registry, DHT) are in [discovery.md](discovery.md).

---

## 5. Roles and presets

### 5.1 A role is a combination, not hard coding

Which discovery, presence, transport and pattern mechanisms a node enables depends on its role. MSP declares these four kinds of resources with a **`Preset`**:

| Field | Meaning |
|---|---|
| `discovery` | which discovery mechanisms are enabled |
| `presence` | which presence mechanisms are enabled |
| `transports` | which transport backends are enabled |
| `patterns` | which communication patterns are enabled |
| `primary_transport` | which backend is announced to the outside (determines `Endpoint.transport_type`) |
| `capabilities` | role capability bits (`pub` / `sub` / `req` / `rep`) |
| `connect_policy` | connection policy at discovery time: `eager` (connect on discovery) / `lazy` (accept only, dial on demand) |

**A role is not a protocol mechanism.** The "client / server" of classic protocols is, in MSP, nothing but the values of the table above combined along different dimensions:

| Classic role | In MSP it is |
|---|---|
| MCP server | announces tools, discovers no peers, enables only `msp/request-reply` (≈ `CLOUD_SERVICE`) |
| MCP client | discovers tool nodes, announces no tools, enables only `msp/request-reply` |
| A2A agent | both discovers and announces, both provides and calls tools, enables `msp/multi-round` / `msp/task` (≈ `FULL_PEER`) |

MCP's client / server is an **asymmetric** combination (one end only serves, one end only calls), whereas the A2A agent is a **symmetric** combination. MSP presupposes neither end and leaves the choice to the node itself — therefore **a single MSP node can play MCP server, MCP client and A2A agent at the same time**, while in a protocol with fixed roles that would require maintaining three separate components.

### 5.2 Built-in presets

| Preset | discovery | presence | transports | patterns | capabilities | connect_policy |
|---|---|---|---|---|---|---|
| `LOCAL_TOOL` | — | directory | tcp | core two patterns | `pub` `rep` | lazy |
| `LOCAL_TOOL_ADVANCED` | — | directory | tcp | core + multi-round + task | `pub` `rep` | lazy |
| `LOCAL_AI` | directory | directory | tcp | core + multi-round + task | `pub` `sub` `req` `rep` | eager |
| `LOCAL_AI_UDS` | directory | directory | uds | core + multi-round + task | `pub` `sub` `req` `rep` | eager |
| `CLOUD_SERVICE` | — | directory | tcp | core + multi-round + task | `pub` `rep` | lazy |
| `OBSERVER` | directory | — | tcp | publish/subscribe | `sub` | eager |
| `FULL_PEER` | directory | directory | tcp | core + multi-round + task | `pub` `sub` `req` `rep` | eager |
| `MANUAL_PEER` | manual | manual | websocket | core two patterns | `pub` `sub` `req` `rep` | eager |

"The core two patterns" = `msp/request-reply` + `msp/publish-subscribe`.

Normative provisions:

1. When no preset is specified, a node **MUST** use `FULL_PEER`.
2. `primary_transport` **MUST** be among `transports`; otherwise node startup **MUST** fail with an error, and **MUST NOT** silently fall back to another backend.
3. Every name listed in a preset **MUST** already be registered in the corresponding registry; if it is not, startup fails.
4. A preset **MAY** be overridden: it **MAY** be extended at runtime on the same node (see [§5.3](#53-runtime-adjustment)).
5. `LOCAL_AI_UDS` is available **only** on platforms that support `AF_UNIX` ([transports.md](transports.md#33-uds-platform-limits-permissions-and-stale-socket-cleanup)).

### 5.3 Runtime adjustment

| Operation | Effect |
|---|---|
| `node.register_pattern(pattern_id, metadata=None)` | declare a pattern: write it into `Manifest.patterns` (together with `pattern_metadata`), and if the registry holds a matching handler, instantiate and activate it automatically; push the manifest immediately while the node is running |
| `node.add_manual_source(...)` | injected by the `install_api` of manual discovery; append a discovery source dynamically at runtime |

Normative provision: `register_pattern` **MUST** be idempotent (repeating the declaration has no side effects); when called on a running node it **MUST** push the manifest at once ([base-protocol.md §4.4](base-protocol.md#44-manifest-exchange-and-update)).

---

## 6. Capability negotiation

### 6.1 The handshake is the negotiation

The capability manifest (`Manifest`) is exchanged **at handshake time**, so both sides know, **before the connection is established**, which communication patterns the other supports, which tools it provides and which paths it will publish:

```text
   node_a                                         node_b
     │  ── hello {manifest: {patterns: [...],      │
     │            tools: [...], signals: [...]}} ─► │
     │                                             │  compare patterns:
     │                                             │  · intersection = ways to communicate
     │                                             │  · missing = downgrade or give up
     │  ◄──────── ack {manifest: {...}} ────────── │
     │  compare likewise                           │
     ▼                                             ▼
```

**This is more efficient than "connect first, probe later"**, and it gives pattern fallback (`fallback_to`) its informational basis: before sending a request, the caller can already tell whether "the other side supports `msp/multi-round`", instead of sending it and waiting for a failure.

Normative provisions:

1. Both sides **MUST** carry the **complete** capability manifest in the handshake message (not a delta).
2. The manifest **MUST** contain every pattern ID the node has enabled (`patterns`).
3. A node **MUST NOT** use the signal types of a pattern without having announced that pattern. On receiving such a signal, handle it by lenient reading ([base-protocol.md §2.3](base-protocol.md#23-lenient-reading)).
4. The manifest **MAY** contain capability declarations that are not yet implemented — but this leaves the peer "seeing a promise it cannot use". An implementation **SHOULD** announce only the capabilities it really implements ([capabilities.md §current state](capabilities.md) — the current implementation is in exactly this state).

### 6.2 Capability bits and authorization are two different things

| | Where it lives | Semantics | Exchangeable |
|---|---|---|---|
| **capability bits** `pub` / `sub` / `req` / `rep` | `Manifest.capabilities` | "what I claim I can do" | ✅ exchanged with the manifest |
| **authorization** `grants` | local `Preset` | "what I allow you to do" | ❌ **MUST NOT** be exchanged |

**Authorization never depends on what the peer reports about itself.** A node claiming the `req` capability does **not** mean others have to accept its calls. See [security.md §Authorization](security.md#3-authorization).

### 6.3 Pattern metadata

`Manifest.pattern_metadata` lets a pattern attach metadata **it defines itself** (the key is the `pattern_id`):

```json
"patternMetadata": {
  "msp/task": { "name": "...", "skills": [ ... ] }
}
```

Normative provision: the Manifest core **does not perceive and does not validate** the content of this field; it is exchanged verbatim with the manifest. The format is defined by each pattern (`msp/task` uses it to carry a projection of the A2A Agent Card, see [task.md](patterns/task.md#62-agent-card-projection)).

---

## 7. `Peer`: a read-only view of a neighbour

A neighbour's information is naturally scattered: the `Endpoint` at the node layer, the `Connection` and the capability manifest at the protocol layer. `Peer` aggregates them into one object.

**`Peer` is a view, not a store**: it holds no state, and every attribute access reads live from the owning node. After the peer updates its manifest or disconnects, **the same `Peer` object immediately reflects the latest state** — there is no copy to synchronise. A `Peer` object may therefore be created and discarded freely.

| Member | Type | When not discovered / not connected |
|---|---|---|
| `endpoint` | `Endpoint \| None` | `None` |
| `manifest` | `dict \| None` (**shallow copy**) | `None` |
| `connection` | `Connection \| None` | `None` |
| `is_discovered` | bool | `False` |
| `is_connected` | bool | `False` |
| `tools()` / `signals()` / `patterns()` | `list` | `[]` |
| `supports(pattern_id)` | bool | `False` |
| `has_tool(name)` / `has_signal(path)` | bool | `False` |

Normative provisions:

1. **Query only, never act.** `call` stays on the node; `publish` is a broadcast and does not address a single peer, so it does **not** belong to `Peer`.
2. **Be lenient towards unknown peers.** Querying an unknown `peer_id` **MUST** return `None` / `[]` / `False`, and **MUST NOT** raise.
3. `manifest` **MUST** return a copy; modifying the returned value **MUST NOT** pollute the node's internal state.
4. Enumeration API of the view: `node.peers()` (all known neighbours, including unconnected ones) and `node.connected_peers()` (connected ones only), both sorted by `node_id`.

---

## 8. Connection policy and `settle`

### 8.1 `connect_policy`

| Policy | Behaviour on discovery | Connection time |
|---|---|---|
| `eager` | dial asynchronously on discovery | at discovery |
| `lazy` | only record it in the neighbour table | on the first `call()` / `fetch_manifest()` (`ensure_connected`) |

**Both policies MUST guarantee the same thing**: any user API that needs a connection **MUST** call `ensure_connected(peer_id)` internally as a fallback, so that "the neighbour is known but not connected" never becomes the caller's burden.

**Concurrent connection establishment MUST be deduplicated**: one connection lock per peer, so that several threads do not trigger duplicate dials at the same time (a duplicate connection is deduplicated by the peer, but the cost is one pointless handshake and a cooldown record, see [base-protocol.md §4.3](base-protocol.md#43-duplicate-connection-deduplication)).

### 8.2 Peer failure: errors as values, soft cooldown, no neighbour removal

A peer may become unreachable at any time (crash, restart, network loss). "The peer is gone" is **the normal case, not an exception**:

| Mechanism | What it solves | Provision |
|---|---|---|
| **errors as values** | a gone peer should not interrupt the caller's program | `call()` returns `ToolResult(error=...)` for an unreachable / unknown / timed-out / mid-flight-disconnected peer in every case, and **MUST NOT** raise |
| **suspected death = soft cooldown** | telling "temporarily unconnectable" from "really dead" | a failed connection records `now + connect_backoff`; within the cooldown it fails fast instead of dialling again; a success clears it |
| **no neighbour removal** | a hard delete would make a peer that merely failed temporarily disappear for good | a failed connection **MUST NOT** remove the peer from the neighbour table |
| **directory lease + TTL = hard cleanup** | clean up nodes that really are dead, automatically | the announcing side renews its lease periodically, the discovering side discards expired declarations ([discovery.md](discovery.md#32-lease-and-ttl)) |

**Soft marking and hard cleanup are separate**: a failed connection is a "suspicion", an expired declaration is a "confirmation"; the two time scales do not interfere. This is the central trade-off in MSP's handling of peer failure, and every implementation **SHOULD** keep this separation, otherwise it degrades into "one network hiccup and a peer is lost for good".

### 8.3 Startup timing and `settle`

**Problem**: the timing of the layers inside `start()` is mixed — transport listening is synchronous, presence is synchronous, **discovery is synchronous too** (`watch()` runs a full scan first), but `eager` dialling happens in a background thread. So the state when `start()` returns is "**neighbours known, connections not necessarily there**":

- an immediately following `publish()` fans out to an **empty connection set** — under the broadcast model this is neither an exception nor an error code, but **silent loss**;
- an immediately following `call()` leans on `ensure_connected()` as an on-the-spot fallback (it can connect, but it pushes the latency of the first call onto the caller).

For users, this means the question "should I sleep after `start()`" became one that must be answered from experience. The `wait_until(lambda: "a" in node.connections())` scattered through the tests is the external symptom of this problem.

**Decision**: `start(settle=True, settle_timeout=0.5)` — after startup completes, wait once for "all discovery-driven dials in flight to land (succeed or fail)", and return whether things settled before the timeout; a separate `node.settle(timeout)` is also provided.

```python
node.start()                          # settle=True by default: discovery-driven dials have landed on return
ok = node.start(settle_timeout=1.0)   # custom upper bound; False means dials are still in flight
node.start(settle=False)              # purely non-blocking: connections form in the background
node.settle(0.5)                      # or wait separately; returns whether it settled before the timeout
```

Three properties are **deliberate**:

1. **On by default**: on the success path dials usually land within tens of milliseconds, so `settle` returns immediately at almost no extra cost; only peers that cannot be reached exhaust the timeout. Off by default would leave this pitfall to every caller.
2. **Wait only, never initiate**: `settle()` **never** calls `ensure_connected()`. It waits only for connections "someone is already making". It is therefore a **no-op** under `connect_policy="lazy"` (there is no dial in flight, it returns `True` immediately), and **never** turns a lazy node into an eager one — `settle` and `connect_policy` are orthogonal.
3. **Register before starting the thread**: the discovery callback **MUST** count the peer in the "in flight" set synchronously, **before** starting the dial thread, and the thread deregisters in `finally` and signals. If registration happened inside the dial thread instead, `settle` might see an empty set before the dial thread is scheduled and misjudge "not yet started" as "already settled" — and the guarantee of being on by default would be fake.

**Boundaries (the honest version)**:

- **Discovery-driven dialling only**: connections initiated by `call()` / `fetch_manifest()` / `msp/task` themselves are **not** counted.
- **No promise to "connect to all future nodes"**: nodes that announce only after `start()` returns take the normal discovery path.
- **The timeout is an upper bound, not an error**: `False` only means dials are still in flight; the node remains usable as usual.
- **No "connect to at least N"**: such a requirement would escalate "the peer is not ready" into a startup failure, which conflicts with the fault-tolerant stance of "errors as values". When a strong guarantee is needed, the user **SHOULD** check `connections()` itself after `settle`.

---

## 9. Startup and shutdown order

`start()` **MUST** execute in the following order (the order itself is part of the contract):

```text
   1. transport layer listen_all()              all backends start listening
   2. determine the external endpoint           primary_transport → Endpoint
   3. write the manifest                        merge the preset's patterns and capability bits → push_manifest
   4. presence layer announce(endpoint)         others can now discover me
   5. discovery layer watch(on_add, on_remove)  run one synchronous full scan → neighbours enter the table
   6. each transport backend starts its accept loop
   7. start all signal_source generator threads
   8. settle (0.5 s by default)
```

Step 3 **MUST precede** step 4: the capability manifest is exchanged **at handshake time**, and the handshake is initiated by the other side — if the announce precedes manifest readiness, a fast peer might dial in before the manifest is written, and the two sides would exchange an incomplete capability manifest.

`stop()` **MUST** execute in reverse order: withdraw the announce → stop discovery → close the protocol layer (close all connections, wake all in-flight requests) → close the transport layer. Calling `stop()` on a node that was never started **MUST NOT** raise an error (the heartbeat thread started during construction still needs to be stopped).

---

## 10. Division of the node API surface

| Category | API | Notes |
|---|---|---|
| declare capabilities | `declare_signal(path, schema, description)`, `signal_source(path)` / `signal(path)`, `tool(name, description, input_schema)`, `register_pattern(id, metadata)` | write into `Manifest` and push |
| register callbacks | `on(path)`, `on_connected(cb)`, `on_disconnected(cb)` | `path=None` matches everything; `*` / `**` supported |
| interaction | `publish(path, payload)`, `call(peer, tool, args, timeout)` | see the two core pattern pages |
| connection | `ensure_connected(peer)`, `settle(timeout)`, `start(...)`, `stop()` | |
| query | `neighbors()`, `connections()`, `peer(id)`, `peers()`, `connected_peers()`, `peer_manifest(id)`, `fetch_manifest(id)`, `pattern(id)` | `peer_manifest` is a read-only cache and does not trigger a connection; `fetch_manifest` does trigger one |

**Design constraint**: `node.call()` is the **only** API that acts on a `Peer`, and it stays on the node rather than on `Peer` — `Peer` remains query-only ([§7](#7-peer-a-read-only-view-of-a-neighbour)).

---

## 11. The extension hook `install_api`

**Problem**: we want syntax sugar such as "add a discovery source dynamically at runtime", yet do not want to add a single line of change to the core.

**Decision**: a component of any layer **MAY** define `install_api(node)`; `MSPNode` calls it (if present) once the components are constructed, and the component can then hang convenience methods on the node without changing the core:

```python
node.start()
node.add_manual_source("http://registry2:8080/nodes")  # add a discovery source dynamically at runtime
```

- communication patterns use it to hang `node.multiround` and `node.task`;
- manual discovery uses it to hang `node.add_manual_source(...)`.

**Convention** (the contract of `PatternHandler.install_api`, which applies equally to discovery / presence):

1. keep `self._node = node` as a back-reference, for use inside its own public methods, so that users need not pass `protocol` / `node_id` by hand;
2. the short name hung on the node **MUST** be unique, and **MUST NOT** collide with the core API;
3. `install_api` **SHOULD NOT** do heavy work (establish no connection, start no thread).

**Cost**: about 4 lines in the core (`_install_layer_api`). When "zero core changes" and "syntax sugar" cannot both be had, take a small core change in exchange for the ability to inject an API at any layer.

---

## 12. Summary of normative provisions

**MUST**:

1. Layers **MUST** pass data only through the four contracts (`Endpoint` / `bytes` / `Signal`+`pattern` / `install_api`).
2. The transport layer **MUST NOT** parse message content; the protocol layer **MUST NOT** understand the semantics of a concrete pattern.
3. `Discovery` and `Presence` **MUST** remain two independent interfaces.
4. When no preset is specified, `FULL_PEER` **MUST** be used; `primary_transport` **MUST** belong to `transports`, otherwise startup fails.
5. Both sides **MUST** exchange the **complete** capability manifest in the handshake, containing all enabled pattern IDs.
6. A node **MUST NOT** use the signal types of a pattern without having announced that pattern.
7. Authorization **MUST NOT** be exchanged with the manifest, and **MUST NOT** depend on what the peer reports about itself.
8. Any user API that needs a connection **MUST** call `ensure_connected()` internally as a fallback.
9. Concurrent connection establishment to the same peer **MUST** be deduplicated (one lock per peer).
10. `call()` **MUST NOT** raise because the peer is unreachable / timed out / disconnected, and **MUST** return an error value.
11. A failed connection **MUST NOT** remove the peer from the neighbour table; only an expired declaration triggers cleanup.
12. `start()` **MUST** execute in the order of [§9](#9-startup-and-shutdown-order), with the manifest written before the announce.
13. `settle()` **MUST NOT** initiate connections; under `connect_policy="lazy"` it **MUST** be a no-op.
14. A "dial in flight" **MUST** be registered **before** the thread is started.
15. `Peer` **MUST** be a query-only view, returning empty values rather than raising for an unknown peer.

**SHOULD**:

16. An implementation **SHOULD** announce only the capabilities it really implements.
17. A new extension **SHOULD** change only the registry and the preset, not the core.
18. When a strong connection guarantee is needed, the user **SHOULD** check `connections()` itself after `settle`.

---

## 13. Known gaps

| # | Gap | Consequence |
|---|---|---|
| 1 | no complete promise of "network ready" | `settle` covers discovery-driven dialling only; connections initiated by `call` / `fetch_manifest` / `msp/task` are not counted |
| 2 | a `lazy` node does not take part in `settle` | on a lazy node `settle()` is always `True` and cannot serve as a criterion for "the peer is connected" |
| 3 | discovery `on_remove` only deletes the neighbour entry, it does not disconnect | after a peer withdraws its announce, the established connection closes only on heartbeat liveness loss (at most `heartbeat_timeout`) |
| 4 | no consistency guarantee across a central registry | when several registry sources coexist, different endpoints of the same `node_id` **MAY** exist in the neighbour table at the same time (the later one wins, see `_on_endpoint`) |
| 5 | the capability manifest has no "not implemented" marker | see [§6.1 item 4](#61-the-handshake-is-the-negotiation): the peer sees entries that are promised but unusable |
| 6 | no topology awareness | broadcast fan-out does no bandwidth optimisation; `N` peers means `N` sends (a deliberate trade-off, not a defect; see [publish-subscribe.md §Security considerations](patterns/publish-subscribe.md#8-security-considerations)) |
| 7 | no persistent node identity | the user must guarantee the uniqueness of `node_id`; the protocol offers no allocation or collision detection |

---

## 14. Reference implementation map

| Provision | Source | Symbol |
|---|---|---|
| five-layer assembly | `src/msp/core/node.py` | `MSPNode.__init__`, `_activate_pattern`, `_install_layer_api` |
| registries | same as above | `DISCOVERY_REGISTRY`, `PRESENCE_REGISTRY`, `TRANSPORT_REGISTRY`, `CORE_PATTERNS` |
| startup / shutdown order | same as above | `start`, `stop`, `_accept_loop`, `_run_signal_source` |
| connection policy and cooldown | same as above | `_on_endpoint`, `ensure_connected`, `_eager_connect`, `_unavailable`, `connect_backoff` |
| `settle` | same as above | `settle`, `_connecting`, `_settle_cv` |
| errors as values | same as above | `MSPNode.call`, `PeerUnavailable`, `UnknownPeer` |
| Peer view | `src/msp/core/peer.py` | `Peer` throughout |
| Preset | `src/msp/core/preset.py` | `Preset` and the 8 built-in presets |
| capability manifest | `src/msp/core/manifest.py` | `Manifest`, `set_pattern_metadata` |
| discovery contract | `src/msp/discovery/base.py` | `Discovery`, `Endpoint` |
| presence contract | `src/msp/presence/base.py` | `Presence` |
| pattern contract | `src/msp/patterns/base.py` | `PatternHandler` |
| pattern registry | `src/msp/patterns/__init__.py` | `PATTERN_REGISTRY` |
| the full argument for the layering principle | `docs/DESIGN.md` | throughout |

---

**See also**: [base-protocol.md](base-protocol.md) (message layer) | [transports.md](transports.md) | [discovery.md](discovery.md) | [patterns.md](patterns.md) | [security.md](security.md) (trust boundary and authorization) | [interop.md](interop.md) (role mapping)
