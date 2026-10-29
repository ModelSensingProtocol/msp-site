---
sidebar_label: "Weather node: provide one tool"
---

# Weather node: provide one tool

The smallest capability provider: one tool, one node id. It shows that `@node.tool` announces the tool into the manifest, so a neighbour sees it during the handshake.

## Running

```bash
PYTHONPATH=src python examples/weather.py
```

## What you will see

It prints `[weather] online: get_weather announced, waiting for neighbours`, then waits silently to be called.

## Code

Download: <a href="../weather.py" download><code>weather.py</code></a> (Docusaurus rewrites static-file links in md to hashed paths, and that address returns 404, so here we use a native a tag pointing at the real file)

```python
"""Example 1: the smallest node that provides a tool.

    PYTHONPATH=src python examples/weather.py

It does one thing: puts get_weather on the network. Any other node (or agent) that connects can call it.
"""

from __future__ import annotations

import os
import time

from msp import MSPNode, Preset

# Set MSP_NODES_DIR to isolate the demo environment (default ~/.msp/nodes)
NODES_DIR = os.environ.get("MSP_NODES_DIR", "~/.msp/nodes")


def main() -> None:
    node = MSPNode("weather", preset=Preset.LOCAL_TOOL, nodes_dir=NODES_DIR)

    @node.tool("get_weather", "Look up the weather for a city (demo only, returns a fixed value)")
    def get_weather(location: str, days: int = 3) -> dict:
        return {
            "location": location,
            "days": days,
            "temp_c": 21,
            "note": "example data, not real weather",
        }

    node.start()
    print(f"[weather] online: get_weather announced, waiting for neighbours")
    print("[weather] Ctrl+C to quit")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        node.stop()
        print("\n[weather] offline")


if __name__ == "__main__":
    main()
```

## Worth noting

- `nodes_dir` defaults to `~/.msp/nodes`; the environment variable `MSP_NODES_DIR` can point it elsewhere, so they do not interfere with each other.
- The weather here is a fixed value — the example demonstrates the protocol only, not the business logic.
