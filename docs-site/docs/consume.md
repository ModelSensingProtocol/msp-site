# Using capabilities: discovery, calling, subscribing

## Discovery

```python
node.start()
print(node.neighbors())        # known neighbour ids
print(node.connections())      # ids of neighbours already connected
print(node.peer_manifest("weather"))   # the raw manifest the other side announced
```

The difference between `neighbors()` and `connections()` matters: **a known neighbour is not a connected one**. By default `connect_policy="eager"` dials out eagerly, while `"lazy"` waits until a call is actually made.

### Does start() block

`start(settle=True)` (the default) waits for every connection triggered by discovery **during this startup** to land, up to `settle_timeout` (0.5 seconds by default), and returns whether things settled before the timeout. So:

- A `publish` / `call` straight after startup does not hit an empty connection set
- But it **only waits, it never dials** — it will not connect new nodes in the name of "settling"
- In lazy connection mode it is a no-op

To settle again by hand:

```python
node.start(settle=False)
node.settle(1.0)
```

## Calling tools

```python
result = node.call("weather", "get_weather", {"location": "Hangzhou"}, timeout=5.0)
```

Failure **does not raise**; it returns a `ToolResult` carrying the error:

```python
if result.is_error:
    print("failed:", result.error)      # peer unreachable / unknown tool / timeout / dropped midway
else:
    data = result.structured          # the dict returned by the tool function
```

Two convenience methods:

| Usage | Behaviour |
|---|---|
| `result.unwrap()` | Returns `structured` on success, raises `ToolError` on failure |
| `result.text()` | Joins all text blocks into a string |

**On success `result.error` is the empty string, not `None`** — test success with `is_error` or `if result.error:`, never with `if result.error is None`.

## Subscribing to broadcasts

```python
@node.on("weather.*")
def handle(sig):
    print(sig.path, sig.payload, sig.source)
```

- Paths support `*` (one segment) and `**` (many segments)
- `node.on(None)` receives everything
- Handlers run on a **separate thread** (ordered, and they do not block the read loop); a slow callback does not stall the heartbeat

### Signals get lost, and that is by design

Signals are broadcasts with no retention: **one sent while you are not connected is lost for good**, and reconnecting does not replay it. So the correct usage is "treat signals as change notifications, and query state through tools":

```python
@node.on("download.completed")
def done(sig):
    # do not trust the payload to be the complete state; read it back
    task = node.call("downloader", "get_task", {"taskId": sig.payload["taskId"]}).unwrap()
    ...
```

## Disconnection and reconnection

- Heartbeat PING every 15 seconds; 45 seconds without a response counts as liveness loss
- On liveness loss **every pending call fails and returns at once**; nothing waits out its timeout for nothing
- Reconnection is the discovery mechanism's job: the node's announcement is still in the directory, and the next scan dials it again
- To observe state changes:

```python
node.on_connected(lambda peer: print("connected", peer))
node.on_disconnected(lambda peer: print("disconnected", peer))
```

## Observation

```python
print(node.metrics())
```

The counters cover: connections (opened/replaced/condemned), signals (accepted/out/rejected/broadcastSkipped), tools (dispatched/rejected/shed), task threads (active/peak).

When troubleshooting, look at `metrics_line()` first: `signalsRejected>0` is usually an authorization problem, and `broadcastSkipped>0` means the other side did not subscribe to that path (under the protocol this is normal, not an error).
