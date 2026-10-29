---
sidebar_label: 下载节点：长任务 + 信号
---

# 下载节点：长任务 + 信号

`start_task` 立刻返回 `taskId`，进度与完成通过信号推送；`get_task` 供回查。这就是「长任务不必阻塞」的最小形态。

## 运行

```bash
PYTHONPATH=src python examples/downloader.py
```

## 你会看到

打印已上线；被调用后每 0.2 秒发一条 `download.progress`，结束时发 `download.completed`。

## 代码

下载：<a href="../downloader.py" download><code>downloader.py</code></a>（Docusaurus 会把 md 里的静态文件链接改写成带 hash 的路径，而那个地址 404，所以这里用原生 a 标签指向真实文件）

```python
"""示例 2：长任务节点。

    PYTHONPATH=src python examples/downloader.py

它演示两件事：
  - 用 task 模式暴露「有队列、可回查」的能力（start_task / get_task）
  - 进度与完成通过**信号**推送，调用方不必轮询

真正的下载器只要把 time.sleep 换成实际 IO 即可。
"""

from __future__ import annotations

import os
import threading
import time
import uuid

from msp import MSPNode, Preset

# 想隔离演示环境就设 MSP_NODES_DIR（默认 ~/.msp/nodes）
NODES_DIR = os.environ.get("MSP_NODES_DIR", "~/.msp/nodes")

TASKS: dict[str, dict] = {}


def main() -> None:
    node = MSPNode("downloader", preset=Preset.LOCAL_TOOL, nodes_dir=NODES_DIR)
    node.declare_signal("download.progress", description="下载进度")
    node.declare_signal("download.completed", description="下载完成")

    @node.tool("start_task", "开始一个下载任务，立刻返回 taskId")
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

    @node.tool("get_task", "按 taskId 回查任务状态")
    def get_task(taskId: str) -> dict:
        return TASKS.get(taskId, {"taskId": taskId, "state": "unknown"})

    node.start()
    print("[downloader] 已上线：start_task / get_task + download.progress/completed 信号")
    print("[downloader] Ctrl+C 退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        node.stop()
        print("\n[downloader] 已下线")


if __name__ == "__main__":
    main()
```

## 值得注意

- 真实下载器把 `time.sleep` 换成实际 IO 即可，其余部分不用动。
- 信号是发完即忘的：订阅者离线期间发出的那条就丢了，所以状态要能 `get_task` 回查。
