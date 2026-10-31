---
sidebar_label: Proactive events (pub/sub)
---

# Proactive events: pushing without a webhook

MCP's Events (subscribe plus a Webhook URL) make sense in the cloud: the subscriber is a process
somewhere behind a firewall, and HTTP is the only common ground. On one machine it costs more than it
buys.

| | MCP Events | MSP |
|---|---|---|
| How a subscription is made | client sends `events/subscribe` with a Webhook URL | one line: `@node.on("file.**")` |
| How long it lasts | a TTL the client must keep renewing | as long as the connection; reconnect is automatic |
| Who initiates | directed: client → server | non-directional: the publisher never knows who listens |
| What the machine must expose | an HTTPS endpoint | nothing — the node already announces itself |
| Topology | client–server, the AI at the centre | mesh, the AI is just another node |

One sentence: **local processes are peers; receiving an event should not require demoting yourself to a
client.**

## The shape — three snippets

### 1. A normal local program (the producer)

```python
from msp import MSPNode, Preset

watcher = MSPNode("file-watcher", preset=Preset.LOCAL_TOOL)

@watcher.signal_source("file.modified")    # declare the path and supply the source, in one step
def watch_inbox():
    for path in new_files():               # any blocking or long-running loop
        yield {"name": path.name, "path": str(path)}

watcher.start()
```

`signal_source` takes a **generator**. Each yielded dict is published. No socket to open, no URL to
register, no need to know whether anyone is listening. No thread, no callback, no lifecycle to manage —
that is the whole point: the generator *is* the nerve ending.

### 2. A proactive agent (the consumer)

```python
ai = MSPNode("ai", preset=Preset.LOCAL_AI)

@ai.on("file.**")                          # * matches one segment, ** matches the rest
def on_any_file(sig):
    print(sig.path, sig.payload)

ai.start()
```

That is the subscription. No `events/subscribe`, no webhook, no TTL renewal, no polling.

### 3. Discovery, for free

Both nodes call `start()`; the shared-directory leases let them find each other, and `ai` dials
`file-watcher`. **The dialled side never learns who dialled it** — it does not need to.

## Run it

<a href="/msp-site/docs/examples/proactive_pubsub.py" download><code>proactive_pubsub.py</code></a> — two nodes, one temporary inbox, about six
seconds:

```bash
PYTHONPATH=src python docs-site/static/examples/proactive_pubsub.py
```

Real output from an isolated run (`MSP_NODES_DIR` pointed at an empty directory):

```
2. wait for the discovery layer to connect them (shared directory, zero config)
   ai sees:      ['file-watcher']
   watcher sees: ['ai']
   ↑ watcher is the dialled side: it does not know who is dialling it

3. drop three files into the directory
  [watcher] detected screenshot-1.png → publish('file.modified')
  [ai] received file.modified: {'name': 'screenshot-1.png', 'size': 6}
  ... two more ...

4. result
   AI received 3 signals
```

Run it **without** `MSP_NODES_DIR` and the neighbour list grows on its own: on the machine this was
written on it showed `notchpeninsula` and a DeepSeek Harness node — real software, discovered and
connected with no configuration. That is the part worth watching: zero-config discovery is not a demo
effect, it is what the network does.

## What the demo proves, line by line

| Claim | Where it shows |
|---|---|
| no webhook to register | no URL appears anywhere in the run |
| no TTL to renew | the only subscription is `@ai.on("file.**")`; nothing is sent again afterwards |
| the link is not directed | `watcher` never learns who received the signal |
| mesh, peers | the two nodes run the same code and differ only in preset |
| push, not poll | the signal is emitted by the watcher, not requested by the agent |

## Two Windows gotchas

1. The console defaults to GBK: Chinese text and box characters come out as mojibake. Add
   `sys.stdout.reconfigure(encoding="utf-8")` at the top (the example does).
2. `node.connections` is a **method**: `node.connections()`, not an attribute.

## When MCP Events is still the right answer

Across the public internet, through a firewall, or when the other side will only expose HTTPS — there
the client–server shape is correct, and MCP is the right tool. MSP covers the other half: processes on
**one machine**, each already announcing itself.

## See also

- [Signals: pushing, and what it costs](signals.md) — the mechanics behind `signal_source` and `on()`
- [Node and preset](library/node-and-preset.md) — why the producer is never told who listens
- [`spec/patterns/publish-subscribe.md`](pathname:///msp-site/docs/spec/patterns/publish-subscribe/) —
  the normative pattern
