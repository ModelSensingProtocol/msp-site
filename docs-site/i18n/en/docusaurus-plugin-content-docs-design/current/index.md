# MSP Protocol Design Document

This document records MSP's design decisions and trade-offs (why it is designed this way), complementing the README (how to use it).
For the architecture overview see the "Architecture" chapter of [README.md](https://github.com/hxh230802/MSP/blob/master/README.md).

## Design principles

- **Everything is a node**: a node's identity, capabilities and state are unified as `Manifest` + `Endpoint`.
- **Everything is a signal**: tool calls, broadcasts, handshakes, heartbeats and state updates are all instances of `Signal`; only `type` differs.
- **Every layer is extensible**: everything outside `core` — discovery / presence / transport / patterns — is pluggable, keeping core changes to a minimum.

## ProReAct: waiting is a subscription, not an action

### Problem

The classical ReAct loop is pull-based and turn-based: observations come only from tool return values, so "waiting", a non-action, has no legitimate expression inside the loop and can only be disguised as an action. When the agent has to wait for an asynchronous task to finish (a file download, a build push, a job run), all it can do is `sleep(45)` and check again, then `sleep` and check again if the task is not done. Polling is not a strategy here but a forced expression: the model hard-codes "not acting" as "acting", and tokens and turns are all spent on "nothing happened".

### Decision

MSP's signal broadcast takes "waiting" out of the loop and hands it to the protocol layer: the agent registers "what I am interested in" as a local callback (`on("notify.web.download", cb)`) and then suspends; when the state really changes, the peer `publish`es that path, the signal is broadcast to every connected node, and the local callback, once it matches, wakes the agent up. Waiting is demoted from an "action" to a "subscription" (a local declaration of interest), and turns from active polling into passive wake-up — this is where the "Sensing" in the protocol's name lands.

### Boundary

This does not mean "ReAct is absolutely incapable of event-driven operation": give the model a blocking `wait_until(path)` tool, or let the environment inject events into the context, and an equivalent effect can be cobbled together at the agent layer. The difference lies in where the responsibility sits — sensing is the model's own responsibility in ReAct (an agent-layer workaround), whereas in MSP it is a first-class primitive of the protocol layer. The same capability, one owned by the model, one owned by the protocol.

## Naming conventions

Three namespaces, each with its own job, so that their semantics stay apart:

| Type | Separator | Format | Example |
|---|---|---|---|
| Node ID | none | `[a-z0-9_-]+` | `file_monitor` |
| Signal path | `.` | `segment(.segment)*` | `system.file.modified` |
| Pattern ID | `/` | `[namespace/]name` | `msp/multi-round` |
| Tool name | none | `[a-z0-9_-]+` | `get_weather` |

### Layering convention for signal paths: domain first

A signal path follows **`<domain>.<entity>.<action>`**, with the domain first:

| Level | Meaning | Example |
|---|---|---|
| Domain | A stable functional classification | `notify`, `system`, `ai`, `sensor` |
| Entity | Where the signal comes from, or what it is about | `web`, `file`, `state`, `temperature` |
| Action | What actually happened | `download`, `modified`, `progress` |

- **Domain first**: `notify.web.download` rather than `web.notify.download`. The domain is a stable,
  function-oriented classification; the entity is a mutable, implementation-oriented source. Putting
  the domain first means a receiver can capture every existing and future notification once and for
  all with `notify.**`, without amending its filter rules whenever a new source is added.
- Wildcards `*` / `**` match segment by segment, anchored on the domain (see the next section).
- Pattern IDs use slashes because a global namespace needs them (a reverse-domain prefix); this is
  a different concept from the dot-separated layering of signal paths, and the two are never mixed.

## Wildcard filtering (local callbacks)

Beyond exact matching of a signal path, the local callback `on()` supports two wildcards (only at the end of a pattern):

| Pattern | Semantics | Example |
|---|---|---|
| Exact | `path == pattern` | `ai.state` matches only `ai.state` |
| `*` | Exactly one segment | `ai.*` matches `ai.state`, not `ai.state.sub` |
| `**` | Zero or more segments | `system.**` matches `system` and anything below it |

The implementation is in `protocol/matcher.py`: the pure function `pattern_matches(pattern, path)`. Under the
broadcast model there is no subscription table — `publish` sends the signal to every connected peer, the
receiving side matches locally against the patterns registered through `on()`, and only the callbacks that
hit are triggered. The on-the-wire format is unchanged: a wildcard is just a string in the `on()` pattern.

### Use case: the virtual bus

Wildcard filtering turns "middleware" and "aggregators" into ordinary nodes, with no central broker needed:

- Notification-tuning software does `on("notify.**")`, and any signal published under the agreed `notify.*` prefix is received automatically;
- A log aggregator receives `log.**`, a monitoring dashboard receives `metric.**`, a permission audit receives `auth.**`;
- Each middleware is an independent node that receives a namespace, transforms signals and forwards them — the Unix pipeline philosophy reappearing at the signal layer.

### Future extension: node wildcards (two-dimensional matching)

Only path wildcards are implemented today. The node dimension (`@node.on(node="*", path="notify.**")`) is the
next step: add a node dimension to the `on()` pattern, have local callbacks filter by `sig.source`, and
"node × path" two-dimensional matching appears (a capability MQTT / Redis Pub/Sub do not have). Broadcast
already delivers every signal to every node, so this step is pure local filtering and needs no change to the protocol layer.

## Relation to JSON-RPC 2.0

**Conclusion: at the encoding layer MSP does not adopt the JSON-RPC envelope, but it does align semantics with JSON-RPC 2.0 on the "tool call" subset; interoperability rests on an optional `Signal ↔ JSON-RPC` bridge, with no change to the core.**

### Background

JSON-RPC 2.0 defines only an envelope: requests `{jsonrpc, method, params, id}`, responses `{jsonrpc, result|error, id}`, and notifications (no `id`). It defines neither discovery, nor publish-subscribe, nor capability negotiation, nor transport — and those are exactly MSP's core. The message layer of MCP (Model Context Protocol), by contrast, is precisely JSON-RPC 2.0, and that is the only external reason MSP has to consider alignment.

### Scope of overlap

Within MSP's `Signal`, only the request-reply pattern is semantically isomorphic to JSON-RPC:

| MSP Signal | JSON-RPC 2.0 |
|---|---|
| `reqid` | `id` |
| `payload.tool` | `method` |
| `payload.args` | `params` |
| `payload.content` / `payload.structuredContent` | `result` |
| `payload.error` | `error.message` (`error.code` takes conventional values, such as `-32603` for an internal error and `-32601` for an unknown tool) |
| `type: "tool_call"` | request (with an `id`) |
| `type: "tool_result"` | response |

The remaining signals fall outside JSON-RPC's scope:

- `SIGNAL` (signal broadcast) — JSON-RPC has no publish-subscribe semantics;
- `input_required` / `input_response` (multi-round round trips) — these require the server to send a request back to the client, which JSON-RPC's one-way model cannot express;
- `HELLO/ACK`, `MANIFEST_UPDATE`, `PING/PONG` — MSP's own handshake / capability / liveness mechanisms;
- `pattern` / `source` / `target` / `path` — the JSON-RPC envelope has no corresponding fields, so they could only be stuffed into `params`.

### Decision: no full conformance, semantic alignment only

Reasons for **not fully conforming**:

1. **One-way vs full duplex**: JSON-RPC is one-way request → response; MSP is a full-duplex protocol in which either side can send messages spontaneously.
2. **Envelope mismatch**: `pattern` routing, `path` and `source/target` on `Signal` are first-class citizens in MSP; squeezing them into `method/params` would either lose semantics or take a detour.
3. **Migration cost**: a full migration would change `_encode/_decode`, `Signal` and the `on_signal` of every pattern, fracturing the unity of "Everything is a signal", while covering only about 20% of messages.

The **semantic alignment** approach (zero code): declare the mapping in the table above — "MSP's `tool_call` is a JSON-RPC request, `tool_result` is a JSON-RPC result/error". MSP's tool calls are therefore semantically compatible with JSON-RPC 2.0.

### The interoperability hook: an optional codec bridge

Should direct interoperability with the MCP / JSON-RPC ecosystem be needed later, write a `Signal ↔ JSON-RPC` converter that sits above the transport and is as pluggable as the transport, rather than changing `core`. Interoperability is an optional capability; the core keeps the unified `Signal` envelope.

## Task pattern (msp/task) and the A2A equivalence mapping

**Conclusion: A2A is not "a pattern" but "a protocol stack"; MSP takes over only the "task semantics" that A2A genuinely adds, landing them as the `msp/task` pattern and reusing the existing primitives for the interaction.**

### Problem

A2A (Agent2Agent) solves "one agent delegating a whole task to another agent": a task state machine (submitted→working→input-required→completed/failed/canceled) plus artifacts (Artifact). MSP already has request-reply / pubsub / multi-round; what it lacks is precisely the abstraction "task lifecycle". Can MSP natively produce task semantics equivalent to A2A's?

### Decision

Implement an `msp/task` pattern: split A2A's task semantics into signals (defined inside the pattern, so the core `SignalType` is not polluted), adding only the "state machine + artifacts" layer:

| A2A | msp/task |
|---|---|
| `message/send` | `task_submit` → `task_submit_result` (blocks until "accepted", not until completion) |
| `message/stream` (SSE) | the `task_status` / `task_artifact` / `task_result` stream |
| `tasks/get` | `task_query` → `task_query_result` |
| `tasks/cancel` | `task_cancel` → `task_cancel_result` |
| `input-required` state | `ctx.ask()` (`input_required` / `input_response`, reusing multi-round's ask mechanism) |
| TaskState | state string 1:1 |
| Artifact + Part | `Artifact(name, description, parts=[content blocks])` (reusing content.py) |
| `contextId` | optional `context_id` pass-through |
| Agent Card | `Manifest.pattern_metadata["msp/task"]` (a future adapter projects it into an A2A card on demand) |
| webhook push (single subscriber) | **observer broadcast**: additionally publish to `task.<id>.<kind>`, so any node can watch with `on("task.**")` |

### Trade-offs

1. **submit is non-blocking**: `submit()` blocks only until "accepted" (returning the task_id and the submitted state), consistent with A2A's `message/send` returning a non-terminal Task; to wait for completion use `handle.wait()` (there is also the `submit_and_wait` sugar). Blocking until completion is an anti-pattern: a task may run for hours, and the client should not sit there waiting.
2. **Cancellation is cooperative**: set cancel_event and emit the terminal state at once; everything the worker emits afterwards is a no-op; threads are not killed forcibly (a Python limitation).
3. **Multiple observers are a capability A2A does not have**: A2A's SSE and webhook are both single-subscriber; MSP's pubsub naturally lets third-party nodes watch task progress, which is this pattern's point of differentiation from A2A.
4. **input-required reuses multi-round's ask mechanism**: nothing is rebuilt; the task pattern defines same-named signals internally (a different pattern, so routing does not collide).
5. **A2A is a protocol stack, not a pattern**: this pattern takes over only A2A's "task semantics"; an adapter to the A2A ecosystem over HTTP/JSON-RPC is the next step, and this pattern is its foundation.

## Tool input schema: signature introspection and zero hard dependencies

### Problem

Tool parameters need to declare descriptions and constraints outwards (like C#'s `<param>` comments), and schema validation will have to be done sooner or later, so constraints should be extracted along with them.

### Decision

`schema_from_func` generates a JSON Schema from the function signature: generated by default, and where one is passed explicitly the passed one wins. Parameter descriptions and constraints are both supported:

| Form | What is extracted |
|---|---|
| `Annotated[str, "city name"]` | `description` |
| `Annotated[int, Field(ge=0, le=100)]` | `ge` / `le` / `gt` / `lt` / `min_length` / `max_length` / `pattern` |
| An `enum.Enum` subclass | JSON `enum` (using `.value`, consistent with pydantic / FastAPI) |

Two implementation points:

1. **`get_type_hints(func, include_extras=True)`**: the default `get_type_hints` strips `Annotated` metadata, so `include_extras` must be turned on explicitly.
2. **Pydantic compatibility without a hard dependency**: no `import pydantic`; duck-typing `type(meta).__name__ == "FieldInfo"` recognises `Field`, so it runs whether or not the user has pydantic installed. The project's only third-party dependency is still `watchdog`.

### Trade-offs

- The inner schema of `Optional[Literal]` / `Optional[Enum]` has no `type` key; `anyOf` expresses nullability, avoiding an illegal `{"type": null}`.
- Introspection results are currently used only for outward declaration and take no part in runtime validation; validation is left to the future, with the constraint fields already in place.

## The Peer view

### Problem

Information about a neighbour is scattered over several places: the `Endpoint` lives at the node layer, while `Connection` and the capability manifest live at the protocol layer. "Reaching everything known about a neighbour" requires assembling it across layers.

### Decision

Introduce `Peer`, aggregating the scattered information into a single read-only object:

- **A view, not storage**: `Peer` holds no state; every attribute access reads live from the owning node. After a peer updates its manifest or disconnects, the same `Peer` object reflects the latest state at once, with no synchronised copy.
- **Query only, never operate**: `call` stays on the node; `publish` is a broadcast, not directed at a single peer, so it is not part of `Peer`.
- **Tolerant of unknown peers**: querying an unknown peer returns `None` / `[]` / `False` instead of raising.

API: `peer.endpoint` / `peer.manifest` (returns a copy) / `peer.connection` / `peer.is_discovered` / `peer.is_connected` / `peer.tools()` / `peer.signals()` / `peer.patterns()` / `peer.supports(pattern_id)` / `peer.has_tool(name)` / `peer.has_signal(path)`.

## Peer failure: errors as values, suspected-death cooldown and the directory lease

### Problem

In a P2P setting a peer may be unreachable at any moment (crash, restart, loss of network). "The peer is gone" is the normal case, not an exception; were `call()` to raise, it would break the caller's program outright. At the same time a mechanism is needed to tell "temporarily unconnectable" from "really dead", and to clean up dead nodes automatically.

### Decision

Three mechanisms, each with its own job:

1. **Errors as values**: `node.call()` returns `ToolResult(error=...)` in every case — unreachable peer (`PeerUnavailable`), unknown node (`UnknownPeer`), timeout, mid-flight disconnect — rather than raising and breaking the caller; only programming errors are raised, and `unwrap()` raises `ToolError` explicitly.
2. **Suspected death = soft cooldown, no neighbour removal**: a failed connection records `now + connect_backoff` in `_unavailable`; within the cooldown it fails fast and does not redial; a success clears the entry. **`_neighbors` is not deleted** — `DirectoryScan` deduplicates by declaration hash, so a still-present declaration file means no rediscovery, and a hard delete would permanently lose a peer that only failed temporarily.
3. **Directory lease + TTL = hard cleanup**: `DirectoryWrite` refreshes `timestamp` periodically (the lease); `DirectoryScan` discards declarations older than `stale_after`. A crashed node stops renewing → its declaration expires → it disappears naturally from the neighbour table.

### Trade-offs

- **Soft marking and hard cleanup are separate**: a failed connection is a "suspicion", an expired declaration is a "confirmation", and the two time scales do not interfere.
- Old declarations missing a `timestamp` are treated as never expiring (backward-compatible with the existing file format).
- The handshake read timeout is **now in place** (a former gap): `MSPProtocol.handshake_timeout` (10 s by default, overridable through the node's `config`) together with `Connection.set_read_timeout()`; when a peer accepts the TCP connection but never returns an ACK, the handshake ends with `ConnectionClosed` and the connection is closed, instead of blocking the dialling thread for ever.

## Startup timing: settle (wait for dials to land by default)

### Problem

The timing of the layers inside `start()` is mixed: transport `listen` is synchronous, presence `announce` is synchronous,
**and discovery is synchronous too** (`watch()` runs a full scan first), yet eager dialling happens in a background thread.
So the state when `start()` returns is "neighbours known, connections not necessarily there": an immediately following `publish()` fans out to
an empty connection set — under the broadcast model this is neither an exception nor an error code, but **silent loss**; an immediately following
`call()` then falls back on `ensure_connected()` on the spot (it can connect, but it pushes the latency of the first call onto the caller).

To users this means the question "should I sleep a little after `start()`" became one that must be answered from experience. The
`wait_until(lambda: "a" in node.connections())` scattered through the tests is the external symptom of this problem.

### Decision

`start(settle=True, settle_timeout=0.5)`: after startup completes, wait once for "all discovery-driven dials in flight to land (succeed or fail)",
and return whether things settled before the timeout; a separate `node.settle(timeout)` is also provided.

Three properties are deliberate:

1. **On by default**: on the success path dials usually land within tens of milliseconds, so settle returns at once at almost no extra
   cost; only peers that cannot be reached exhaust the timeout. Off by default would equal leaving this pitfall to every caller.
2. **Wait only, never initiate**: `settle()` never calls `ensure_connected()`; what it waits for is only "connections someone is already
   making". It is therefore a no-op under `connect_policy="lazy"` (no dial in flight, it returns `True` at once), and
   it **never** turns a lazy node into an eager one — settle and `connect_policy` are orthogonal.
3. **Register before starting the thread**: `_on_endpoint` counts the peer into the "in flight" set synchronously, **before** starting the dial
   thread, which deregisters and signals in `finally`. If registration happened inside `ensure_connected()` instead, settle
   might see an empty set before the dial thread is scheduled and misjudge "not yet started" as "already settled" — and the default
   guarantee would be fake.

### Trade-offs

- **Not a complete promise of "the network is ready"**: the boundary is explicit — only discovery-driven dialling is covered, not `call()` /
  `fetch_manifest()` / `msp/task` initiating connections themselves; nor is there any guarantee for nodes that announce only
  after `start()` returns.
- **No branching on policy**: it is not written as "settle only for eager". Auto no-op under lazy is more predictable: callers
  need not know which preset they have, and "change the preset and the semantics change" cannot arise.
- **The timeout is an upper bound, not an error**: `False` only means dials are still in flight, and the node remains usable as usual. The handshake read timeout (10 s by default,
  see the previous section) shows up here as that dial failing relatively quickly and entering its cooldown, rather than leaving `call()` stuck for ever.
- **No "connect to at least N"**: such a requirement would escalate "the peer is not ready" into a startup failure, conflicting with the
  fault-tolerant stance of "errors as values"; when a strong guarantee is needed, the user should check `connections()` itself after settle.

## Extension hooks (install_api)

### Problem

One wants sugar such as "add a discovery source dynamically at runtime", without adding a single line to the core.

### Decision

Components at any layer may define `install_api(node)`; `MSPNode` calls it after constructing the components (if it exists), and the component can then hang convenience methods on the node without touching the core. The cost is about 4 lines in the core (`_install_layer_api`).

- The communication patterns use it to hang `node.multiround`;
- Manual discovery uses it to hang `node.add_manual_source(...)` (adding a discovery source dynamically at runtime).

```python
node.start()
node.add_manual_source("http://registry2:8080/nodes")  # add a discovery source dynamically at runtime
```

### Trade-offs

When "zero core changes" and "sugar" cannot both be had, choose a small core change (about 4 lines) in exchange for the ability to inject an API at any layer.

## UDS transport (local)

### Problem

The local self-organising network uses loopback TCP by default. Loopback TCP carries protocol-stack overhead, and local inter-process communication can use the lighter Unix Domain Socket.

### Decision

`UDSTransport`: the byte stream goes over `AF_UNIX`, reusing `TCPConnection`'s 4-byte length-prefix framing (zero new framing logic). The address is a file path (by default `msp-<pid>-<rand>.sock` in the temporary directory), which fits shared-directory discovery naturally. `Preset.LOCAL_AI_UDS` is `LOCAL_AI` with the transport swapped for UDS.

### Trade-offs

- **Linux/macOS only**: Windows' Python does not expose `socket.AF_UNIX`, so `listen()` / `connect()` raise `RuntimeError`; keep using TCP on Windows.
- The socket file is not deleted automatically when the process exits: `listen()` first cleans up leftovers (deleting only files of type `stat.S_ISSOCK`, so ordinary files are not deleted by mistake), and `close()` then `unlink`s it.
- Permissions are tightened to `0o600` (only the same user may connect), consistent with the security model's "full trust for the same user on the local machine".

## Security model

### Conclusion: the trust boundary = transport reachability, authentication ≠ authorization

MSP's security model in one sentence: **the trust boundary is the boundary of the transport** — whoever can connect in is inside the trust domain. The protocol layer therefore has no built-in TLS / authentication / authorization logic; security is decided by the deployment shape, not by each individual message.

But after "connecting in" there are still two layers to distinguish: **authentication** (who you are) and **authorization** (what you may do). Authentication ≠ authorization — a certificate can only prove "you are node_b", not that "node_b is entitled to call the `rm -rf` tool".

### Threat model

Three classes of attacker, matched by three layers of countermeasure:

| Attacker | What they can do | Countermeasure |
|---|---|---|
| An eavesdropper / tamperer on the link | Read, modify and replay messages | TLS encryption |
| A node that connects without authenticating | Impersonate any node_id, slip into discovery, disturb deduplication, freeload on broadcasts | Node authentication |
| An authenticated but untrusted node | Call tools that were not opened up, trigger side effects with publish, pry into broadcasts | Authorization |

### Local self-organising network: equal permission sets, no authentication needed

The first class of scenario MSP targets is the local self-organising network: a group of processes / nodes on the same machine interconnected over localhost, each organising itself independently, sharing the discovery registry and broadcasting to one another.

In this shape, authentication achieves nothing, because **every node has the same permission set**:

- All nodes run under the **same OS user**, so their reachable permissions on the file system, network ports, environment variables and process signals are exactly identical;
- Whatever one node can read, call or write, another node can equally read, call and write;
- An encrypted channel (TLS) protects confidentiality "in transit", while the localhost loopback passes through no untrusted network segment, so there is no man in the middle to intercept.

So the local scenario skips TLS and node authentication: **authenticating a peer with the same permissions as yourself is authenticating yourself** — it adds no real security benefit, only handshake complexity and deployment cost.

### Across machines: security follows the transport

The security model is one where security "follows the transport" rather than "follows the protocol". Cross-machine exposure is a mode that is **explicitly enabled and off by default**: a node listens on localhost by default, and whoever wants to go cross-machine opens a `0.0.0.0` listener themselves and configures the set below at the same time.

When the transport changes from localhost to a real network (`TCPTransport` listening on `0.0.0.0`, or UDP / QUIC added in future), the trust boundary widens with it, and the following must then be added **above the transport layer, with the protocol core untouched**:

1. **TLS**: encryption plus server identity verification, guarding against eavesdropping and the man in the middle.
2. **Node authentication**: after the connection is established, verify the peer's identity, preventing unauthorized nodes from slipping into the discovery registry or listening in on sensitive namespaces. Two options: **mTLS** (certificate CN/SAN = node_id, suited to data centres that already have a PKI), or **signed HELLO** (the node signs its own manifest with an Ed25519 private key, node_id bound to the public key, relying on explicit key pinning / TOFU + manual confirmation — a better fit for P2P, without the burden of a PKI). The default preference is the latter.
3. **Identity binding**: the `node_id` declared in HELLO must coincide with the TLS / key identity; on a mismatch, disconnect — otherwise impersonating a node_id can disturb node_id-ordered deduplication and the discovery registry.
4. **Authorization**: see the next section. Authentication settles only "who you are"; authorization settles "what you may do".

All of this hangs on "pluggable transport wrappers" or "pre-handshake verification", decoupled from `core` in the same way as the JSON-RPC bridge and discovery sources — **the protocol core continues to recognise only `Signal`, and security is the responsibility of the transport and handshake stages**.

### Authorization: by default only the reply channel is left open (design final, implementation pending scheduling)

**Authorization is separate from capability**: the capability bits (`pub` / `sub` / `req` / `rep`) live in the manifest and say "what I claim I can do"; authorization (grants) lives in the local Preset and says "what I allow a peer to do" — authorization never depends on what a peer reports about itself, and is never exchanged with the manifest.

The authorization table is declared in the Preset, in the same "preset" style as `capabilities` / `connect_policy`:

```python
# Preset (local policy, not exchanged with the manifest)
grants = {
    # Any peer not listed: by default only the reply channel is left open
    "*":      {"req": [],            "pub": False, "sub": False, "rep": True},
    # Per-peer override
    "node_b": {"req": True,          "pub": ["notify.**"], "sub": ["metric.**"], "rep": True},
    "node_c": {"req": ["read_file"], "pub": False, "sub": False, "rep": True},
}
```

The four actions correspond to four classes of signal:

| Action | Semantics | What is authorized | Matching | Default |
|---|---|---|---|---|
| `req` | Allow it to call my tools | A list of tool names | Exact match (`True` = all) | `[]`: none at all |
| `pub` | Allow its publish to trigger my `on()` | path patterns | Reuses `pattern_matches` | `False` |
| `sub` | Allow it to receive my broadcasts | path patterns | Reuses `pattern_matches` | `False` |
| `rep` | Allow its replies (`tool_result`) in | boolean | Not per tool | `True` |

**`rep` is not in the same class as the other three.** `req` / `pub` / `sub` are **restrictions on it** — turning one off means it may not do that to me on its own initiative; `rep` is **a channel I leave open for myself** — interactions I initiate and it answers (the return value of `call()`) pass by default. "rep-only by default" therefore means precisely: **by default a peer can only be a responder towards me — I cannot count on it to act on its own, but I can count on it at any time**. Writing `rep` explicitly as `True` makes this default posture visible in the table, and also keeps an implementation from mistaking "replies" for "requests" and rejecting them together.

**Default values**: `"*"` is the default posture for network peers — `req` is an empty allow-list (nothing exposed; a tool opens up only when its name is added explicitly), `pub` is denied (its publish cannot enter `on()`), `sub` is denied (broadcasts are not sent to it), `rep` is allowed. On the local machine (loopback / UDS under the same user) the whole table is bypassed with full trust; only cross-machine peers go through it.

**There are only two enforcement points, and core still recognises only `Signal`**:

- Inbound: `_dispatch(peer_id, sig)` checks authorization first — `tool_call` checks `req`, `signal` checks `pub`, `tool_result` checks `rep`; a failure is dropped outright (an `ERROR` may be returned).
- Outbound: in the fan-out loop of `publish()`, each peer is checked against `sub`, and unlicensed peers are skipped.

**Tension with broadcast**: `sub` authorization is fan-out filtering on the sending side — "broadcast = send to all" and "do not let the unlicensed see it" collide here. It resembles the removed subscription table in shape but differs in nature: a subscription table expressed "who **wants** it" (a bandwidth optimisation), whereas `sub` authorization expresses "who **may** see it" (security), so per-peer filtering comes back as a security requirement, with no bandwidth optimisation mixed in.

### One-line comparison

| Deployment shape | Trust boundary | What is needed |
|---|---|---|
| localhost self-organising network | The same OS user | No TLS / authentication / authorization |
| Cross-machine / public network | The reachable extent of the network | TLS + node authentication + authorization (by default only the reply channel is left open) |

## Trust boundary: separating "peer input" from "local state" into layers

**Problem** (from a risk review of the merged code): three independent SEV-1 findings point at the same root cause — what a peer reports about itself goes straight into the control flow.

- **Authorization falls through to allow for pattern-private signals**: `authorized()` checks only `tool_call` / `signal` / `tool_result` and `return True` for everything else. Any newly introduced signal type name therefore automatically acquires "authorization-exempt" status: `task_submit` executed its task function just the same under `req=[]` (the default of leaving only the reply channel open). In testing — with `req` denying everything, an ordinary tool call was correctly rejected, yet `task_submit` went through and returned its artifacts. The specification at the time recorded "who owns the authorization of pattern-private signals" as **undefined** and required implementations to tighten it at the pattern layer; the implementation did not.
- **Failure of an optional capability was placed on the fatal path**: `task_store` was read as UTF-8 text, bad bytes raised `UnicodeDecodeError`, and it was called during **node construction** → one bad line pinned the node **permanently** (reproduced on every restart, with no code path that would ever fix that line). The same module's docstring still said "bad lines are skipped; the whole file is not lost over one bad line" — the code contradicted its own promise.
- **An unserialisable artifact kills the worker**: the serialisation exception is raised at the write-to-disk site and then **raised a second time, uncaught**, at the terminal-state write → the daemon thread dies, the task stays in a non-terminal state for ever, and the submitter waits for `task_result` for ever (with nothing to do but exhaust the timeout).

**Decision**

1. **Authorization denies by default** (`security.md` §3.9): the three core types are still looked up as before, connection-mechanism types are explicitly exempted, and **every other pattern-private signal must have its ownership declared by the registered pattern itself** (`PatternHandler.authorize`, whose default implementation returns `False`). When a new pattern or a new signal type is added, the consequence of forgetting to classify it is "denied" rather than "allowed".
2. **Source verification follows connection identity, not self-reported fields** (§3.10): `sig.source` is what the peer reports about itself; `peer_id` is a fact established locally after the handshake. **The read direction and the write direction must be symmetric** — `task_query` / `task_cancel` used to verify `client_id`, whereas `task_status` / `task_artifact` / `task_result` verified the sender not at all, so a third party could forge the terminal state and artifacts of someone else's task.
3. **Failure of an optional capability must not be fatal**: persistence is off by default, so any failure of it degrades only to "not persisted + a warning" — it does not refuse to start, does not kill the worker and does not change task semantics. State is authoritative in memory; the disk is best effort.
4. **Foreign input is normalised at the entry point** (peer manifests, the authorization table): a wrong type is treated as absent, rather than letting a type error turn into a disconnect at runtime in the form of an `AttributeError`, or freeze manifest updates silently in the form of a `TypeError`.

**Trade-offs**

- **Both normalisation and defensive fallbacks are done**: entry-point normalisation (handshake / update / construction) is responsible for semantic correctness, fallbacks at the point of use (`Peer.tools()` and the like) are responsible for "not being crashed". Doing both is deliberate — there is more than one injection path.
- **An unserialisable artifact chooses to fail early** (the task then goes `failed`) rather than being silently replaced with text: failure is a terminal state too, and the submitter receives it; a silent degradation would leave "the artifact lost content" known to nobody.
- **`mr-<n>`, the predictable `reqid`, was left alone**: source verification already closes cross-peer injection (only the called peer can reply), and changing reqid generation would touch existing messages and tests for insufficient benefit. The specification still requires that `reqid` not be treated as a security token.
- **The whole-table bypass for local peers was not touched**: under the same OS user permissions are equal anyway, so bypassing "authorization" means nothing. Cross-machine is the reason the authorization table exists, and the scenario this fix targets.

**Verification**: `tests/test_risk_fixes.py`, 24 cases, all red before the fix. Five of them are guardrails for "existing behaviour must not change" — local peers still bypass the whole table, an `req` allow-list hit is still allowed, an unknown signal type still returns `-32600`, and a normal receipt from the executor is still accepted.

## Capability surface: resources / prompts / sampling (design, not yet implemented)

### Background: MCP's capability surface

Besides tools, MCP has three further capability classes, plus two notification classes:

- **resources**: the server exposes context data to the client as resources (URI → content); the client can `read` them and `subscribe` to changes (on a change the server pushes `resources/updated`). This lets the model do more than call tools: it can also "read" context such as files and database records.
- **prompts**: the server predefines reusable prompt templates (a name plus parameters); when the client `get`s one, the server renders the complete prompt. This moves knowledge of "how to write the prompt" from client to server.
- **sampling**: a reverse capability. When the server needs "the model to generate a passage" mid-processing (say, reasoning over an agent subtask), it sends a request to the client, which generates the passage with the LLM behind it and returns it. Master and servant are inverted: the server becomes the capability requester, the client (the LLM host) the provider.
- **elicitation**: the server needs a user decision / input and asks the client for it. Isomorphic to MSP's multi-round (`input_required` / `input_response`).
- **roots**: the client declares its filesystem roots one-way, and the server uses them to decide which paths it may access.

### The MSP mapping: everything is a signal

"Everything is a signal" means these three capability classes are not three mechanisms but several groups of new SignalTypes:

| MCP operation | MSP signal | Direction |
|---|---|---|
| `resources/read` | `resource_read` → `resource_content` | client→server request / response |
| `resources/subscribe` | `resource_subscribe` / `resource_unsubscribe` → `resource_updated` | subscription + change notification |
| `prompts/get` | `prompt_get` → `prompt_content` | client→server request / response |
| `sampling/createMessage` | `sampling_request` → `sampling_result` | server→client reverse request |
| `elicitation/create` | `elicitation_request` → `elicitation_result` | server→client reverse request |
| `roots/list` | `roots_list` → `roots` / `roots_changed` | client→server notification |

### Three key trade-offs

1. **The manifest is the list, so the list round trip is dispensed with**: MCP's `resources/list` and `prompts/list` need an extra request; MSP's `resources` / `prompts` already live in the Manifest, so the handshake plus `MANIFEST_UPDATE` completes "listing". Hence no list signals, only read / get.
2. **Reverse capability is a natural advantage of full duplex**: MCP rests on one-way JSON-RPC, so sampling requires client and server to swap roles; in MSP both sides can send signals spontaneously, so `sampling_request` is simply "a `tool_call` with the direction reversed", with isomorphic reqid correlation and no role flip needed.
3. **Resource subscription and path filtering are two dimensions**: signals are broadcast by path (dot-separated layers) and filtered locally by the receiver's `on()`, while resources are subscribed by URI. The dimensions differ, so URIs are not forced into paths and `resource_subscribe` is used separately.

### Current state and how to fill the gap

`Manifest` already declares the "bits" for these capabilities: the `resources` / `prompts` descriptors, and the three booleans `clientCapabilities.sampling / elicitation / roots`. What is missing is the corresponding SignalTypes and protocol operations — the way to fill the gap is to add branches to `_dispatch_core` (isomorphic to `tool_call`) and to add `@node.resource(...)`, `@node.prompt(...)`, `node.sample(peer, ...)` and similar APIs at the node layer. Until that is done, a peer that receives the manifest "sees the promise but cannot use it", so these declarations are currently reserved only.

## The remote tool view: turning a peer's schema into local functions

### Problem

The code that calls a remote tool is only three lines. The real friction lies **before** that: one must first `fetch_manifest()`, then read `inputSchema` by hand, just to learn what the tool is called, what its parameters are called, and which are required. A wrong parameter name is especially costly — it does not fail locally but crosses the network and comes back as a string returned by the peer (`__init__() got an unexpected keyword argument 'city'`), with no stack trace and no location, leaving manual comparison against the manifest as the only recourse.

And this schema is already in hand: `ToolDescriptor.inputSchema` is exchanged during the handshake. So no code-generation step is **needed** here, and no new wire fields either — gRPC wants a `.proto`, OpenAPI wants a spec file, but MSP's IDL is already inside the protocol.

### Decision

`peer.t`: projects `inputSchema` into an `inspect.Signature` and a lazy callable proxy (`core/remote_tools.py`). Three deliberate constraints:

1. **Hang it under its own namespace, not directly on `Peer`.** `Peer` already has 12 members (`tools` / `signals` / `manifest` / `node_id` …), and the tool-name grammar `[a-z0-9_-]+` may well collide with them; `__getattr__` fires only when an attribute is not found, so hanging tools directly on `Peer` would **silently** return the wrong thing, with not even a chance of detection. A sub-namespace reduces the reserved names from 12 to 5, and a colliding tool remains reachable through `t[...]` / `t.tool(...)`.
2. **Attribute access is pure.** Connecting and calling are deferred to **the moment of the call**; otherwise `hasattr` / `dir` / a debugger expanding the object would all trigger network I/O, and `Peer`'s contract is "querying an unknown peer returns empty values, raises nothing and has no side effects".
3. **No new error-semantics switch.** By default it returns `ToolResult` (errors as values); to raise, use the existing `unwrap()`. Adding an `on_error="raise"` would amount to quietly overturning the specification's headline decision inside a convenience function; reusing the existing contract cannot possibly conflict with the specification.

The signature mapping follows "if it cannot be recognised, degrade to `Any`, never guess": no `properties` key → the signature is unknown (keyword pass-through, so `**kwargs`-style tools remain callable); `properties: {}` → strictly no parameters; a parameter name that is not a valid identifier or is a keyword → **never silently renamed**, only listed in `unrepresentable` and `conflicts()`. Required parameters go into positional slots (preserving manifest order), optional ones are always keyword-only — so "an optional parameter before a required one" cannot trigger Python's `non-default argument follows default argument`, and the manifest need not be reordered for the sake of ordering.

### Trade-offs

- **The upper bound on signature quality is the fidelity of `schema_from_func`.** It currently produces no `default` (optional parameters show as `<optional>` rather than their real default), and under pydantic v2 `Field(ge=…)` is silently lost. This module only degrades faithfully; it does not compensate — compensating would amount to inventing, on the client, constraints the provider never declared. Seen the other way round, this feature pushes `inputSchema` from "used only for declaration" into a **load-bearing structure**, which turns "fix the generator" into something with a motive behind it.
- **Return values are still `Any`.** `ToolDescriptor.outputTypes` is always empty, so return values have no schema; full typing would first require the output side to be filled in.
- **What it does not do**: it does not resolve `$ref`, does not fetch remote references (no SSRF surface), does not generate `.py` files, does not use `exec` (a peer's schema is untrusted input), and does not cache — the view is created and discarded as needed, with tool names and signatures read live from `Peer`, so a peer's `manifest_update` takes effect at once.
- **No timeout parameter**: all keyword arguments are passed to the peer as-is, so there is no reserved word; to customise the timeout use `node.call(peer, tool, args, timeout=...)` directly.
- **The specification gained exactly one clause**: `inputSchema` is part of the outward contract (request-reply §7.2). The mapping from JSON Schema to a host language **does not enter the specification** — it is a client-side choice, not on the wire, and forms no interoperability surface. This boundary is deliberate: in the last comparison with MCP, the one thing held onto was "the wire format does not grow".
