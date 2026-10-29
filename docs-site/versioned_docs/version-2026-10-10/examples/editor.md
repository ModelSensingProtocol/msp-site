---
sidebar_label: "Editing a node: subscribe + app-to-app direct connection"
---

# Editing a node: subscribe + app-to-app direct connection

It subscribes to `download.*`. The downloader hands the finished file to it, **without going through the agent** — this is exactly where MSP parts ways with "everything goes through the model".

## Running

```bash
PYTHONPATH=src python examples/editor.py
```

## What you will see

It prints the neighbour list; when a signal arrives it prints `[editor] received download.completed: {...}` and checks back once with `get_task`.

## Code

Download: <a href="../editor.py" download><code>editor.py</code></a> (Docusaurus rewrites static-file links in md to hashed paths, and that address returns 404, so here we use a native a tag pointing at the real file)

```python
"""Example 3: a subscriber + app-to-app direct connection.

    PYTHONPATH=src python examples/editor.py

It subscribes to the downloader's completion signal. **The downloader hands the file to it,
without going through the agent** — that is the relationship MSP wants to express. The signal
carries only taskId and the path; fetch the real state with get_task (signals can be lost, tools cannot).
"""

from __future__ import annotations

import os
import time

from msp import MSPNode, Preset

# Set MSP_NODES_DIR to isolate the demo environment (default ~/.msp/nodes)
NODES_DIR = os.environ.get("MSP_NODES_DIR", "~/.msp/nodes")


def main() -> None:
    node = MSPNode("editor", preset=Preset.FULL_PEER, nodes_dir=NODES_DIR)
    received: list[dict] = []

    @node.on("download.*")
    def on_download(sig) -> None:
        received.append(sig.payload)
        print(f"[editor] received {sig.path}: {sig.payload}")
        if sig.path == "download.completed":
            # Do not trust the payload in the signal as complete state; check back once
            try:
                task = node.call("downloader", "get_task", {"taskId": sig.payload["taskId"]})
                if not task.is_error:
                    print(f"[editor] check-back result: {task.structured}")
            except Exception as exc:  # noqa: BLE001 - the example only wants to see the error
                print(f"[editor] check-back failed: {exc}")

    node.start()
    print(f"[editor] online, neighbours: {node.neighbors()}")
    print("[editor] Ctrl+C to quit")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        node.stop()
        print(f"\n[editor] received {len(received)} signals in total")


if __name__ == "__main__":
    main()
```

## Worth noting

- The example deliberately **does not trust** the payload in the signal, and checks back instead — use a signal as a notification, and a tool for state.
- Only `Preset.FULL_PEER` can both be connected to and connect to others; `LOCAL_TOOL` can only be connected to.
