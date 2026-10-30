# Debugging a node

MSP has no log aggregation and no tracer. What it has is a small, honest set of counters and two
inspectable files — enough to answer "did it get there?" in almost every case.

## The three questions

Work down this list; each step narrows the next.

1. **Does the peer know the node exists?** → `ls <nodes_dir>` and `node.neighbors()`
2. **Is there a connection?** → `node.connections()` and `peer_manifest(peer)` on both sides
3. **Did the message arrive?** → `metrics_line()` on both sides

Almost every bug is answered at step 1 or 2; jumping to step 3 first usually wastes an hour.

## `metrics_line()` — what the numbers mean

```
[msp] connections opened=12 replaced=1 condemned=0
      signals accepted=40 out=17 rejected=0 resultsDropped=0 broadcastSkipped=3
      tools dispatched=5 rejected=0 shed=0
      task threads active=1 peak=3
```

| Counter | Read it as |
|---|---|
| `opened` / `replaced` | `replaced` climbing means two nodes keep evicting each other — usually a **duplicate node id** |
| `signals accepted` | signals that arrived *and matched a handler* |
| `signals rejected` | authorisation refused them; expect this across machines until you grant a path |
| `broadcastSkipped` | peers that were not subscribed — normal, not an error |
| `resultsDropped` | a reply arrived for a call that had already timed out; usually a slow tool |
| `tools rejected` | the call arrived but the tool was unknown or refused |
| `tools shed` | the node hit its concurrency limit and refused work instead of queueing it |

Two nodes, one suspicious behaviour: print both lines. "No packets" and "packets arriving but dropped"
look identical from one side.

## The tools you already have

```python
node.neighbors()          # known from the directory
node.connections()        # actually connected
node.peer_manifest("x")   # what they advertise (tools, signals, capabilities)
node.exposed_bindings()   # what *you* advertise — call after start()
```

A useful habit: assert `"peer" in node.connections()` in tests rather than `in node.neighbors()`.
Neighbours include nodes that are dead but whose lease has not expired yet.

## Watching a network without joining it

```bash
PYTHONPATH=src python examples/probe.py
```

`Preset.OBSERVER` scans but never announces, so you can look at a machine and leave no trace. If you
want the connection graph as well, the DeepSeek Harness plugin's `/msp/graph` endpoint returns nodes
plus edges with the evidence behind each edge.

## When the tools are not enough

- **`watchdog` not firing?** The poll fallback means discovery still works, 30 s late. If it is *late*
  rather than broken, that is the poll; if it is broken, check the directory is not on a network mount
  that does not emit inotify events.
- **Windows:** no `AF_UNIX`, so the UDS transport tests are skipped, and `nodes_dir` is a normal path
  (no `~` expansion surprises if you pass an absolute path).
- **Timing:** a node takes up to 60 s to disappear after a crash. A test that asserts "peer is gone"
  immediately after `kill -9` is asserting the wrong thing.

## See also

- [FAQ and troubleshooting](faq.md) — the symptom → cause table
- [Topology and what you cannot see](topology.md) — why an edge in a diagram may be a guess
- [`docs/spec/discovery.md`](pathname:///msp-site/docs/spec/discovery/) — exact lease semantics when the numbers matter
