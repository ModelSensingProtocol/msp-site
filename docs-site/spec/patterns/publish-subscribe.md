# Core Pattern: Publish–Subscribe (`msp/publish-subscribe`)

| | |
|---|---|
| **Protocol revision** | `2026-10-10` |
| **Status** | ✅ implemented (including sender-side `sub` authorization filtering) |
| **Defined on this page** | The core communication pattern `msp/publish-subscribe`: the broadcast model (`publish` fans out to every connected peer, **no subscription table**), receiver-side local filtering (`on(path)`), path syntax and the wildcard matching algorithm (`pattern_matches`, line by line), matching boundaries and pitfalls, the virtual bus and versioned paths, and security considerations |

> This page concretises [patterns.md](../patterns.md). `msp/publish-subscribe` is a **core pattern**: it is implemented directly in the protocol layer, does not enter `PATTERN_REGISTRY`, and has no Handler instance (the rationale is in [patterns.md §4.2](../patterns.md#42-why-these-two-are-core)).

---

## 1. Overview

The semantics of `msp/publish-subscribe` in one sentence: **the publisher fans one `type="signal"` message out to every connected peer; the receiver filters locally with a path pattern, and only the callbacks that match are triggered.**

Its key design trade-off is that there is **no subscription table**:

- **There is no subscribe / unsubscribe signal on the wire.** The publisher does not know who "subscribed" to what, and does not need to.
- **Publishing needs no negotiation.** `publish()` sends the signal straight to every connected peer, including peers that have never expressed interest.
- **The filtering responsibility lies with the receiver.** Whether to consume is decided by the receiver's `on()` pattern.

What this trade-off buys is a minimal protocol surface: a node that implements only `msp/publish-subscribe` needs to maintain no per-peer subscription state, and needs to handle no ordering race between subscriptions and disconnection (is a subscription still there after the peer drops? — the question does not arise, because there are no subscriptions).

The cost is **bandwidth**: `N` connected peers means `N` sends, irrespective of "how many are actually interested". This is a **deliberate trade-off, not a defect** (see [architecture.md §Known gaps](../architecture.md#13-known-gaps)).

### 1.1 Position in the layering

| Capability | Public API | Protocol-layer implementation |
|---|---|---|
| Publish | `node.publish(path, payload)` | `MSPProtocol.publish` |
| Subscribe (local filtering) | `node.on(path)` | `MSPProtocol.on`, `MSPProtocol._on_signal` |
| Path matching | — | `protocol/matcher.py` → `pattern_matches` |
| Automatic repeated publishing | `@node.signal_source(path)` / `@node.signal(path)` | `MSPNode._run_signal_source` |

---

## 2. Contract

### 2.1 Message shape

`publish(path, payload)` constructs **exactly** the following signal:

```python
Signal.make(
    type=SignalType.SIGNAL,   # "signal"
    source=self.node_id,
    path=path,
    payload=payload,
)
```

**MUST** satisfy:

| Field | Value | Level |
|---|---|---|
| `type` | always `"signal"` | **MUST** |
| `source` | always this node's `node_id` | **MUST** |
| `path` | the path supplied by the caller, which **MUST** conform to `segment(.segment)*` (`[README.md §5.3](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#53-命名规范)`) | **MUST** |
| `payload` | the dictionary supplied by the caller | **MUST** |
| `target` | `None` (a broadcast has no single target) | **MUST** be `None` |
| `pattern` | `None` (core patterns write no routing key) | **MUST** be `None` |
| `reqid` | `None` (a broadcast needs no reply correlation) | **MUST** be `None` |
| `timestamp` | filled in automatically by `Signal.make` | **MUST** |

**Note**: there is **no** `path` field inside `payload` — the path is the **envelope field** `Signal.path`, not a payload field. Implementations **MUST NOT** stuff the path into `payload`.

### 2.2 Fan-out semantics

`publish()` **MUST**:

1. snapshot the connection table under the lock (`list(self.connections.items())`) and **MUST NOT** perform network sends while holding the lock;
2. send the encoding of the same message to **every** connected peer;
3. for a peer that raises `ConnectionClosed` on send, **MUST** trigger that peer's disconnection cleanup (`_handle_disconnect(peer_id, conn)`) and keep sending to the remaining peers;
4. **MUST NOT** break out of the fan-out loop because one peer failed;
5. **MUST NOT** return any success/failure count — the return value of `publish()` is `None`. A broadcast is "best-effort", not "delivered to all".

> The precise meaning of "best-effort": if a peer's connection is **already** closed when `publish()` is called, that peer does not receive the signal; if the connection closes during the send, the fan-out loop notices and cleans up; if the peer process is dead but TCP has not yet noticed, the message is written into the kernel buffer and then vanishes with the connection timeout. There is **no** delivery confirmation, and there **SHOULD NOT** be — if you need confirmation, use `msp/request-reply`.

### 2.3 Receiver-side local filtering

The receiver **MUST** process a received `signal` by the following rules:

1. step 1 of `_dispatch` does not match (`signal` is not a core signal type);
2. step 2 of `_dispatch` does not match (`pattern` is `None`);
3. `_dispatch_core` matches `SignalType.SIGNAL` → `_on_signal(peer_id, msg)`;
4. `_on_signal` snapshots the callback list under the lock, then iterates outside the lock;
5. for each `(path_filter, func)`:
   - if `path_filter is None` → call **unconditionally**;
   - otherwise, if `pattern_matches(path_filter, msg.path)` is true → call;
   - otherwise skip.

**MUST** satisfy:

| # | Provision | Level |
|---|---|---|
| 1 | a callback with `path=None` **MUST** match **all** paths | **MUST** |
| 2 | each matching callback **MUST** be called exactly once; when several callbacks match, all of them **MUST** be called | **MUST** |
| 3 | any exception raised by a single callback **MUST** be caught (logged as a warning) and **MUST NOT** affect subsequent callbacks | **MUST** |
| 4 | callbacks **MUST** be invoked on the protocol-layer read-loop thread (**not** a worker thread) | **MUST** |
| 5 | a callback **MUST NOT** perform long-running work — it blocks message reception on that connection (same as [patterns.md §3.5](../patterns.md#35-the-thread-on_signal-runs-on-and-the-blocking-prohibition)) | **MUST NOT** |
| 6 | callback registration **MUST** be possible at any time, including while the read loop is running (the registry is modified under the lock) | **MUST** |
| 7 | a callback **MUST NOT** deregister itself from inside the callback — there is currently **no** deregistration API (see §10 G1) | **MUST NOT** |

The callback signature is `func(sig)`, where `sig` is the complete `Signal` object (`sig.source` / `sig.path` / `sig.payload` / `sig.timestamp` are available).

### 2.4 Registration API

The protocol layer's `on(path=None, callback=None)` supports two forms:

```python
# Form one: decorator
@proto.on(path="ai.state")
def handler(sig): ...

# Form two: direct registration
proto.on(path="ai.state", callback=handler)
```

The node layer's `node.on(path=None)` exposes only the decorator form:

```python
@node.on("ai.state")
def handler(sig): ...

@node.on()          # path=None: receive everything
def spy(sig): ...
```

**MUST** satisfy:

1. the same callback **MAY** be registered several times and will then be called several times — implementations **MUST NOT** deduplicate;
2. registration **MUST** return the decorated function itself (decorator form), so that the function remains callable;
3. the `path` parameter **MUST** allow `None`;
4. implementations **MUST NOT** validate the format of the `path` parameter — an invalid path pattern is not an error, it simply never matches (see §4.5).

### 2.5 Automatic repeated publishing

`@node.signal_source(path)` (alias `@node.signal(path)`) decorates a **generator** function. After the node starts, each signal source iterates continuously on its **own thread**:

```
for payload in func():
    if not running: break
    if not isinstance(payload, dict): continue
    publish(path, payload)
```

**MUST** satisfy:

1. every `yield` of the generator **MUST** be a `dict`; anything that is not a `dict` **MUST** be skipped (no error, no publish);
2. an arbitrary delay before the first yield is allowed (commonly used to wait for subscribers);
3. exceptions raised inside the generator function **MUST** be caught and logged as "signal source terminated abnormally", and **MUST NOT** affect other signal sources or the node;
4. `signal_source` **MUST** also declare the path (equivalent to calling `declare_signal(path)` once), so that the path appears in `Manifest.signals`;
5. after the node has stopped it **MUST NOT** keep publishing — the loop breaks while `_running` is false.

---

## 3. Path syntax

A path is a signal's **logical address**; it is independent of transport addresses and of `node_id`.

### 3.1 Characters and layering

| Item | Rule |
|---|---|
| Separator | the dot `.` |
| Format | `segment(.segment)*` |
| Characters within a segment | **SHOULD** be `[a-z0-9_-]` (the same style as `node_id` / tool names); **MUST NOT** contain dots, spaces, or wildcards |
| Case | **SHOULD** be all lowercase; matching **MUST** be case-sensitive (`ai.state` ≠ `Ai.State`) |

### 3.2 Domain-first convention

A path **MUST** follow **`<domain>.<entity>.<action>`**, with the domain first:

| Layer | Meaning | Examples |
|---|---|---|
| domain | stable, function-oriented classification | `notify`, `system`, `ai`, `sensor`, `log`, `metric`, `auth`, `task` |
| entity | the source or subject of the signal | `web`, `file`, `state`, `temperature` |
| action | what actually happened | `download`, `modified`, `progress`, `changed` |

Correct and incorrect examples side by side:

| Form | Assessment |
|---|---|
| `notify.web.download` | ✅ domain first: a receiver's `notify.**` covers every present and future notification once and for all |
| `web.notify.download` | ❌ entity first: every new notification source forces a change to the filtering rules |

The **normative consequence** of domain-first: receivers **SHOULD** subscribe per domain (`notify.**`, `log.**`, `metric.**`) rather than entity by entity. This is the premise that makes "no filtering-rule changes for new sources" hold.

### 3.3 Difference from Pattern ID

Paths use dots, Pattern IDs use slashes, and the two **MUST NOT** be mixed:

| Object | Separator | Format | Example |
|---|---|---|---|
| Signal path | `.` | `segment(.segment)*` | `notify.web.download` |
| Pattern ID | `/` | `[namespace/]name` | `msp/publish-subscribe` |

A path segment of the form `msp/...` **MUST NOT** appear in a path, and a path **MUST NOT** be used as the value of `Signal.pattern`.

### 3.4 Wildcards

A wildcard is allowed **only** at the **end** of a pattern, and only in two forms:

| Form | Name | Semantics |
|---|---|---|
| `*` | single-segment wildcard | exactly **one** segment (≥ 1 non-empty segment) |
| `**` | multi-segment wildcard | **zero or more segments** (including the prefix itself) |

**MUST** satisfy:

> A wildcard **MUST** appear only at the end of the pattern. A `*` in the middle is a **literal**, produces no wildcard semantics, and the pattern **never matches any path** (see §4.5, pitfall 1).

### 3.5 Path declaration (optional)

`node.declare_signal(path, schema=None, description="")` **MAY** write a path into `Manifest.signals` for subscribers to consult:

- this is a **declaration** and produces no signal;
- `schema` is an optional JSON Schema, used **only for announcing**; it is **not** validated at publish time and **not** enforced at subscribe time;
- `signal_source` declares the path implicitly.

The path list in a manifest **MAY** therefore disagree with the paths actually published at runtime — implementations **MUST NOT** treat it as an admission list.

---

## 4. Wildcard matching algorithm

Matching is a **pure function**: `pattern_matches(pattern, path) -> bool`. The receiver calls it independently for each registered pattern. This section maps line by line onto the reference implementation.

### 4.1 Algorithm

```
pattern_matches(pattern, path):
    # Branch 1: exact equality
    if pattern == path:
        return True

    # Branch 2: multi-segment wildcard ".**"
    if pattern.endswith(".**"):
        prefix = pattern[:-3]                  # strip the trailing 3 characters ".**"
        return path == prefix or path.startswith(prefix + ".")

    # Branch 3: single-segment wildcard ".*"
    if pattern.endswith(".*"):
        prefix = pattern[:-2]                  # strip the trailing 2 characters ".*"
        if not path.startswith(prefix + "."):
            return False
        return "." not in path[len(prefix) + 1:]   # the remainder must not contain a dot

    # Branch 4: everything else does not match
    return False
```

The three tests **MUST** be executed in the order above, returning on the first hit.

### 4.2 The branches one by one

| Branch | Condition | Result | Key point |
|---|---|---|---|
| 1 | `pattern == path` | `True` | ordinary paths without wildcards take this branch. **Note**: this branch **also applies to strings containing `*`** — when pattern and path are literally identical (for example both sides are `ai.*`) it returns `True` |
| 2 | pattern ends with `.**` | `path == prefix` **or** `path.startswith(prefix + ".")` | `prefix` is the remainder after removing `.**`. Note that the `path == prefix` branch means `.**` matches **the prefix itself** (zero segments) |
| 3 | pattern ends with `.*` | prefix matches and the remainder contains no dot | `.*` does **not** match the prefix itself — it requires **at least** one segment |
| 4 | anything else | `False` | this is where "a `*` in the middle of the pattern" and "a pattern without wildcards that is not equal" land |

### 4.3 Match results derived from the algorithm

The table below **MUST** agree with the implementation:

| Pattern | Semantics | Matching example | Non-matching example |
|---|---|---|---|
| `ai.state` | exact | `ai.state` | `ai.state.x`, `ai`, `ai.states` |
| `ai.*` | exactly one segment | `ai.state`, `ai.progress` | `ai`, `ai.state.x` |
| `system.**` | zero or more segments | `system`, `system.cpu`, `system.cpu.load.1` | `systematic`, `system.cpuX` (without a dot, `path == prefix` holds only for `system`) |
| `*` | wildcard in the middle / standalone (literal) | —— | **every path** (always `False`) |
| `ai.*.state` | the `*` in the middle is treated as a literal | —— | **every path** (always `False`) |
| `**` | does not end with `.**` | —— | **every path** (always `False`) |
| `*.state` | the `*` in the middle is treated as a literal (it ends with neither `.*` nor `.**`, so it falls to branch 4) | only the path `*.state` that is **literally identical** | everything else, including `ai.state`, `*.x`, `*.a.b` |
| `` (empty string) | the exact branch matches the empty path | the empty path `""` | everything else |

> The behaviour in rows 7 and 8 of the table above is the **literal result** of the algorithm, not the design intent. Implementations **MUST NOT** deviate from the algorithm in order to make those rows "look more reasonable" — the matching rules are part of the interoperability contract ([README.md §1.3](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#1-修订历史) states that changing the matching algorithm **MUST** ship a new revision number).

### 4.4 Two pitfalls (**MUST** be explicit)

**Pitfall 1: a wildcard is effective only at the end of a pattern; a `*` in the middle is a literal and never matches.**

`ai.*.state` does **not** match `ai.cpu.state`. Branch 3 of the algorithm recognises only "ends with `.*`", and `ai.*.state` ends with `state`, so it falls to branch 4 and returns `False`. Likewise:

- `system.*.cpu` → always `False`;
- `*.state` → true only when the path is **literally equal** to `*.state`, `False` otherwise (it does not end with `.*`, so it falls to branch 4).

> Conclusion: when "any one layer" is needed, `*` **MUST NOT** be written in the middle. Use `**` at the **end** instead (`ai.**`), which matches `ai` and any depth below it — at the cost of also matching a single segment and deeper multiple segments, with lower precision than "exactly one segment".

**Pitfall 2: empty patterns and "prefixes that contain no dot" behave as the algorithm actually says — do not guess.**

Derivation one by one (the case where `prefix` is empty):

| Pattern | `prefix` | Actual behaviour of branches 2/3 | Actual result |
|---|---|---|---|
| `*` | not applicable | ends with neither `.**` nor `.*` → falls to branch 4 | always `False` (except the literally equal path `"*"`) |
| `.*` | `""` | branch 3: requires `path.startswith(".")`, then requires `path[1:]` to contain no dot | matches paths such as `.a` (literally starting with a dot); `False` for `a.b` |
| `.**` | `""` | branch 2: `path == ""` or `path.startswith(".")` | matches `""` and any path starting with a dot |
| `system.*` | `system` | branch 3: `path.startswith("system.")` and `path[7:]` contains no dot | matches `system.cpu`; does not match `system` (**`.*` does not match the prefix itself**) nor `system.cpu.load` |
| `system.**` | `system` | branch 2: `path == "system"` or `path.startswith("system.")` | matches `system`, `system.cpu`, `system.cpu.load` (**`.**` matches the prefix itself**) |
| `**` | not applicable | does not end with `.**` (only 2 characters) → falls to branch 4 | always `False` |

Two normative-level conclusions follow:

1. **`system.*` does not match `system`**, whereas **`system.**` does match `system`**. To mean "everything under a domain (including the domain itself)" you **MUST** use `.**`.
2. **A bare `*` and a bare `**` are not valid patterns.** They never match (except literally), **SHOULD** be regarded as a user typo, and implementations **MAY** warn at registration time but **MUST NOT** treat them as shorthand for "match everything".

### 4.5 Scope of matching

| Scenario | Uses path wildcards |
|---|---|
| local callback filtering for `signal` (`on()`) | ✅ yes |
| tool names (`payload.tool`) | ❌ **no** — **MUST** match exactly (`_tools` is a dictionary lookup) |
| Pattern ID (`Signal.pattern`) | ❌ **no** — **MUST** match exactly (`protocol.patterns` is a dictionary lookup) |
| `node_id` | ❌ **no** — **MUST** match exactly (`connections` / `_neighbors` are dictionary lookups) |
| `pub` / `sub` entries in the authorization table | ✅ reuses `pattern_matches` ([security.md §3.3](../security.md#33-the-four-actions)) |
Therefore: **tool invocation is not affected by wildcards**. Declaring a tool name such as `get_*` does **not** make `get_weather` invocable as `get_*`.

---

## 5. Message flow

### 5.1 Broadcast and local filtering

```
 Publisher node_c                            Receiver node_d
      │                                              │
      │ 1. @node.signal("ai.state") generator yields │
      │      {"status": "thinking", "seq": 0}        │
      │ 2. node.publish("ai.state", payload)         │
      │ 3. lock, snapshot connections ──────────────┐│
      │                                             ││
      │ ── signal(path="ai.state", payload=…) ──────▶│ 4. read loop _dispatch
      │      (one copy per connected peer)           │     step 1: no match
      │                                              │     step 2: no match (pattern=None)
      │                                              │     → _dispatch_core → _on_signal
      │                                              │ 5. iterate the handler table
      │                                              │     on("ai.state") match → call
      │                                              │     on("ai.*")     match → call
      │                                              │     on("system.**") no match → skip
      │                                              │ 6. handler exception → log warning, next
      ▼                                              ▼
```

### 5.2 Failure handling during fan-out

```
 publish(path, payload)
        │
        ├─ lock: peers = list(connections.items())
        │
        └─ for peer_id, conn in peers:
               try:
                   conn.send(encoded)
               except ConnectionClosed:
                   _handle_disconnect(peer_id, conn)   ← clean up this peer, continue with the next
```

**MUST**: a send failure for one peer **MUST NOT** interrupt the loop and **MUST NOT** throw outwards.

### 5.3 "The bus without a bus"

The broadcast model needs no central broker to assemble a middleware topology: **each middleware is just an ordinary node**.

```
 Source nodes                   Middleware node fmt                          Observer nodes
   │                                    │                                            │
   │ ── signal(log.app.raw) ──────────▶ │                                            │
   │ ── signal(log.web.raw) ──────────▶ │                                            │
   │                                    │ @on("log.**") collect raw logs             │
   │                                    │ transform (timestamps, levels, redaction)  │
   │                                    │ publish("log.formatted.**")                │
   │                                    │ ─────────────────────────────────────────▶ │ @on("log.formatted.**")
   ▼                                    ▼                                            ▼
```

Normative provisions:

1. the middleware **MUST** be an ordinary `MSPNode` — the protocol layer **MUST NOT** be required to provide any broker/proxy role;
2. the middleware **SHOULD** "subscribe to one domain and publish to another" (`log.**` → `log.formatted.**`), so that downstream can switch between the "raw stream" and the "processed stream" at domain granularity;
3. the middleware **MUST NOT** change the semantics of the path it forwards — it **SHOULD** express processing by **adding** a domain or layer (`log.formatted.*`) rather than reusing the original path;
4. a middleware's forwarding **MUST NOT** create a self-exciting loop on the same path (for example `@on("log.**")` and `publish("log.x")` at the same time); implementations **SHOULD** avoid this through domain isolation.

### 5.4 Versioned paths

Paths are **strings**, so evolution relies on **mounting in parallel** rather than changing semantics:

| Approach | Assessment |
|---|---|
| publishing `x.changed` and `x.changed.v2` **in parallel** | ✅ recommended: old subscribers keep receiving `x.changed`, new subscribers use `x.changed.v2`; the two do not interfere, and switching is a choice on the subscriber side |
| changing the meaning of `x.changed` to v2 in place | ❌ **MUST NOT**: old subscribers would silently receive data with different semantics |

Argument:

1. **The matching algorithm is prefix-based.** `x.changed.**` matches both `x.changed` and `x.changed.v2` — because branch 2 requires `path == "x.changed"` or `path.startswith("x.changed.")`, and both hold. "Subscribing to all versions at once with a wildcard" is therefore **possible**, which is convenient during a migration.
2. **Exact subscription is the isolation tool.** A subscriber that wants to pin itself to v1 uses the exact pattern `x.changed`, which does **not** match `x.changed.v2`.
3. **The domain-first convention lets the version follow the action.** The third layer of `<domain>.<entity>.<action>` is the action, so the version number **SHOULD** appear as a new segment after the action (`x.changed.v2`), and **MUST NOT** be inserted between domain and entity (`x.v2.changed` would break the domain granularity of `x.**`).

**SHOULD**: on a breaking change, publish the old and the new version **side by side** for at least one version cycle, and declare both in `Manifest.signals`.

### 5.5 Publisher self-visibility

A publish does **not** loop back to the node itself: `publish()` iterates only over `connections`, so the caller's own `on()` callbacks are **not** triggered by signals it published itself.

This **MUST** be stated explicitly — implementations **MUST NOT** rely on the assumption that "a local publish also triggers local callbacks":

- when local processing is needed, the local function **MUST** be called directly after `publish()`, or an explicit local loopback **MAY** be implemented (not required by this specification);
- this is a **known difference** from models such as MQTT, where "a client subscribing to its own topic receives its own messages"; in cross-implementation interop you **MUST NOT** assume the other side loops back.

---

## 6. Data types

### 6.1 Fields of the `signal` signal

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | `"signal"` | **MUST** | |
| `source` | `str` | **MUST** | the publisher's `node_id`; the receiver **MAY** filter by source on that basis (currently **not** implemented, see §10 G4) |
| `path` | `str` | **MUST** | the path, see §3 |
| `payload` | `object` | **MUST** | any JSON object; defaults to `{}` |
| `target` | `null` | **MUST** | a broadcast has no target |
| `pattern` | `null` | **MUST** | core patterns write no routing key |
| `reqid` | `null` | **MUST** | a broadcast correlates nothing |
| `timestamp` | `float` | **MUST** | Unix timestamp, from the publisher's local clock |

JSON example:

```json
{
  "type": "signal",
  "source": "node_c",
  "pattern": null,
  "target": null,
  "path": "ai.state",
  "reqid": null,
  "payload": {"status": "thinking", "seq": 0},
  "timestamp": 1791331200.5
}
```

`Signal` envelope fields are always **snake_case**. Field names inside `payload` are chosen by the **publisher** and **SHOULD** agree with the declaration of the publisher's `Manifest.signals[path].schema`; the receiver **MUST** be lenient about unknown fields (it must not fail on unknown fields).

### 6.2 Callback registration entries

`handlers` is a `list[tuple[Optional[str], Callable]]`:

| Element | Type | Description |
|---|---|---|
| 1st item | `str \| None` | path pattern; `None` matches everything |
| 2nd item | `Callable[[Signal], None]` | the callback function |

There is **no** deregistration API, **no** priority, and **no** "fire once" semantics. Iteration order is registration order, but **MUST NOT** be relied upon — see §10 G2.

### 6.3 No subscription table

It **MUST** be stated explicitly: no subscription table exists in the implementation (the `PathMatcher` container was deleted when the broadcast model landed).

| Dimension | The removed subscription table | This pattern's `handlers` | `sub` authorization filtering |
|---|---|---|---|
| Position | the publisher's remote side | the receiver's local side | the publisher's local side |
| Content | "which peer wants which path" | "which callback in this process cares about which path" | "which peer is allowed to receive which paths" |
| How it changes | needs subscribe / unsubscribe signals | local `on()` call, **zero wire messages** | local Preset configuration |
| Purpose | bandwidth optimisation | consumption dispatch | **security** |
| Status | removed | ✅ present | 🔵 planned |

`sub` authorization and the removed subscription table are **similar in shape but different in nature**: the subscription table answers "who **wants** it", `sub` authorization answers "who **can** see it". Per-peer filtering is therefore added back for **security** needs, **without** mixing in bandwidth optimisation ([security.md §3.7](../security.md#37-tension-with-the-broadcast-model)).

---

## 7. Boundaries

### 7.1 Where wildcards earn their keep

| Scenario | Description |
|---|---|
| **observation / monitoring dashboards** | `on("metric.**")` covers every metric in one go |
| **log aggregation** | `on("log.**")` receives the whole log domain |
| **authorization auditing** | `on("auth.**")` receives every authentication event |
| **coarse-grained awareness** | `on("notify.**")` covers every present and future notification source |
| **task observation** | `on("task.**")` observes the status and artifact broadcasts of `msp/task` |

The common thread: **the receiver does not know in advance which concrete paths will appear**, but knows that they **will** fall under some domain. This is exactly what the domain-first convention serves.

### 7.2 Where wildcards do **not** apply

| Scenario | Reason |
|---|---|
| tool invocation | `payload.tool` **MUST** match exactly (`_tools` dictionary lookup); the set of tool names is **closed** and announced during the handshake |
| Pattern routing | `Signal.pattern` **MUST** match exactly (`protocol.patterns` dictionary lookup) |
| `node_id` location | the connection table and the neighbour table are dictionary lookups; the peer arguments of `node.connections()` / `on_connected` are exact IDs |

"Wildcards are convenient" **SHOULD NOT** be generalised to these three places — all of them need **determinism**: invoking a tool, routing a pattern, and sending a frame to one peer must not carry the ambiguity of "possibly matching several".

### 7.3 Known behavioural boundaries

| Boundary | Description |
|---|---|
| no delivery confirmation | `publish()` returns `None`; you do not know who received it |
| no cross-peer ordering promise | the receive order at different peers is not guaranteed to agree |
| no deduplication | two signals with identical content on the same path **MUST** be treated as two events |
| no history | peers that connect late do not receive signals published before they connected; **MUST NOT** expect backfill |
| no local loopback | see §5.5 |
| no filter push-down | see §8 |

---

## 8. Security considerations

### 8.1 Broadcast = send to all, no filtering by content

**MUST** recognise the default shape of this pattern: **`publish()` sends the signal to every connected peer, without distinguishing recipients and without looking at the content.**

The normative consequences:

1. before publishing **sensitive data**, the publisher **MUST** confirm the trust assumptions of the receiving side: under local self-organising networking all peers share the same OS user (the premise of §8.1, in which `sub` authorization is, by design, **bypassed for the whole table**), whereas a cross-machine deployment **MUST** configure `sub` authorization — when neither holds, the protocol has no dependable interception to offer;
2. when "show it only to certain peers" is needed, you **MUST NOT** rely on path naming (giving a path an obscure name **does not constitute** access control);
3. the correct narrowing mechanism is **sender-side fan-out filtering** (`sub` authorization), see §8.2.

### 8.2 `sub` authorization is sender-side fan-out filtering (✅ implemented)

Following the design of [security.md §3.6](../security.md#36-enforcement-points-only-two), there is **exactly one** enforcement point for outbound filtering: the fan-out loop of `publish()` — each peer's `sub` authorization is consulted and unauthorised peers are skipped.

| Item | Rule | Status |
|---|---|---|
| Location | inside the fan-out loop of `publish()`, one decision per peer | 🔵 planned (design finalised) |
| Matching | reuses `pattern_matches`, comparing the path-pattern list in `sub` entry by entry | 🔵 |
| Default | `sub: False` (network peers **do not** receive my broadcasts by default) | 🔵 |
| Local exception | loopback / UDS peers under the same user skip the whole authorization table | 🔵 |
| Difference from the subscription table | "who **can** see it" (security), not "who **wants** it" (bandwidth) | — |

**MUST**:

1. `sub` filtering **MUST** be enforced on the **sender side** — you **MUST NOT** rely on the receiver's self-restraint (the receiver may be an attacker);
2. filtering **MUST NOT** alter the message bytes (no trimming of `payload`, no change to `path`); it only decides "send or do not send";
3. while authorization is unimplemented, the documentation and deployment notes **MUST** state explicitly that "broadcasts are visible to all connected peers", and **MUST NOT** silently assume safety.

### 8.3 The receiving side is untrusted

| Risk | Mitigation |
|---|---|
| a malicious peer floods broadcasts | receivers **SHOULD** rate-limit locally; the protocol layer currently has **no** inbound rate limit (§10 G5) |
| callback exceptions used as an amplification vector | exceptions are caught and logged (§2.3 item 3) — but **the logs themselves** can be drowned by a flood, so implementations **SHOULD** sample their logs |
| side effects executed inside callbacks | callbacks run on the read-loop thread; implementations **MUST** hand heavy work to a worker thread (§2.3 item 5) |
| `payload` carrying malicious content | receivers **MUST** parse `payload` as untrusted input; the protocol layer does **not** validate the structure of `payload` |

### 8.4 Path naming is not authorization

You **MUST NOT** use path naming to carry authorization functionality:

- paths are **public** (emitted with the broadcast and also exchanged with `Manifest.signals`);
- path matching is a **receiver-local** behaviour, and an attacker can register any pattern;
- "only those who know the path can receive it" therefore **does not hold** — under the broadcast model, knowing the path does not affect **whether** you receive, only **whether** you process it. The only thing that truly decides "whether you receive" is the sender-side `sub` filter.

Auxiliary measures (**MAY** be adopted, but **MUST NOT** be treated as the sole line of defence):

- content-level encryption: encrypt `payload` with the peer's public key, so that a peer without the key cannot read it even if it receives it;
- publish into separate domains: send sensitive data over an **isolated transport/network** (a separate UDS listener, a separate TLS channel), so that untrusted peers cannot reach it at the transport layer at all.

### 8.5 The reality of local self-organising networking

Under the default deployment shape (a localhost self-organising network, the same OS user), the conclusion of [security.md](../security.md#23-local-self-organising-network-why-there-is-no-authentication) applies: all nodes have equal permission sets, and broadcast visibility **does not constitute** additional risk — a process that can connect already reads the same things.

The contrary condition **MUST** be stated explicitly: once the listener is extended to `0.0.0.0` or across machines, that premise **lapses immediately**, and TLS + node authentication + `sub` authorization **MUST** then all be in place (see [security.md §2.4](../security.md#24-cross-machine-security-follows-the-transport)).

---

## 9. Summary of normative provisions (MUST/SHOULD list)

| # | Provision | Level |
|---|---|---|
| P1 | the `type` constructed by `publish` **MUST** be `"signal"`, and `target` / `pattern` / `reqid` **MUST** be `null` | **MUST** |
| P2 | the path **MUST** go in `Signal.path` and **MUST NOT** go into `payload` | **MUST NOT** |
| P3 | fan-out **MUST** iterate over every connected peer; a send failure **MUST NOT** interrupt the loop | **MUST** |
| P4 | `publish()` **MUST NOT** return delivery confirmation; a broadcast is best-effort | **MUST NOT** |
| P5 | `on(path=None)` **MUST** match all paths | **MUST** |
| P6 | every matching callback **MUST** be called; callback exceptions **MUST** be caught and **MUST NOT** affect other callbacks | **MUST** |
| P7 | callbacks **MUST** be invoked on the read-loop thread; they **MUST NOT** block there for long | **MUST NOT** |
| P8 | callback registration **MUST** be re-entrant (registration during runtime is possible); **MUST NOT** deduplicate | **MUST** |
| P9 | paths **MUST** follow domain-first `<domain>.<entity>.<action>` | **MUST** |
| P10 | a path **MUST NOT** contain separators other than the dot, and **MUST NOT** mix in the slash of Pattern IDs | **MUST NOT** |
| P11 | wildcards **MUST** appear only at the end of a pattern; a `*` in the middle is a literal and **MUST** return `False` | **MUST** |
| P12 | the matching algorithm **MUST** execute in the four-branch order of §4.1 | **MUST** |
| P13 | `.**` **MUST** match the prefix itself; `.*` **MUST** match exactly one segment and **MUST NOT** match the prefix itself | **MUST** |
| P14 | bare `*` / bare `**` / patterns with `*` in the middle **MUST** return `False` per the algorithm and **MUST NOT** be treated as "match everything" | **MUST NOT** |
| P15 | matching **MUST** be case-sensitive | **MUST** |
| P16 | tool names / Pattern IDs / `node_id` **MUST NOT** use wildcard matching | **MUST NOT** |
| P17 | values produced by a signal source that are not `dict` **MUST** be skipped | **MUST** |
| P18 | signal-source exceptions **MUST** be isolated and **MUST NOT** affect other signal sources | **MUST** |
| P19 | publishing **MUST NOT** continue after the node has stopped | **MUST NOT** |
| P20 | breaking path changes **MUST** use a new parallel path (`x.changed` / `x.changed.v2`) and **MUST NOT** change semantics in place | **MUST NOT** |
| P21 | a broadcast **MUST NOT** loop back to the publisher itself | **MUST NOT** |
| P22 | `sub` authorization **MUST** run in the sender-side fan-out loop; while it is unimplemented, the send-to-all nature of broadcasts **MUST** be declared in the documentation | **MUST** |
| P23 | receivers **MUST** treat `payload` as untrusted input; the protocol layer does **not** validate its structure | **MUST** |

---

## 10. Known gaps

| # | Gap | Impact | Basis |
|---|---|---|---|
| G1 | **no deregistration API**. `handlers` only grows, never shrinks; there is no `off()` / `unsubscribe()` | the lifecycle of dynamic subscriptions can only be simulated by "setting a flag inside the callback itself"; long-running processes that register frequently keep growing | `MSPProtocol.on` has only a registration path; `handlers` has no removal point |
| G2 | **order dependence without priority**. callbacks are iterated in registration order, and there is no "stop propagation" mechanism | implementations **MUST NOT** rely on order; one callback cannot stop later callbacks from running | `for path_filter, func in handlers` in `_on_signal` |
| G3 | **`pattern_matches` validates no input**. empty patterns, bare wildcards, and mid-string wildcards all silently return `False` | a mistyped subscription gives no feedback at all — it shows up as "receiving nothing" | the fallback `return False` on line 36 of `matcher.py` |
| G4 | **no source filtering**. `on()` has only the path dimension, not the `sig.source` dimension | there is no way to "listen only to node_a's notify.**"; node wildcards are the next step recorded in [DESIGN.md](/design) | the elements of `handlers` are `(path, callback)` pairs |
| G5 | **no inbound rate limiting** | a malicious peer can flood broadcasts to exhaust the receiver's CPU / logs | `_on_signal` processes each message immediately, with no token bucket |
| G6 | ~~**`sub` authorization unimplemented**~~ ✅ implemented | unauthorised peers no longer receive broadcasts (per-peer filtering on the sender side) | the fan-out loop of `publish()` calls `grant_sub()` per peer (`src/msp/protocol/protocol.py`); local peers bypass the whole table by design ([security.md §3.5](../security.md#35-defaults-and-scope)). Residual: `pub` / `sub` have no "allow everything for one pattern" form ([security.md §9](../security.md#9-known-gaps) item 5) |
| G7 | **publishing has no confirmation and no retransmission** | signals emitted while a peer is offline are lost for good; late joiners get no history | `publish()` returns `None` |
| G8 | **no local loopback** | differs from MQTT semantics, which is easy to trip over in cross-implementation interop | `publish()` iterates only over `connections` |
| G9 | **no schema validation for `payload`** | `declare_signal(schema=...)` is used only for announcing, the same gap as the `inputSchema` of `node.tool` | the `declare_signal` docstring states explicitly that "no validation is done at publish time" |
| G10 | **`on()` at the node layer does not support the `callback=` keyword** | `node.on(path="x", callback=cb)` fails; you can only use the decorator or call `node.protocol.on(...)` directly | `MSPNode.on(path=None)` takes a single parameter |
| G11 | **the literal `pattern == path` branch of `pattern_matches`** | if a path itself contains `*` (violating the naming specification), a pattern containing wildcards may match literally, producing an unexpected match | lines 22–23 of `matcher.py` |

---

## 11. Reference implementation map

| Provision | Source files and symbols |
|---|---|
| §2.1 message shape | `src/msp/protocol/protocol.py` → `MSPProtocol.publish` |
| §2.2 fan-out and failure handling | `src/msp/protocol/protocol.py` → `MSPProtocol.publish`, `_handle_disconnect` |
| §2.3 receiver-side filtering | `src/msp/protocol/protocol.py` → `_dispatch`, `_dispatch_core`, `_on_signal` |
| §2.4 registration API | `src/msp/protocol/protocol.py` → `MSPProtocol.on`; `src/msp/core/node.py` → `MSPNode.on` |
| §2.5 automatic repeated publishing | `src/msp/core/node.py` → `MSPNode.signal_source`, `signal`, `_run_signal_source`, `start` |
| §3.2 domain-first convention | `docs/DESIGN.md` "Signal path layering: domain first"; `src/msp/core/node.py` → `declare_signal` (the path is only declared, not validated) |
| §3.5 path declaration | `src/msp/core/manifest.py` → `Manifest.add_signal`, `SignalDescriptor` |
| §4.1–4.3 matching algorithm | `src/msp/protocol/matcher.py` → `pattern_matches` |
| §4.4 the two pitfalls | the module docstring of `src/msp/protocol/matcher.py` and lines 22–36 |
| §4.5 scope of matching | `src/msp/protocol/protocol.py` → `_tools`, `patterns`, `connections` (all exact dictionary lookups) |
| §5.3 the bus without a bus | `docs/DESIGN.md` "Use case: a virtual bus" |
| §5.4 versioned paths | relies on the prefix branches of `pattern_matches` (lines 25–34 of `matcher.py`) |
| §5.5 no local loopback | `src/msp/protocol/protocol.py` → `MSPProtocol.publish` (iterates only over `connections`) |
| §6.2 structure of a registration entry | the type annotation of `src/msp/protocol/protocol.py` → `MSPProtocol.handlers` |
| §6.3 no subscription table | the docstring of `src/msp/protocol/matcher.py`: "the original `PathMatcher` container was deleted along with it" |
| §8.2 `sub` authorization | `src/msp/protocol/protocol.py` → `MSPProtocol.grant_sub` (the call site in the fan-out loop) and `MSPProtocol.publish`; the authorization table is in `src/msp/core/grants.py` |
| §10 G1 no deregistration | `src/msp/protocol/protocol.py` → `MSPProtocol.on` (only a registration path) |
| §10 G4 no source filtering | `docs/DESIGN.md` "Future extension: node wildcards (two-dimensional matching)" |
