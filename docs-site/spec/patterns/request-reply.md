# 核心模式：请求—响应（`msp/request-reply`）

| | |
|---|---|
| **协议修订** | `2026-10-10` |
| **状态** | ✅ 已实现 |
| **本页定义** | 核心通讯模式 `msp/request-reply`：`tool_call` / `tool_result` 的完整载荷字段、`reqid` 关联与并发隔离、调用方与被调方的逐步流程、返回值规范化规则、「错误即值」语义、工具注册与超时语义、错误码归属边界 |

> 本页是 [patterns.md](../patterns.md) 的具体化。模式层契约、路由判定顺序、`PatternHandler` 与本文无关——`msp/request-reply` 是**核心模式**，直接实现在协议层，不进 `PATTERN_REGISTRY`，也没有 Handler 实例。

---

## 1. 概述

`msp/request-reply` 是 MSP 的**最低公分母**：一条 TCP 连接 + `Signal` 信封 + 本模式，两个各自独立实现即可互相调用工具（[README.md §7](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#7-一致性)）。

它的语义一句话：**A 向 B 发一条带 `reqid` 的 `tool_call`，B 在独立线程里执行工具，回一条带同一个 `reqid` 的 `tool_result`；A 靠 `reqid` 从 `pending_calls` 中找回自己的等待者。**

与 JSON-RPC 2.0 的语义对应关系见 [interop.md](../interop.md#json-rpc-20-语义对齐)：

| MSP | JSON-RPC 2.0 |
|---|---|
| `reqid` | `id` |
| `payload.tool` | `method` |
| `payload.args` | `params` |
| `payload.content` / `payload.structuredContent` | `result` |
| `payload.error` | `error.message` |
| `type: "tool_call"` | request |
| `type: "tool_result"` | response |

---

## 2. 契约

### 2.1 `reqid`

| 项 | 规定 |
|---|---|
| 类型 | `str` |
| 生成 | **必须**由**发起方**生成，`Signal.new_reqid()`，即 `uuid.uuid4().hex[:16]`（32 位十六进制取前 16 位） |
| 位置 | `Signal.reqid`（**信封字段**，不是 `payload` 字段） |
| 语义 | 在一对连接上唯一标识一次请求；`tool_result` **必须**回显同一个值 |
| 生命周期 | 发起时登记进 `pending_calls`，收到结果或超时后**必须**注销 |

**必须**满足：

1. `tool_call` **必须**携带非空 `reqid`。被调方收到 `reqid` 为空的 `tool_call` **必须**直接忽略（当前实现即 `return`，见 §11 G1）。
2. `tool_result` **必须**回显 `reqid`。接收方对未知 `reqid` 的 `tool_result` **必须**静默忽略——它不是错误，通常只是「我早已超时放弃」的迟到回包。
3. `reqid` **不得**在 `payload` 内重复出现。

### 2.2 `pending_calls`

协议层用一个受 `threading.Lock` 保护的字典登记未完成的请求：

```python
self.pending_calls: dict[str, tuple[threading.Event, list]] = {}
#                        reqid          (event,        [peer_id, result])
```

**必须**满足：

1. **登记**发生在发包**之前**（否则对端回包可能先于登记到达）。实现的顺序是：生成 `reqid` → 建 `Event` → 加锁写入 `pending_calls[reqid] = (event, [peer_id, None])` → `_send(...)`。
2. 等待者只**可以**通过 `event.wait(timeout)` 阻塞；**不得**轮询 `pending_calls`——那是忙等。
3. **结果写入**由读线程完成（`_on_tool_result`）：加锁取回 `(event, holder)`，写 `holder[1] = ToolResult(...)`，再 `event.set()`。
4. **注销**由等待者完成，且**必须**从字典弹出（`pop`），否则字典无界增长。
5. **并发隔离**：不同 `reqid` 的条目互不影响，因此同一连接上**可以**有任意多个在飞请求；不同线程并发 `call()` 是安全的。
6. `peer_id` 存在 `holder[0]`，用于连接断开时按对端批量唤醒。

### 2.3 结果读取路径

```
tool_result 到达
      │
      ├─ reqid 为空 ─────────────────▶ 忽略
      │
      └─ 加锁查 pending_calls[reqid]
             ├─ 未登记（已超时/已注销）─▶ 忽略
             └─ 命中
                  holder[1] = ToolResult(
                      content    = payload.get("content", []),
                      structured = payload.get("structuredContent"),
                      error      = payload.get("error", ""),
                  )
                  event.set()          ← 唤醒 call()
```

注意 `structuredContent` 的缺省值是 `None`（`dict.get` 的无默认重载），而 `content` / `error` 的缺省分别是 `[]` / `""`。

### 2.4 超时后的清理

`event.wait(timeout)` 返回 `False` 时**必须**：

1. 加锁 `pending_calls.pop(reqid, None)` —— 注销条目，防止迟到回包误唤醒；
2. 抛 `TimeoutError(f"调用 {tool} 超时")`。

`node.call()` 会把该 `TimeoutError` 转换为 `ToolResult(error="调用 <tool> 超时")`（§6）。

---

## 3. 报文

### 3.1 信封字段

两个信号都是标准 `Signal`。`pattern` 字段**必须**为 `null`（核心模式不写路由键），`target` **应当**填对端 `node_id`。

| 字段 | `tool_call` | `tool_result` |
|---|---|---|
| `type` | `"tool_call"` | `"tool_result"` |
| `source` | 调用方 `node_id` | 被调方 `node_id` |
| `target` | 被调方 `node_id` | 调用方 `node_id` |
| `reqid` | **必须**，非空 | **必须**，回显请求值 |
| `payload` | 见 §3.2 | 见 §3.3 |
| `pattern` | `null` | `null` |
| `path` | `null` | `null` |
| `timestamp` | 自动填充 | 自动填充 |

`Signal` 信封字段一律 **snake_case**（`type` / `source` / `pattern` / `target` / `path` / `reqid` / `payload` / `timestamp`）。

### 3.2 `tool_call.payload`

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `tool` | `str` | **必须** | 工具名，**精确匹配**（**不得**用通配符，见 [publish-subscribe.md](publish-subscribe.md#7-边界)）；**必须**符合 `[a-z0-9_-]+` |
| `args` | `object` | **可以** | 关键字参数对象，缺省 `{}`；键名**必须**与工具函数形参名逐字一致 |

```jsonc
// tool_call：调用方 → 被调方
{
  "type": "tool_call",
  "source": "node_b",
  "pattern": null,
  "target": "node_a",
  "path": null,
  "reqid": "9f2c1ab34de5f607",
  "payload": {
    "tool": "get_weather",
    "args": {"location": "Beijing", "days": 3}
  },
  "timestamp": 1791331200.5
}
```

### 3.3 `tool_result.payload`

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `content` | `list` | **应当** | content 块列表。字段名是 **snake_case**（与信封一致），值是 content 块 dict |
| `structuredContent` | `any` | **可以** | 结构化结果。字段名是 **camelCase**（沿用 MCP 命名），与 `Manifest` 的 `inputSchema` / `mimeType` 同风格 |
| `error` | `str` | **可以** | 失败原因，成功时缺省（`_run_tool` 的成功分支**不写**该键；`msp/multi-round` 则写 `""`） |

```jsonc
// 成功（工具返回 dict）
{
  "type": "tool_result",
  "source": "node_a",
  "pattern": null,
  "target": "node_b",
  "path": null,
  "reqid": "9f2c1ab34de5f607",
  "payload": {
    "content": [{"type": "text", "text": "{\"temp\": 22, \"location\": \"Beijing\"}"}],
    "structuredContent": {"temp": 22, "location": "Beijing"}
  },
  "timestamp": 1791331201.1
}

// 失败（未知工具或工具抛异常）
{
  "type": "tool_result",
  "source": "node_a",
  "pattern": null,
  "target": "node_b",
  "path": null,
  "reqid": "9f2c1ab34de5f607",
  "payload": {"content": [], "error": "未知工具: get_wether"},
  "timestamp": 1791331201.1
}
```

**注意**：`structuredContent` 在失败时**不出现**（`_run_tool` 的异常分支只写 `content` 与 `error`）。接收方对其缺省值是 `None`。

### 3.4 content 块类型

`content` 数组的元素**必须**是 §5.2 列出的块之一。未知 `type` 的块**必须**原样保留（宽容读取），**不得**因此报错或丢弃整个结果。

---

## 4. 消息流

### 4.1 时序图

```
 调用方 (node_b)                                   被调方 (node_a)
      │                                                  │
      │ 1. node.call("node_a", "get_weather", {...})      │
      │      └─ ensure_connected("node_a")                │
      │            ├─ 已连接 → 直接继续                    │
      │            ├─ 未连接但在邻居表 → 拨号 + 握手        │
      │            └─ 不在邻居表 → UnknownPeer             │
      │                                                  │
      │ 2. reqid = Signal.new_reqid()                     │
      │ 3. pending_calls[reqid] = (event, [peer, None])   │
      │                                                  │
      │ ── tool_call(reqid, tool, args) ────────────────▶ │
      │                                                  │ 4. _dispatch → 第 3 步
      │                                                  │    → _on_tool_call
      │ 5. event.wait(5.0)   ← 阻塞当前线程               │ 6. 起工作线程 _run_tool
      │                                                  │      ├─ 查 _tools[tool]
      │                                                  │      ├─ 未注册 → raise
      │                                                  │      └─ 已注册 → func(**args)
      │                                                  │ 7. _normalize_tool_result
      │ ◀── tool_result(reqid, content, structured…) ──── │
      │                                                  │
      │ 8. 读线程 _on_tool_result                         │
      │      └─ holder[1] = ToolResult(...); event.set()  │
      │ 9. call() 醒来，pop pending_calls[reqid]          │
      │ 10. 返回 ToolResult 给用户                        │
      ▼                                                  ▼
```

### 4.2 调用方逐步

| 步 | 动作 | 失败时的表现 |
|---|---|---|
| 1 | `node.call(peer_id, tool, args, timeout=5.0)` | — |
| 2 | `ensure_connected(peer_id)`：已连接直接返回；未知节点抛 `UnknownPeer`；拨号/握手失败抛 `PeerUnavailable`；冷却期内抛 `PeerUnavailable` | 转 `ToolResult(error=str(e))`（§6） |
| 3 | 生成 `reqid`、登记 `pending_calls` | — |
| 4 | 发 `tool_call`（`_send` 在未连接时抛 `RuntimeError`） | 转 `ToolResult(error="未连接到 <peer>")` |
| 5 | `event.wait(timeout)` | 超时 → 注销条目 → `TimeoutError` → 转 `ToolResult(error="调用 <tool> 超时")` |
| 6 | 醒来后 `pop` 条目，取 `holder[1]` | 若期间断开，`holder[1]` 已被读线程写为 `ToolResult(error="连接断开")` |
| 7 | 返回 `ToolResult` | — |

### 4.3 被调方逐步

| 步 | 动作 | 依据 |
|---|---|---|
| 1 | 读线程收到 `tool_call` | `_read_loop` |
| 2 | `_dispatch` 第 1 步不命中（`tool_call` 不是核心信号类型）→ 第 2 步不命中（`pattern` 为 `None`）→ 第 3 步 | `_dispatch` |
| 3 | `_dispatch_core` 命中 `SignalType.TOOL_CALL` → `_on_tool_call` | `_dispatch_core` |
| 4 | `reqid` 为空 → 直接返回（忽略） | `_on_tool_call` |
| 5 | 取 `tool = payload.get("tool")`、`args = payload.get("args", {})` | 同上 |
| 6 | **起独立线程**执行 `_run_tool`，读循环立即返回 | 同上，见 §4.4 |
| 7 | 工作线程查 `_tools[tool]`；未注册 → `raise ValueError(f"未知工具: {tool}")` | `_run_tool` |
| 8 | 调用 `func(**args)`，规范化返回值 | `_run_tool` + `_normalize_tool_result` |
| 9 | 发 `tool_result`；`_send` 失败（对端已断）只记调试日志，**不得**重试 | `_run_tool` |

### 4.4 为什么**必须**在独立线程执行

读循环线程（`_read_loop`）是**该连接唯一**的消息接收者。若在被调方在读循环线程里同步执行工具：

1. **阻塞该连接的消息接收**。一个 30 秒的慢工具会让这条连接 30 秒内收不到任何消息——包括心跳 `ping`，于是对端按 `heartbeat_timeout`（默认 45 秒）判定失联并断开；也收不到同一连接上的其它 `tool_call`（并发度退化为 1）。
2. **工具内部回调对端会死锁**。这是更严重的一条：多轮模式的服务端在工具执行中调用 `ctx.ask()` 向调用方追问，然后阻塞等待 `input_response`。而 `input_response` 正需要读循环来接收——读循环却在等工具返回。**互相等待，永久死锁。**

因此规范条文：

> 被调方**必须**在独立线程中执行工具函数，**不得**在协议层读循环线程内同步执行。

参考实现在 `MSPProtocol._on_tool_call` 的文档字符串里把这两条理由都写明了，并注明与 `msp/multi-round` 的 `_run_tool` 同理。

---

## 5. 数据类型

### 5.1 `ToolResult`

`node.call()` 的返回值。定义在 `src/msp/core/content.py`。

| 成员 | 类型 | 缺省 | 说明 |
|---|---|---|---|
| `content` | `list` | `[]` | content 块列表 |
| `structured` | `Any` | `None` | 结构化结果（对应线上 `structuredContent`）。**注意本地属性名是 `structured`，线上字段名是 `structuredContent`** |
| `error` | `str` | `""` | 失败原因 |

| 方法 / 属性 | 返回值 | 语义 |
|---|---|---|
| `is_error` | `bool` | `bool(self.error)` —— 只要 `error` 非空串即为错误 |
| `unwrap()` | `Any` | `error` 非空时**抛 `ToolError(error)`**；否则返回 `structured` |
| `text()` | `str` | 把所有 `type="text"` 块（dict 或对象）的文本用 `"\n"` 拼接 |

**必须**满足：

1. `content` / `structured` / `error` 三者**不得**同时表达矛盾语义。规范要求：`error` 非空时 `structured` 的含义未定义，调用方**应当**先查 `is_error`。
2. **不得**用 `content` 是否为空判断成功失败——成功也可能没有 content 块（例如工具返回 `None`）。

### 5.2 content 块类型

| `type` | 关键字段 | 说明 |
|---|---|---|
| `text` | `text`（`str`）、可选 `annotations` | 纯文本 |
| `image` | `data`（Base64）、`mimeType`、可选 `annotations` | 图片 |
| `audio` | `data`（Base64）、`mimeType`、可选 `annotations` | 音频 |
| `resource` | 嵌套 `resource: {uri, mimeType, text?, blob?}`、可选 `annotations` | 嵌入资源 |
| `resource_link` | `uri`、`name`、`mimeType`、`description` | 资源引用 |
| `blob_ref` | `blobId`、`mimeType`、`size`、`checksum` | MSP 扩展，指向独立 blob 通道 |

块内字段名混用两种风格，**必须**逐字遵守：`mimeType`、`blobId` 是 camelCase；`annotations`、`text`、`data`、`uri`、`size`、`checksum`、`description` 无大小写歧义；`resource` 是嵌套对象而**不是**块自己的键。

未知 `type` 的块**必须**原样返回（`block_from_dict` 对未知类型返回输入 dict 本身），**不得**抛错。

### 5.3 返回值规范化规则

`_normalize_tool_result(result)` 返回 `(content_blocks, structured_data)` 二元组。工具函数的返回值**必须**按以下**顺序**判定，命中即返回：

| # | 输入形态 | `content` | `structured` | 备注 |
|---|---|---|---|---|
| 1 | `None` | `[]` | `None` | 显式空结果 |
| 2 | **非空** `list` 且**每个**元素都是 content 块 | 逐元素 `to_dict()` 后的列表 | `None` | 「已经是 content 块列表」 |
| 3 | 单个对象且有 `to_dict()` | `[result.to_dict()]` | `None` | 「单个 ContentBlock」 |
| 4 | `str` | `[{"type": "text", "text": result}]` | `result`（**同时**给） | 字符串既当 content 又当 structured |
| 5 | 其它（`dict` / `list` / `int` / `float` / `bool`） | `[{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]` | `result` | 结构化数据 |

**判定「是不是 content 块」的规则**（`_is_content_block`）：有 `to_dict` 属性，**或**是含 `"type"` 键的 `dict`。普通数据 dict（如 `{"name": "Alice"}`）**不算** content 块——这是为了不让结构化数据被误判成块列表。

#### 5.3.1 空列表陷阱（易错点，**必须**注意）

判定顺序中的第 2 分支带一个**非空**前置条件：

```python
if isinstance(result, list) and result and all(_is_content_block(b) for b in result):
```

若不写 `and result`，那么 `all(...)` 对空列表恒为 `True`，于是：

- 工具返回 `[]` 会被当成「空 content 块列表」，`structured` 变成 `None`；
- 实际期望是走第 5 分支——`content` 得到一条 `text` 块 `"[]"`，`structured` 得到 `[]`。

因此：

> 返回值 `[]` **必须**走结构化分支（第 5 分支），得到 `content=[{"type": "text", "text": "[]"}]`、`structured=[]`。

参考实现在源码里以注释显式标注了这个陷阱（「注意：空列表 [] 走结构化分支，避免 all() 恒真的陷阱」）。

#### 5.3.2 为什么 `content` 与 `structuredContent` 同时给

第 4、5 分支**同时**填两个字段，原因是两类消费者：

- **面向人 / 面向模型的消费者**读 `content`——它已经是可直接渲染的块（文本、图片…），不需要知道原始 Python 类型的 JSON 表示；
- **面向程序的消费者**读 `structuredContent`——它保留原始数据结构（`dict` / `list` / 数值），`unwrap()` 直接把它交回，避免「先 JSON 序列化、再解析回来」的往返。

二者**不得**被视为冗余而省略其一：省略 `structuredContent` 会迫使程序消费者解析文本块；省略 `content` 会使结果在只懂 content 块的实现（MCP 风格）里不可读。

---

## 6. 错误处理

### 6.1 错误即值

> `node.call()` 对**对端侧的一切失败**一律返回 `ToolResult(error=...)`，**不得**抛出异常打断调用方；只有**程序性错误**才 `raise`。

程序性错误指「调用方自己用错了 API」，例如把 `args` 传成 `None`（`func(**args)` 会 `TypeError`，但那发生在被调方）、或对未注册的 `node` 对象调用方法。**必须**显式拿到异常时，用 `ToolResult.unwrap()` —— 它在 `error` 非空时抛 `ToolError`。

### 6.2 五类失败与 `error` 文案来源

| # | 失败 | 触发点 | `error` 文案来源 | 文案形态 |
|---|---|---|---|---|
| F1 | 对端不可达 | `ensure_connected` → `PeerUnavailable` | `MSPNode.call` 的 `except (PeerUnavailable, UnknownPeer)` | `节点 <id> 不可达: <e>` 或 `节点 <id> 疑似失效，冷却中` |
| F2 | 未知节点 | `ensure_connected` → `UnknownPeer` | 同上 | `未知节点 <id>，无法连接` |
| F3 | 调用超时 | `MSPProtocol.call` → `TimeoutError` | `MSPNode.call` 的 `except (TimeoutError, ...)` | `调用 <tool> 超时` |
| F4 | 中途断连 | `_handle_disconnect` 写入 `holder[1]` | 协议层直接构造 | `连接断开` |
| F5 | 协议已停止 | `MSPProtocol.stop` 写入 `holder[1]` | 协议层直接构造 | `协议已停止` |

补充一条**同通道**的失败：

| # | 失败 | 触发点 | `error` 文案 | 归属 |
|---|---|---|---|---|
| F6 | 发包时发现未连接 | `_send` → `RuntimeError` | `未连接到 <peer>` | `MSPNode.call` 的 `except (TimeoutError, ConnectionClosed, RuntimeError)` |

**必须**满足：

1. F1–F6 全部**必须**以 `ToolResult(error=...)` 返回；调用方**不得**为了捕获它们而包裹 `try/except`。
2. 对端侧的失败（F3 除外）**必须**由调用方本地判定，**不得**依赖对端发 `error` 信号——对端可能已经死了，发不出任何东西。
3. F5 的覆盖范围：`stop()` 只唤醒 `holder[1] is None` 的条目，因此已经拿到 F4 结果的调用不会被 `协议已停止` 覆盖。

### 6.3 工具侧的失败与错误码归属

**工具执行失败有两条通道**，边界**必须**清楚：

| 通道 | 何时用 | 载体 | 错误码 |
|---|---|---|---|
| **错误即值** | 工具不存在、工具抛异常、参数不匹配导致 `TypeError` | `tool_result.payload.error`（字符串） | 无错误码（见下） |
| **协议错误** | 信号层级的问题：未知 `type` | `error` 信号 | `-32600` |

**错误码归属边界**（对照 [README.md §5.4](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#54-错误码)）：

| 码 | 规范定义的出现位置 | 参考实现现状 |
|---|---|---|
| `-32600` | 收到未知 `type` 时回 `error` | ✅ 已实现：`_dispatch_core` 的 `else` → `_reply_error(code=-32600, message="未知信号类型: <type>")` |
| `-32601` | 工具调用指向未注册工具 | 🟡 **未在核心协议层落地**：`_run_tool` 把它变成 `tool_result.payload.error` 的字符串 `未知工具: <name>`，**不带** `code` |
| `-32602` | 参数不满足工具声明的 `inputSchema` | 🟡 **未在核心协议层落地**：核心不做 schema 校验（§7.3），参数不匹配表现为 `TypeError` → `payload.error` 字符串 |
| `-32603` | 工具执行中抛出异常 | 🟡 **未在核心协议层落地**：异常消息原文进 `payload.error`，**不带** `code` |
| `-32000`~`-32099` | 实现自定义，保留给模式层 | 核心未使用 |

`-32601` / `-32602` / `-32603` 三个常量**只在** `src/msp/mcp/jsonrpc.py`（JSON-RPC 桥）中定义，核心协议层没有任何引用点。因此：

> 实现方**不得**期待在 `tool_result.payload` 中看到 `code` 字段。把 `payload.error` 字符串映射到错误码**应当**由适配层（如 [interop.md](../interop.md) 的 JSON-RPC 桥）完成。

### 6.4 未知工具的具体行为

被调方收到指向未注册工具的 `tool_call`：

1. `_run_tool` 中 `self._tools.get(tool_name)` 返回 `None` → `raise ValueError(f"未知工具: {tool_name}")`；
2. 异常被 `_run_tool` 的 `except Exception as e` 捕获 → `payload = {"content": [], "error": str(e)}`；
3. 发 `tool_result`（**不是** `error` 信号），`reqid` 回显。

因此**不会**产生协议层 `error` 信号。协议层的 `error`（`-32600`）只在**未知 `type`** 时发出。这条边界**不得**混淆：把「未知工具」升级成 `error` 信号会破坏 `reqid` 关联（`error` 信号虽带 `reqid`，但接收端没有对应的唤醒路径）。

---

## 7. 工具注册

### 7.1 装饰器签名

```python
@node.tool(name, description="", input_schema=None)
def my_tool(...) -> ...: ...
```

| 参数 | 类型 | 缺省 | 说明 |
|---|---|---|---|
| `name` | `str` | **必须** | 工具名，**必须**精确匹配调用方的 `payload.tool`；**必须**符合 `[a-z0-9_-]+` |
| `description` | `str` | `""` | 人类可读描述，进 `Manifest` |
| `input_schema` | `dict \| None` | `None` | 参数 JSON Schema |

注册动作**必须**同时完成三件事：

1. `manifest.add_tool(ToolDescriptor(name=..., description=..., input_schema=schema))` —— 进能力清单，随握手交换；
2. `protocol.tool(name)(func)` —— 进协议层的 `_tools` 派发表，**运行时**只查这张表；
3. `_push_manifest()` —— 若已连接则推 `manifest_update`。

### 7.2 `input_schema` 的产生

- **缺省**（`input_schema is None`）：由 `schema_from_func(func)` 从函数签名自省生成（含 `Annotated` 参数描述）；
- **显式传入**：**以传入为准**，**不得**与自省结果合并。

细节（`Annotated` 描述、`Field` 约束、`enum`、`Optional[Literal]` 的 `anyOf` 表达、零硬依赖 Pydantic 兼容）见 [schema.md](../schema.md)。

**`inputSchema` 也是客户端生成调用接口的依据。** 对端**可以**把清单里的 `inputSchema` 投影成宿主语言的可调用接口（参考实现：`peer.t`，见[仓库 README](https://github.com/hxh230802/MSP/blob/master/README.zh-CN.md) 的「把对端的工具当函数调用」）。由此：

- 提供方**应当**让 `inputSchema` 与实现一致——它不再只是给人看的说明，而是**对端生成 API 的依据**；
- 但参考实现当前**不保证**：`schema_from_func` 不产出 `default`，pydantic v2 下 `Field(ge=…)` 一类约束会静默丢失（见 [schema.md](../schema.md) 的「边界行为与脆弱性」）。因此生成方**必须**按「认不出就退化为 `Any`」处理，**不得**假定约束存在；
- **JSON Schema → 宿主语言的映射是客户端行为，非规范性。** 它不在线上、不构成互操作面，**不得**被写进本规范；线上只多这一条：`inputSchema` 是宣告契约的一部分。

### 7.3 自省结果只用于宣告（**已知缺口**）

> 自省 / 显式传入的 `inputSchema` **不参与运行时校验**——但这不等于它「只是说明」：它同时是**对端生成调用接口的依据**（§7.2），因此提供方**应当**让它与实现一致。

即：`Manifest` 里会如实列出参数约束，但被调方的 `_run_tool` 只做 `func(**args)`，**不**校验 `args` 是否满足 `inputSchema`。

后果**必须**如实预期：

1. 缺少必填参数 → `TypeError` → `payload.error`（不是 `-32602`）；
2. 多传参数 → `TypeError: unexpected keyword argument` → `payload.error`；
3. 类型不符（如把 `"3"` 传给 `int`）→ **不报错**，函数体拿到 `"3"`，行为由工具自身决定。

因此：

> 需要参数校验的实现**必须**在工具函数内部自行校验，**不得**假设框架会拦下非法参数。将来若加入运行时校验，报文形态**可以**通过在同一修订内「追加」`payload.code` 完成（[README.md §1](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#1-修订历史)）。

### 7.4 声明的工具与派发表的一致性

`Manifest.tools` 与 `protocol._tools` 是两张独立的表，同一次 `@node.tool` 会同时写两张。实现**不得**只写其中一张——只写清单会出现「宣告了但调不通」，只写派发表会出现「调得通但别人不知道」。

---

## 8. 超时、连接兜底与生命周期

### 8.1 超时语义

| 项 | 规定 |
|---|---|
| 缺省 | `5.0` 秒（[README.md §5.6](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#56-默认参数)） |
| 作用域 | 只覆盖**等待 `tool_result`** 的时间，**不覆盖** `ensure_connected` 的拨号与握手 |
| 超时行为 | 注销 `pending_calls[reqid]` → `raise TimeoutError(f"调用 {tool} 超时")` → `MSPNode.call` 转 `ToolResult(error="调用 <tool> 超时")` |
| 超时后的迟到结果 | `_on_tool_result` 查不到 `reqid` → 静默忽略；**不得**记成错误 |
| 被调方的执行 | 超时**不**通知被调方，工具照常执行完毕（其 `tool_result` 会被忽略）。需要真正取消长任务请用 `msp/task` 的协作式取消 |

### 8.2 `ensure_connected` 兜底

`ensure_connected(peer_id)` 是**所有需要连接的用户 API** 的统一入口（`call` / `fetch_manifest`）。行为：

| 状态 | 行为 |
|---|---|
| 已在 `protocol.connections` | 立即返回（无锁快路径） |
| 在 `_neighbors` 且未连接 | 取该 peer 的连接锁（`_connect_locks[peer_id]`），锁内二次检查后拨号 + 握手 |
| 不在 `_neighbors` | `raise UnknownPeer(f"未知节点 {peer_id}，无法连接")` |
| 在冷却期（`_unavailable[peer_id] > now`） | `raise PeerUnavailable(f"节点 {peer_id} 疑似失效，冷却中")` |
| 拨号 / 握手失败 | 记 `_unavailable[peer_id] = now + connect_backoff`（默认 `5.0` s）并抛 `PeerUnavailable`；**不删邻居** |
| 拨号成功 | 清除 `_unavailable[peer_id]` |

**必须**满足：

1. 每个对端**必须**有独立的连接锁（「每个对端一把连接锁」），避免并发触发重复建连；
2. 锁内**必须**二次检查 `connections`，防止等锁期间对端已由他人连上；
3. 冷却失败**不得**删除 `_neighbors` 条目——声明文件还在，硬删会让该对端永久失去（[DESIGN.md](/design) 的「软标记与硬清理分离」）；
4. `connect_policy="lazy"` 的节点**必须**由本方法按需建连，**不得**期望发现层替它连。

### 8.3 `RuntimeError("未连接到 X")` 的转换

`MSPProtocol.call` 在第一步就检查 `if peer_id not in self.connections: raise RuntimeError(f"未连接到 {peer_id}")`；`_send` 在找不到连接时抛同样的 `RuntimeError`。

`MSPNode.call` 的 `except (TimeoutError, ConnectionClosed, RuntimeError)` **必须**把它转成 `ToolResult(error="未连接到 <peer>")`。转换**不得**吞掉其它异常类型。

### 8.4 连接丢失时的清理

`_handle_disconnect(peer_id, conn)` **必须**：

1. 若传入的 `conn` 已不是当前登记的那条（去重场景下被淘汰的旧连接），**必须**直接返回，**不得**误删新连接的状态；
2. 清理 `connections` / `peer_manifests` / `_last_seen`；
3. 遍历 `pending_calls`，把 `holder[0] == peer_id` 的条目写成 `ToolResult(error="连接断开")` 并 `event.set()`（**唤醒所有等待者**）；
4. 在锁**外**关闭连接，避免 `shutdown` 阻塞持锁；
5. 调用 `_on_disconnected` 回调。

---

## 9. 规范条文汇总（MUST/SHOULD 清单）

| # | 条文 | 级别 |
|---|---|---|
| R1 | `tool_call` **必须**携带非空 `reqid`；`tool_result` **必须**回显 | **必须** |
| R2 | `pending_calls` 的登记**必须**发生在发包之前 | **必须** |
| R3 | 等待**必须**用 `Event`，**不得**轮询 | **必须** |
| R4 | 超时后**必须**注销 `pending_calls` 条目 | **必须** |
| R5 | 未知 `reqid` 的 `tool_result` **必须**静默忽略 | **必须** |
| R6 | `reqid` 为空或缺失的 `tool_call` **必须**被忽略 | **必须** |
| R7 | 被调方**必须**在独立线程执行工具，**不得**在读循环线程内同步执行 | **必须** |
| R8 | 工具执行失败**必须**放进 `tool_result.payload.error`，**不得**发 `error` 信号 | **必须** |
| R9 | 未知 `type` **必须**回 `error(code=-32600)`，且**不得**断开连接 | **必须** |
| R10 | `node.call()` 对 F1–F6 六类失败**必须**返回 `ToolResult(error=...)` | **必须** |
| R11 | `unwrap()` 在 `error` 非空时**必须**抛 `ToolError` | **必须** |
| R12 | 返回值规范化**必须**按 §5.3 的五分支顺序判定 | **必须** |
| R13 | 空列表 `[]` **必须**走结构化分支 | **必须** |
| R14 | `content` 与 `structuredContent` **应当**同时给出（第 4、5 分支） | **应当** |
| R15 | 未知类型 content 块**必须**原样保留 | **必须** |
| R16 | `input_schema` 缺省时**必须**自省生成，显式传入时**必须**以传入为准 | **必须** |
| R17 | 对端不存在 / 不可达时**不得**删除 `_neighbors` 条目 | **不得** |
| R18 | 每个对端**必须**有独立连接锁，锁内**必须**二次检查 | **必须** |
| R19 | 断开时**必须**唤醒该对端的全部等待者 | **必须** |
| R20 | 工具名匹配**必须**精确，**不得**支持通配符 | **必须** |
| R21 | 实现**不得**期待 `tool_result.payload` 中出现 `code` 字段 | **不得** |

---

## 10. 安全考量

1. **工具调用是最需要授权的动作。** 按 [security.md](../security.md#3-授权) 的设计，`req` 授权（允许对端调我的哪些工具）**必须**在 `_dispatch` 的最前面执行，工具名列表**必须**精确匹配（`True` = 全部）。参考实现**尚未**落地授权（见 §11 G6），因此**不得**把当前版本暴露到不可信网络。
2. **`pattern` 不能充当访问控制。** 路由契约规定未登记 `pattern` 的信号降级到核心分发（[patterns.md §3.4](../patterns.md#34-未登记模式的行为必须遵守)），所以给 `tool_call` 加一个未登记的 `pattern` **不会**让调用失败——它仍会被执行。访问控制**必须**基于 `payload.tool`。
3. **参数未经校验即执行。** §7.3 的缺口意味着 `args` 直接进入 `func(**args)`。工具实现**必须**把参数当作不可信输入处理（路径穿越、命令注入、反序列化）。
4. **`error` 文案会泄漏内部信息。** F1–F6 与工具异常都直接用 `str(e)`，可能泄露文件路径、依赖版本、SQL 片段。面向不可信对端的实现**应当**在回包前做错误信息脱敏，并在本地日志保留原文。
5. **一个连接上的请求数无上限。** `pending_calls` 没有容量限制，客户端**可以**发起任意多并发调用。面向不可信对端的实现**应当**加 per-peer 在飞请求上限。
6. **工具在线程池外执行。** 每次 `tool_call` 起一个 `daemon` 线程，没有并发上限。占用型工具的洪泛会耗尽线程资源——这属于部署层面的限流责任，**不得**指望协议层拦截。

---

## 11. 已知缺口

| # | 缺口 | 影响 | 依据 |
|---|---|---|---|
| G1 | `reqid` 为空的 `tool_call` / `tool_result` 被**静默忽略**，无日志、无回包 | 调用方会一直等到超时 | `_on_tool_call` / `_on_tool_result` 的 `if not reqid: return` |
| G2 | `-32601` / `-32602` / `-32603` 在核心协议层**无实现**，仅在 JSON-RPC 桥中定义 | `payload.error` 是纯文本，程序化分派需要适配层 | 全代码库仅 `mcp/jsonrpc.py` 使用这三个常量 |
| G3 | `inputSchema` **不参与运行时校验** | 非法参数只能靠工具自己挡（§7.3） | `_run_tool` 直接 `func(**args)` |
| G4 | **工具执行无并发上限**，每调用一线程 | 洪泛风险 | `_on_tool_call` 无条件 `Thread(...).start()` |
| G5 | `_run_tool` 的 `except Exception` **过宽**，会把 `KeyboardInterrupt` 之外的编程错误一并当成工具业务错误 | 实现 bug 被报成业务失败，难以区分 | `except Exception as e: payload = {..., "error": str(e)}` |
| G6 | 授权（`grants` 的 `req` / `rep`）**未实现** | 任何已连对端都能调本地全部工具 | [security.md](../security.md) 标为 🟡；`Preset` 无 `grants` 字段 |
| G7 | **`call` 超时不通知对端** | 对端继续执行已无人等待的工具；无取消路径 | `MSPProtocol.call` 只在本地 `pop` |
| G8 | **同步阻塞是唯一形态** | `node.call()` 阻塞调用线程；无异步 API | `MSPProtocol.call` 用 `event.wait` |
| G9 | ~~超时**不覆盖握手**~~ ✅ **已修复** | 握手阶段的 `receive()` 现受 `handshake_timeout`（默认 10 s）约束，对端 accept 后不回 ACK 会在超时后关闭连接 | [base-protocol.md §9](../base-protocol.md#9-已知缺口) |
| G10 | `structuredContent` 在失败回包中**缺省**，而成功回包中当工具返回 `None` 时其值为 `null` | 接收方需要区分「缺键」与「值为 null」 | `_run_tool` 的两个 `payload` 构造分支 |

---

## 12. 参考实现映射

| 条文 | 源码文件与符号 |
|---|---|
| §2.1 `reqid` 生成 | `src/msp/core/signal.py` → `Signal.new_reqid`（`uuid.uuid4().hex[:16]`） |
| §2.2 `pending_calls` 登记与注销 | `src/msp/protocol/protocol.py` → `MSPProtocol.__init__`、`call` |
| §2.3 结果写入 | `src/msp/protocol/protocol.py` → `MSPProtocol._on_tool_result` |
| §2.4 超时清理 | `src/msp/protocol/protocol.py` → `MSPProtocol.call` |
| §3.2 `tool_call.payload` | `src/msp/protocol/protocol.py` → `MSPProtocol.call` 的 `Signal.make(...)` |
| §3.3 `tool_result.payload` | `src/msp/protocol/protocol.py` → `MSPProtocol._run_tool` |
| §4.2 调用方流程 | `src/msp/core/node.py` → `MSPNode.call`、`ensure_connected`；`src/msp/protocol/protocol.py` → `MSPProtocol.call` |
| §4.3 被调方流程 | `src/msp/protocol/protocol.py` → `_dispatch_core`、`_on_tool_call`、`_run_tool` |
| §4.4 独立线程理由 | `src/msp/protocol/protocol.py` → `MSPProtocol._on_tool_call` 文档字符串；`src/msp/patterns/multi_round.py` → `MultiRoundHandler._on_tool_call` |
| §5.1 `ToolResult` | `src/msp/core/content.py` → `ToolResult`、`ToolError` |
| §5.2 content 块 | `src/msp/core/content.py` → `TextContent` / `ImageContent` / `AudioContent` / `EmbeddedResource` / `ResourceLink` / `BlobRef`、`block_from_dict` |
| §5.3 五分支规范化 | `src/msp/protocol/protocol.py` → `_normalize_tool_result`、`_is_content_block` |
| §5.3.1 空列表陷阱 | `src/msp/protocol/protocol.py` → `_normalize_tool_result` 的 `and result` 与源码注释 |
| §6.2 五类失败 | `src/msp/core/node.py` → `MSPNode.call` 的两个 `except` 子句；`src/msp/protocol/protocol.py` → `_handle_disconnect`、`stop` |
| §6.3 错误码边界 | `src/msp/protocol/protocol.py` → `_dispatch_core` 的 `else`、`_reply_error`；`src/msp/mcp/jsonrpc.py` → `METHOD_NOT_FOUND` / `INVALID_PARAMS` / `INTERNAL_ERROR` |
| §6.4 未知工具 | `src/msp/protocol/protocol.py` → `MSPProtocol._run_tool` |
| §7.1 工具注册 | `src/msp/core/node.py` → `MSPNode.tool`；`src/msp/protocol/protocol.py` → `MSPProtocol.tool` |
| §7.2 schema 自省 | `src/msp/core/schema.py` → `schema_from_func` |
| §7.4 两张表 | `src/msp/core/manifest.py` → `Manifest.add_tool`；`src/msp/protocol/protocol.py` → `MSPProtocol._tools` |
| §8.1 超时 | `src/msp/protocol/protocol.py` → `MSPProtocol.call` 的 `timeout: float = 5.0` |
| §8.2 `ensure_connected` | `src/msp/core/node.py` → `MSPNode.ensure_connected`、`_connect_to`、`_eager_connect`、`_unavailable`、`connect_backoff` |
| §8.4 断连清理 | `src/msp/protocol/protocol.py` → `MSPProtocol._handle_disconnect` |
