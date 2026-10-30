# Running across machines

MSP is local-first, but the transport is plain TCP — nothing stops a node on another machine. What
does not carry over is the part everyone forgets: **discovery is a shared directory**, and a directory
is local to a machine.

This page is the checklist for going from "works on my laptop" to "works on the LAN".

## 1. The directory has to be shared, or discovery does not happen

Options, in order of how much I would recommend them:

| Approach | Effort | Notes |
|---|---|---|
| Share `nodes_dir` over a network mount (SMB/NFS) | low | works; file events over SMB are unreliable, so you are on the 30 s poll — expect up to 60 s to see a new node |
| `add_manual_source(...)` / explicit peer list | low | deterministic, no polling surprises; best for two fixed machines |
| Copy declaration files by hand | none | fine for a demo, useless in practice |
| Central registry service | high | you have just reintroduced the broker MSP avoids |

For two machines, manual registration is usually the right answer. Sharing a directory to get
automatic discovery across a network is a lot of moving parts for a feature you can hardcode.

## 2. Bind where you mean to bind

A node listens on the address you give it. Binding to `0.0.0.0` makes it reachable from the network —
which, given the [trust model](security.md), means *callable by anything that can route to it*.

```python
node = MSPNode("bridge", preset=Preset.FULL_PEER, config={"listen_host": "0.0.0.0"})
```

Only do this on a network you control, and firewall the port to the machines that need it.

## 3. Cross-machine peers are not "local", so grants matter

Loopback and UDS peers are allow-listed automatically. A peer arriving over the LAN is not, so:

- **Calls** from it are refused unless you grant the tool paths.
- **Subscriptions** from it are refused unless you grant the signal paths.

If a remote peer connects but nothing works, `signalsRejected` / `tools rejected` in `metrics_line()`
is where you will see it.

## 4. Node ids must still be unique — across machines too

The id is the key in the connection table. Two machines both calling themselves `bridge` will evict
each other, and whichever dialled last wins. Use a stable, machine-qualified id:

```
office-pc-bridge
nas-bridge
```

The dedup rule is lexicographic on `node_id`: the smaller id is responsible for the outbound
connection. That is a tie-breaker, not a security mechanism — but it does mean names are not neutral.

## 5. What you lose

- **`is_local_peer()` is false** — no automatic allowance.
- **Discovery latency** rises to the poll interval (30 s) if the mount does not emit events.
- **The transport is in clear text.** There is no `wss://`; if the path crosses a network you do not
  control, put it behind a tunnel.
- **Clock skew matters.** Leases are timestamps; machines disagreeing by minutes will produce
  phantom-live or phantom-dead nodes.

## A sane two-machine setup

1. Give both nodes distinct ids (`alpha-pc`, `beta-nas`).
2. On each, register the other explicitly — no shared directory, no polling.
3. Bind to the LAN interface on both, firewalled to each other's address.
4. Grant only the paths the other side actually needs.
5. Verify with `connections()` and `metrics_line()` before building anything on top.

## See also

- [Security and trust](security.md) — why the firewall is not optional
- [Debugging](debugging.md) — reading `signalsRejected`
- [`spec/transports.md`](pathname:///msp-site/docs/spec/transports/) — tcp / uds / websocket details
