# FAQ and Troubleshooting

## Common questions

### How does MSP relate to MCP?

Not as a replacement — the shapes differ: MCP is a hub-and-spoke tool protocol, MSP is a mesh
peer-to-peer protocol — nodes hold leases (a sense of presence), can broadcast on their own
initiative (push), and can serve each other directly. For why that decides which one local
software should use, see
[`docs/POSITIONING.zh-CN.md`](https://github.com/hxh230802/MSP/blob/master/docs/POSITIONING.zh-CN.md).

The `mcp/` directory in the repository is the **interoperability adapter layer**: it wraps MCP
servers as MSP nodes, rather than making the runtime speak two protocols at once.

### Why not just use MCP over stdio?

With stdio the lifetime is tied to the session: the client **spawns** the process, and the
process dies when the session ends; what gets spawned is also a **second instance**, which
cannot see the document open on your screen. Desktop software wants "while the software is
alive, its capabilities are there", and stdio cannot structurally deliver that.

### Can two machines use it?

Yes — TCP has always worked across machines. But you have to sort out the rest yourself:
addresses and discovery (the discovery directory is local, so across machines you either share
a directory or use `add_manual_source` / name the peer manually), TLS (the WebSocket transport
currently has **no** `wss://`, so you need a reverse proxy to terminate TLS), and authorization
(across machines the default is not "reachable means trusted").

### Some cases are skipped on Windows

Windows has no `AF_UNIX`, so the four UDS cases in `tests/test_uds.py` are skipped
automatically — they are not failures.

### What to watch out for when running several nodes on one machine?

- **Node ids** **MUST** be distinct: the id is the key of the connection table, so two processes
  with the same id look like one peer to the other side, and the later connection kicks out the
  earlier one
- For isolation, give each node its own `nodes_dir`

## Troubleshooting table

| Symptom | What to check first | Common causes |
|---|---|---|
| `neighbors()` is empty | Whether both sides use the same `nodes_dir`; whether the other side's `<id>.json` is in that directory | Different directories; the id contains illegal characters (uppercase letters / dots); the announce has not been renewed for over 30 s (the discovery side can take up to 60 s to notice) |
| Neighbours exist, `connections()` does not | Whether the other side's port is reachable; firewall | Port blocked; the other side has exited but its announce has not expired |
| `call()` reports "not connected / unknown node" | The exception message from `ensure_connected(peer_id)` | The name is misspelled; the other side did not announce that tool |
| `call()` times out | Whether `dispatched` in the other side's `metrics_line()` is increasing | The tool function is stuck (a blocking synchronous operation); `timeout` set too short |
| Signals are not received | The publisher's `metrics_line()`: `broadcastSkipped` | The publisher filtered you out by `sub` authorization; or the path pattern you subscribed to does not match |
| A signal stops halfway through | Whether the connection was ever re-established | Signals are not retained; anything sent while the link is down is not replayed |
| The connection count keeps rising and falling (`replaced` is increasing) | Whether two nodes are using the same id | Id conflict; or two nodes repeatedly reconnecting at the same time |
| Signals on the same path are rejected (`signalsRejected`) | The authorization table | Across machines, unauthorized paths are not allowed by default |

## Narrowing it down (in order)

1. **Discovery layer**: `ls ~/.msp/nodes/` — is the other side's `<id>.json` there, and is the
   timestamp fresh?
2. **Connection layer**: `node.connections()`; can the other side see me in
   `node.peer_manifest("me")`?
3. **Capability layer**: is that tool/signal in `node.peer_manifest("peer")`?
4. **Counter layer**: print `metrics_line()` on both sides, to see whether it was "never sent"
   or "never received"
5. **On-the-wire messages**: when you really need it, switch the connection to a local socket and
   capture one 4-byte length prefix + JSON

## The two easiest things to do while debugging

```python
node = MSPNode("probe", preset=Preset.FULL_PEER)
node.start()
print(node.neighbors(), node.connections())        # discovery + connections
print(node.peer_manifest("weather"))               # what the other side actually announced
```

## Still not working

Paste all of these together — far more useful than describing the symptoms:

- the id, `preset` and `nodes_dir` of both nodes
- the output of `ls -l <nodes_dir>` (to see the announce file timestamps)
- `metrics_line()` from both sides
- operating system and Python version
