# 使用能力：发现、调用、订阅

## 发现

```python
node.start()
print(node.neighbors())        # 已知的邻居 id
print(node.connections())      # 已经连上的邻居 id
print(node.peer_manifest("weather"))   # 对方宣告的原始清单
```

`neighbors()` 与 `connections()` 的差别很重要：**邻居已知 ≠ 连接已建立**。默认
`connect_policy="eager"` 会主动去连，`"lazy"` 则等到真要调用时才连。

### start() 会不会阻塞

`start(settle=True)`（默认）会等**这次启动过程中**由发现触发的建连全部落地，最多
`settle_timeout`（默认 0.5 秒），返回是否在超时前稳定。所以：

- 启动后立刻 `publish` / `call` 不会打到空的连接集合上
- 但它**只等、不发起**——不会为了"稳定"去连新的节点
- 懒连接模式下它是空操作

想手动再稳一次：

```python
node.start(settle=False)
node.settle(1.0)
```

## 调用工具

```python
result = node.call("weather", "get_weather", {"location": "杭州"}, timeout=5.0)
```

失败**不抛异常**，返回带错误的 `ToolResult`：

```python
if result.is_error:
    print("失败:", result.error)      # 对端不可达 / 未知工具 / 超时 / 中途断开
else:
    data = result.structured          # 工具函数返回的 dict
```

两个便利方法：

| 用法 | 行为 |
|---|---|
| `result.unwrap()` | 成功返回 `structured`，失败抛 `ToolError` |
| `result.text()` | 把所有 text 块拼成字符串 |

**成功时 `result.error` 是空字符串，不是 `None`**——判断成功请用 `is_error` 或 `if result.error:`，
不要写 `if result.error is None`。

## 订阅广播

```python
@node.on("weather.*")
def handle(sig):
    print(sig.path, sig.payload, sig.source)
```

- 路径支持 `*`（单段）与 `**`（多段）
- `node.on(None)` 收全部
- 处理函数在**独立线程**里跑（保序、不阻塞读循环）；慢回调不会拖住心跳

### 信号会丢，这是设计

信号是广播、没有留存：**没连上时发的就永久丢失**，重连也不补发。所以正确的用法是
"信号当变化通知，状态靠工具去查"：

```python
@node.on("download.completed")
def done(sig):
    # 不信任 payload 是完整状态，回查一次
    task = node.call("downloader", "get_task", {"taskId": sig.payload["taskId"]}).unwrap()
    ...
```

## 断线与重连

- 心跳 15 秒 PING、45 秒无响应判失联
- 失联时**所有挂起的调用立刻失败返回**，不会白等到超时
- 重连由发现机制负责：节点的声明还在目录里，下一轮扫描会重新拨过去
- 想感知状态：

```python
node.on_connected(lambda peer: print("连上", peer))
node.on_disconnected(lambda peer: print("断开", peer))
```

## 观测

```python
print(node.metrics())
```

计数覆盖：连接（opened/replaced/condemned）、信号（accepted/out/rejected/broadcastSkipped）、
工具（dispatched/rejected/shed）、任务线程（active/peak）。

排查时先看 `metrics_line()`：`signalsRejected>0` 通常是授权问题，`broadcastSkipped>0` 说明
对方没订阅那条路径（协议上这是正常的，不是错误）。
