---
sidebar_label: 天气节点：提供一个工具
---

# 天气节点：提供一个工具

最小的能力提供方：一个工具、一个节点 id。它演示 `@node.tool` 会把工具宣告进清单，邻居握手时就能看到。

## 运行

```bash
PYTHONPATH=src python examples/weather.py
```

## 你会看到

打印 `[weather] 已上线：get_weather 已宣告，等待邻居`，然后静默等待被调用。

## 代码

下载：<a href="../weather.py" download><code>weather.py</code></a>（Docusaurus 会把 md 里的静态文件链接改写成带 hash 的路径，而那个地址 404，所以这里用原生 a 标签指向真实文件）

```python
"""示例 1：提供工具的最小节点。

    PYTHONPATH=src python examples/weather.py

它只做一件事：把 get_weather 挂到网上。其它节点（或 agent）连上来就能调。
"""

from __future__ import annotations

import os
import time

from msp import MSPNode, Preset

# 想隔离演示环境就设 MSP_NODES_DIR（默认 ~/.msp/nodes）
NODES_DIR = os.environ.get("MSP_NODES_DIR", "~/.msp/nodes")


def main() -> None:
    node = MSPNode("weather", preset=Preset.LOCAL_TOOL, nodes_dir=NODES_DIR)

    @node.tool("get_weather", "查询城市天气（演示用，返回固定值）")
    def get_weather(location: str, days: int = 3) -> dict:
        return {
            "location": location,
            "days": days,
            "temp_c": 21,
            "note": "示例数据，不是真实天气",
        }

    node.start()
    print(f"[weather] 已上线：get_weather 已宣告，等待邻居")
    print("[weather] Ctrl+C 退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        node.stop()
        print("\n[weather] 已下线")


if __name__ == "__main__":
    main()
```

## 值得注意

- `nodes_dir` 默认 `~/.msp/nodes`，可用环境变量 `MSP_NODES_DIR` 指到别处，互不干扰。
- 这里的天气是固定值——示例只演示协议，不演示业务。
