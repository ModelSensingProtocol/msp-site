# Introduction

Two nodes, five minutes: one offers a tool, the other discovers it and calls it.

## 1. Install

```bash
pip install --pre msp-py        # pre-release on PyPI for now
# or from source:
pip install -e .
```

`pip install -e .` is an editable install — source edits take effect immediately (use a virtual
environment).

## 2. The side that offers a capability

Save as `weather.py`:

```python
from msp import MSPNode, Preset

node = MSPNode("weather", preset=Preset.LOCAL_TOOL)


@node.tool("get_weather", "Look up the weather")
def get_weather(location: str, days: int = 3) -> dict:
    return {"location": location, "days": days, "temp_c": 21}


if __name__ == "__main__":
    node.start()
    input("press enter to quit\n")
```

`@node.tool` does more than register a function: it **declares the tool in the node's capability
manifest**, so a neighbour sees it during the handshake.

## 3. The side that uses it

Save as `agent.py`, run one in each terminal:

```python
from msp import MSPNode, Preset

node = MSPNode("agent", preset=Preset.FULL_PEER)
node.start()

print("neighbours:", node.neighbors())

result = node.call("weather", "get_weather", {"location": "Hangzhou"})
print("result:", result.unwrap() if not result.is_error else result.error)
```

Within two seconds you should see `neighbours: ['weather']` and a JSON payload.

## 4. How they found each other

Both write a "I am here" declaration into the same directory and poll that directory:

```
~/.msp/nodes/weather.json     ← the node id is the file name
~/.msp/nodes/agent.json
```

- A node writes its endpoint (host/port) on start and renews the lease every 5–10 s
- Other nodes scan the directory and dial anything new
- **A declaration not renewed within 30 s is ignored** — a crashed process needs no cleanup

Pass `nodes_dir=` to use another directory. Two nodes using different directories simply cannot
see each other.

## 5. Next

- Expose more interfaces, push events → [Provide tools and signals](provide-tools.md)
- Handle failed calls, subscribe to broadcasts → [Discover, call, subscribe](consume.md)
- Run the whole example at once (no second terminal) → `PYTHONPATH=src python docs/wiki/examples/two_nodes.py`
