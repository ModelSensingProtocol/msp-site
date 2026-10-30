# Topology, and what you cannot see

A diagram of an MSP network is always partly a guess, and it is worth knowing which parts. This page
explains why — it is the reasoning behind the edge types the [landing page](https://modelsensingprotocol.github.io/msp-site/)
draws, and behind the DeepSeek Harness plugin's `/msp/graph` endpoint.

## The gap

`HELLO` carries a capability manifest: tools, signals, patterns, transports. It does **not** carry a
peer list, and there is no "who are your neighbours" request in the protocol.

So a node knows exactly two things:

1. **Which nodes exist** — from the discovery directory (all of them, whether connected or not).
2. **Which nodes it is connected to** — its own edges, and only its own.

It cannot see the edge between two other nodes. Not "does not bother to" — cannot.

## Three kinds of evidence

Any view above a single node has to combine these, and must label which is which:

| Edge | Evidence | Strength |
|---|---|---|
| **observed** | it is in my own connection table | fact |
| **reported** | the peer told me its own peer list (e.g. via a `ping` tool that returns `peers`) | second-hand but checkable |
| **inferred** | same discovery directory and both connected to me, so presumably connected to each other | a guess |

Inference is wrong in a specific, predictable way: **lazy nodes never dial each other.** Three nodes
with `connect_policy=lazy` in one directory are all discoverable and none of them are connected to each
other; a naive "same directory ⇒ full mesh" rule draws three false edges.

Reporting fixes it, and it also **removes** edges: if a peer reports its peer list and the other node
is not in it, they are not connected — even if inference would have drawn a line. That is why an
honest topology view needs a probe, and why it must not colour inferred edges as if they were facts.

## Probing without a protocol feature

The plugin's probe is opportunistic: it calls a read-only-looking tool (`ping`, `status`, `info`,
`health`, `peers`, `topology`) that takes no required arguments, and looks for a peer list in the
reply. Consequences worth stating:

- A node with no such tool can only be inferred — the line stays dashed.
- A node that lies is believed. There is no verification beyond "two peers agreeing".
- It costs a call per peer, so it is throttled (`topologyProbeMs`, default 30 s in the plugin).

A protocol-level answer would be a link-state signal (`link.up` / `link.down`), which is what a future
revision should add: it makes edges observed instead of inferred, and gives you "someone went offline"
as an event rather than a diff of two polls.

## Reading a graph

- Solid edge to a node you can call — fine.
- Dashed edge between two others — **ask one of them**, do not build on it.
- Node present but not connected — the lease is alive, the socket is not. Common after a crash within
  the 60 s window, or when the peer is lazy.

## See also

- [Leases and discovery](leases.md) — why the node list and the connection list differ
- [Debugging](debugging.md) — `connections()` vs `neighbors()` in practice
- [The example network](examples/index.md) — a small mesh you can run and watch
