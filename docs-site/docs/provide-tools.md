# Providing capabilities: exposing tools and signals

## Registering tools

```python
@node.tool("get_weather", "Look up the weather")
def get_weather(location: str, days: int = 3) -> dict:
    return {"location": location, "days": days, "temp_c": 21}
```

Three things are written into the manifest, and a neighbour sees them at handshake time: the name, the description, the input schema.

### Where the schema comes from

By default it is generated from the type annotations in the function signature:

```python
from typing import Annotated

@node.tool("search", "Search local files")
def search(
    pattern: Annotated[str, "regular expression"],
    path: Annotated[str, "search root directory"] = ".",
    limit: Annotated[int, "maximum number of results"] = 50,
) -> dict:
    ...
```

For full control, pass it explicitly:

```python
node.tool("raw", "hand-written description", input_schema={"type": "object", "properties": {...}})
```

**The schema is for announcing capabilities only; it does not validate at runtime** — do not expect it to stop invalid arguments. The tool function has to defend itself.

### How the return value becomes a result

The dict returned by a tool function goes into `ToolResult.structured`. To return rich content (text or image blocks), return MCP-style content blocks;
see [`src/msp/mcp/`](https://github.com/hxh230802/MSP/tree/master/src/msp/mcp/).

## Publishing signals

Two steps: **declare** which path you will publish, then **publish**.

```python
node.declare_signal("weather.updated", description="weather data updated")

node.publish("weather.updated", {"location": "Hangzhou", "temp_c": 21})
```

`publish` is fire-and-forget: it does not wait, there is no receipt, and no error is raised if nobody is subscribed.

### Wiring in external event sources

When a background thread or listener keeps producing events, decorate a **zero-argument generator** with `signal_source`. Once the node starts, it iterates the generator and publishes automatically:

```python
@node.signal_source("system.file.modified")
def watch():
    for event in watch_downloads_folder():     # your own blocking iterator
        yield {"path": str(event.path), "size": event.size}
```

Note that this function **MUST be a generator** (it needs a `yield` inside) and it **cannot take arguments** — `@node.signal` is an alias for it.

### Why declaring matters

`declare_signal` writes the path into the manifest. That is how neighbours learn "this node publishes this kind of signal", and it is what makes path-based authorization possible at all
(`sub` authorization matches **path patterns**, not content). You can publish without declaring, but then nobody knows to expect it.

## Batched manifest updates: `defer_manifest`

When registering a dozen tools at once, pushing the manifest once per tool is wasteful. Use the context manager to collect them into a single push:

```python
with node.defer_manifest():
    for name, fn in handlers.items():
        node.tool(name, "")(fn)
```

It only affects manifest pushes. It is not a general-purpose concurrency primitive.

## Long-running work: the task pattern

Capabilities like `get_task` / `list_tasks` — ones backed by a queue that need a follow-up query — are less work with the `msp/task` pattern than as bare tools:
the caller receives a task snapshot it can query again. See [`src/msp/patterns/task.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/task.py)
and the "Tasks" section of [`docs/DESIGN.md`](https://github.com/hxh230802/MSP/blob/master/docs/DESIGN.md).

## Checking what you have announced

```python
node.start()
print(node.exposed_bindings())     # tools and signals this node exposes
print(node.metrics_line())         # counts for connections / signals / tools
```

`metrics_line()` is your first-hand evidence when you need to find out whether the other side actually sent anything.
