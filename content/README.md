# MSP 手册（wiki）

面向**要用起来**的人：装上一个节点、把能力暴露出去、调用邻居、订阅广播。规范条文在
[`docs/spec/`](../spec/README.md)，设计取舍在 [`docs/DESIGN.md`](../DESIGN.md)，与 MCP 的关系在
[`docs/POSITIONING.zh-CN.md`](../POSITIONING.zh-CN.md)。这里只讲怎么用。

## 从哪读起

| 你想做的事 | 读这一页 |
|---|---|
| 五分钟内让两个节点互相调用 | [快速开始](01-getting-started.md) |
| 搞清节点、信号、工具、租约分别是什么 | [核心概念](02-concepts.md) |
| 把自己的能力暴露给别人 | [提供能力](03-provide.md) |
| 调用邻居、订阅广播、处理错误 | [使用能力](04-consume.md) |
| 跑不通时先看这里 | [FAQ 与排查](05-faq.md) |
| 术语对齐 | [术语表](06-glossary.md) |

## 三十秒速览

```python
from msp import MSPNode, Preset

node = MSPNode("weather", preset=Preset.LOCAL_TOOL)   # 宣告自己、可被发现

@node.tool("get_weather", "查询天气")                   # 暴露一个工具
def get_weather(location: str, days: int = 3) -> dict:
    return {"location": location, "days": days, "temp_c": 21}

node.start()                                          # 启动（等发现到的建连落地）
```

另一个节点上：

```python
peer = MSPNode("agent", preset=Preset.FULL_PEER)
peer.start()

print(peer.neighbors())                                # ['weather']
print(peer.call("weather", "get_weather", {"location": "杭州"}).unwrap())
```

## 本手册的示例都跑过

[`examples/two_nodes.py`](examples/two_nodes.py) 是本手册的完整示例（发现 + 调用 + 订阅 + 指标），
可以真的运行：

```bash
PYTHONPATH=src python docs/wiki/examples/two_nodes.py
```

改文档时请同步跑它——手册里的片段和这个文件保持一致，避免写出跑不通的代码。

## 一页纸的边界

MSP 负责的是**节点之间怎么互相发现、怎么调用、怎么广播**。它不负责：鉴权与加密（当前信任模型是
"传输可达即信任"）、持久化、模型推理本身。这些留给上层或部署环境。

## 为什么不用 GitHub 的 Wiki 标签页

GitHub 的 Wiki 是**独立一个 git 仓库**（`<repo>.wiki.git`），和代码仓库分开；本仓库目前是私有的，
而**私有仓库在免费账号下开不了 wiki**（API 接受了 `has_wiki=true` 但不生效，`MSP.wiki.git`
始终 404）。所以手册先放在仓库内的 `docs/wiki/`——它跟着代码一起版本化、能进 code review、
`git grep` 搜得到。

仓库公开之后如果要那个标签页，一条命令即可同步过去：

```bash
python tools/sync_wiki.py      # 生成到 _wiki/，脚本会把相对链接改成绝对链接
git -C _wiki init && ...       # 推到 MSP.wiki.git
```

[`tools/sync_wiki.py`](../../tools/sync_wiki.py) 已经写好：wiki 是独立仓库，`../spec/` 这类相对
路径在那边不成立，脚本会把它们换成 GitHub 绝对 URL，并把首页改名成 `Home`、生成 `_Sidebar.md`
导航。
