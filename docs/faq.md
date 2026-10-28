# FAQ 与排查

## 常见问题

### MSP 和 MCP 是什么关系？

不是替代关系，是形状不同：MCP 是 hub-and-spoke 的工具协议，MSP 是网状的对等协议——节点有租约
（存在感）、能主动广播（推送）、能互相直接服务。为什么这决定了本地软件该用哪个，见
[`docs/POSITIONING.zh-CN.md`](https://github.com/hxh230802/MSP/blob/master/docs/POSITIONING.zh-CN.md)。

仓库里的 `mcp/` 是**互操作适配层**：把 MCP server 包成 MSP 节点，而不是让运行时同时说两种协议。

### 为什么不直接用 stdio 的 MCP？

stdio 的生命周期绑在会话上：客户端**拉起**进程，会话结束进程就死；而且拉起的是**第二个实例**，
看不到你屏幕上开着的那个文档。桌面软件要的是"软件活着能力就在"，这一点 stdio 结构上给不了。

### 能给两台机器用吗？

可以，TCP 本来就能跨机。但要自己解决：地址与发现（发现目录是本机的，跨机要么共享目录、要么用
`add_manual_source` / 手动指定对端）、TLS（WebSocket 传输目前**没有** `wss://`，需要反向代理终结
TLS）、以及授权（跨机默认不是"可达即信任"）。

### Windows 上有些用例被跳过

Windows 没有 `AF_UNIX`，`tests/test_uds.py` 的 4 个 UDS 用例会自动 skip——不是失败。

### 同一台机器跑多个节点要注意什么？

- **节点 id 必须互不相同**：id 是连接表的键，两个进程同 id 会在对端眼里变成同一个 peer，后连的
  把先连的踢掉
- 想隔离就各用各的 `nodes_dir`

## 排查表

| 症状 | 先查什么 | 常见原因 |
|---|---|---|
| `neighbors()` 是空的 | 两边 `nodes_dir` 是否同一个目录；目录里有没有对方的 `<id>.json` | 目录不同；id 含非法字符（大写/点号）；声明超过 30 秒没续租 |
| 邻居有，`connections()` 没有 | 对方端口是否可达；防火墙 | 端口被拦；对方已退出但声明还没过期 |
| `call()` 报"未连接/未知节点" | `ensure_connected(peer_id)` 的异常信息 | 名字打错；对方没宣告这个工具 |
| `call()` 超时 | 对方的 `metrics_line()` 里 `dispatched` 有没有涨 | 工具函数卡住（同步阻塞操作）；`timeout` 设太短 |
| 收不到信号 | 发布方的 `metrics_line()`：`broadcastSkipped` | 发布方按 `sub` 授权过滤掉了你；或你订阅的路径模式不匹配 |
| 信号收到一半就没了 | 连接是否重建过 | 信号没有留存，断线期间的发不补 |
| 连接数反复涨跌（`replaced` 在涨） | 两个节点是否用了同一个 id | id 冲突；或两个节点同时反复重连 |
| 同一路径的信号被拒（`signalsRejected`） | 授权表 | 跨机时默认不放行未授权路径 |

## 定位手段（按顺序）

1. **发现层**：`ls ~/.msp/nodes/`，看对方的 `<id>.json` 在不在、时间戳新不新
2. **连接层**：`node.connections()`；对方 `peer_manifest("我")` 能不能看到我
3. **能力层**：`node.peer_manifest("对方")` 里有没有那个工具/信号
4. **计数层**：两边都打印 `metrics_line()`，看是"没发出"还是"没收到"
5. **线上报文**：真需要时，把连接换成本地 socket 抓一次 4 字节长度前缀 + JSON

## 调试时最省事的两条

```python
node = MSPNode("probe", preset=Preset.FULL_PEER)
node.start()
print(node.neighbors(), node.connections())        # 发现 + 连接
print(node.peer_manifest("weather"))               # 对方到底宣告了什么
```

## 还是不通

把这几样一起贴出来，比描述现象有用得多：

- 两边节点的 id、`preset`、`nodes_dir`
- `ls -l <nodes_dir>` 的结果（看声明文件时间戳）
- 两边的 `metrics_line()`
- 操作系统与 Python 版本
