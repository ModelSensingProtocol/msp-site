---
sidebar_label: Node and preset
---

# Node and preset

A node is a participant with an id. A **preset** is the local policy that decides how it participates.
The preset is a dataclass of frozensets, so it is inspectable, composable, and — importantly — never
sent to anyone.

## What a preset is made of

```python
Preset(
    name="LOCAL_TOOL",
    discovery=frozenset({"directory"}),   # how we find others
    presence=frozenset({"directory"}),    # how others find us
    transports=frozenset({"tcp"}),        # what we can speak over
    patterns=frozenset({...}),            # which patterns we can run
    primary_transport="tcp",
    capabilities=frozenset({"pub", "sub", "req", "rep"}),
    connect_policy="eager",               # or "lazy"
)
```

Six knobs, and the built-in presets are just common combinations of them:

| Preset | discovery | presence | connect | Reads as |
|---|---|---|---|---|
| `LOCAL_TOOL` | directory | directory | **lazy** | a provider: listed, accepts, never dials |
| `LOCAL_AI` | directory | directory | eager | a consumer: finds and dials providers |
| `FULL_PEER` | directory | directory | eager | serves and uses |
| `OBSERVER` | directory | — | lazy | looks, never announces |
| `MANUAL_PEER` | — | — | eager | only the peers you hand it |

## A preset is not in the manifest

This is the misconception worth killing early. Two nodes exchange `manifest` at handshake: tools,
signals, patterns, transports, capabilities. They do **not** exchange presets.

Consequences:

- Peer A cannot tell whether peer B is eager or lazy, or whether B reads the directory at all.
- "Why doesn't B connect to me?" cannot be answered from B's manifest. It is a local policy, not a
  published fact.
- Two nodes with identical manifests can behave completely differently — one dials everything, the
  other waits.

That is deliberate: policy stays local, and the wire stays about capability.

## Building your own

The six knobs can be recombined. A node that is listed but never dials anyone:

```python
from msp.core.preset import Preset

ANNOUNCE_ONLY = Preset(
    name="ANNOUNCE_ONLY",
    discovery=frozenset(),                 # never scan
    presence=frozenset({"directory"}),     # still write our declaration
    transports=frozenset({"tcp"}),
    patterns=frozenset({"msp/request-reply"}),
    primary_transport="tcp",
    capabilities=frozenset({"rep"}),
    connect_policy="lazy",
)

node = MSPNode("log-sink", preset=ANNOUNCE_ONLY)
```

Anyone who discovers it can call it; it will never call them. Flip the two frozensets and you get the
mirror image (an observer).

## `connect_policy` decides who dials

With `lazy`, discovery and connection are visibly separate — measured, not assumed:

```
after settle():   peer.is_discovered == True ,  peer.is_connected == False
after one call:   peer.is_connected == True
```

That is the behaviour behind "lazy means connect on demand", and the reason a first call against a lazy
peer can take noticeably longer than the second: the handshake happens inside that call.

`eager` dials on discovery. Two eager nodes in the same directory connect; two lazy nodes never do, even
though each appears in the other's `neighbors()`.

## Ids

`node_id` must match `^[a-z0-9_-]+$`. It is also the tie-breaker for deduplication: when two nodes
discover each other simultaneously they both dial, and the pair resolves which connection to keep by
comparing ids lexicographically — the **smaller** id owns the outbound connection.

This is a rule, not a security feature, but it has a visible consequence: naming a node matters when you
name several. `alpha-pc`, `beta-nas` behave predictably; `Bridge` and `bridge` do not (and the uppercase
one is invalid anyway).

## See also

- [Signal and path](signal-and-path.md) — what a node actually sends
- [Peer view](peer-view.md) — what a node actually sees
- [`docs/spec/discovery.md`](pathname:///msp-site/docs/spec/discovery/) — the normative rules behind
  discovery and presence
