# Leases and discovery

A node does not register with anything. It writes a file, and keeps rewriting it. Everything else in
MSP's discovery follows from that one decision.

## The declaration

```
~/.msp/nodes/<node_id>.json
```

That is the whole "registration". The file name is the node id (so it must match `^[a-z0-9_-]+$`), and
the content is the endpoint plus a timestamp. Change `nodes_dir=` if you want a different directory;
two nodes that use different directories cannot see each other, by construction.

## The numbers

| Parameter | Value | Meaning |
|---|---|---|
| renew interval | **10 s** | the writer rewrites `timestamp` this often |
| stale threshold | **30 s** | `now - timestamp > 30s` means expired — treated as "node is gone" |
| poll fallback | **30 s** | full directory scan when the event channel misses something |

So a crashed node takes **at most 60 s to disappear**: up to 30 s before its lease is judged stale,
plus at most one more 30 s poll cycle before a reader notices.

Nothing cleans up the file. A stale declaration is ignored, not deleted — which is why a machine that
has been up for weeks accumulates dead files, and why "is it in the directory?" is not the same
question as "is it running?".

## Two legs of discovery

- **Event channel** (`watchdog` filesystem events) — realtime; a new declaration is picked up as soon
  as it lands.
- **Polling, every 30 s** — the safety net for when events are lost (directory recreated, watcher died,
  a filesystem that does not emit events).

You do not choose between them; both are on. The poll is why "I wrote the file and nobody noticed" is
never a real explanation for more than 30 seconds.

## Discovery and presence are orthogonal

This is the part people get wrong: **announcing** (writing your own declaration) and **discovering**
(reading others') are separate layers, and each can be on or off.

| Announcing | Discovering | You get |
|---|---|---|
| on | on | a normal peer — sees and is seen |
| on | off | *only speaks*: listed by others, never dials anyone |
| off | on | *only looks*: `Preset.OBSERVER`, sees everything, invisible |
| off | off | not on the network at all |

The [observer example](examples/probe.md) is the third row.

## Why a lease instead of a registry

A registry is a service: something to deploy, keep alive, and patch. A directory of timestamped files
is something you can inspect with `ls`, delete by hand, and understand from a stack trace. The cost is
that expiry is approximate (the 60 s bound above) and that the directory is machine-local — for a LAN
you need a shared mount or manual registration.

## See also

- [`spec/discovery.md`](pathname:///msp-site/docs/spec/discovery/) — the normative rules: exact JSON, strict `>` expiry,
  `timestamp` absent means never expire
- [Running across machines](lan.md) — what changes when the directory is not shared
- [Debugging](debugging.md) — how to tell "not discovered" from "discovered but not connected"
