# Glossary

Ordered from the lowest to the highest layer in the protocol.

| Term | English | One-liner | Where |
|---|---|---|---|
| **Signal** | signal | A JSON message carrying a path; the 8 top-level fields are fixed, unknown fields go into `extras` | [`core/signal.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/signal.py) |
| **Framing** | framing | 4-byte big-endian length prefix + UTF-8 JSON | [`protocol/framing.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/framing.py) |
| **Manifest** | manifest | A node announces its own tools, signals, capabilities and patterns | [`core/manifest.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) |
| **Handshake** | handshake | `HELLO` (with a manifest) → `ACK` (with the other side's manifest) | [`protocol/protocol.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) |
| **Deduplication arbitration** | dedup / canonical direction | When two nodes dial each other at the same time, keep one direction by node_id lexicographic order | Same as above |
| **Tool** | tool | A request/reply capability with a name, a description and an input schema | [`core/node.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) |
| **Call** | call | Call a peer's tool and get back a `ToolResult`; a failure raises no exception | Same as above |
| **Broadcast** | publish / broadcast | Send one signal to every subscribed peer; fire and forget, nothing is retained | Same as above |
| **Subscription** | subscription | Register a local callback with a path pattern (`*` / `**`) | [`protocol/matcher.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/matcher.py) |
| **Discovery** | discovery | Scan the shared directory and turn new nodes into dialable peers | [`discovery/`](https://github.com/hxh230802/MSP/tree/master/src/msp/discovery/) |
| **Presence** | presence | Write your own declaration file into the shared directory and renew the lease | [`presence/`](https://github.com/hxh230802/MSP/tree/master/src/msp/presence/) |
| **Lease** | lease | Renewed every 10 seconds; it lapses after 30 seconds without renewal; the discovery side's upper bound is 60 seconds | Same as above |
| **Preset** | preset | A package of capabilities: discovery, presence, transport, pattern, connect policy | [`core/preset.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/preset.py) |
| **Connect policy** | connect policy | `eager` (connect on discovery) / `lazy` (connect on use) | Same as above |
| **Settle** | settle | Wait for the connections triggered by this startup to land; it only waits, never initiates | [`core/node.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) |
| **Pattern** | pattern | A pluggable interaction shape: `request-reply` / `publish-subscribe` / `multi-round` / `task` | [`patterns/`](https://github.com/hxh230802/MSP/tree/master/src/msp/patterns/) |
| **Task** | task | One kind of multi-round: it has a queue, it has state, and it can be queried later | [`patterns/task.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/task.py) |
| **Grant** | grant | Decides whether one may send/receive/call, by `(peer, path pattern)`; other machines are untrusted by default | [`protocol/protocol.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) |
| **Local peer** | local peer | A peer connected over loopback TCP or UDS, treated as local by default | Same as above |
| **Metrics** | metrics | Counters for each dimension: connections / signals / tools / task threads | [`core/node.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) |
| **Adapter** | adapter | The layer that wraps an MCP server into an MSP node | [`mcp/`](https://github.com/hxh230802/MSP/tree/master/src/msp/mcp/) |
