"""示例 3：订阅方 + 应用间直连。

    PYTHONPATH=src python examples/editor.py

它订阅 downloader 的完成信号。**下载器把文件交给它，不经过 agent**——
这正是 MSP 想表达的那种关系。信号里只有 taskId 与路径，
真实状态用 get_task 回查（信号可能丢，工具不会）。
"""

from __future__ import annotations

import os
import time

from msp import MSPNode, Preset

# 想隔离演示环境就设 MSP_NODES_DIR（默认 ~/.msp/nodes）
NODES_DIR = os.environ.get("MSP_NODES_DIR", "~/.msp/nodes")


def main() -> None:
    node = MSPNode("editor", preset=Preset.FULL_PEER, nodes_dir=NODES_DIR)
    received: list[dict] = []

    @node.on("download.*")
    def on_download(sig) -> None:
        received.append(sig.payload)
        print(f"[editor] 收到 {sig.path}: {sig.payload}")
        if sig.path == "download.completed":
            # 不信任信号里的 payload 是完整状态，回查一次
            try:
                task = node.call("downloader", "get_task", {"taskId": sig.payload["taskId"]})
                if not task.is_error:
                    print(f"[editor] 回查结果: {task.structured}")
            except Exception as exc:  # noqa: BLE001 - 示例里只想看到错误
                print(f"[editor] 回查失败: {exc}")

    node.start()
    print(f"[editor] 已上线，邻居: {node.neighbors()}")
    print("[editor] Ctrl+C 退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        node.stop()
        print(f"\n[editor] 共收到 {len(received)} 条信号")


if __name__ == "__main__":
    main()
