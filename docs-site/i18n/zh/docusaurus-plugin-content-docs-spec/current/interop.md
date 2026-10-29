# MSP 规范 — 互操作：MCP ⊆ MSP、`msp.mcp` 适配层、JSON-RPC 2.0 语义对齐

| | |
|---|---|
| **协议修订** | `2026-10-10` |
| **状态** | ✅ **已实现（stdio + tools + Streamable HTTP 载体）** — 适配层源码可验证；Streamable HTTP 的 `GET` SSE 长流与 resources / prompts / sampling 为 🔵 |
| **上游依据** | [../whitepaper.md](https://github.com/hxh230802/MSP/blob/master/docs/whitepaper.md) §5、[../DESIGN.md](/design)「与 JSON-RPC 2.0 的关系」 |
| **本页定义** | MCP 行为到 MSP 的映射结论与边界、`msp.mcp` 适配层的真实签名与语义、JSON-RPC 2.0 语义对齐与错误码转换、可选 codec 桥（🔵）、A2A 与 Streamable HTTP 的指针 |

本页把「MCP ⊆ MSP」从结论落成可核对的映射表与可运行的代码契约。✅ 的条文与 `src/msp/mcp/` 逐字一致；🔵 的条文**实现者可以不实现，但一旦实现必须符合条文**。

## 1. 概述

MSP 与 MCP 的关系有三层：**语义**上，MCP 在工具调用场景下的行为可被行为保持地映射进 MSP，反之不然（§2）；**代码**上，`msp.mcp` 提供 client / server / 桥接三个组件，不进入核心层（§3.1、§4）；**线格式**上，MSP 编码层**不**采用 JSON-RPC 信封，只在工具调用子集上做语义对齐，互通靠可选桥（§2 的「Signal ↔ JSON-RPC 映射表」、§3.3）。

三条边界先声明：① **映射不是价值判断**——「MCP 是 MSP 的子集」只等价于「MSP 提供了一个能兼容 MCP 语义的更一般框架」，二者互补而非对立（[../whitepaper.md](https://github.com/hxh230802/MSP/blob/master/docs/whitepaper.md) §5.1）；② **互操作面是工具调用子集**——参考实现只覆盖 tools 能力（`initialize` / `tools/list` / `tools/call`），其余**方法**为 🔵（§9）；**传输**已有 stdio 与 Streamable HTTP 两种载体；③ **适配层不进入核心**——全部 MCP 相关代码收在 `src/msp/mcp/` 包内，核心层不认识任何 MCP 概念（[../src/msp/mcp/__init__.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/__init__.py)）。

## 2. 映射与契约

### MCP ⊆ MSP

| MCP | MSP | 状态 |
|---|---|---|
| 握手（`initialize` + 能力交换） | `hello` / `ack` + `Manifest`（[base-protocol](base-protocol.md) §4.2、§4.4） | ✅ |
| `notifications/initialized` | 无对应；握手即完成，`hello`/`ack` 已交换清单（由适配层吸收） | ✅ |
| `tools/call` | `msp/request-reply` 的 `tool_call` / `tool_result`（[patterns/request-reply](patterns/request-reply.md)） | ✅ |
| `tools/list` | 无对应；工具住在 `Manifest.tools`，握手 + `manifest_update` 即完成「列出」 | ✅ |
| `ping` | `ping` / `pong`（形状相同，触发机制不同，见 §2 的「JSON-RPC 2.0 语义对齐」） | ✅（适配层翻译） |
| `resources/list` | 无对应；`Manifest.resources` 即列表 | 🔵（[capabilities](capabilities.md) §2.2） |
| `resources/read` | `resource_read` → `resource_content` | 🔵 |
| `resources/subscribe` / `unsubscribe` + `notifications/resources/updated` | `resource_subscribe` / `resource_unsubscribe` → `resource_updated` | 🔵 |
| `resources/templates/list` | 无对应（`ResourceDescriptor` 无模板字段） | 🔵 缺口 |
| `prompts/list` | 无对应；`Manifest.prompts` 即列表 | 🔵 |
| `prompts/get` | `prompt_get` → `prompt_content` | 🔵 |
| `sampling/createMessage` | `sampling_request` → `sampling_result`（反向） | 🔵 |
| `elicitation/create` | `elicitation_request` → `elicitation_result`（反向） | 🔵 |
| `roots/list` + `notifications/roots/list_changed` | `roots_list` → `roots`；`roots_changed` | 🔵 |
| `notifications/cancelled` / `notifications/progress` | `cancel` / `progress`（[base-protocol](base-protocol.md) §6.3–6.4） | 🔵 |
| `logging/setLevel`、`completion/complete` | 无对应 | — |
| **（无对应）** | 发布—订阅 `msp/publish-subscribe`：任意节点广播任意主题，接收方本地通配过滤 | ✅ |
| **（无对应）** | 可扩展模式 `msp/multi-round` / `msp/task`；`manifest_update` 驱动的清单动态演进；节点对等（不预设 client / server 角色，任一方都可主动发起） | ✅ |

条文：映射**必须**行为保持——映射后的 MSP 交互在可达状态、结果与错误语义上与 MCP 原交互一致；实现**不得**要求对端先支持 MSP 扩展语义才能互通工具调用，互通的最低公分母是 TCP + `Signal` 信封 + `msp/request-reply`（[README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §7）。

### 映射不是满射（这不是价值判断）

**MCP 的行为都能在 MSP 中表达，反之不然。** 表末两行（发布—订阅、可扩展模式与节点对等）在 MCP 中没有对等物，因此映射不是满射。

**这不是价值判断。** 它只说明 MSP 是一个更一般的框架，MCP 语义是它的一个子集；反过来，MCP 在生态成熟度、SDK 覆盖与「模型宿主」这一角色上有 MSP 不试图取代的位置——`msp.mcp` 的存在正是为了**包含**而不是**替代**（[../whitepaper.md](https://github.com/hxh230802/MSP/blob/master/docs/whitepaper.md) §5.5 第 2 条）。

### JSON-RPC 2.0 语义对齐

**结论：MSP 在编码层不采用 JSON-RPC 信封，但在「工具调用」这一子集上做 JSON-RPC 2.0 语义对齐；互通靠可选的 `Signal ↔ JSON-RPC` 桥，不改核心。**（[../DESIGN.md](/design)「与 JSON-RPC 2.0 的关系」）

| MSP `Signal` | JSON-RPC 2.0 |
|---|---|
| `reqid` | `id` |
| `payload.tool` | `method` |
| `payload.args` | `params` |
| `payload.content` / `payload.structuredContent` | `result` |
| `payload.error` | `error.message`（`error.code` 取约定值，如内部错误 `-32603`）；**注意**：MCP 把「未知工具」放在**协议错误**通道、其规范示例用 `-32602`，而 MSP 把工具失败一律放进 `payload.error`（错误即值，核心从不发码）——两者在这一类上的**通道**不同，见 §9 G10 |
| `type: "tool_call"` | request（有 `id`） |
| `type: "tool_result"` | response |

**不全面采用信封的两个理由**：① **信封不匹配**——`pattern` / `path` / `source` / `target` 是 MSP 的一等公民（[base-protocol](base-protocol.md) §2.1 把它们定义为顶层字段）：`pattern` 是模式路由键、`path` 是发布—订阅的逻辑地址、`source` / `target` 是节点寻址；压进 `method` / `params` 会丢语义或绕弯，`method` 是单字符串，承载不了「路由键 + 工具名」两个维度。② **迁移成本高而收益窄**——全面迁移要改 `_encode` / `_decode`、`Signal`、所有模式的 `on_signal`，破坏「Everything is a signal」的统一性，而收益只覆盖约 **20%** 的消息。

**方向不是理由。** JSON-RPC 2.0 定义的是**单条消息的形状**（请求 / 响应 / 通知），本身**不**限制哪一方发起；MCP 就用它做双向通信，包括服务端反向请求（`sampling/createMessage`、`elicitation/create`、`roots/list`）。因此「MSP 是全双工、JSON-RPC 是单向」这个说法是**错误**的：MSP 与它的差别在**信封里的字段**，不在方向。

**超出 JSON-RPC 范围的部分**：`signal`（JSON-RPC 无发布—订阅语义，MCP 的通知是协议固定的几类事件，应用**不得**自行定义「课表变更时通知我」这类主题）；`input_required` / `input_response`（被调方在**同一次调用的 `reqid` 内**追问，见 [patterns/multi-round](patterns/multi-round.md)——MCP 的 `elicitation` 能达到类似效果，但它是**另起**一次反向请求，**不延续**原调用的请求标识）；`hello` / `ack`（携带 `Manifest` 的能力交换）；`manifest_update`（无「对端能力变更」语义）；`ping` / `pong`（MSP 的心跳是**周期性**探活 + 失联判定，见 [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.6 的 `heartbeat_interval` / `heartbeat_timeout`；MCP 也有 `ping` 请求，形状相同但触发机制不同，两者由适配层各自翻译）。

### Signal ↔ JSON-RPC 映射表

上表是语义对齐；若要做**线格式**转换（§3.3 的桥），逐字段规则如下：

| MSP 字段 | JSON-RPC 2.0 字段 | 转换规则 |
|---|---|---|
| 信封 `type = "tool_call"` | 有 `id` 的对象 | 生成 `{"jsonrpc":"2.0","id":…,"method":…,"params":…}` |
| 信封 `type = "tool_result"` | 有 `id` + `result` 的对象 | 生成 `{"jsonrpc":"2.0","id":…,"result":…}` |
| 信封 `reqid` | `id` | **必须**一一对应。MSP 侧 `reqid` 是字符串，JSON-RPC `id` **可以**是数字，故反向映射**必须**规范化为字符串（`str(id)`），否则 MSP 的 `pending_calls` 关联会失配 |
| `payload.tool` | `method` | 逐字搬运 |
| `payload.args` | `params` | 逐字搬运；`args` 为 `{}` 时**可以**省略 `params` |
| `payload.content` + `payload.structuredContent` | `result` | 一起放进 `result`；映射为 MCP 的 CallToolResult 时 `content` ↔ `result.content`、`structuredContent` ↔ `result.structuredContent` |
| `payload.error`（字符串） | `result.isError = true` | **不得**映射为 JSON-RPC `error` 对象：MCP 的工具执行失败是**成功响应里的 `isError`**（见 §3.1 `MCPServer._run_tool`） |
| `type = "error"` 的 `payload.code` / `payload.message` | `error.code` / `error.message` | 两边取值同源于 JSON-RPC 约定值，**必须**原样搬运（§6） |
| 信封 `pattern` / `path` / `source` / `target` / `timestamp` | 无对应 | 降级策略见 §3.3 |

### A2A 映射（指针）

A2A 的详细映射在 [patterns/task](patterns/task.md#9-与-a2a-的等价映射)，本页只固定一个契约：**Agent Card 由 `Manifest.pattern_metadata["msp/task"]` 按需投影而成**。写入路径是 `MSPNode.register_pattern("msp/task", metadata=agent_card)` → `Manifest.set_pattern_metadata()` 把模式 ID 追加进 `patterns`、把 `metadata` 存进 `pattern_metadata["msp/task"]` 并递增 `version`（[../src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py)）；序列化键为 `patternMetadata`，随 `hello` / `ack` / `manifest_update` 传播，`Manifest` 核心**不**感知、**不**校验其格式。投影是**消费方**的行为，**不得**要求所有节点都理解 A2A；不认识该键的实现按宽容读取忽略它（[base-protocol](base-protocol.md) §2.3）。

## 3. 报文

### 3.1 `msp.mcp` 适配层：真实签名

包导出面（[../src/msp/mcp/__init__.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/__init__.py) 的 `__all__`）：`MCPClient` / `MCPError` / `MCPServer` / `mount_mcp_tools` / `PROTOCOL_VERSION` / `StdioConnection` / `spawn` / `current_stdio`。

| 组件 | 真实签名 / 行为 |
|---|---|
| `MCPClient(conn)` | `conn` 只需实现 `send(bytes)` / `receive() -> bytes` / `close()`（[../src/msp/transport/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/base.py) 的 `Connection`），不关心底层是 stdio 还是未来的 Streamable HTTP。属性：`protocol_version`、`server_info`、`capabilities`；模块常量 `PROTOCOL_VERSION = "2025-11-25"` |
| `.initialize()` | `-> dict`。发 `initialize`，`params = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "msp", "version": __version__}}`；保存 `protocolVersion` / `serverInfo` / `capabilities`；随后发**通知** `notifications/initialized`；返回原始 result |
| `.list_tools()` | `-> list`。发 `tools/list`（`params = {}`），返回 `result["tools"]`（缺失则 `[]`）；未初始化时先自动 `initialize()` |
| `.call_tool(name, arguments)` | `-> dict`。发 `tools/call`，`params = {"name": name, "arguments": arguments or {}}`；返回**完整** result（`{content, structuredContent?, isError?}`），不预先解包 |
| `.close()` | `-> None`。关闭底层连接（stdio 下终止子进程），异常被吞掉 |
| 关联方式与错误 | `_request()` 持一把锁**串行化**发送，`reqid = self._counter`（整数，从 `0` 开始自增）；读循环中 `id` 不匹配的消息**直接忽略**（`continue`）。result 里出现 `error` 时抛 `MCPError(code, message, data=None)`，`str(e)` 形如 `MCP 错误 [-32601]: …` |
| `MCPServer(node, conn)` | `node` 是 `MSPNode`，`conn` 是 `Connection`；`run() -> None` 顺序读循环：读一行 → `jsonrpc.decode` → 分发 → 回一行，`ConnectionClosed` 即退出；工具在工作线程执行，慢工具不阻塞读循环 |
| `MCPServer` 分发表 | `initialize`（请求）→ `{"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": {"name": "msp", "version": __version__}}` 并置 `_initialized`；`notifications/initialized`、`ping`（请求）→ 分别置标志 / 回 `{}`；`tools/list` → `{"tools": [...]}`（每项 `{name, inputSchema}`，`description` 非空时附加）；`tools/call` → 工作线程执行 `node.protocol._tools[name](**args)` 并回 CallToolResult；其它方法的**请求**回 `error`（`-32601`，`"未知方法: <method>"`），其它**通知**静默忽略；无法解析的行回 `error`（`-32700`，`"Parse error"`，`id = null`） |
| 工具结果转换 | 复用核心 `_normalize_tool_result()`：`{"sum": 3}` → `result.content = [{"type":"text","text":"{\"sum\": 3}"}]` **且** `structuredContent = {"sum": 3}`；`[{"type":"text","text":"hello"}]` → `content` 原样、**无** `structuredContent`；`[1, 2, 3]` → `content = [{"type":"text","text":"[1, 2, 3]"}]`、**无** `structuredContent`（因为它不是 `dict`）；工具抛异常（含未知工具）→ `result = {"content": [{"type":"text","text": <异常文本>}], "isError": true}`——**是成功响应，不是 JSON-RPC error** |
| `mount_mcp_tools(node, client)` | `-> list`，返回挂载成功的工具名（按 `client.list_tools()` 顺序）。逐个 `node.tool(name, description=…, input_schema=…)(stub)`，因此远端工具**必须**出现在本节点 `Manifest.tools` 里；`t["name"]` 直接下标取值（缺失会 `KeyError`），`description` / `inputSchema` 缺失时取 `""` / `{}`。stub 用 `client.call_tool(tool_name, kwargs)` **逐字透传**参数名（本地只做声明不做校验）；`isError` 为真 → 抛 `ToolError(<content 里 text 块按 "\n" 拼接> or "MCP 工具执行失败")`，否则 `structuredContent` 非 `None` 时返回它、否则返回 `content` 列表。**不**关闭 `client`，生命周期由调用方负责 |
| `spawn(command, args=None, env=None)` | `-> StdioConnection`。`command` 传 list / tuple 时原样作 argv（推荐，避免 shell 解析），传字符串时与 `args` 拼成 `[command, *args]`；`subprocess.Popen(argv, stdin=PIPE, stdout=PIPE, env=env)`——**stderr 未重定向**，子进程 stderr 直接继承父进程；`env=None` 继承父进程环境 |
| `StdioConnection(reader, writer, proc=None)` | 帧格式**换行分隔**：`send(data)` 写 `data + b"\n"` 后 `flush()`；`receive()` 读一行并 `rstrip(b"\r\n")`。`close()` 幂等：`proc` 存活时先 `terminate()`、等 `2.0` s，未退出则 `kill()` 再等 `2.0` s，随后依次关 `writer`、`reader`；已关闭或 `OSError` / `ValueError` 时 `send` / `receive` 抛 `ConnectionClosed` |
| `current_stdio()` | `-> StdioConnection`。把**当前进程**的 `sys.stdin.buffer` / `sys.stdout.buffer` 包成连接（`proc=None`，`close()` 只关流、不杀进程），用于「MSP 节点被外部 MCP client 以子进程拉起」 |
| `jsonrpc.py` | `PARSE_ERROR` / `INVALID_REQUEST` / `METHOD_NOT_FOUND` / `INVALID_PARAMS` / `INTERNAL_ERROR` = `-32700` / `-32600` / `-32601` / `-32602` / `-32603`；`encode(obj) -> bytes` 用紧凑分隔符 + `ensure_ascii=False`；`decode(data) -> dict` 只做 `json.loads`，**不校验** `jsonrpc` 成员与消息形状；`make_request(reqid, method, params=None)`（`params` 非 `None` 才附加）、`make_result(reqid, result)`、`make_error(reqid, code, message, data=None)`、`make_notification(method, params=None)`（无 `id`） |

条文：`MCPClient` **必须**在 `tools/call` / `tools/list` 之前完成 `initialize`（参考实现由 `_ensure_initialized()` 自动补做），并**不得**被假设为能应答 MCP server 发起的反向请求（参考实现会静默忽略，见 §9 缺口 G2）；`MCPServer` 的工具失败**必须**用 `result.isError = true` 表达、**不得**回 JSON-RPC `error`，成功时**应当**省略 `isError`；`spawn` 传 list / tuple 时**必须**原样作 argv，**不得**再做 shell 解析。

### 3.2 可运行示例

与 [../../README.zh-CN.md](https://github.com/hxh230802/MSP/blob/master/README.zh-CN.md) 的「MCP 互操作（adapter）」小节一致：

```python
from msp import MSPNode
from msp.mcp import MCPClient, spawn, mount_mcp_tools

# MSP → MCP：调用本地 MCP server（stdio 子进程）
client = MCPClient(spawn(["npx", "-y", "@modelcontextprotocol/server-filesystem"]))
print(client.list_tools())
print(client.call_tool("read_file", {"path": "/tmp/a.txt"}))

# 桥接：把上面这个 MCP server 的工具挂到本节点，其它 MSP 节点即可调用
node_a = MSPNode("node_a")
mount_mcp_tools(node_a, client)
node_b.call("node_a", "read_file", {"path": "/tmp/a.txt"})

# MCP → MSP：把 node 作为 MCP server 跑起来，外部 MCP client 用 stdio 拉起本进程
#   from msp.mcp import MCPServer, current_stdio
#   MCPServer(node, current_stdio()).run()
```

### 3.3 可选 codec 桥的设计（🔵）

**定位**：桥挂在 **transport 之上**，与 transport 一样可插拔，**不改 core**（[../DESIGN.md](/design)「互通的钩子：可选 codec 桥」）。实现形态是包装 `Connection` 的装饰器：`send()` 把 MSP `Signal` 的 JSON 字节翻成 JSON-RPC 字节，`receive()` 反向翻译；核心的 `Signal`、`_encode` / `_decode`、各模式的 `on_signal` 一行不改。

**转换规则**：按 §2 的「Signal ↔ JSON-RPC 映射表」逐字段搬运。强制条文：① `reqid` ↔ `id` **必须**一一对应，JSON-RPC `id` 不是字符串时**必须**规范化为字符串再填入 `reqid`；② `payload.tool` ↔ `method`、`payload.args` ↔ `params` **必须**逐字搬运，**不得**重命名或包裹；③ `payload.content` / `payload.structuredContent` ↔ `result` **必须**保结构搬运；④ `jsonrpc` 成员**必须**由桥生成（`"2.0"`），收到的消息缺少或值不为 `"2.0"` 时**应当**记日志但**不得**丢弃报文（[base-protocol](base-protocol.md) §2.3）。

**无对应字段的降级策略**：`pattern` / `path` / `source` / `target` / `timestamp` 在 JSON-RPC 信封里没有位置。桥**必须**把它们放进 JSON-RPC 消息的**顶层成员 `_msp`**（一个对象），**不得**混进 `params`——`params` 与业务参数一一对应，混入会污染工具实参。对端若严格拒绝未知顶层成员，桥**可以**配置为丢弃 `_msp`；丢弃时 `source` / `target` **应当**由连接身份推断，`pattern` **应当**取核心模式 `msp/request-reply`，并**必须**在桥的配置中显式开启该模式。无法映射的**消息类型**（`signal`、`manifest_update`、`input_required` / `input_response`、以及 [capabilities](capabilities.md) 定义的能力面信号）：桥**必须**丢弃、**必须**在计数器里记录、**不得**伪造 `method` 把它们塞进 JSON-RPC；丢弃是**静默**的（不产生任何字节），因为 JSON-RPC 侧没有可回的错误对象。例外：MCP 侧确实存在的对等物**应当**映射——`notifications/cancelled` ↔ `cancel`、`notifications/progress` ↔ `progress`、`notifications/resources/updated` ↔ `resource_updated`、`notifications/roots/list_changed` ↔ `roots_changed`（后两者依赖 [capabilities](capabilities.md) 落地）。

**错误映射**：MSP → JSON-RPC 时，`error` 信号的 `payload.code` / `payload.message` → `error.code` / `error.message`，`payload.data`（若有）→ `error.data`；`tool_result.payload.error` 非空 → **`result` + `isError: true`**（与 `MCPServer._run_tool` 一致），**不得**映射为 `error` 对象。JSON-RPC → MSP 时，`error.code` ∈ `-32000` ~ `-32099` **必须**原样透传、**不得**改写为 `-32603`；`error.data` **可以**放入 `error.payload.data`，接收方**应当**忽略该未知字段。

**测试方法**（可运行，复用现成设施）：① 进程内管道——`tests/test_mcp.py` 的 `_pipe_pair()` 造两条单向管道拼成全双工，桥包在中间即可直接断言字节；② 子进程假对端——`spawn([sys.executable, "-c", script])` 拉起只做 JSON-RPC 回声的脚本（`test_spawn_echo_roundtrip` 即此模式）；③ 往返不变量——对 `tool_call` / `tool_result` / `error` 断言 `decode(encode(bridge(x))) == x`（字段逐字相等）；④ 丢弃不变量——对 `signal` / `manifest_update` 断言「无字节 + 计数器 +1」；⑤ 不回归——关掉桥时行为与现状逐字一致。

## 4. 消息流

### MSP 节点 ←→ `MCPServer` ←→ 外部 MCP client

```text
 外部 MCP client                 子进程（MSP 节点）              MSP 网络
   │ spawn([python, "-c", …]) ──▶ │ ← 由 client 拉起
   │ ─ initialize ──────────────▶ │ MCPServer._initialize()
   │ ◀ {protocolVersion,          │
   │    capabilities:{tools:{}},  │
   │    serverInfo:{name:"msp"}}  │
   │ ─ notifications/initialized▶ │ 置 _initialized
   │ ─ tools/list ──────────────▶ │ _list_tools()
   │ ◀ {tools:[{name,inputSchema,…}]} ← 翻译 node.manifest.tools
   │ ─ tools/call ──────────────▶ │ 工作线程 _run_tool()
   │   {name, arguments}          │ func(**args) + _normalize_tool_result()
   │ ◀ {content:[…],              │
   │    structuredContent?:{…}}   │
   │  工具抛异常时：               │
   │ ◀ {content:[{type:text,…}],  │ result.isError = true
   │    isError:true}             │ （不是 JSON-RPC error）
```

### `mount_mcp_tools` 的桥接路径

```text
 MSP 节点 B            MSP 节点 A                    MCP server（子进程）
   │                     │ mount_mcp_tools(A, client)    │
   │                     │ ├ client.list_tools() ──────▶ │
   │                     │ │ ◀── tools:[{name,…}]        │
   │                     │ └ node.tool(name)(stub)       │
   │                     │    写入 A.manifest.tools      │
   │ 发现 A（目录/直连）  │                               │
   │ ─ tool_call ───────▶│ A 的核心 request-reply 路径    │
   │   {tool:"read_file"}│ stub(**kwargs)                │
   │                     │ └ client.call_tool() ───────▶ │ tools/call
   │                     │    ◀── {content, …}           │
   │ ◀ tool_result ──────│ structuredContent 优先，       │
   │   {content,structured} 否则回 content 块列表；       │
   │                     │ isError → ToolError → payload.error
```

要点：桥接**没有**新增 MSP 侧的任何信号类型或路径——远端工具就是一个普通的 MSP 工具，`B` 完全不需要知道它背后是 MCP。

### codec 桥的位置（🔵）

```text
 MSPProtocol ── Signal ──▶ _encode() ──▶ [ codec 桥 ] ──▶ Connection ──▶ 线
                                            send: Signal JSON → JSON-RPC JSON
                                            recv: JSON-RPC JSON → Signal JSON
                                            无对应字段 → 顶层 _msp
                                            无对应类型 → 丢弃 + 计数
```

## 5. 数据类型

### 5.1 MCP 侧（逐字取自源码与 MCP 既定字段名）

request = `{"jsonrpc": "2.0", "id": <int | str>, "method": <str>, "params"?: <object>}`；result = `{"jsonrpc": "2.0", "id": …, "result": <any>}`；error = `{"jsonrpc": "2.0", "id": …, "error": {"code": <int>, "message": <str>, "data"?: <any>}}`；notification = `{"jsonrpc": "2.0", "method": <str>, "params"?: <object>}`（无 `id`）。

| 名字 | 形态 |
|---|---|
| 工具描述 | `{"name": <str>, "inputSchema": <object>, "description"?: <str>}` |
| CallToolResult | `{"content": [<ContentBlock>], "structuredContent"?: <object>, "isError"?: <bool>}` |
| `initialize` 结果 | `{"protocolVersion", "capabilities": {"tools": {}}, "serverInfo": {"name", "version"}}` |
| `initialize` 参数 | `{"protocolVersion", "capabilities": {}, "clientInfo": {"name": "msp", "version": "0.1.0"}}` |

### 5.2 MSP 侧

`Signal` 信封为 snake_case（`type` / `source` / `pattern` / `target` / `path` / `reqid` / `payload` / `timestamp`），字段级条文见 [base-protocol](base-protocol.md) §2；`payload` 内部多为 camelCase（如 `structuredContent`）。本次涉及的 JSON 形态：`ToolDescriptor` = `{"name", "description", "inputSchema", "outputTypes", "annotations"}`；`Manifest` = `{"version", "patterns", "patternMetadata", "capabilities", "signals", "tools", "resources", "prompts", "clientCapabilities": {"sampling", "elicitation", "roots"}}`；内容块见 [../src/msp/core/content.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) 的 `text` / `image` / `audio` / `resource` / `resource_link` / `blob_ref`。

### 5.3 传输侧互通：Streamable HTTP（✅ 载体 / 🔵 SSE 长流）

MCP 的另一种传输。**载体已实现**（`src/msp/mcp/http.py`，客户端与服务端两个方向），下表条文中除 **`GET` 的 SSE 长流**外均已落地：

| 项 | 条文 |
|---|---|
| 端点 | 单一 HTTP 端点（如 `/mcp`），**不得**要求多个路径区分操作 |
| 请求 | `POST` 承载**一条** JSON-RPC 消息；`Accept` **必须**同时包含 `application/json` 与 `text/event-stream` |
| 响应 | `Content-Type: application/json` 回单条响应，或 `text/event-stream`（SSE）承载该请求的响应**以及**后续 server→client 消息 |
| 会话 | `initialize` 响应**可以**带 `Mcp-Session-Id`；后续请求**必须**回填该头；`DELETE` 终止会话；`GET` **可以**打开一条只承载 server→client 消息的 SSE 流 |
| 版本与认证 | 请求**应当**带 `MCP-Protocol-Version` 头；需要鉴权时回 `401`，由 MCP 的 OAuth 流程处理——**不得**把 HTTP 认证等同于 MSP 的授权（[security](security.md)） |

接入 MSP 的真实障碍（如实记录）：`Connection`（[../src/msp/transport/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/base.py)）是「一次 `send(bytes)` ↔ 一次 `receive() -> bytes`」的**单条消息**抽象，而 Streamable HTTP 的一次 `POST` 可能返回 SSE 多帧、且 server→client 消息可以在另一条 `GET` 流上独立到达。

**已落地的部分**（[../src/msp/mcp/http.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/http.py)）：单一端点；一次 `POST` 承载一条消息；`Accept` 同时声明 `application/json` 与 `text/event-stream`；回填 `Mcp-Session-Id` 与 `MCP-Protocol-Version`；`DELETE` 终止会话；请求体有 16 MiB 上限与总读时限（只靠 socket 级超时拦不住「无限慢」的发送者）。

**有意不做的部分**：`GET` 的 SSE 长流——即 server→client 主动消息。其**前置条件**是「按 JSON-RPC `id` 分派的接收抽象」（读线程 + pending 表），或 `Connection` 之上的多路复用抽象，而本适配层的收发模型撑不起它。因此 `GET` 明确回 **`405 + Allow: POST, DELETE`**——拒绝得清楚，而不是假装接受后不给消息；`POST` 响应里若出现承载**本次响应之外**的 SSE 帧，只取本次响应那一帧，其余丢弃并计数（`dropped_sse_frames`）。

**不得**为接入该传输而改动 `Signal` 信封或核心路由。§9 的 G4 现已缩小为「`GET` 的 SSE 长流未实现」。

## 6. 错误处理

### 6.1 两套错误空间与转换规则

MSP 侧是 `error` 信号的 `payload.code` / `payload.message`，工具失败走 `tool_result.payload.error`（[base-protocol](base-protocol.md) §6.1–6.2）；MCP / JSON-RPC 侧是 `{"error": {"code", "message", "data"?}}`，工具失败走 `result.isError = true`（§3.1）。两者**同源**：MSP 的错误码直接取 JSON-RPC 的约定值（[README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.4），因此 `-32600` / `-32601` / `-32602` / `-32603` 作为**数值**在两侧同义，转换**必须**原样搬运。**但数值同义不等于通道一致**：MCP 把「未知工具」「请求形状不合法」归入**协议错误**（其规范示例对未知工具用 `-32602`），而 MSP 核心把工具执行失败一律写成 `payload.error` 字符串、从不发码（本页 §3.1 的 `MCPServer` 也把未知工具回成 `result.isError = true`）。实现**不得**假定「MSP 侧不会出现协议错误」或「MCP 侧的工具失败都带 `isError`」；跨桥时**必须**显式决定未知工具走哪条通道并写进实现文档（见 §9 G10）。

| 场景 | 规则 |
|---|---|
| MCP `tools/call` 抛异常 | → `result = {"content": [{"type":"text","text": <异常文本>}], "isError": true}`；**不得**回 JSON-RPC `error`（`MCPServer._run_tool` 的实际行为） |
| MSP `tool_result.payload.error` 非空 | → MCP `result` + `isError: true`（桥在 MSP→MCP 方向时） |
| MSP `error` 信号 ↔ JSON-RPC `error` | `code` / `message` 原样搬运；反向时 `reqid` 回填 `id`；`-32000` ~ `-32099` 原样透传 |
| `MCPClient` 收到 `error` | 抛 `MCPError(code, message, data)`，`data` 原样保留 |
| MSP 未知 `type` | 回 `error`（`-32600`），**不得**断开连接（[base-protocol](base-protocol.md) §2.3） |
| MCP 未知方法 | 请求形式回 `error`（`-32601`，`"未知方法: <method>"`）；通知形式**静默忽略** |
| 无法解析的行 | 回 `error`（`-32700`，`"Parse error"`，`id = null`） |
| `mount_mcp_tools` 的远端失败 | 远端 `isError` → 本地 `ToolError` → MSP 侧 `tool_result.payload.error` |

条文：适配层**不得**吞掉错误——每一个失败**必须**出现在上表的两套空间之一里；**不得**一边回 JSON-RPC `error` 一边又返回部分 `result`。

## 7. 规范条文汇总（MUST/SHOULD 清单）

**必须**：① `MCPClient` 在 `tools/call` / `tools/list` 之前完成 `initialize` 并发送 `notifications/initialized`（§3.1）；② `MCPServer` 的工具失败表达为 `result.isError = true`、**不得**回 JSON-RPC `error`，未知方法的请求回 `-32601`（§3.1、§6.1）；③ `structuredContent` 仅当规范化结果是 `dict`，其余类型留在 `content` 块里（§3.1）；④ `mount_mcp_tools` 挂载的每个远端工具注册进本节点 `Manifest.tools`（§3.1）；⑤ `spawn` 传 list / tuple 时原样作 argv（§3.1）；⑥ `StdioConnection` 按「一行一条消息」成帧：发送追加 `\n` 并 `flush`，接收剥离 `\r\n`（§3.1）；⑦ 错误码原样搬运，`-32000` ~ `-32099` **不得**改写（§2 的「Signal ↔ JSON-RPC 映射表」、§6.1）；⑧ codec 桥把无对应字段放进顶层 `_msp`、**不得**混进 `params`，对无对应的消息类型丢弃并计数、**不得**伪造 `method`（§3.3）；⑨「MCP ⊆ MSP」的映射行为保持，且**不得**把「不满射」表述为价值判断（§2）。

**应当**：⑩ `MCPServer` 成功响应省略 `isError`（§3.1）；⑪ 桥收到 `jsonrpc` 成员缺失或不为 `"2.0"` 时记日志但不丢报文（§3.3）；⑫ Streamable HTTP 请求带 `MCP-Protocol-Version` 头并回填 `Mcp-Session-Id`（§5.3）；⑬ Agent Card 由消费方按需投影，**不得**要求全网理解（§2 的「A2A 映射」）。

**不得**：⑭ 适配层代码进入 `src/msp` 核心模块（§1、§3.1）；⑮ 假设 `MCPClient` 能应答 MCP server 的反向请求（§3.1、§9）；⑯ 用「MSP 是全双工、JSON-RPC 是单向」作为不采用信封的理由——方向不是理由（§2 的「JSON-RPC 2.0 语义对齐」）；⑰ 为接入 Streamable HTTP 改动 `Signal` 信封与核心路由（§5.3）；⑱ `mount_mcp_tools` 替调用方关闭 `client`（§3.1）。

**可以**：⑲ `payload.args` 为 `{}` 时桥省略 `params`（§2 的「Signal ↔ JSON-RPC 映射表」）；⑳ 桥配置为丢弃 `_msp` 以适配严格对端，此时由连接身份推断 `source`/`target` 并给 `pattern` 取 `msp/request-reply`（§3.3）；㉑ `MCPServer` 在工具执行期间继续读循环（参考实现用工作线程做到）（§3.1）；㉒ `call_tool` 返回完整 result 由调用方自行解包（§3.1）。

## 8. 安全考量

1. **MCP server 是外部进程。** `spawn` 执行的是**任意外部命令**：命令与参数**必须**来源于可信配置，**不得**由远端 MSP 对端提供；`env` **应当**最小化，**不得**把本机凭据透传给子进程。参考实现**不**重定向子进程 stderr，因此子进程报错会直接进入父进程 stderr——**不得**在此路径上打印敏感内容。
2. **提示注入经桥传入。** `mount_mcp_tools` 把远端 `content` 原样带回 MSP，最终可能进入模型上下文；消费方**应当**把它标注为外部不可信内容（与 [capabilities](capabilities.md) §8 第 2 条同理）。
3. **授权与自述分离。** `Manifest` 与 `manifest_update` 是自述，适配层**不得**因为对端清单里出现某个工具就跳过本地授权判定（[README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.5、[security](security.md)）。
4. **工具名冲突。** `mount_mcp_tools` 用 `node.tool(name)` 注册，与本地同名工具**会**互相覆盖；实现**应当**提供命名空间前缀或冲突检测，**不得**静默覆盖后仍宣称两套工具都可用。
5. **协议版本。** MCP 自 `2026-07-28` 起改为无状态 per-request envelope（不再有 `initialize`，改用 `server/discover`）；本适配层走经典 `initialize` 握手，故固定使用握手系列的最新版本 `2025-11-25`。**不得**在未实现 `server/discover` 时声称支持 `2026-07-28` 及以后的修订。
6. **Streamable HTTP 的认证面与桥的可观测性。** HTTP `401` / OAuth 解决的是传输身份，**不得**与 MSP 授权混为一谈（§5.3）；静默丢弃 `signal` / `manifest_update` 会造成「消息看上去发出去了」的错觉，桥**必须**暴露计数器或日志，运维侧**应当**监控它。

## 9. 已知缺口

| # | 缺口 | 状态 | 说明 |
|---|---|---|---|
| G1 | 只覆盖 tools 能力（传输已不止 stdio） | 🟡 | 支持的方法就 5 个：`initialize`、`notifications/initialized`、`ping`、`tools/list`、`tools/call`；`resources/*`、`prompts/*`、`sampling/createMessage`、`elicitation/create`、`roots/list`、`logging/setLevel`、`completion/complete`、`resources/templates/list`、`notifications/tools/list_changed` 均未实现，收到即回 `-32601` |
| G2 | `MCPClient` 不能应答 MCP server 发起的反向请求 | 🟡 | `_request()` 忽略 `id` 不匹配的消息，因此 sampling / elicitation / roots 请求会被**静默丢弃**；它也因此**不**上报能力（`initialize` 固定发 `capabilities: {}`） |
| G3 | `MCPServer` 只处理 `notifications/initialized`，其余通知静默忽略 | 🟡 | 无 `notifications/*` 的通用处理 |
| G4 | Streamable HTTP 的 **`GET` SSE 长流**未实现 | 🔵 | **`POST` / `DELETE` 载体已实现**（[../src/msp/mcp/http.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/http.py)），含 `Mcp-Session-Id` 回填与 `MCP-Protocol-Version`；`GET` 明确回 `405 + Allow: POST, DELETE`，响应内多余的 SSE 帧被丢弃并计数（`dropped_sse_frames`）。前置条件仍是「按 JSON-RPC `id` 分派的接收抽象」（§5.3） |
| G5 | `jsonrpc.decode` 不做任何校验 | 🟡 | `json.loads` 后直接使用，不校验 `jsonrpc` 成员、不区分请求 / 响应 / 通知形状；`MCPServer` 依赖 `"id" in msg` 判断是否为请求 |
| G6 | `mount_mcp_tools` 无命名空间与冲突检测 | 🟡 | 与本地同名工具互相覆盖（§8 第 4 条） |
| G7 | 无 codec 桥 | 🔵 | `Signal ↔ JSON-RPC` 的线格式转换尚未实现（§3.3 已完整定义）；当前互通完全依赖 `msp.mcp` 适配层 |
| G8 | `MCPClient` 无超时参数 | 🟡 | `_request()` 阻塞在 `receive()` 上，没有超时，对端不响应会永久阻塞（MSP 侧的 `call(timeout=5.0)` 不适用于此路径） |
| G9 | `resources` / `prompts` / `sampling` 无 MCP 转换器；A2A 侧只提供指针 | 🔵 / ✅ | [capabilities](capabilities.md) 定义了 MSP 侧信号但 `msp.mcp` 不翻译它们（G1 的另一面）；Agent Card 投影与 `msp/task` 的完整映射在 [patterns/task](patterns/task.md)，该页尚未落地时以本页 §2 的「A2A 映射」契约为准 |
| G10 | 「未知工具」的**错误通道**与 MCP 不一致 | 🟡 | MCP 把「未知工具」「请求不满足 CallToolRequest schema」归入**协议错误**（JSON-RPC `error`；MSP 具备的 MCP 规范示例对未知工具用 `-32602`），而 MSP 核心把工具失败一律写成 `tool_result.payload.error`、**从不发码**，本页 §3.1 的 `MCPServer` 也把未知工具回成 `result.isError = true`。因此「错误码原样搬运」只覆盖**数值同义**，不覆盖通道选择：跨桥实现**必须**显式决定未知工具走哪条通道并在文档中说明，**不得**假定两侧一致（§2 的映射表、§6.1） |
| G11 | MCP 工具名字符集宽于 MSP | 🟡 | MCP 建议工具名为 1–128 字符、区分大小写、允许 `A-Za-z0-9_-.`（均为 `SHOULD`）；MSP 的[命名规范](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#53-命名规范)把工具名限定为 `[a-z0-9_-]+`（**必须**，无大写、无点号）。`mount_mcp_tools` 逐字使用远端 `name` 注册，因此挂载 `getUser` / `admin.tools.list` 这类工具会产出**违反 MSP 自身文法**的本地工具名——本地字典查表仍能命中，但清单与其他实现无法按规范解析。实现**应当**做名映射（统一小写、`.` → `_` 等）或拒绝并在文档中说明，**不得**静默注册违规名 |

## 10. 参考实现映射

| 条文 | 状态 | 源码文件与符号 |
|---|---|---|
| §3.1 `MCPClient` 全部签名 | ✅ | [../src/msp/mcp/client.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/client.py) `MCPClient` / `.initialize` / `.list_tools` / `.call_tool` / `.close` / `._request` / `._notify` / `._ensure_initialized`；`MCPError`；`PROTOCOL_VERSION` |
| §3.1 `MCPServer` 分发与结果转换 | ✅ | [../src/msp/mcp/server.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/server.py) `MCPServer` / `.run` / `._dispatch` / `._initialize` / `._list_tools` / `._on_tool_call` / `._run_tool` / `._reply` |
| §3.1 工具结果规范化 | ✅ | [../src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `_normalize_tool_result` |
| §3.1 `mount_mcp_tools` | ✅ | [../src/msp/mcp/bridge.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/bridge.py) `mount_mcp_tools` / `_content_text` |
| §3.1 `spawn` / `StdioConnection` / `current_stdio` | ✅ | [../src/msp/mcp/stdio.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/stdio.py) `spawn` / `StdioConnection` / `.send` / `.receive` / `.close` / `current_stdio` |
| §3.1 JSON-RPC 编解码与错误码常量、导出面 | ✅ | [../src/msp/mcp/jsonrpc.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/jsonrpc.py) `encode` / `decode` / `make_request` / `make_result` / `make_error` / `make_notification` 与五个错误码常量；[../src/msp/mcp/__init__.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/__init__.py) `__all__` |
| §3.1 连接抽象 | ✅ | [../src/msp/transport/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/base.py) `Connection` / `ConnectionClosed` |
| §2 的「MCP ⊆ MSP」（握手与清单交换）；MSP 侧工具调用 | ✅ | [../src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `handshake_outbound` / `handshake_inbound` / `push_manifest` / `_on_manifest_update` / `call` / `_on_tool_call` / `_run_tool` / `_on_tool_result` |
| §2 的「A2A 映射」（`patternMetadata` 与 Agent Card） | ✅ | [../src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `Manifest.set_pattern_metadata` / `to_dict`；[../src/msp/core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `MSPNode.register_pattern` |
| §2 的「JSON-RPC 2.0 语义对齐」（错误码同源） | ✅ | [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.4；[base-protocol](base-protocol.md) §6.2；`jsonrpc.py` 的五个常量 |
| §3.3 codec 桥 | 🔵 未实现 | 规划落点为包装 `Connection` 的装饰器，不进入 `src/msp/protocol` 与 `src/msp/core` |
| §5.3 Streamable HTTP | ✅ 载体 / 🔵 SSE 长流 | [../src/msp/mcp/http.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/http.py)（客户端与服务端载体）；`GET` 的 SSE 长流未实现 |
| 行为验证 | ✅ | [../tests/test_mcp.py](https://github.com/hxh230802/MSP/blob/master/tests/test_mcp.py) `StdioConnectionTest` / `MCPInProcessTest` / `MCPSubprocessTest` / `MCPBridgeTest` |

测试已核实的行为（可作为条文的可验证锚点）：`initialize` 返回 `protocolVersion == "2025-11-25"` 且 `capabilities` 含 `tools`；`tools/list` 返回 `add` / `greet` / `nums`；`tools/call` 对 dict 结果给出 `structuredContent`、对内容块列表给出 `content`、对非 dict 结果（`[1, 2, 3]`）**不**给 `structuredContent`、对未知工具给 `isError: true`；子进程端到端 `MCPServer(node, current_stdio()).run()` + `MCPClient(spawn([...]))` 可完成 `initialize` / `tools/list` / `tools/call`；`mount_mcp_tools(a, client)` 返回 `["add"]`，MSP 节点 `b` 可 `b.call("A", "add", {"x": 1, "y": 2}).unwrap() == {"sum": 3}`。
