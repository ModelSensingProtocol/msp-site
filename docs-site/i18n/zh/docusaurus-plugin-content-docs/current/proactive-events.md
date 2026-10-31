---
sidebar_label: 主动式事件推送
---

# 主动式事件推送：不需要 Webhook 的推

MCP 的 Events（`events/subscribe` + Webhook URL）在云端是对的：订阅方在防火墙后面，HTTP 是唯一
共同语言。但在同一台机器上，这套形状成本高于收益。

| | MCP Events | MSP |
|---|---|---|
| 订阅怎么建立 | 客户端发 `events/subscribe`，带一个 Webhook URL | 一行 `@node.on("file.**")` |
| 订阅活多久 | 有 TTL，客户端要不断续期 | 跟着连接走；断线自动重连 |
| 谁先发起 | 有向：客户端 → 服务端 | 无向：发布者不知道谁在听 |
| 本机要暴露什么 | HTTPS 端点 | 什么都不用，节点本来就在宣告自己 |
| 拓扑 | Client–Server，AI 在中心 | 网状，AI 只是其中一个节点 |

一句话：**本机进程本来就是平级的，接收事件不该要求你把自己降级成客户端。**

## 三段代码

### 1. 一台普通的本机软件（生产者）

```python
from msp import MSPNode, Preset

watcher = MSPNode("file-watcher", preset=Preset.LOCAL_TOOL)

@watcher.signal_source("file.modified")    # 声明路径 + 提供信号源，一步
def watch_inbox():
    for path in new_files():               # 任意阻塞/长跑逻辑
        yield {"name": path.name, "path": str(path)}

watcher.start()
```

`signal_source` 收的是**生成器**：`yield` 出去的字典会被推走。没有 socket 要开、没有 URL 要注册、
不需要知道有没有人在听。也不用写线程、写回调、管生命周期——**生成器本身就是那根神经末梢**。

### 2. 主动式 Agent（消费者）

```python
ai = MSPNode("ai", preset=Preset.LOCAL_AI)

@ai.on("file.**")                          # * 匹配一段，** 匹配多段
def on_any_file(sig):
    print(sig.path, sig.payload)

ai.start()
```

订阅就是这一行。没有 `events/subscribe`，没有 Webhook，没有 TTL 续期，没有轮询。

### 3. 发现是自动的

两个节点各自 `start()`，共享目录的租约让它们互相看见，`ai` 主动连 `file-watcher`。
**被连的那一方全程不知道谁在连它**——它也不需要知道。

## 跑一遍

<a href="/msp-site/docs/examples/proactive_pubsub.py" download><code>proactive_pubsub.py</code></a>：两个节点、一个临时 inbox，约六秒。

```bash
PYTHONPATH=src python docs-site/static/examples/proactive_pubsub.py
```

隔离环境下的真实输出（`MSP_NODES_DIR` 指向一个空目录）：

```
2. 等发现层把邻居连上（共享目录宣告，零配置）
   ai 看到的邻居：['file-watcher']
   watcher 看到的邻居：['ai']
   ↑ watcher 是被连的那一方：它不需要知道谁在连它

3. 往目录里丢三个文件
  [watcher] 检测到 screenshot-1.png → publish('file.modified')
  [ai] 收到 file.modified：{'name': 'screenshot-1.png', 'size': 6}
  …… 另外两个 ……

4. 结果
   AI 收到 3 条信号
```

**不设** `MSP_NODES_DIR` 时，邻居列表会自己变长：写这段时的那台机器上还出现了
`notchpeninsula` 和一个 DeepSeek Harness 节点——都是真实在跑的软件，零配置被顺带发现并连上。
这一屏比任何论证都硬：零配置发现不是演示效果，是它本来就在做的事。

## 这个 demo 逐行证明了什么

| 论断 | 证据 |
|---|---|
| 不需要注册 Webhook | 全程没有出现过一个 URL |
| 不需要 TTL 续期 | 唯一的订阅是 `@ai.on("file.**")`，之后没再发过一个包 |
| 不是"有向的" | `watcher` 从头到尾不知道谁收到了信号 |
| 网状、对等 | 两个节点跑同一段代码，只有 preset 不同 |
| 推，不是轮询 | 信号由 watcher 发出，不是 AI 去问 |

## 两个 Windows 注意点

1. 控制台默认 GBK：中文和框线字符会乱码。开头加
   `sys.stdout.reconfigure(encoding="utf-8")`（示例里已经加了）。
2. `node.connections` 是**方法**不是属性：`node.connections()`。

## 什么时候仍然该用 MCP Events

跨公网、要穿防火墙、对端只肯暴露 HTTPS——那时 Client–Server 的形状是对的，MCP 是正确选择。
MSP 补的是另一半：**同一台机器上、彼此都在宣告自己的那些进程。**

## 相关

- [信号：推送，以及它的代价(pathname:///msp-site/docs/zh/signals/) —— `signal_source` 与 `on()` 背后的机制
- [节点与 preset(pathname:///msp-site/docs/zh/library/node-and-preset/) —— 为什么生产者永远不会知道谁在听
- [`spec/patterns/publish-subscribe.md`](pathname:///msp-site/docs/spec/patterns/publish-subscribe/) ——
  规范性描述
