# Node roles: consumer, provider, or both

MSP has no client/server split — it has **nodes**, and a node's role is a property of what it does,
not of a type you declare. The same process can call out, answer calls, publish and subscribe at
the same time.

That said, three shapes cover almost everything, and picking one early saves you from wiring up
capabilities you will not use.

| Shape | Preset | Can be called | Can call out | Typical use |
|---|---|---|---|---|
| **Provider** | `Preset.LOCAL_TOOL` | yes | no (it does not dial) | an app that exposes what it already does — a widget, a player, a device bridge |
| **Consumer** | `Preset.LOCAL_AI` | no | yes | an agent, a script, an assistant that drives other apps |
| **Peer** | `Preset.FULL_PEER` | yes | yes | a node that both serves and uses: a downloader that hands files to an editor |

Two more exist for the edges of the design:

- `Preset.OBSERVER` — scans the discovery directory but never announces itself. Useful for looking at
  a machine without leaving a trace. It cannot be called, because nothing knows it exists.
- `Preset.MANUAL_PEER` — no automatic discovery; you hand it the peers. For tests and for networks
  where the directory is not shared.

## Provider is not "server"

A provider still has the same wire format, the same lease, the same manifest. The difference is
**connect policy**: `LOCAL_TOOL` is `lazy`, meaning it accepts incoming connections but does not dial
out when it discovers someone. That is why two providers never connect to each other — there is
nothing for them to call.

That is a feature. A media widget should not be opening sockets to a weather service just because
they happen to share a directory.

## Consumer is not "client"

A consumer is just a node whose use case is calling. It still answers on its own socket, so a provider
that needs to push a signal back (progress, a finished job) can do so — and often should, instead of
making the consumer poll.

If you find yourself adding `@node.tool` to a node that "only consumes", ask whether the callback
should be a **signal** rather than a tool. Pushing is usually the better shape for progress.

## Choosing by question

> Does the app have state a human is looking at right now?

- **Yes** — it is a provider (or a peer). Give it tools that read that state.
- **No, it drives other apps** — it is a consumer. Give it no tools, and test it against a provider.
- **Both** — it is a peer. Start from `FULL_PEER` and remove what you do not use.

## See also

- [Core concepts](architecture.md) — the five pieces and how they depend on each other
- [Provide tools and signals](provide-tools.md) — what a provider actually registers
- [Discover, call, subscribe](consume.md) — what a consumer actually does
- [`core/preset.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/preset.py) — the
  presets themselves, if you want to read the flags rather than trust this page
