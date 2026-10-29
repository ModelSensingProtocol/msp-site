---
sidebar_label: "Observer: look but say nothing"
---

# Observer: look but say nothing

`Preset.OBSERVER` only **scans** the directory; it does not **announce** itself: it can see what is on the network, others cannot see it. Discovery and announcement are two orthogonal layers.

## Running

```bash
PYTHONPATH=src python examples/probe.py
```

## What you will see

Every 5 seconds it prints the neighbour list; this node will not appear in anyone else's neighbour list.

## Code

Download: <a href="../probe.py" download><code>probe.py</code></a> (Docusaurus rewrites static-file links in md to hashed paths, and that address returns 404, so here we use a native a tag pointing at the real file)

```python
"""Example 4: look but say nothing (observer).

    PYTHONPATH=src python examples/probe.py

Discovery and announcement are two orthogonal layers:
  - this node **scans** the directory, so it can see others;
  - but it **does not announce** itself (it writes no announcement file), so others cannot see it.
Good for temporary troubleshooting: take a look at what is on the network now and leave no trace.
"""

from __future__ import annotations

import os
import time

from msp import MSPNode, Preset

# Set MSP_NODES_DIR to isolate the demo environment (default ~/.msp/nodes)
NODES_DIR = os.environ.get("MSP_NODES_DIR", "~/.msp/nodes")


def main() -> None:
    # OBSERVER preset: discovery only, no announcement
    node = MSPNode("probe", preset=Preset.OBSERVER, nodes_dir=NODES_DIR)
    node.start()

    print("[probe] look but say nothing: I can see others, others cannot see me")
    try:
        while True:
            peers = node.neighbors()
            print(f"[probe] {len(peers)} neighbours: {peers}")
            time.sleep(5)
    except KeyboardInterrupt:
        node.stop()
        print("\n[probe] exited")


if __name__ == "__main__":
    main()
```

## Worth noting

- Good for temporary troubleshooting: see what is running now and leave no trace.
- "Say only" is the other half: in `Preset` a combination with presence but no discovery is enough; this example does not go into it.
