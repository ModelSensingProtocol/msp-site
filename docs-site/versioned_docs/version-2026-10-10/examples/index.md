# 示例节点

四个能直接跑的节点，覆盖 MSP 的几条主线。每个页面里的代码与
`static/examples/*.py` **逐字一致**（由脚本生成，不会写歪），并且都跑过：

```bash
cd docs-site
PYTHONPATH=../src python tools/check_examples.py
```

| 示例 | 演示什么 | 关键 API |
|---|---|---|
| [天气节点](weather.md) | 最小能力提供方 | `@node.tool` |
| [下载节点](downloader.md) | 长任务 + 进度推送 + 回查 | `start_task` / `get_task` / `publish` |
| [编辑节点](editor.md) | 订阅 + **应用间直连** | `@node.on("download.*")` |
| [观察者](probe.md) | 只看不说（发现与宣告正交） | `Preset.OBSERVER` |

## 一起跑

开三个终端（都在 `ModelSensingProtocol` 仓库根目录，先 `export PYTHONPATH=src`）：

```bash
python examples/downloader.py     # 终端 1：提供 start_task / get_task
python examples/editor.py         # 终端 2：订阅 download.*
python examples/weather.py        # 终端 3：纯工具节点，可选
```

再让任意一个节点（或 agent）调一次：

```python
from msp import MSPNode, Preset

node = MSPNode("driver", preset=Preset.FULL_PEER)
node.start()
print(node.call("downloader", "start_task", {"url": "https://example.com/x", "size_mb": 5}).unwrap())
```

几秒后，终端 2 会打印 `[editor] 收到 download.completed: {...}` —— 这条路径**没有经过模型**。

## 隔离演示环境

每个示例都读环境变量 `MSP_NODES_DIR`（默认 `~/.msp/nodes`）：

```bash
MSP_NODES_DIR=/tmp/msp-demo python examples/weather.py
```

这样演示节点不会和你真正的节点混在同一个发现目录里。

## 这些示例不是"看起来能跑"

`tools/check_examples.py` 做三件实事：

1. 起 `weather.py`，用客户端调 `get_weather`，断言返回值字段；
2. 起 `downloader.py` + `editor.py`，触发任务，断言订阅方**真的**收到了完成信号；
3. 起 `probe.py`，断言它能看见别人。

每次改示例或改 `tools/check_examples.py` 都跑一遍；三个都绿才算数。
