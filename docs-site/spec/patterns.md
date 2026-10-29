# MSP Pattern Layer

| | |
|---|---|
| **Protocol revision** | `2026-10-10` |
| **Status** | ✅ Implemented (`msp/streaming`, `msp/callback-push` and `msp/async-polling` are 🔵 planned) |
| **This page defines** | The abstract contract for communication patterns (`PatternHandler`), the order of routing decisions from the protocol layer to the pattern layer, the basis for dividing core patterns from extensible patterns, the fallback and mutual-exclusion semantics, the pattern registration procedure, and the complete message definitions of the three planned patterns |

> Constant sources: signal types, pattern IDs, error codes and default parameters are all governed by [README.md](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#5-规范常量速查). This page **MUST NOT** introduce new constants outside the index; pattern-private signal types are declared one by one in the body text.

---

## 1. Overview

### 1.1 Why the pattern layer exists

The pattern layer turns "the semantics of one kind of interaction" into a **pluggable unit**, so that adding a pattern **does not modify the protocol core**.

The protocol core knows only one thing: which connection a `Signal` came from, what its `type` is, and what its `pattern` is. It does not know that "a request–response has to wait for a reply packet", nor that "a publish has to fan out". Those are semantics, and semantics belong to patterns.

Pulling semantics out of the core brings three verifiable benefits:

1. **A new pattern = one new file + one registry entry**. The decision order of the protocol layer's `_dispatch` needs no change at all (see §3), because the routing key `Signal.pattern` is already in the envelope.
2. **Patterns do not perceive each other**. `msp/task` does not know that `msp/multi-round` exists; both use the two identically named signal types `input_required` / `input_response`, and the `pattern` field decides ownership, so they do not collide.
3. **A pattern can fail without dragging the connection down**. An unregistered pattern cannot handle its own signals, but the routing contract guarantees that it degrades to the protocol layer's default dispatch instead of having the connection torn down (see §3.4).

### 1.2 Position in the layering

```
 User API layer  MSPNode (node.call / node.publish / node.on / node.tool …)
      │
 Pattern layer   PatternHandler instances (msp/multi-round, msp/task …)
      │  ▲            ▲
      │  └── protocol._send() ──┐
      ▼                         │
 Protocol layer  MSPProtocol.patterns (routing table) · _dispatch (routing)
      ▼
 Transport layer Connection.send / receive (moves bytes only)
```

The pattern layer **sits above** the protocol layer, but **does not own** it: it is registered through `protocol.patterns`, sends packets through `protocol._send()`, and receives packets through `on_signal(protocol, peer_id, sig)`.

### 1.3 Relationship to other pages

| Page | Relationship |
|---|---|
| [README.md](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#52-模式-id) | The single authoritative list of pattern IDs and their status |
| [base-protocol.md](base-protocol.md) | Definition of the `Signal` envelope and of the core signal types |
| [request-reply.md](patterns/request-reply.md) | One of the core patterns; §4 of this page explains why it does not go through a Handler |
| [publish-subscribe.md](patterns/publish-subscribe.md) | The second core pattern; as above |
| [multi-round.md](patterns/multi-round.md) | Reference implementation of an extensible pattern, demonstrating the "pattern-private signal type" convention |
| [task.md](patterns/task.md) | Reference implementation of an extensible pattern; as above |
| [schema.md](schema.md) | Complete field definitions in JSON form |

---

## 2. Contract: PatternHandler

`PatternHandler` (`src/msp/patterns/base.py`) is an abstract base class (`abc.ABC`). Every **extensible pattern** implementation **MUST** be a subclass of it.

### 2.1 Class attributes

| Member | Type | Required | Semantics |
|---|---|---|---|
| `pattern_id` | `str` | **MUST** | The unique identifier of the pattern, byte-for-byte identical to the string in `Signal.pattern` and `Manifest.patterns` |
| `fallback_to` | `str \| None` | **MAY** be omitted, default `None` | Target pattern ID for fallback (§6) |
| `conflicts_with` | `list[str]` | **MAY** be omitted, default `[]` | List of pattern IDs mutually exclusive with it (§4.3) |

`pattern_id` **MUST** conform to the Pattern ID format `[namespace/]name` of [README.md §5.3](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#53-命名规范). Patterns using the `msp/` prefix **MUST** be defined by this specification; third-party patterns **MUST** use a prefix of their own (for example `acme/streaming`) and **MUST NOT** occupy `msp/`.

Reference implementation example (`msp/multi-round`):

```python
class MultiRoundHandler(PatternHandler):
    pattern_id = "msp/multi-round"
    fallback_to = "msp/request-reply"
```

### 2.2 Abstract method `on_signal`

```python
@abstractmethod
def on_signal(self, protocol, peer_id: str, sig) -> None: ...
```

| Parameter | Type | Semantics |
|---|---|---|
| `protocol` | `MSPProtocol` | The protocol layer instance, through which the Handler calls `_send` and other methods |
| `peer_id` | `str` | The `node_id` of the **peer** that sent this signal |
| `sig` | `Signal` | The complete signal object |

**MUST** be satisfied:

1. `on_signal` **MUST** be called on the **protocol layer's read-loop thread** (routing is synchronous dispatch and does not retreat to a worker thread). It **MUST NOT**, therefore, perform long-running operations inside it.
2. A Handler that needs to do long work (tool invocation, network round trips, waiting for the peer's answer) **MUST** hand that work to a separate thread (`threading.Thread(...).start()`); the reason is in §3.5.
3. The return value of `on_signal` is `None`; a pattern's "response" **MUST** be sent explicitly through `protocol._send()` and **MUST NOT** be returned through the return value.

### 2.3 Optional method `install_api`

```python
def install_api(self, node) -> None:
    """Injects syntactic sugar into the node and stores the back-reference to the node. Does nothing by default."""
    pass
```

Conventions (taken from the docstring in `base.py`, and followed by `msp/multi-round` and `msp/task`):

1. **SHOULD** store `self._node = node`, for use inside its own public methods, so that users need not pass `protocol` / `node_id` by hand.
2. **MAY** attach a short name on `node` (such as `node.multiround = self`, `node.streaming = self`).
3. The short name **MUST** be unique and **MUST NOT** conflict with the core API of `MSPNode`. The core API includes at least: `node_id`, `manifest`, `endpoint`, `preset`, `protocol`, `transport`, `discoveries`, `presences`, `start`, `stop`, `settle`, `publish`, `on`, `on_connected`, `on_disconnected`, `call`, `tool`, `signal`, `signal_source`, `declare_signal`, `register_pattern`, `pattern`, `ensure_connected`, `neighbors`, `connections`, `peer`, `peers`, `connected_peers`, `peer_manifest`, `fetch_manifest`.
4. The base class default implementation is a no-op, so a pattern that injects no syntactic sugar **MAY** leave it unoverridden.

### 2.4 Activation timing

Handlers are instantiated by the **registry** at activation time; users **SHOULD NOT** construct them by hand (the docstring of `node.register_pattern` gives "consistent with the Preset start-up path" as the reason). The activation process is in §3.6.

---

## 3. Routing contract

This section is the **only** interface agreement between the pattern layer and the protocol layer, and **MUST** correspond line for line with `MSPProtocol._dispatch`.

### 3.1 Three-step decision order

On receiving any signal, the protocol layer **MUST** decide in the following order, and **MUST** **return immediately** once an earlier step matches, without continuing:

**Step 1 — core signal types**

If `sig.type` ∈ `{hello, ack, ping, pong, error}`, it **MUST** be handed to the protocol layer for its own handling (`_dispatch_core`) and **MUST NOT** be looked up in the pattern table.

> This provision means that even if a `hello` signal carries a `pattern` field, it **will** not be routed to any Handler. Core signal types are a **no-go area** for the pattern layer.

**Step 2 — carries `pattern` and is registered**

Otherwise, if `sig.pattern` is non-empty **and** `sig.pattern` hits `protocol.patterns` (that is, this node has activated a Handler for that pattern), the protocol layer **MUST** call that Handler's `on_signal(protocol, peer_id, sig)`, and then return.

`protocol.patterns` is a `dict[str, PatternHandler]` keyed by `pattern_id`.

**Step 3 — default core dispatch**

Otherwise (`sig.pattern` is empty, **or** `sig.pattern` is non-empty but unregistered), the signal **MUST** be handed to `_dispatch_core`. An unknown `type` **MUST** be answered with `error`, with payload `code = -32600`, `message = "unknown signal type: <type>"` (`_reply_error` carries the original signal's `reqid`).

### 3.2 Decision flow diagram

```
                      Signal received
                           │
        ┌──────────────────┴──────────────────┐
        │ type ∈ {hello, ack, ping, pong,     │ yes
        │         error} ?                    ├──────▶ _dispatch_core (handled by the protocol layer itself)
        └──────────────────┬──────────────────┘
                           │ no
        ┌──────────────────┴──────────────────┐
        │ pattern non-empty and registered ?  │ yes
        └──────────────────┬──────────────────┘──────▶ handler.on_signal(protocol, peer_id, sig)
                           │ no
                           ▼
                    _dispatch_core
                    ├─ signal          → _on_signal (local callback filtering)
                    ├─ tool_call       → _on_tool_call (executed on a separate thread)
                    ├─ tool_result     → _on_tool_result (wakes the reqid waiter)
                    ├─ manifest_update → _on_manifest_update
                    ├─ ping            → replies with pong
                    ├─ pong            → ignored (last_seen is already updated in the read loop)
                    ├─ error           → _on_error (logs)
                    └─ any other type  → replies with error(code=-32600)
```

### 3.3 Who writes the routing key

The party sending a signal **MUST** declare `pattern` explicitly when constructing the signal:

```python
protocol._send(peer_id, Signal.make(
    type=self.TOOL_CALL,          # pattern-private signal type
    source=self._node.node_id,
    target=peer_id,
    reqid=reqid,
    payload={"tool": tool, "args": args},
).with_pattern(self.pattern_id))  # ← the routing key
```

`Signal.with_pattern(pattern)` sets the `pattern` field in place and returns `self`, which makes chaining convenient.

**Core patterns' signals carry no `pattern`**: the `pattern` of `tool_call` / `tool_result` is `None` (see [request-reply.md](patterns/request-reply.md)), and the `pattern` of `signal` is `None` (`publish` does not set that field, see [publish-subscribe.md](patterns/publish-subscribe.md)). They therefore reliably take step 3.

### 3.4 Behaviour with unregistered patterns (**MUST** be observed)

1. **MUST**: an unknown `pattern` **MUST NOT** cause the connection to be dropped. After step 2 fails, step 3 **MUST** still run.
2. **MUST**: a signal carrying an unregistered `pattern` is degraded per step 3. If its `type` is a known core type, it is handled as that type (for example a signal with `type="tool_call"` and an unknown `pattern` **will** be executed as an ordinary tool call).
3. **MUST**: an unknown `type` is answered with `error(code=-32600)`, with `message` shaped like `unknown signal type: <type>`, and the connection **MUST NOT** be closed because of it.
4. **SHOULD**: implementations log one debug line for "received a signal with an unregistered `pattern`"; the reference implementation currently does **not** log it, see G3 in §10.

> Note one consequence of 3.4.2: giving a `tool_call` an **unregistered** `pattern` does not amount to "refusing the peer" — it merely loses the pattern layer's special semantics and is still executed with core semantics. Security filtering **MUST NOT** depend on the `pattern` field (see §9).

### 3.5 The thread `on_signal` runs on, and the blocking prohibition

`_dispatch` is called synchronously by `_read_loop`, and `_read_loop` is **the only read thread of that connection**. Therefore:

- performing a long-running operation inside `on_signal` **will** block the receipt of every subsequent message on that connection;
- if the long-running operation itself also has to wait for the peer's reply (for example `ask()` in multi-round), it **will** deadlock — the peer's answer is precisely the message that is being blocked.

So any Handler that needs to execute a tool, wait for the peer, or perform blocking I/O **MUST**:

```python
threading.Thread(target=self._run_tool, args=(...), daemon=True).start()
```

This convention is consistent in `msp/multi-round` (`_on_tool_call` → `_run_tool`) and in the protocol core (`_on_tool_call` → `_run_tool`); it is the pattern-layer isomorphic statement of a **MUST**-level requirement of this specification.

### 3.6 Activation path

A Handler enters the routing table by two equivalent paths, and both **MUST** land on the same activation action:

| Path | Trigger | Behaviour |
|---|---|---|
| Preset start-up | Each ID in `Preset.patterns` | Construct `cls()` and activate; core pattern IDs are skipped |
| Runtime registration | `node.register_pattern(pattern_id, metadata=None)` | Take the class from `PATTERN_REGISTRY`; if it exists and is not active, construct it and activate |

The activation action (`MSPNode._activate_pattern`) is fixed at three things, and the order **MUST** be:

1. `handler.install_api(node)` — inject the syntactic sugar;
2. `node._patterns[handler.pattern_id] = handler` — the node-side index (the lookup source for `node.pattern(id)`);
3. `protocol.patterns[handler.pattern_id] = handler` — the protocol layer routing table.

Step 1 comes before step 3 so that the short names and public methods attached inside `install_api` are already available when routing takes effect.

---

## 4. Core patterns and extensible patterns

### 4.1 Division

| Category | Pattern ID | Implementation location | `PATTERN_REGISTRY` entry |
|---|---|---|---|
| **Core pattern** | `msp/request-reply` | Protocol layer (`MSPProtocol`'s `call` / `_on_tool_call` / `_run_tool` / `_on_tool_result`) | **None** |
| **Core pattern** | `msp/publish-subscribe` | Protocol layer (`MSPProtocol`'s `publish` / `on` / `_on_signal`) | **None** |
| **Extensible pattern** | `msp/multi-round` | Standalone file `patterns/multi_round.py` | Yes |
| **Extensible pattern** | `msp/task` | Standalone file `patterns/task.py` | Yes |
| **Planned** | `msp/streaming` / `msp/callback-push` / `msp/async-polling` | Not implemented yet | Not registered yet |

The basis for deciding "this is a core pattern" is a constant set, not a convention:

```python
CORE_PATTERNS = frozenset({"msp/request-reply", "msp/publish-subscribe"})
```

`MSPNode.__init__` and `register_pattern` **MUST** use this set for the decision and skip Handler instantiation. Hence no core-pattern entry **will** appear in `protocol.patterns` or `node._patterns` — this is not an omission but evidence that core patterns do not take part in pattern-layer routing.

### 4.2 Why these two are core

Three reasons, each of which points at **protocol-layer state**:

1. **Signal routing depends on the protocol layer**. `_dispatch` is itself a protocol-layer function; if request-reply / publish-subscribe also went through `on_signal`, then step 2 of "receive → route" would hit them at once, and step 3's default dispatch (including `manifest_update`, `ping`) would instead become unreachable code. Core semantics **MUST** sit **below** routing, not **above** it.
2. **`reqid` correlation depends on protocol-layer state**. `pending_calls: dict[str, tuple[threading.Event, list]]` is a protocol-layer field, and `_on_tool_result` needs it to wake the waiter. Moving it into a Handler would mean that on disconnect (`_handle_disconnect`) every Handler has to be called back across layers to clean up its own wait table — splitting one cohesive failure handling into N copies.
3. **Broadcast fan-out depends on protocol-layer state**. `publish` needs to iterate over `connections: dict[str, Connection]` and call `conn.send()` directly. A Handler can only send one peer at a time through `protocol._send(peer_id, ...)`; the fan-out loop, `ConnectionClosed` handling and connection deduplication (the normative direction of `_finish_handshake`) all belong to the protocol layer.

There is one further **compatibility** reason: `tool_call` / `tool_result` / `signal` / `manifest_update` are core signal types frozen by [README.md §5.1](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#51-核心信号类型signaltype). If they were handed to the pattern layer, then "a minimal implementation that only uses request-reply" (the lowest common denominator for interoperation) would also have to load the pattern layer, raising the floor.

### 4.3 Semantics of `conflicts_with`

`conflicts_with: list[str]` declares that "this pattern and the listed patterns **MUST NOT** be active at the same time".

- The attribute's semantics are **declarative**: it **MUST NOT** be read as "it will shut the other side down automatically". The reference implementation currently does **not read** `conflicts_with` (see G2 in §10), so runtime automatic validation **MUST NOT** be relied on.
- An implementation that reads `conflicts_with` when activating patterns and refuses conflicting combinations **MUST** terminate start-up with an explicit error, and **MUST NOT** silently ignore one of the parties.
- Two patterns that merely share a signal type name while having different semantics (such as `msp/multi-round` and `msp/task`, both defining `input_required` / `input_response`) **do not** constitute a conflict — because both route with different `pattern` values and their message spaces do not overlap.

---

## 5. How patterns obtain protocol-layer capabilities, and the generalisation of `install_api`

### 5.1 Obtaining protocol-layer capabilities

The first parameter of `on_signal` is the `MSPProtocol` instance. A Handler uses protocol-layer capabilities through it:

| Capability | Usage | Nature |
|---|---|---|
| Sending | `protocol._send(peer_id, sig)` | **Private method, but an established convention** |
| Broadcast | `protocol.publish(path, payload)` | Public method |
| This node's ID | `protocol.node_id` | Public attribute |
| Connection table lookup | `protocol.connections` | Public attribute |

On the underscore prefix of `_send`, this specification states it plainly:

> **`protocol._send()` is a private method, but in the pattern layer it is an established convention.** All directed sends of `msp/multi-round` and `msp/task` go through it; the `protocol` object is an explicit parameter of `on_signal` precisely in order to hand this capability legitimately to the Handler. It **MUST NOT** be demanded, on the grounds that "it is a private method", that the pattern layer switch to `conn.send()` — that would bypass connection registration and the uniform failure semantics of `RuntimeError("not connected to X")`.

Calling conventions:

1. `_send(peer_id, sig)` raises `RuntimeError(f"not connected to {peer_id}")` when **not connected**, and `ConnectionClosed` when the connection has **just closed**. A Handler **SHOULD** catch both and log a debug line, and **MUST NOT** let the exception pierce through to the read loop (it would trigger the `except Exception` branch of `_read_loop` and drop the connection to the peer).
2. When sending a signal, `source=protocol.node_id` **MUST** be filled in; a directed reply **SHOULD** fill `target=<peer node_id>`; a round trip that needs correlation **MUST** fill `reqid`.
3. A Handler **MUST NOT** directly manipulate `protocol.connections` to delete or replace entries — the sole authority for the connection lifecycle is the protocol layer.

### 5.2 The generalisation of `install_api`

`install_api` is a generic extension point for **components of any layer**, not only for the pattern layer:

| Layer | Component implementing the method | Syntactic sugar injected |
|---|---|---|
| Pattern layer | `MultiRoundHandler` | `node.multiround` |
| Pattern layer | `TaskHandler` | `node.task` |
| Discovery layer | `ManualConnect` | `node.add_manual_source(...)` (adds a discovery source dynamically at runtime) |
| Presence layer | None in the reference implementation yet | — |

The injection point exists in only one place, at a cost of about 4 lines:

```python
def _install_layer_api(self, component) -> None:
    install = getattr(component, "install_api", None)
    if install is not None:
        install(self)
```

Call timing: `MSPNode.__init__` calls it **immediately after** constructing each discovery / presence instance; the pattern layer's `install_api` is called by `_activate_pattern` (§3.6).

Provisions:

1. A component of any layer **MAY** define `install_api(node)`; if it does, it **MUST** accept one positional parameter `node` and only one;
2. The component **SHOULD** store the node back-reference there (`self._node = node`);
3. The name attached to `node` **MUST** be unique and **MUST NOT** conflict with the core API listed in §2.3;
4. `install_api` **MUST NOT** initiate network I/O or block waiting inside it — it runs on the `MSPNode.__init__` path.

---

## 6. `fallback_to` and fallback semantics

### 6.1 Attribute semantics

`fallback_to` declares "which pattern this pattern **SHOULD** fall back to when the peer has not announced it". It **MUST** be another defined Pattern ID and **SHOULD NOT** form a cycle (`A → B → A`).

### 6.2 Direction decision

The trigger for fallback is the **peer's manifest**, not local configuration:

1. The sender **SHOULD** first read `protocol.peer_manifests[peer_id]["patterns"]` (or `node.peer(peer_id).supports(pattern_id)`);
2. If the target pattern is in the list (or the peer is an all-pattern preset such as `FULL_PEER`) → use this pattern;
3. Otherwise → use the pattern named by `fallback_to`, or refuse to initiate at all.

### 6.3 Current implementation status (as it is)

**The reference implementation does not implement automatic fallback.** Evidence:

- `fallback_to` is declared **once each** on `MultiRoundHandler` (`multi_round.py:56`) and `TaskHandler` (`task.py:302`) (both values `"msp/request-reply"`), and **there is no read site anywhere in the codebase**;
- `MSPProtocol.call()` **does not check** `peer_manifests[peer_id]["patterns"]` and sends `tool_call` straight out;
- `MSPNode.call()` does not check either;
- when the peer has not activated the pattern, the signal degrades to step 3's default dispatch per [§3.4](#34-behaviour-with-unregistered-patterns-must-be-observed) — **which is exactly request-reply semantics**, so "the expected fallback" **happens to hold** in the core-pattern direction rather than being explicitly implemented.

Therefore:

- **SHOULD**: implementers check `peer.supports(pattern_id)` themselves before initiating an extensible-pattern interaction, and choose the fallback or the refusal themselves;
- **MUST NOT**: treat "the peer has not announced this pattern" as a connection-level error;
- **MAY**: implement automatic fallback, but once implemented it **MUST** keep `reqid` correlation semantics unchanged while falling back (fallback changes only the message form, not the scope of the correlation key).

### 6.4 The corresponding fields on the `Manifest` side

The list of patterns the peer supports comes from `Manifest.patterns` (serialised as `patterns: list[str]`). Note that the JSON key name is **the snake_case `patterns`**, whereas most fields inside `Manifest` serialise to camelCase (`patternMetadata`, `inputSchema`, `mimeType`). Pattern-private metadata lives in `patternMetadata: {pattern_id: dict}` and is written by `Manifest.set_pattern_metadata()`.

### 6.5 Difference from the other fallback paths

"Fallback" appears three times in this specification with different semantics, and they **MUST NOT** be conflated:

| Term | Trigger | Landing point | Level |
|---|---|---|---|
| `fallback_to` fallback | The peer has not announced the target pattern | Switch to another pattern's messages (chosen by the sender) | **SHOULD** |
| Routing fallback | `pattern` is not registered in `protocol.patterns` | Take step 3's default core dispatch (automatic at the protocol layer) | **MUST** |
| Transport fallback | The connection is unreachable / cooling down | `PeerUnavailable` → `ToolResult(error=...)` | **MUST** |

The first two differ only when "the pattern assembly is incomplete": `fallback_to` is **actively switching patterns**, whereas routing fallback is **passively falling back to core semantics**.

---

## 7. Planned patterns

The three patterns in this section have status 🔵 **planned**. Per the definition in [README.md §2](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#2-规范性用语): **implementers may leave them unimplemented, but once implemented they MUST conform to the provisions**.

The three patterns **share** the following general rules:

- a pattern-private signal type **MUST** also carry a `pattern` field (valued with the corresponding `pattern_id`) in order to be routed;
- payload fields **MUST** use the key names given in this section verbatim; `Signal` envelope fields use snake_case (`type` / `source` / `target` / `path` / `reqid` / `payload` / `timestamp` / `pattern`), while fields inside `payload` **SHOULD** follow camelCase (consistent with the existing style of `structuredContent`, `blobId`, `mimeType`), and this section spells them out field by field;
- all three patterns **MUST NOT** add new core signal types;
- all three patterns **MUST** be announced in `Manifest.patterns` before the peer can initiate them; when they are initiated without announcement, degradation is decided per §6.2 (`msp/async-polling` is precisely the fallback target of `msp/streaming` and `msp/callback-push`).

### 7.1 `msp/streaming` — chunked streaming

**Purpose**: split a one-off long result into several incremental chunks pushed to the receiver, so that the receiver can consume it before the result is complete (incremental rendering, use while downloading, progress awareness).

**Private signal types**: `stream_start` (opens the stream), `stream_chunk` (a data chunk), `stream_end` (ends, carrying a terminal summary), `stream_cancel` (bidirectional; either side may request cancellation; optional to implement). All four types **MUST** carry `reqid` and `pattern="msp/streaming"`.

**Payload fields** (key names **MUST** be identical verbatim):

| Signal | Field | Type | Required | Semantics |
|---|---|---|---|---|
| `stream_start` | `streamId` | `str` | **MUST** | Stream identifier; coexists with `reqid` — `reqid` is for correlation, `streamId` for logging and for multiplexing several streams |
| | `totalChunks` / `totalBytes` | `int \| null` | **MAY** | Known total; omitted or `null` when unknown |
| | `contentType` | `str` | **MAY** | Payload MIME type, default `application/octet-stream` |
| | `ordering` | `str` | **MAY** | `"ordered"` (default) or `"unordered"`, declaring whether chunks may arrive out of order |
| | `meta` | `object` | **MAY** | Additional pattern-independent metadata (such as tool name, task ID) |
| `stream_chunk` | `seq` | `int` | **MUST** | Chunk sequence number, monotonically increasing from `0`; it **MUST** still be given when `ordering="unordered"`, and the receiver reorders by it |
| | `data` | `str` | **MUST** | Chunk content; binary **MUST** be Base64-encoded |
| | `encoding` | `str` | **MAY** | `"utf-8"` (default) or `"base64"` |
| | `final` | `bool` | **MAY** | Defaults to `false`; `true` is shorthand equivalent to a following `stream_end` |
| `stream_end` | `status` | `str` | **MUST** | `"ok"` / `"canceled"` / `"error"` |
| | `chunks` / `bytes` | `int` | **MAY** | Actual number of chunks / bytes sent |
| | `checksum` | `str` | **MAY** | Whole-stream checksum (such as `sha256:<hex>`) |
| | `error` | `object` | **MAY** | **MUST** be given when `status="error"`, shaped like `{"code": int, "message": str}` |

The `streamId` of `stream_chunk` and `stream_end` **MUST** likewise be given, and be identical to that of `stream_start`.

**Message flow**:

```
 Sender                                Receiver
   │ ── stream_start(reqid=R) ─────────▶ │  prepare to receive (register streamId)
   │ ── stream_chunk(seq=0) ───────────▶ │  consume chunk 0
   │ ── stream_chunk(seq=1) ───────────▶ │  consume chunk 1
   │        ⋮                            │
   │ ◀── stream_cancel(reqid=R) ──────── │  (optional) the receiver asks to stop
   │ ── stream_end(status="canceled") ─▶ │  the sender confirms termination
   │ ── stream_end(status="ok") ───────▶ │  terminal state: the stream is closed, reqid can be reclaimed
```

**Terminal state**: every stream **MUST** end with exactly one `stream_end`. After the terminal state is received, that `reqid` and `streamId` **MUST** be deregistered by both sides.

**Errors**:

| Case | Handling |
|---|---|
| `stream_chunk` with an unknown `streamId` | **MUST** be dropped and logged; **SHOULD** answer with `stream_cancel` |
| Duplicate `seq` | **MUST** keep the first to arrive and drop the later ones |
| Gap in `seq` | With `ordering="ordered"`, **SHOULD** wait for the reordering window; after the timeout it **MUST** end with `status="error"` |
| The connection drops before the terminal state | **MUST** mark the local stream as failed and release resources, and **MUST NOT** keep a half-finished stream forever |
| Payload verification fails | **MUST** end with `status="error"` |

**Backpressure**: `streaming` **MUST NOT** assume that the sender can push without bound. The receiver **MAY** apply coarse-grained backpressure with `stream_cancel`; an implementation **MAY** define fine-grained flow control (such as a window `chunk_window` / `stream_ack`), but once defined it **MUST** be declared in `patternMetadata["msp/streaming"]` and follow the "append" rule of [README.md §1](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#1-修订历史); the sender **MUST NOT** block the read loop because the peer processes slowly — pushing **MUST** happen on its own thread.

**Relationship with the large-object `blob_ref`**: the two **MUST NOT** substitute for each other.

| Dimension | `msp/streaming` | `blob_ref` content block |
|---|---|---|
| Purpose | Incremental consumption (use as it arrives, progress, incremental rendering) | **Reference passing** of a large object, with the content fetched on demand over a separate channel |
| Carries the complete data | Yes (carried in chunks) | No (carries only `blobId` / `mimeType` / `size` / `checksum`) |
| Where it appears | An independent signal stream | One block of `tool_result.payload.content`, with `type="blob_ref"` |

Use `streaming` for data that **needs to be consumed while in transit**; use `blob_ref` for data that is merely **large and can be fetched later**. The retrieval channel of `blob_ref` (the `blob_chunk` signal stream) belongs to the scope of [base-protocol.md](base-protocol.md); this page does not define its messages.

**Mutual exclusion and fallback**: `conflicts_with = []` (it can coexist with `msp/task`'s artifact broadcast); `fallback_to = "msp/request-reply"`, and the fallback semantics = "return the complete result in one go as a `tool_result`".

### 7.2 `msp/callback-push` — callback-style return for long tasks

**Purpose**: after submitting a long task, **do not block waiting**; when the task completes, the delegate **actively pushes** one callback signal to the submitter (it may also push to a third-party observer named by the submitter).

**Private signal types**: `callback_register` (register a callback), `callback_ack` (a receipt accepting or refusing), `callback_push` (result return), `callback_cancel` (revoke; optional to implement). All four types **MUST** carry `reqid` and `pattern="msp/callback-push"`.

**Payload fields**: the `callbackId` of the three signals **MUST** all be given and echo each other.

| Signal | Field | Type | Required | Semantics |
|---|---|---|---|---|
| `callback_register` | `callbackId` | `str` | **MUST** | Identifier of this callback, generated by the submitter |
| | `topic` | `str` | **MUST** | Logical topic, implementation-defined (may use `node_id` or `task.<id>`) |
| | `deliverTo` | `str` | **MAY** | Result delivery target `node_id`; when omitted, the registering party itself |
| | `path` | `str` | **MAY** | `signal.path` to use when the delivery mode is broadcast |
| | `expiresAt` | `float` | **MAY** | Unix timestamp; after it the registration **MUST** become invalid |
| | `expect` | `str` | **MAY** | `"result"` (default) or `"progress"` |
| `callback_ack` | `callbackId` / `accepted` | `str` / `bool` | **MUST** | Echo, and whether it is accepted |
| | `ttl` | `float` | **MAY** | Seconds for which the delegate is willing to keep the registration |
| | `reason` | `str` | **MAY** | **SHOULD** be given when `accepted=false` |
| `callback_push` | `state` | `str` | **MUST** | `"progress"` / `"completed"` / `"failed"` / `"canceled"` |
| | `content` | `list` | **MAY** | List of content blocks, format exactly identical to `tool_result.payload.content` |
| | `structuredContent` | `any` | **MAY** | Structured result, format identical to `tool_result.payload.structuredContent` |
| | `error` | `str` | **MAY** | Failure reason; **SHOULD** be given when `state="failed"` |
| | `seq` | `int` | **MAY** | Progress sequence number when `state="progress"` |

**Message flow**:

```
 Submitter                             Delegate
   │ ── callback_register(reqid=R) ────▶ │  register callbackId → (deliverTo, topic)
   │ ◀── callback_ack(accepted=true) ─── │  receipt
   │                                     │  ……the task runs asynchronously……
   │ ◀── callback_push(state=progress) ── │  (optional) progress
   │ ◀── callback_push(state=completed) ─│  terminal state
   │ ── callback_cancel(reqid=R) ──────▶ │  (optional) revoke
```

**Terminal state**: exactly one of `callback_push.state` ∈ `{completed, failed, canceled}` **MUST** be the last push of this callback; afterwards that `callbackId` **MUST** be deregistered by both sides.

**Errors**:

| Case | Handling |
|---|---|
| `callback_ack.accepted=false` | The submitter **MUST** stop waiting for pushes and fall back to explicit polling per `fallback_to` |
| Registration expired (`expiresAt` has passed) | The delegate **MUST** drop that `callbackId`; a failed push **MUST NOT** be retried without bound |
| Push target unreachable | The delegate **MUST** drop that registration and log it, and **MUST NOT** block the task thread |
| `callback_push` with an unknown `callbackId` | The receiver **MUST** drop it and log it |
| Duplicate terminal push | The receiver **MUST** take the first terminal state as authoritative |

**Mutual exclusion and fallback**: `conflicts_with = []` (it can be used together with `msp/task` — `msp/task` handles the state machine and multi-observer broadcast, this pattern handles directed return); `fallback_to = "msp/async-polling"`, and the fallback semantics = "register no callback; instead the submitter polls explicitly by `callbackId`".

### 7.3 `msp/async-polling` — explicit polling semantics (interoperability fallback)

**Purpose**: interoperability fallback. When the peer supports neither `streaming` nor `callback-push`, long-task collaboration is completed with the plainest semantics of "submit → poll → fetch result". Of the three planned patterns it is the one that is **weakest in capability but most portable**, and it is also the fallback target of the other two.

**Private signal types** (seven; they **MUST** carry `reqid` and `pattern="msp/async-polling"`): `poll_submit` → `poll_submit_result`, `poll_status` → `poll_status_result`, `poll_fetch` → `poll_fetch_result`, plus the optional `poll_cancel`.

**Payload fields**:

- `poll_submit`: `tool` (`str`, **MUST**), `args` (`object`, **MAY**), `jobId` (`str`, **MAY**; generated by the executor when omitted), `ttl` (`float`, **MAY**; seconds the job is retained).
- `poll_submit_result`: `jobId` (**MUST**), `state` (**MUST**), `accepted` (`bool`, **MUST**).
- `poll_status`: `jobId` (**MUST**). `poll_status_result`: `jobId` (**MUST**), `state` (**MUST**), `progress` (`float`, **MAY**, `0.0`–`1.0`), `eta` (`float`, **MAY**).
- `poll_fetch`: `jobId` (**MUST**), `offset` (`int`, **MAY**; used when fetching the result in slices). `poll_fetch_result`: `jobId` (**MUST**), `state` (**MUST**), `content` (`list`, **MAY**), `structuredContent` (`any`, **MAY**), `error` (`str`, **MAY**).

**`state` values** (private to this pattern, and **MUST NOT** be mixed with the state strings of other patterns): `pending` (accepted, not started), `running` (executing), `completed` (**terminal**, the result can be `poll_fetch`ed), `failed` (**terminal**), `canceled` (**terminal**), `not_found` (**terminal**; an unknown or expired `jobId`).

**Message flow**:

```
 Submitter                             Executor
   │ ── poll_submit(reqid=R1) ─────────▶ │  accepts the job, returns jobId
   │ ◀── poll_submit_result(jobId=J) ─── │  state=pending
   │ ── poll_status(reqid=R2, J) ──────▶ │
   │ ◀── poll_status_result(state=running)│
   │        ⋮  (submitter-set interval)  │
   │ ── poll_status(reqid=R3, J) ──────▶ │
   │ ◀── poll_status_result(state=completed)
   │ ── poll_fetch(reqid=R4, J) ───────▶ │
   │ ◀── poll_fetch_result(content=…) ── │  terminal-state data delivery
```

**Terminal state**: when `poll_status_result.state` or `poll_fetch_result.state` is one of the terminal states, this collaboration ends; the executor **MAY** reclaim that `jobId` after `ttl`, and queries afterwards **MUST** return `not_found` (and **MUST NOT** return `failed`).

**Errors**:

| Case | Handling |
|---|---|
| Unknown / expired `jobId` | **MUST** answer with the corresponding result signal carrying `state="not_found"`, and **MUST NOT** answer with an `error` signal |
| Polling too fast | The executor **MAY** answer `state="running"` with `eta`, and **MUST NOT** drop the connection because of it |
| `poll_fetch` called in a non-terminal state | **MUST** answer `state=running` and **MUST NOT** attach `content` |
| Cancellation | Cooperative: **MUST** set a cancellation flag and answer `state="canceled"` as soon as possible; **MUST NOT** promise to force-kill the executing thread |

**Mutual exclusion and fallback**: `conflicts_with = []`; `fallback_to = None` — this pattern is **the end of the fallback chain**; below it there is only "use `msp/request-reply` to wait synchronously for one short tool", which is outside the definition of this pattern (see §6.2).

### 7.4 The order in which the three are chosen (**SHOULD**)

```
needs incremental consumption ─────▶ msp/streaming ──(not announced by the peer)──▶ msp/callback-push
   needs the result pushed back actively ──▶ msp/callback-push ──(not announced by the peer)──▶ msp/async-polling
       last resort ──▶ msp/async-polling ──(not announced by the peer)──▶ msp/request-reply
```

---

## 8. Pattern registration

Adding an extensible pattern **MUST** complete the following steps (corresponding to the evolution order of [README.md §8](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#8-参与演进)):

| Step | Action | Landing point |
|---|---|---|
| 1 | Add a row to the pattern ID table of [README.md §5.2](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#52-模式-id), with a status marker | Specification |
| 2 | Give the complete provisions in §7 of this page (planned) or in a new page (implemented): signal types, payload fields, message flow, terminal state, errors, mutual exclusion, `fallback_to` | Specification |
| 3 | Keep the message shapes in sync in [schema.md](schema.md) | Specification |
| 4 | Create `src/msp/patterns/<name>.py` and implement a `PatternHandler` subclass | Implementation |
| 5 | Add a `"<pattern_id>": <HandlerClass>` entry to `PATTERN_REGISTRY` | Implementation |
| 6 | To start it with a preset, add it to the corresponding `Preset.patterns`; otherwise register it at runtime with `node.register_pattern(pattern_id)` | Implementation |
| 7 | Add tests; for an incompatible change, add a revision number to the revision history | Implementation + specification |

Constraints:

- Steps 4–5 **MUST** appear as a pair. Adding a registry entry without a Handler file will make the `PATTERN_REGISTRY` import fail.
- A pattern ID using the `msp/` prefix **MUST** have completed steps 1–3 first; third-party patterns **MUST** bring a prefix of their own.
- A pattern-private signal type **MUST NOT** share a name with any of the nine core types of [README.md §5.1](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#51-核心信号类型signaltype); patterns outside `msp/` **MUST** prefix their own types (`acme_stream_start`) to avoid name collisions across patterns.
- A pattern **MUST NOT** require changing the decision order of `_dispatch` (§3.1).

A minimal skeleton:

```python
# src/msp/patterns/streaming.py
class StreamingHandler(PatternHandler):
    pattern_id = "msp/streaming"
    fallback_to = "msp/request-reply"

    def install_api(self, node) -> None:
        self._node = node          # convention: store the back-reference
        node.streaming = self      # convention: attach a short name (MUST NOT conflict with the core API)

    def on_signal(self, protocol, peer_id: str, sig: Signal) -> None:
        ...  # dispatch by sig.type; hand heavy work to a separate thread
```

```python
# src/msp/patterns/__init__.py
PATTERN_REGISTRY["msp/streaming"] = StreamingHandler   # add one registry entry
```

**Note**: once the three planned patterns such as `msp/streaming` land, they **MUST** also appear in `PATTERN_REGISTRY` and **MUST NOT** be added to `CORE_PATTERNS` — they do not depend on protocol-layer state and are extensible patterns.

---

## 9. Security considerations

| # | Consideration | Provision |
|---|---|---|
| 1 | **`pattern` is not a security boundary** | The routing contract has a signal with an unregistered `pattern` degrade to the default dispatch (§3.4), so an attacker can omit or forge `pattern` to bypass any self-built check of the pattern layer. Authorization decisions **MUST** be based on the signal type and payload (such as `tool_call`'s `payload.tool`) and **MUST NOT** be based on `pattern` |
| 2 | **The `type` field is shared by several patterns** | `msp/multi-round` and `msp/task` both define `input_required`. Semantics **MUST NOT** be decided by `type` alone and **MUST** be decided together with `pattern`; it **MUST NOT** be assumed that the same `type` means interchangeable payloads |
| 3 | **`install_api` attaches names to `node`** | Overwriting the core API (such as `node.call = ...`) would directly break node behaviour (see the naming prohibition in §2.3). The loading path `PATTERN_REGISTRY` is a **static import**, a supply-chain trust issue rather than a vulnerability that a remote party can trigger at runtime |
| 4 | **The pattern layer and the protocol layer have equal rights** | Through `protocol._send` a Handler can send signals to any connected peer (the observer broadcast of `msp/task` is such a use). Patterns **MUST** be installed by the node operator, and remote registration of patterns by a peer **MUST NOT** be supported |
| 5 | **The resource-exhaustion surface of `streaming` (🔵)** | A chunked stream splits "one large message" into "N small messages", and a receiver keeping a buffer for every unfinished stream introduces a memory-amplification attack surface. Implementations **MUST** set a resource limit per `streamId` and, on exceeding it, end with `stream_end(status="error")` (the same intent appears in `ttl` and `expiresAt`) |
| 6 | **The landing point of authorization filtering is not the pattern layer** | `sub` authorization filtering on outbound fan-out belongs to the protocol layer's `publish` loop (see [publish-subscribe.md](patterns/publish-subscribe.md#8-security-considerations), [security.md](security.md#36-enforcement-points-only-two)). A pattern **MUST NOT** implement its own "who may see it" policy, otherwise the policy would drift in several places |

---

## 10. Known gaps

Listed by fact rather than by intention, so that implementers can judge how far they may rely on them.

| # | Gap | Impact | Evidence |
|---|---|---|---|
| G1 | `fallback_to` has no read site at all; **automatic fallback is not implemented** | You **MUST** check `peer.supports(pattern_id)` yourself before initiating an extensible pattern; otherwise the message goes out and is handled by the default dispatch | One declaration each in `multi_round.py:56` and `task.py:302`, with zero read sites across the codebase |
| G2 | `conflicts_with` has no read site at all; **mutual exclusion has no runtime validation** | Conflicting combinations can be active together, with undefined behaviour | No read site anywhere in the codebase |
| G3 | Signals with an unregistered `pattern` **degrade silently**, with no log | Pattern assembly errors are hard to locate (the same `tool_call` executes successfully, but over the core path rather than the pattern path) | Step 2 of `_dispatch` has no `else` branch |
| G4 | `protocol.patterns` and `node._patterns` do not contain core patterns | `node.pattern("msp/request-reply")` returns `None`; a core pattern's API is reachable only on `node` (`node.call` / `node.publish` / `node.on`) | The `CORE_PATTERNS` skipping logic |
| G5 | Pattern **capability negotiation stops at the "enumeration" level** | `Manifest.patterns` is exchanged, but no code checks before sending whether the peer has announced the pattern | Neither `_dispatch` nor `call` consults the manifest |
| G6 | The three planned patterns (`msp/streaming` / `msp/callback-push` / `msp/async-polling`) **are not implemented** | The provisions in §7 of this page cannot currently be verified against the reference implementation | No corresponding files or registry entries |
| G7 | Short-name conflicts in `install_api` have **no runtime detection** | An assignment such as `node.multiround = self` silently overwrites an existing attribute | `_install_layer_api` only does a `getattr` and then calls |
| G8 | An exception thrown by `on_signal` is caught by `_read_loop`'s `except Exception` and **drops the connection** | A local Handler bug escalates into a connection-level failure | `_read_loop`'s `logger.warning("read loop exception…")` + `_handle_disconnect` |

---

## 11. Reference implementation map

| Provision | Source file and symbol |
|---|---|
| §2.1–2.3 The `PatternHandler` contract (`pattern_id` / `fallback_to` / `conflicts_with` / `on_signal` / `install_api`) | `src/msp/patterns/base.py` → `PatternHandler` (four implementation points: `patterns/multi_round.py`, `patterns/task.py`, the `install_api` of `discovery/manual.py`) |
| §3.1 Three-step decision order and default dispatch | `src/msp/protocol/protocol.py` → `MSPProtocol._dispatch`, `_dispatch_core` |
| §3.1 Unknown type answers `-32600` | `src/msp/protocol/protocol.py` → `_dispatch_core` (the `else` branch), `_reply_error` |
| §3.3 Writing the routing key | `src/msp/core/signal.py` → `Signal.with_pattern`; `patterns/multi_round.py` → `call_multiround` / `_ask` / `_reply_result` |
| §3.4 Degradation of unregistered patterns | `src/msp/protocol/protocol.py` → `_dispatch` (step 2 has no `else`) |
| §3.5 Execution on a separate thread | `src/msp/protocol/protocol.py` → `_on_tool_call`; `patterns/multi_round.py` → `MultiRoundHandler._on_tool_call` |
| §3.6 / §8 Activation and registration | `src/msp/core/node.py` → `__init__`, `register_pattern`, `_activate_pattern`, `_install_layer_api`, `pattern`; `src/msp/patterns/__init__.py` → `PATTERN_REGISTRY`; `src/msp/core/preset.py` → `Preset.patterns` |
| §4.1 The core pattern set | `src/msp/core/node.py` → `CORE_PATTERNS` |
| §4.2 `reqid` and fan-out state | `src/msp/protocol/protocol.py` → `pending_calls`, `connections`, `call`, `publish` |
| §5.1 Using the private `_send` | `src/msp/protocol/protocol.py` → `_send`; `patterns/task.py` → each `_send` call site |
| §6.3 No automatic fallback | `src/msp/patterns/multi_round.py` → `MultiRoundHandler.fallback_to`; `src/msp/patterns/task.py` → `TaskHandler.fallback_to` (two declarations, neither with a read site) |
| §6.4 Manifest-side fields | `src/msp/core/manifest.py` → `Manifest.patterns`, `pattern_metadata`, `set_pattern_metadata`, `to_dict` |
| §7.1–7.3 The three planned patterns | None (🔵 planned, with no corresponding files or registry entries) |
| §10 G7 / G8 | `src/msp/core/node.py` → `_install_layer_api`; `src/msp/protocol/protocol.py` → `_read_loop`, `_handle_disconnect` |
