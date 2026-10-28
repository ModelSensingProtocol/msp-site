# Positioning: neighbours, not sockets

> This document answers one question: for local software talking to AI, why MSP rather than MCP?
> It is not a "protocol war" argument — it is about **shape**.

中文版（含原文表述）：[`POSITIONING.zh-CN.md`](POSITIONING.zh-CN.md)

## MCP and MSP are not the same kind of thing

| | MCP | MSP |
|---|---|---|
| Topology | hub-and-spoke: the model is the centre, every server attaches to it | mesh: nodes are peers, the agent is just one of them |
| Direction | pull-dominant: the model asks | pull **and push**: an app can broadcast when something happens |
| Presence | one entry in a config file | leases: what is running right now is a fact you can read |
| Lifetime | one call, one session | long-lived connection + heartbeat + multi-round / task semantics |
| App-to-app | must go through the model | direct (A's capability can serve B) |

So for the vision "every piece of local software can interact with AI", MCP has the wrong shape: it
assumes software is a pile of passive tools, whereas what we want is a pile of **stateful neighbours
that speak up and know each other**. Wrapping MCP in a shim is not merely complex — it compresses a
mesh into a hub and throws away push and presence, the two things actually worth having.

## Why desktop software needs "neighbour" semantics

### 1. Lifecycle ownership — stdio gets it backwards

```
stdio:          the agent spawns the process -> session ends, process dies -> capability dies with the session
resident server: the app runs its own server -> app lives, capability lives -> capability follows the software
```

"Presence" requires that a capability exists **while the software runs**. stdio ties it to a session
instead, with two concrete consequences:

- **State fidelity is lost**: what the client spawns is a *second* instance that does not know which
  document the user has open.
- **Multi-client mutual exclusion breaks**: two agents spawn two copies → two writers on one file.

### 2. Presence must be "known right now", not "written down once"

Leases make "what is running" a fact that can be read at any moment instead of a list somebody has to
maintain. A crashed node disappears; a restarted one reappears — **nobody has to synchronise state**.

### 3. Speaking up is what local software does

A download finishes, playback changes, a file lands, a device is plugged in — these happen *in the
software*, not in the model's question. Only push carries them where they are needed.

## Three transport shapes

| Dimension | stdio | streamable HTTP | MSP WebSocket transport |
|---|---|---|---|
| Lifecycle owner | **client** | app ✓ | app ✓ |
| Talks to the running instance | ✗ | ✓ | ✓ |
| Stable address | ✗ | has a port, but nobody knows which | directory declaration + lease ✓ |
| Push | ✗ | yes, on the same stream, but the client must stay connected | full duplex ✓ |
| Multi-client | one process per client ✗ | ✓ | ✓ |
| **Discovery** | none needed (spawned) | **the user types a URL** ✗ | automatic ✓ |

**stdio is a convention for wiring tools** (fine for filesystem, git, sqlite — stateless or with state
on disk), not a convention for neighbours.

**Streamable HTTP fixes the lifecycle but hands discovery straight back to you**: the user still has to
know `http://127.0.0.1:8721/mcp`, and has to know whether it changed today. Whatever transport MCP uses,
the missing piece is the same: **a stable addressing layer that appears and disappears by itself**. MCP
has never standardised it; it always defers to config files.

Practical traps on Windows: a fixed port collides, a dynamic port needs a declaration file even more;
binding `0.0.0.0` triggers a firewall prompt while `127.0.0.1` stays quiet; any local process can hit
the port, so authorisation ends up being "put a token in a file and let file permissions be the
credential" — exactly the MSP lease idea. And the ecosystem reality: most MCP servers are still stdio,
because early clients only supported stdio.

## What this choice costs us

**Choosing MSP keeps the supply-side cost on our own books.** MCP has a ready ecosystem (thousands of
servers, vendor support); we give up that free supply.

And to be honest: **MSP's adoption problem is the same problem MCP has — some app has to implement it.
A discovery mechanism does not fix "nobody wants to implement it".**

The trade is worth making, but make it **deliberately**, and do not come back later asking "why is
there no ecosystem". It is a chosen cost, not an oversight.

## The boundary: one protocol at runtime, MCP only at import time

Do not maintain a dual-protocol runtime. Put MCP at **import time**, not at runtime:

> The runtime speaks MSP only. MCP appears exactly once, during conversion.

```
Conversion (once):
  run a tool -> start the MCP server -> call tools/list -> record the tool list -> write a declaration

Runtime (forever after):
  agent -- MSP --> [adapter process] -- MCP --> the original app
                        ^
              an ordinary MSP node that happens to speak MCP internally
```

The point: **the agent side never knows MCP exists.** It sees "there is a node called `wps` with six
tools".

| | Wrapper (permanent dual protocol) | Adapter (one-time move) |
|---|---|---|
| Core code | gains an MCP branch | untouched |
| Config | gains an endpoint type | none; the node announces itself |
| When it breaks | "MSP, the shim, or the server?" | the node is offline; the panel shows it |
| Enable / disable | edit the core | stop the process |
| Replace it | touches the core | swap the adapter |

> A wrapper invites the translator into the driver's seat; a move unloads the van and the translator
> leaves.

One honest clarification: **the tool list can be moved once, but calls still have to reach the app** —
you cannot rewrite WPS in MSP. So the accurate statement is "MCP lives only inside a separate adapter
process, and that process is just an ordinary MSP node to the agent". The value is not "MCP vanished"
but:

1. the core stays single-protocol (one failure mode, one debugging story);
2. MCP's mess is isolated in the layer that is **easiest to write, drop and replace**;
3. that shell has the same shape as the SDK for native apps — so there is **one integration shape**, not two.

### Rule of thumb

**"Does this app have user-visible state?"**

- Yes (editors, players, download managers, IDEs) → it should be a **native MSP node** hosting its own server.
- No (filesystem, git, web scraping, SQLite) → **wrap it in an adapter**; do not rework the app.

## Open questions (honest list)

1. **An OS-level discovery convention**: the mechanism exists (lease directory); what is missing is
   vendors willing to write it. An ecosystem problem, not a technical one.
2. **A 20-line SDK** for C#/C++/Node/Python: declaration, forwarding, heartbeat included. Authors
   should be filling in three fields, not implementing a protocol.
3. **One-time consent**: discovery-as-trust is a hole locally (any process can claim to be WPS).
   Ask once, "allow this app?", then stay quiet.
4. **Tool explosion**: 30 local apps × 10 tools = 300 schemas, which blows up the context window.
   **Auto-discovery turns "resident catalogue, on-demand contracts" from an optimisation into a necessity.**

## In one sentence

> MSP is not selling "yet another tool protocol"; it sells **presence for local software** — it knows
> who is connected to it, it can speak up when something happens, and it can work with its neighbours
> directly. MCP's structure cannot give you those three.

## The most painful example

> You say: "delete the third row of the sheet I just opened."
> The sheet is on your screen, never saved, titled "Workbook1".
> Under stdio, the agent spawns **a second WPS process**: its window list is empty, there is no
> "Workbook1", so all it can answer is: "Please give me the file path."
> — and you have not even named it yet.
>
> That is the shape problem: **you and the agent are not looking at the same software.**
