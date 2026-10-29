"""示例 4：只看不说（观察者）。

    PYTHONPATH=src python examples/probe.py

发现与宣告是两个正交的层：
  - 这个节点**扫描**目录，所以能看见别人；
  - 但它**不宣告**自己（不写声明文件），所以别人看不见它。
适合临时排查：看一眼网上现在有什么，不留下痕迹。
"""

from __future__ import annotations

import os
import time

from msp import MSPNode, Preset

# 想隔离演示环境就设 MSP_NODES_DIR（默认 ~/.msp/nodes）
NODES_DIR = os.environ.get("MSP_NODES_DIR", "~/.msp/nodes")


def main() -> None:
    # OBSERVER 预设：只有发现，没有宣告
    node = MSPNode("probe", preset=Preset.OBSERVER, nodes_dir=NODES_DIR)
    node.start()

    print("[probe] 只看不说：我能看见别人，别人看不见我")
    try:
        while True:
            peers = node.neighbors()
            print(f"[probe] 邻居 {len(peers)} 个: {peers}")
            time.sleep(5)
    except KeyboardInterrupt:
        node.stop()
        print("\n[probe] 已退出")


if __name__ == "__main__":
    main()
