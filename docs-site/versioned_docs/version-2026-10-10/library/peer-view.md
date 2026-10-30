---
sidebar_label: Peer view
---

# Peer view

`node.peer("weather")` returns a `Peer` object: your local view of that node, built from its manifest.
It exists so you do not have to keep a copy of somebody else's JSON and remember which key holds what.

```python
peer = node.peer("weather")

peer.is_discovered   # True  — its lease is in the directory
peer.is_connected    # True  — we have a live connection
peer.endpoint        # {transport_type, address, node_id}
peer.manifest        # the raw dict, if you need something exotic
```

The distinction in the first two lines is the one people trip over: **discovered is not connected.** A
peer can be listed for up to 60 s after it died; only `is_connected` means a call will work.

## Asking what it can do

```python
peer.tools()                       # ['get_weather']
peer.signals()                     # ['device.thermometer.reading']
peer.patterns()                    # ['msp/publish-subscribe', 'msp/request-reply']
peer.supports("msp/task")          # capability check before you rely on it
peer.has_tool("get_weather")       # exact name, not a substring
peer.has_signal("device.thermometer.reading")
```

`supports()` is the one to use when a feature is optional — multi-round and task patterns are exactly
the kind of thing a peer may not have. Checking first turns "it hung" into "it cannot, so I will fall
back".

## Calling with the tool view

`peer.t` turns the peer's advertised `inputSchema` into something you can call as if it were local:

```python
peer.t.get_weather(location="Hangzhou")          # attribute style
peer.t["get_weather"](location="Hangzhou")       # dynamic name
peer.t.signature("get_weather")                  # "(location: str, *, days: int = <optional>)"
peer.t.tool("get_weather")(location="Hangzhou")  # escape hatch if the name collides
```

Three details that matter:

- **Attribute access is pure.** `peer.t.get_weather` does not dial anything and does not read the
  manifest. The connection and the call happen at the moment you *invoke* it.
- **It returns a `ToolResult`, not a dict.** Use `.unwrap()` for the structured value, `.text()` for the
  text blocks, or check `.is_error` first.
- **It is not validation.** The schema is used for the signature hint; the peer validates nothing
  either. Wrong argument names produce a provider-side error, not a local one.

```python
result = peer.t.get_weather(location="Hangzhou")
print(result.unwrap())        # {'location': 'Hangzhou', 'days': 3, 'temp_c': 21}
```

The escape hatch matters more than it looks: `t` is reserved for the tool view, so a peer that exposes a
tool literally named `t` is reachable as `peer.t["t"]` — and `peer.t.tool("t")` always works.

## How fresh is this view

The manifest arrives at handshake and is replaced when the peer pushes `manifest_update` (a tool added
or removed at runtime). So:

- Right after connect: accurate.
- After the peer adds a tool: accurate again within a round trip — the node pushes the new manifest.
- While disconnected: **stale, but retained.** The tools are kept deliberately so tool names do not
  flicker under a model; a call returns "not connected" instead of vanishing.

That last decision is a trade: a stale list is friendlier than a list that empties every time a socket
drops, but it means `peer.tools()` is a claim about the last known manifest, not a probe.

## Enumerating peers

```python
node.neighbors()          # ids from the directory (may be dead)
node.connections()        # ids we are connected to right now
node.peers()              # all known peers, as Peer objects
node.connected_peers()    # only the live ones
```

Rule for tests and for anything load-bearing: **iterate `connected_peers()`**, not `neighbors()`.

## See also

- [Node and preset](node-and-preset.md) — why a peer's policy is invisible in this view
- [Discover, call, subscribe](pathname:///msp-site/docs/consume/) — the `node.call()` form and its error semantics
- [`docs/spec/capabilities.md`](pathname:///msp-site/docs/spec/capabilities/) — what a manifest contains
