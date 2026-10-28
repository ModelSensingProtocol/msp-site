# 提供能力：把工具和信号暴露出去

## 注册工具

```python
@node.tool("get_weather", "查询城市天气")
def get_weather(location: str, days: int = 3) -> dict:
    return {"location": location, "days": days, "temp_c": 21}
```

三样东西会被写进能力清单，邻居握手时就能看到：名字、描述、输入 schema。

### schema 从哪来

默认从函数签名的类型注解生成：

```python
from typing import Annotated

@node.tool("search", "在本地文件里搜索")
def search(
    pattern: Annotated[str, "正则表达式"],
    path: Annotated[str, "搜索根目录"] = ".",
    limit: Annotated[int, "最多返回条数"] = 50,
) -> dict:
    ...
```

想完全自己控制就显式传：

```python
node.tool("raw", "手工描述", input_schema={"type": "object", "properties": {...}})
```

**schema 只用于对外宣告，不做运行时校验**——别指望它挡住非法参数，工具函数自己要防御。

### 返回值怎么变成结果

工具函数返回的 dict 进 `ToolResult.structured`。想返回富内容（文本/图片块）就返回 MCP 风格的内容块，
见 [`src/msp/mcp/`(https://github.com/hxh230802/MSP/tree/master/src/msp/mcp/)。

## 发布信号

两步：**声明**会发布哪条路径，然后**发布**。

```python
node.declare_signal("weather.updated", description="天气数据更新")

node.publish("weather.updated", {"location": "杭州", "temp_c": 21})
```

`publish` 是发完即忘的：不等待、没有回执、没人订阅也不报错。

### 把外部事件源接进来

有个后台线程/监听器不断产生事件时，用 `signal_source` 装饰一个**无参生成器**，节点启动后会自动迭代并发布：

```python
@node.signal_source("system.file.modified")
def watch():
    for event in watch_downloads_folder():     # 你自己的阻塞迭代器
        yield {"path": str(event.path), "size": event.size}
```

注意这个函数**必须是生成器**（里面要有 `yield`），而且**不能带参数**——`@node.signal` 是它的别名。

### 声明的意义

`declare_signal` 会把路径写进 manifest，邻居才知道"这个节点会发这类信号"，也才谈得上按路径授权
（`sub` 授权是按**路径模式**匹配的，不是按内容）。不声明也能发，但没人知道该期待它。

## 批量改清单：`defer_manifest`

一次注册十几个工具时，逐个推清单很浪费。用上下文管理器攒成一次：

```python
with node.defer_manifest():
    for name, fn in handlers.items():
        node.tool(name, "")(fn)
```

它只影响清单推送，不是通用并发原语。

## 长任务：任务模式

`get_task` / `list_tasks` 这种"有队列、要回查"的能力，用 `msp/task` 模式比裸工具更省事——
调用方拿到的是一份可回查的任务快照。见 [`src/msp/patterns/task.py`(https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/task.py)
与 [`docs/DESIGN.md`(https://github.com/hxh230802/MSP/blob/master/docs/DESIGN.md) 里"任务"一节。

## 检查自己宣告了什么

```python
node.start()
print(node.exposed_bindings())     # 本节点对外暴露的工具与信号
print(node.metrics_line())         # 连接 / 信号 / 工具各维度的计数
```

`metrics_line()` 是排查"对方到底有没有发过来"的第一手证据。
