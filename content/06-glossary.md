# 术语表

按在协议里的层次从低到高排。

| 术语 | 英文 | 一句话 | 在哪 |
|---|---|---|---|
| **信号** | signal | 一条带路径的 JSON 报文；8 个顶层字段恒定，未知字段进 `extras` | [`core/signal.py`](../../src/msp/core/signal.py) |
| **分帧** | framing | 4 字节大端长度前缀 + UTF-8 JSON | [`protocol/framing.py`](../../src/msp/protocol/framing.py) |
| **清单** | manifest | 节点宣告自己的工具、信号、能力、模式 | [`core/manifest.py`](../../src/msp/core/manifest.py) |
| **握手** | handshake | `HELLO`（带 manifest）→ `ACK`（带回对方 manifest） | [`protocol/protocol.py`](../../src/msp/protocol/protocol.py) |
| **去重仲裁** | dedup / canonical direction | 两个节点同时拨号时，按 node_id 字典序保留一个方向 | 同上 |
| **工具** | tool | 请求-应答的能力，有名字、描述、输入 schema | [`core/node.py`](../../src/msp/core/node.py) |
| **调用** | call | 调对端工具，返回 `ToolResult`；失败不抛异常 | 同上 |
| **广播** | publish / broadcast | 发一条信号给所有已订阅的对端；发完即忘、无留存 | 同上 |
| **订阅** | subscription | 用路径模式（`*` / `**`）注册本地回调 | [`protocol/matcher.py`](../../src/msp/protocol/matcher.py) |
| **发现** | discovery | 扫描共享目录，把新节点变成可拨的对端 | [`discovery/`](../../src/msp/discovery/) |
| **宣告** | presence | 往共享目录写自己的声明文件并续租 | [`presence/`](../../src/msp/presence/) |
| **租约** | lease | 声明的有效期：30 秒没有续租即视为失联 | 同上 |
| **预置** | preset | 一组能力的打包：发现、宣告、传输、模式、连接策略 | [`core/preset.py`](../../src/msp/core/preset.py) |
| **连接策略** | connect policy | `eager`（发现即连）/ `lazy`（用到才连） | 同上 |
| **稳定** | settle | 等"这次启动触发的建连"落地，只等不发起 | [`core/node.py`](../../src/msp/core/node.py) |
| **模式** | pattern | 可插拔的交互形状：`request-reply` / `publish-subscribe` / `multi-round` / `task` | [`patterns/`](../../src/msp/patterns/) |
| **任务** | task | multi-round 的一种：有队列、有状态、可回查 | [`patterns/task.py`](../../src/msp/patterns/task.py) |
| **授权** | grant | 按 `(对端, 路径模式)` 决定能不能发/收/调；跨机默认不信任 | [`protocol/protocol.py`](../../src/msp/protocol/protocol.py) |
| **本机对端** | local peer | 回环 TCP 或 UDS 连接的对端，默认视为本机 | 同上 |
| **指标** | metrics | 连接 / 信号 / 工具 / 任务线程各维度的计数 | [`core/node.py`](../../src/msp/core/node.py) |
| **适配层** | adapter | 把 MCP server 包成一个 MSP 节点的那一层 | [`mcp/`](../../src/msp/mcp/) |
