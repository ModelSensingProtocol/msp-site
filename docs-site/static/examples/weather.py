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
