# 快速开始

五分钟内跑通两个节点：一个提供一个工具，另一个发现它并调用。

## 1. 安装

```bash
pip install --pre msp-py        # PyPI 上目前是预发布版本
# 或者从源码：
pip install -e .
```

`pip install -e .` 是"可编辑"安装，改源码立刻生效（建议在虚拟环境里）。

## 2. 提供能力的一方

存成 `weather.py`：

```python
from msp import MSPNode, Preset

node = MSPNode("weather", preset=Preset.LOCAL_TOOL)


@node.tool("get_weather", "查询城市天气")
def get_weather(location: str, days: int = 3) -> dict:
    return {"location": location, "days": days, "temp_c": 21}


if __name__ == "__main__":
    node.start()
    input("按回车退出\n")
```

`@node.tool` 不只注册函数，还会**把工具声明进自己的能力清单**——邻居握手时就能看到它。

## 3. 使用能力的一方

存成 `agent.py`，两个终端各跑一个：

```python
from msp import MSPNode, Preset

node = MSPNode("agent", preset=Preset.FULL_PEER)
node.start()

print("邻居:", node.neighbors())

result = node.call("weather", "get_weather", {"location": "杭州"})
print("结果:", result.unwrap() if not result.is_error else result.error)
```

两秒内你应该看到 `邻居: ['weather']` 和一份 JSON。

## 4. 它们是怎么互相找到的

默认都往同一个目录写"我在这里"的声明、并轮询这个目录：

```
~/.msp/nodes/weather.json     ← 节点 id 就是文件名
~/.msp/nodes/agent.json
```

`timestamp` 是**租约**，不是元数据：

| 参数 | 值 | 含义 |
|---|---|---|
| 续租周期 | **10 秒** | 宣告方每 10 秒重写一次 `timestamp` |
| 过期阈值 | **30 秒** | `now - timestamp > 30s` 即过期，等同"节点已死" |
| 轮询兜底 | **30 秒** | 事件通道失效时的全量扫描周期 |

所以**崩溃节点的消失上界是 60 秒**：最多 30 秒才被判过期，最坏再等一个 30 秒轮询周期。

发现由两条腿组成：**事件通道**（文件系统监听，实时）与**轮询兜底**（30 秒一次全量扫，
兜住事件丢失）。

想换目录就传 `nodes_dir=`。同一台机器上两个节点用不同目录，就互相看不见。

**「发现」与「宣告」是两个正交的层**：只扫不写 = 只看不说（观察者）；
只写不扫 = 只说（把自己挂出去，但不主动连别人）。

## 5. 下一步

- 想暴露更多接口、想主动推送 → [提供能力](provide-tools.md)
- 想看调用失败怎么办、怎么订阅广播 → [使用能力](consume.md)
- 想一次跑完整个例子（不需要开两个终端）→ `PYTHONPATH=src python docs/wiki/examples/two_nodes.py`
