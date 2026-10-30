# Signals: pushing, and what it costs

A signal is the cheapest thing in MSP and the easiest one to misuse. Two facts decide everything:

1. **Nothing is retained.** A signal sent while nobody was subscribed is gone.
2. **Nothing is acknowledged.** The publisher does not learn whether anyone received it.

Everything below is a consequence of those two sentences.

## When a signal is the right shape

| Situation | Signal? |
|---|---|
| "the download finished" | yes — the interesting moment is the transition |
| "progress is now 40%" | yes, but throttle it; you do not need 1000/s |
| "the document is currently open" | **no** — that is state; expose a tool that reads it |
| "here is the requested data" | **no** — that is a reply; use a tool call |

The rule of thumb: **a signal is a notification that something changed, never a container for the
current state.** Subscribers should treat it as "go ask again", not as the data itself.

## The pattern that survives a dropped signal

```python
@node.on("download.completed")
def on_done(sig):
    task_id = sig.payload.get("taskId")
    if not task_id:
        return
    # never trust the payload to be the full story — ask the owner
    result = node.call("downloader", "get_task", {"taskId": task_id})
    if result.is_error:
        log.warning("task vanished: %s", result.error)
        return
    handle(result.structured)
```

If you skip the `get_task`, you have built a system where a dropped signal means a lost job, and the
drop is not hypothetical: reconnect, process restart, and subscription-before-connection all lose
signals.

## Fan-out and cost

`publish()` walks every connected peer and sends the signal to those whose subscription matches. The
cost is per-peer, so:

- Broadcasting 100 Hz to 8 peers is 800 messages/s — measure before you do it.
- `metrics_line()` counts `signalsOut` and `broadcastSkipped`; if `broadcastSkipped` climbs, peers are
  not subscribing to that path (which is normal, not an error).
- A signal that no one subscribed to still costs one message per connected peer.

## Path patterns

Subscriptions match on a path with `*` (one segment) and `**` (many):

```python
@node.on("download.*")     # download.completed, download.progress
@node.on("device.**")      # device.thermometer.reading, device.a.b.c
node.on(None)              # everything
```

Paths are also what **authorisation** keys on: a cross-machine peer is denied by default unless you
grant it a path pattern. Local (loopback/UDS) peers are allow-listed automatically.

## Ordering, threads, and the one guarantee

- Handlers run on a dedicated thread per subscription, in arrival order. A slow handler does not stall
  the heartbeat, but it does delay later signals on that same path.
- There is no cross-path ordering guarantee. `a.x` and `a.y` may interleave arbitrarily.
- The only guarantee is: if a signal arrived and a handler is registered, the handler runs.

## See also

- [Provide tools and signals](provide-tools.md) — declaring and publishing
- [Discover, call, subscribe](consume.md) — subscribing from the consumer side
- [Topology and what you cannot see](topology.md) — why "who is connected to whom" needs evidence
