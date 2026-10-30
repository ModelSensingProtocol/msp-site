# Performance and costs

MSP is small, but "small protocol" is not "free". This page collects the costs that actually matter
when you put a node in a hot path, and the numbers that are real rather than aspirational.

## Per-message cost

| Item | Cost |
|---|---|
| framing | 4 bytes + UTF-8 JSON; a typical signal is 150–400 bytes on the wire |
| encode/decode | JSON on both ends; no schema binding, no compression |
| fan-out | one message **per connected peer**; a broadcast to 8 peers is 8 writes |
| thread hop | signals are dispatched to a per-subscription thread; a slow handler delays only its own path |

The practical implication: MSP is comfortable with tens of messages per second across a handful of
peers, and not designed for telemetry at kilohertz rates. If you need that, batch into one signal and
let the subscriber unpack.

## Per-node cost

| Item | Cost |
|---|---|
| idle | one renew write every 10 s, one heartbeat round every 15 s |
| discovery | one directory scan every 30 s per node (the poll fallback, on top of file events) |
| connections | one socket + one reader thread per peer |
| tasks | one thread per in-flight task, unless you use your own pool |

A dozen nodes on one machine is fine. A hundred nodes each polling the same directory every 30 s is
30 scans/second of the same directory — measurable, and the reason a shared directory across many
machines does not scale.

## The costs that are not CPU

- **Latency you cannot avoid.** A crashed node takes up to **60 s** to disappear. Any UI that must be
  accurate sooner needs its own liveness check (a call, not a lease).
- **Configuration instead of discovery.** Sharing a directory across machines degrades to the 30 s
  poll; manual registration is faster and more predictable.
- **Debugging.** No distributed tracing. You get counters (`metrics_line()`) and two inspectable files
  (the directory, and the manifest). Budget for it.

## Choosing between the three shapes

The same feature can be built three ways; they cost differently.

| Shape | Latency to first byte | Cost per update | Survives a slow consumer |
|---|---|---|---|
| tool call (pull) | one round trip | one round trip | yes (consumer drives) |
| signal (push) | ~0 | one message per peer | no (fire and forget) |
| task + signal | one round trip, then pushed | one message per peer | yes (state is in `get_task`) |

Rule of thumb: **push transitions, pull state.** That sentence is also a performance rule — states
are large and change often, transitions are small and rare.

## Measuring, not guessing

```python
print(node.metrics_line())
```

`signalsOut`, `dispatched`, `task threads peak` are the three that tell you whether you are near a
limit. A peak thread count that keeps climbing is a leak; a `resultsDropped` that keeps climbing means
your tools are slower than your callers' timeouts.

## What has not been benchmarked

Being explicit, because the numbers above are from reading the code and running the examples, not from
a load test: throughput per peer, behaviour beyond ~50 peers on one machine, and WebSocket transport
under sustained load. If you need those numbers for a decision, measure them — and tell us, so this
page can stop being honest about being incomplete.

## See also

- [Signals](signals.md) — fan-out cost and throttling
- [Long tasks](tasks.md) — the shape that keeps a slow job off the call path
- [Debugging](debugging.md) — the counters referenced above
