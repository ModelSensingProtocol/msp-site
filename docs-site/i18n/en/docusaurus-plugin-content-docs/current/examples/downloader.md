---
sidebar_label: "Downloader node: long-running task + signals"
---

# Downloader node: long-running task + signals

`start_task` returns a `taskId` immediately; progress and completion arrive as signals; `get_task` is there for querying. This is the minimal shape of "a long-running task does not have to block".

## Run

```bash
PYTHONPATH=src python examples/downloader.py
```

## What you will see

It prints that the node is online; once called, it sends a `download.progress` every 0.2 seconds, and `download.completed` at the end.

## Code

Download: <a href="../downloader.py" download><code>downloader.py</code></a> (Docusaurus rewrites static file links in md to hashed paths, and that address 404s, so a native a tag is used here to point at the real file)

```python
"""Example 2: a long-running task node.

    PYTHONPATH=src python examples/downloader.py

It shows two things:
  - exposing "has a queue, can be queried" in task mode (start_task / get_task)
  - progress and completion pushed as **signals**, so the caller need not poll

A real downloader only has to swap time.sleep for actual IO.
"""

from __future__ import annotations

import os
import threading
import time
import uuid

from msp import MSPNode, Preset

# Set MSP_NODES_DIR to isolate the demo environment (default ~/.msp/nodes)
NODES_DIR = os.environ.get("MSP_NODES_DIR", "~/.msp/nodes")

TASKS: dict[str, dict] = {}


def main() -> None:
    node = MSPNode("downloader", preset=Preset.LOCAL_TOOL, nodes_dir=NODES_DIR)
    node.declare_signal("download.progress", description="download progress")
    node.declare_signal("download.completed", description="download completed")

    @node.tool("start_task", "Start a download task, returns taskId immediately")
    def start_task(url: str, size_mb: int = 5) -> dict:
        task_id = uuid.uuid4().hex[:8]
        TASKS[task_id] = {"taskId": task_id, "url": url, "state": "running", "progress": 0}

        def work() -> None:
            steps = 10
            for i in range(1, steps + 1):
                time.sleep(0.2)
                TASKS[task_id]["progress"] = i * 100 // steps
                node.publish("download.progress", {"taskId": task_id, "progress": i * 100 // steps})
            TASKS[task_id]["state"] = "completed"
            node.publish(
                "download.completed",
                {"taskId": task_id, "url": url, "path": f"/tmp/{task_id}.bin", "size_mb": size_mb},
            )

        threading.Thread(target=work, daemon=True, name=f"task-{task_id}").start()
        return TASKS[task_id]

    @node.tool("get_task", "Query task state by taskId")
    def get_task(taskId: str) -> dict:
        return TASKS.get(taskId, {"taskId": taskId, "state": "unknown"})

    node.start()
    print("[downloader] online: start_task / get_task + download.progress/completed signals")
    print("[downloader] Ctrl+C to exit")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        node.stop()
        print("\n[downloader] offline")


if __name__ == "__main__":
    main()
```

## Worth noting

- A real downloader only swaps `time.sleep` for actual IO; the rest needs no change.
- Signals are fire-and-forget: anything published while a subscriber is offline is lost, so state has to be recoverable through `get_task`.
