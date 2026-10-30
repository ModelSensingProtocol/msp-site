---
sidebar_label: Signal and path
---

# One frame, every job

Everything a node does — greeting a peer, calling a tool, publishing an event, answering a heartbeat —
is the **same eight-field structure**. Only `type` changes. There is no separate envelope for tools, no
separate shape for notifications, no separate protocol for discovery.

```python
{"type": "signal", "source": "weather", "pattern": None, "target": None,
 "path": "device.thermometer.reading", "reqid": None,
 "payload": {"temp_c": 22}, "timestamp": 1793000000.0}
```

| Field | Meaning | When it is `null` |
|---|---|---|
| `type` | what this frame is for | never |
| `source` | node id of the sender | never |
| `pattern` | communication pattern carried (`msp/request-reply`, …) | for plain calls |
| `target` | node id of the intended receiver | broadcast — anyone subscribed |
| `path` | logical address of the content | control frames (`hello`, `ping`) |
| `reqid` | correlation id for a request/response pair | anything not part of a call |
| `payload` | the body | rarely |
| `timestamp` | when the sender emitted it | never |

All eight keys are **always present**. A missing value is `null`, never an omitted key — a rule that
makes naive JSON readers work and keeps framing honest.

## The eight types that exist

| `type` | Carries | Sent by |
|---|---|---|
| `hello` | the sender's manifest | either side, at connect |
| `ack` | the receiver's manifest | the other side |
| `signal` | a published event | publisher |
| `tool_call` | tool name + arguments | caller |
| `tool_result` | content blocks + structured value, or an error string | provider |
| `manifest_update` | the new manifest | a node whose capabilities changed |
| `ping` / `pong` | nothing | keepalive, every 15 s |
| `error` | a diagnostic string | either side |

That is the whole vocabulary. A tool call is not a special RPC — it is a signal with `reqid` set and
`type: "tool_call"`. A broadcast is a signal with `target: null`.

## Path: the logical address

`path` is dotted, like `device.thermometer.reading`, and it does three jobs at once:

1. **Subscription key** — a subscriber declares the patterns it cares about.
2. **Authorisation key** — cross-machine peers are granted (or denied) per path pattern.
3. **Naming contract** — two applications that share nothing but a name can interoperate.

That third one is the whole trick behind app-to-app linking: there is no registry of event types, only
a textual path both sides agree on.

## Wildcards: `*` is one segment, `**` is the rest

```python
node.on("device.*")     # device.thermometer — exactly one more segment
node.on("device.**")    # device, device.a, device.a.b.c
node.on(None)           # everything
```

Verified behaviour worth internalising:

- `device.*` does **not** match `device.thermometer.reading` (three segments, not two).
- `device.**` matches that path, and also matches bare `device`.
- A wildcard is only meaningful **at the end** of a pattern; a `*` in the middle is treated as a
  literal segment (`a.*.c` matches the literal `a.*.c`, not `a.b.c`).

If you get this wrong the symptom is silent: no error, no delivery, just a handler that never fires.

## Reading a frame by hand

When something is not arriving, dump the frame rather than guessing:

```python
from msp.core.signal import Signal, SignalType

sig = Signal(type=SignalType.SIGNAL, source="weather",
             path="device.thermometer.reading", payload={"temp_c": 22})
print(sig.to_dict())      # exactly the eight fields, extras merged back in
```

Unknown top-level keys are preserved in `extras` and echoed back on the wire — that is how a peer can
ignore a field it does not understand without breaking a sender that added it.

## See also

- [Node and preset](node-and-preset.md) — who sends these frames, and with what policy
- [Peer view](peer-view.md) — the receiving side of a manifest
- [`spec/base-protocol.md`](pathname:///msp-site/docs/spec/base-protocol/) — the normative frame and
  framing rules
