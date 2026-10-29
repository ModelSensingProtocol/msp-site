# MSP 数据模型参考 —— JSON 形态的完整字段定义

| | |
|---|---|
| **协议修订** | `2026-10-10` |
| **状态** | ✅ 已实现（`Signal` / `Manifest` / `Endpoint` / 内容块 / `Preset` 的全部字段与序列化形态；`grants` 等规划字段标注为 🔵） |
| **本页定义** | 各页报文所用的全部数据模型：`Signal` 信封、`Manifest` 与四个 descriptor、`Endpoint`、声明文件、内容块、`ToolResult`、核心与模式私有载荷、`schema_from_func` 的产出规则、`Preset` 与内置预设 |

> 规范性用语与状态标记见[规范索引 §2](index.md#2-规范性用语)；正文中**加粗**的关键词承担规范效力。
>
> **字段的权威源是 [`schema/2026-10-10/msp.yaml`](https://github.com/hxh230802/MSP/blob/master/schema/2026-10-10/msp.yaml)**——字段名、类型、必填性、默认值、约束，以及 `Signal.type`（+`pattern`）→ payload 的绑定关系，都只在那一个文件里定义；由它生成 [`msp.schema.json`](https://github.com/hxh230802/MSP/blob/master/schema/2026-10-10/msp.schema.json)（JSON Schema 2020-12）供第三方实现与校验器消费，生成物**不要手改**。
>
> **本页是它的解释性视图**：负责讲清「为什么这样设计」与「序列化时有哪些坑」，字段清单**不得**在别处再抄一份。两者不一致时**以 YAML 为准**，并视为本页缺陷——`tools/check_schema_drift.py` 会把「权威源 ↔ 参考实现 ↔ 本页」三方的不一致报出来，`tests/test_schema_source.py` 让它成为测试失败。

---

## 1. 概述

### 类型记号约定

| 记号 | 含义 |
|---|---|
| `string` / `integer` / `number` / `boolean` | JSON 标量：字符串 / 整数 / 数（含浮点） / 布尔 |
| `object` | JSON 对象（键为字符串的映射） |
| `array<T>` | 元素类型为 `T` 的 JSON 数组；`array<string>` 即字符串数组 |
| `map<K, V>` | 以 `K` 为键、`V` 为值的对象（序列化后仍是 `object`） |
| `A \| B` | 联合类型：取值属于 `A` 或 `B` 之一 |
| `null` | JSON `null` |
| `T?`（如 `string?`） | 可选字段：报文中**可以**缺省或为 `null` |
| `any` | 任意 JSON 值（对象、数组、标量、`null` 均可） |

「必填」列描述**报文**中的必填性，「默认」列描述**读取方**在字段缺省时**必须**采用的语义——它不要求发送方省略该字段：参考实现的 `Signal.to_dict()` 会写出全部 8 个键（含 `null`），接收方**必须**同时容忍显式 `null` 与缺省。

### 序列化总则

1. **命名风格分区**：`Signal` 信封的 8 个字段是 **snake_case**；`payload` 内部字段、`Manifest` 及其 descriptor、内容块中的 MSP 扩展字段多为 **camelCase**（如 `structuredContent`、`inputSchema`、`taskId`、`blobId`）。字段名**必须**逐字一致，**不得**混用。
2. **编码**：JSON 文本、UTF-8；参考实现用 `json.dumps(..., ensure_ascii=False)`，非 ASCII 原样传输。
3. **分帧**：TCP / UDS 为 4 字节大端长度前缀 + 负载；WebSocket 用二进制帧；单条消息上限 16 MiB。
4. **宽容读取**：未识别的字段、信号类型、内容块类型、模式 ID **不得**被视为协议错误而断开连接（[README §7](index.md#7-一致性)）。
5. **键序无意义**：除 `Manifest.capabilities` 被实现为 `sorted` 外，键序不构成语义。

---

## 2. 模型与契约

### Signal 信封

`Signal` 是「万物皆信号」的统一数据原子：握手、广播、工具调用、任务、心跳都是它的实例，区别只在 `type`。

| 字段 | 类型 | 必填 | 默认 | 语义与约束 |
|---|---|---|---|---|
| `type` | `string` | 是 | — | 信号类型：`SignalType` 的 9 个核心值之一，或模式私有类型（**必须**同时带 `pattern`） |
| `source` | `string` | 是 | — | 发送方 `node_id`，`[a-z0-9_-]+`（[README §5.3](index.md#53-命名规范)） |
| `pattern` | `string?` | 否 | `null` | **路由键**：模式 ID。核心信号通常为 `null`；模式私有信号**必须**携带 |
| `payload` | `object` | 否 | `{}` | 类型相关载荷，结构由 `type` + `pattern` 决定（见 §3） |
| `target` | `string?` | 否 | `null` | 目标 `node_id`，建议性字段；广播与握手不设 |
| `path` | `string?` | 否 | `null` | 信号逻辑路径，点号分段、域优先（`notify.web.download`）；`signal` 类型**必须**填写 |
| `reqid` | `string?` | 否 | `null` | 请求关联 ID；`tool_call` 与 `tool_result` **必须**携带同一值 |
| `timestamp` | `number` | 否 | 发送时刻 | Unix 秒（浮点） |

- `type` 与 `source` 是**唯二**无默认值的字段：缺任一个，`Signal.from_dict` 抛 `KeyError` → 读循环异常 → 连接断开。
- `pattern` 是**路由键**而不是收件人：`_dispatch` 先看 `type` 是否属于核心信号，再看 `pattern` 能否命中已注册的模式处理器，最后回退核心处理（未知 `pattern` **不得**导致断开，见 §6）。
- `payload` **必须**是对象；数组或标量载荷**不得**直接放在 `payload` 里，而应包一层（如 `{"items": [...]}`）。
- 核心模式**可以**不带 `pattern`（参考实现为 `null`），也**可以**带 `msp/request-reply` / `msp/publish-subscribe`；两种形态都**必须**被接受。

```json
{"type": "tool_call", "source": "node_a", "pattern": null, "target": "node_b",
 "path": null, "reqid": "9f2c1a4b7e0d3856",
 "payload": {"tool": "get_weather", "args": {"location": "上海"}}, "timestamp": 1791500000.0}
```

### SignalType 枚举与扩展规则

`SignalType` 定义 **9 个**字符串常量（[规范索引 §5.1](index.md#51-核心信号类型signaltype) 的表把 `ping` / `pong` 合并为一行，故该表只有 8 行）：

| `type` | 有 `reqid` | `payload` 形态（权威定义见 §3） |
|---|---|---|
| `hello` | 否 | `{"manifest": {...}}` |
| `ack` | 否 | `{"manifest": {...}}` |
| `signal` | 否 | 任意对象；路径在 `path` 字段 |
| `tool_call` | **是** | `{"tool": <string>, "args": <object>}` |
| `tool_result` | **是** | `{"content": [...], "structuredContent": <any>}` 或 `{"content": [], "error": <string>}` |
| `manifest_update` | 否 | `{"manifest": {...}}` |
| `ping` / `pong` | 否 | `{}`（空对象） |
| `error` | 视情况 | `{"code": <integer>, "message": <string>}` |

分类谓词：请求类为 `tool_call` / `hello` / `ping`，响应类为 `tool_result` / `ack` / `pong`；`signal` / `manifest_update` / `error` 不属于任一类。

**模式私有类型的扩展规则**：

- 模式**可以**定义私有类型（现有：`input_required` / `input_response`、9 个 `task_*`），与核心类型共用同一个 `type` 字段空间。
- 模式私有报文**必须**携带 `pattern`（值等于该模式 ID），否则接收方无法路由；接收方**不得**因 `type` 未知而断开连接，**应当**按 [patterns.md](./patterns.md) 的未知模式规则处理。
- `msp/` 前缀由本规范保留；第三方模式**必须**为私有类型加自有前缀（如 `acme_stream_chunk`）。
- 同名类型**可以**在不同模式下语义不同：`input_required` 同时定义于 `msp/multi-round` 与 `msp/task`，靠 `pattern` 区分。

### Manifest

`Manifest` 是节点自述的能力清单，属于节点而不属于协议；协议层只在握手时交换、在变化时推送。

#### 顶层字段

**序列化形态是 camelCase**；四个能力列表是**数组**而不是对象；`capabilities` 是**有序**（`sorted`）字符串数组；`clientCapabilities` 是含三个布尔的对象。

| 字段 | 内部类型 | 线格式类型 | 默认 | 语义 |
|---|---|---|---|---|
| `version` | `int` | `integer` | `0` | 单调递增版本号，只在内容变化时递增（见下） |
| `patterns` | `list[str]` | `array<string>` | `[]` | 本节点支持的模式 ID |
| `patternMetadata` | `dict[str, dict]` | `object` | `{}` | `pattern_id` → 任意对象；格式由模式自定义，清单不感知、不校验 |
| `capabilities` | `set[str]` | `array<string>` | `[]` | 能力位，取值 `pub` / `sub` / `req` / `rep`；序列化时 `sorted` |
| `signals` | `dict[str, SignalDescriptor]` | `array<object>` | `[]` | 发布的信号路径（内部以 `path` 为键） |
| `tools` | `dict[str, ToolDescriptor]` | `array<object>` | `[]` | 提供的工具（内部以 `name` 为键） |
| `resources` | `dict[str, ResourceDescriptor]` | `array<object>` | `[]` | 可读 / 可订阅资源（内部以 `uri` 为键） |
| `prompts` | `dict[str, PromptDescriptor]` | `array<object>` | `[]` | 预定义提示模板（内部以 `name` 为键） |
| `clientCapabilities` | 三个 `bool` | `object` | 三个 `false` | `{"sampling": …, "elicitation": …, "roots": …}` |

- `signals` / `tools` / `resources` / `prompts` **必须**是数组。`from_dict` 对它们**逐项迭代**：若对端写成对象映射，迭代会拿到字符串键并抛 `TypeError`，握手随之失败。
- `capabilities` 的 `sorted` 只是规范化：其值为集合语义，读取方**不得**依赖顺序，也**不得**因看到未列出的能力位而断开。
- `clientCapabilities` **必须**是对象（三个布尔），**不得**写成数组。
- `patternMetadata` 的键**应当**同时出现在 `patterns` 中（`set_pattern_metadata` 会自动补齐）。

```json
{"version": 3, "patterns": ["msp/publish-subscribe", "msp/request-reply", "msp/task"],
 "patternMetadata": {}, "capabilities": ["pub", "rep", "req", "sub"],
 "signals": [{"path": "notify.web.download", "description": "下载完成通知"}],
 "tools": [{"name": "get_weather", "description": "查询城市天气",
            "inputSchema": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]},
            "outputTypes": [], "annotations": {}}],
 "resources": [], "prompts": [],
 "clientCapabilities": {"sampling": false, "elicitation": false, "roots": false}}
```

#### 四个 descriptor 的精确字段

**`SignalDescriptor`**（键为 `path`）：`path`（`string`，必填，总是出现）、`schema`（`object`，**仅当非空**时出现）、`description`（`string`，**仅当非空**时出现）。

**`ToolDescriptor`**（键为 `name`，五个字段**总是出现**）：`name`（`string`，`[a-z0-9_-]+`）、`description`（`string`，可为 `""`）、`inputSchema`（`object`，可为 `{}`；缺省由 `schema_from_func` 生成）、`outputTypes`（`array<string>`，可为 `[]`）、`annotations`（`object`，可为 `{}`）。

**`ResourceDescriptor`**（键为 `uri`，五个字段**总是出现**）：`uri`（`string`）、`name`（`string`）、`description`（`string`）、`mimeType`（`string`）、`subscribable`（`boolean`，默认 `false`）。

**`PromptDescriptor`**（键为 `name`，三个字段**总是出现**）：`name`（`string`）、`description`（`string`）、`arguments`（`array<object>`，可为 `[]`；元素内部结构本修订**未**定义，参考实现原样透传）。

**形态差异**：只有 `SignalDescriptor` 对空 `schema` / 空 `description` 做**条件省略**，其余三个 descriptor 全部无条件写出。读取侧一律以缺省值兜底。

#### Manifest 变更与版本

`version` 是单调递增的**变更计数**，不是时间戳也不是内容哈希。

| 操作 | 何时递增 `version` |
|---|---|
| `add_signal(path, schema, description)` | 若 `path` 已存在且新 descriptor **相等** → 直接返回、**不**递增（去重短路）；否则写入并 `+1`（内容变化也算变更） |
| `remove_signal(path)` | 仅当存在时删除并 `+1` |
| `add_tool(descriptor)` | **无条件**写入并 `+1`（即使与既有 descriptor 完全相同） |
| `remove_tool(name)` | 仅当存在时 `+1` |
| `add_resource(descriptor)` / `remove_resource(uri)` | 同上：写入无条件 `+1`，删除仅存在时 `+1` |
| `add_prompt(descriptor)` / `remove_prompt(name)` | 同上 |
| `add_pattern(pattern_id)` | 仅当不在 `patterns` 中时追加并 `+1` |
| `set_pattern_metadata(pattern_id, metadata)` | **两处变更判定**：① `pattern_id` 不在 `patterns`（追加）；② 现值与 `metadata` 不等（替换）。任一成立则 `+1`（只加一次） |
| `apply_diff(diff)` | **不**递增；把 `version` **覆盖**为 `diff["version"]`（缺键则保留原值） |

- `add_tool` / `add_resource` / `add_prompt` **没有**去重短路（与 `add_signal` 不对称）：重复注册同名 descriptor 会产生一次无内容变化的版本递增与多余的 `manifest_update`。
- `MSPNode.start()` 把 `preset.patterns` 并入 `manifest.patterns`（`sorted(set(preset) | set(current))`）、把 `preset.capabilities` 并入能力位（集合并集）。这一步**不**经过变更操作，因此**不**递增 `version`，随后直接推送整份清单。
- 清单推送是**整份替换**：`manifest_update.payload.manifest` 是完整 `Manifest`；接收方**必须**丢弃 `version` 不大于当前值的推送。

#### diff() 与 apply_diff()

`Manifest.diff(old)` 的**精确键名**如下（新增 / 更新项是 descriptor **字典**，删除项是**排序后的键名数组**）：

| 键 | 类型 | 含义 |
|---|---|---|
| `signals_added` / `signals_updated` | `array<SignalDescriptor>` | 新有旧无 / 两边都有但不等 |
| `signals_removed` | `array<string>` | 旧有新无的 `path`（`sorted`） |
| `tools_added` / `tools_removed` / `tools_updated` | 同上（键为 `name`） | 工具 |
| `resources_added` / `resources_removed` / `resources_updated` | 同上（键为 `uri`） | 资源 |
| `prompts_added` / `prompts_removed` / `prompts_updated` | 同上（键为 `name`） | 提示模板 |
| `version` | `integer` | **新**清单的 `version`（不是旧值，也不是差值） |

`apply_diff(diff)`：按 `*_added` / `*_updated` 覆盖写入、按 `*_removed` 删除（缺键视为空数组），最后 `version = diff.get("version", version)`。

- `diff()` **不含** `patterns` / `patternMetadata` / `capabilities` / `clientCapabilities`：需要传递这些变化时**必须**走整份 `manifest_update`。
- `apply_diff` **无条件**把 `version` 设为 diff 中的值，缺少「拒绝更旧版本」的保护；跨机增量同步的实现**必须**自行加版本单调性校验。
- **当前状态（源码事实）**：`diff()` / `apply_diff()` 在参考实现中**没有任何调用点**（全仓仅在 `manifest.py` 内出现定义与实现）。增量同步是**已定义但未接线**的能力，实现**可以**不实现。

### Endpoint

| 字段 | 类型 | 必填 | 默认 | 语义 |
|---|---|---|---|---|
| `transport_type` | `string` | 是 | — | 传输后端标识：`tcp` / `websocket` / `uds`（`quic` 为实现预留） |
| `address` | `object` | 是 | — | 地址对象，键随 `transport_type` 变化（见下表） |
| `node_id` | `string?` | 否 | `null` | 节点身份；手动发现时可能尚不知道 |

- `Endpoint` **没有** `to_dict()` / `from_dict()`：它不直接上线，而是由发现层产出、由宣告层手工拼进声明文件。
- `address_key()` 返回 `(transport_type, tuple(sorted(address.items())))`；**源码事实**：该方法**无任何调用点**，实际的重复发现抑制由发现层的 `_known[node_id]` 声明哈希完成。调用 `address_key()` 本身不会抛错（`sorted` 只比较互不相同的键）；但它的**返回值**在用作 `set` / `dict` 键时要求 `address` 的值可哈希，因此 `address` 的值**应当**是简单可排序类型（字符串 / 数字），**不得**放嵌套对象。

| `transport_type` | `address` 形态 | 说明 |
|---|---|---|
| `tcp` | `{"host": "127.0.0.1", "port": 45678}` | `listen` 默认 `host="127.0.0.1"`、`port=0`（动态），实际端口取自 `getsockname` |
| `websocket` | `{"url": "ws://127.0.0.1:45678/msp"}` | `listen` 默认 host `127.0.0.1`、port `0`、path `/msp`；解析器只接受 `ws://` |
| `uds` | `{"path": "/tmp/msp-1234-abcd.sock"}` | 仅 Linux / macOS；默认在临时目录生成 `msp-<pid>-<rand>.sock`，权限 `0o600` |
| `quic` 🔵 | 未定义 | `TRANSPORT_REGISTRY` 中仅有注释占位 |

### 声明文件（共享目录宣告）

节点把 `Endpoint` 写进共享目录（默认 `~/.msp/nodes`），扫描方据此发现它。**精确 JSON 形态**（三个顶层键，`endpoint` 恰好两个子键）：

```json
{"node_id": "node_a",
 "endpoint": {"transport_type": "tcp", "address": {"host": "127.0.0.1", "port": 45678}},
 "timestamp": 1791500000.0}
```

1. **文件名规则**：`{node_id}.json`，位于 `nodes_dir`（默认 `~/.msp/nodes`，`~` **必须**展开）；扫描方**不得**读取非 `*.json` 文件。
2. **`endpoint` 不含 `node_id`**：节点身份只出现在顶层；读取侧只取 `transport_type` 与 `address`。
3. **`timestamp` 是租约**：发送方按 `renew_interval`（默认 `10.0` s，见 [README §5.6](index.md#56-默认参数)）覆写；接收方丢弃 `time.time() - timestamp > stale_after` 的声明（`DirectoryScan` 默认 `stale_after = 30.0` s）。**缺** `timestamp` 视为**永不过期**。
4. **原子写入**：**必须**先写 `{文件名}.tmp`，再 `os.replace` 覆写，避免扫描方读到半个 JSON；参考实现用 `json.dump(..., ensure_ascii=False, indent=2)`。
5. **撤销**：`withdraw()` 停止续租并 `unlink`；文件缺失**不得**报错。
6. **只放端点信息**：**不得**写入本地策略（`grants`）、密钥或任何本地安全配置；身份材料只经握手报文交换。
7. **扫描侧校验**：缺 `node_id`、缺 `endpoint`、`node_id` 等于自身、JSON 解析失败的声明**必须**跳过而不报错；未变的声明（按内容哈希判定）**不得**重复触发新增事件。

### 内容块（ContentBlock）

内容块出现在 `tool_result.payload.content`、`Artifact.parts` 等位置。`annotations` 是可选注解对象，**仅当非空**时出现在报文里。

| `type` | 字段 | 说明 |
|---|---|---|
| `text` | `text`、`annotations?` | 纯文本 |
| `image` | `data`、`mimeType`、`annotations?` | 图片，`data` 为 Base64 编码字节 |
| `audio` | `data`、`mimeType`、`annotations?` | 音频，`data` 为 Base64 编码字节 |
| `resource` | `resource`（嵌套对象）、`annotations?` | 嵌入资源，内容在嵌套对象里 |
| `resource_link` | `uri`、`name`、`mimeType`、`description` | 资源引用（只给 URI）；**无** `annotations` 字段 |
| `blob_ref` | `blobId`、`mimeType`、`size`、`checksum` | **MSP 扩展**：指向独立 blob 通道的引用 |

`resource` 的嵌套对象：`resource.uri`（`string`，必填）、`resource.mimeType`（`string`，**总是出现**，可为 `""`）、`resource.text`（**仅当非空**）、`resource.blob`（Base64，**仅当非空**）。

```json
{"type": "text", "text": "上海 21℃ 多云"}
{"type": "resource", "resource": {"uri": "file:///etc/hosts", "mimeType": "text/plain", "text": "127.0.0.1 localhost"}}
{"type": "resource_link", "uri": "file:///var/log/app.log", "name": "app.log", "mimeType": "text/plain", "description": "应用日志"}
{"type": "blob_ref", "blobId": "b-7f3a1c", "mimeType": "video/mp4", "size": 104857600, "checksum": "sha256:…"}
```

**宽容读取规则**：`block_from_dict` 按 `type` 查表构造类型化对象；`type` 未识别时**原样返回该字典**。因此消费方**必须**同时接受「类型化对象」与「原始字典」两种形态（`ToolResult.text()` 两条路径都处理）。

### ToolResult

| 字段 | 类型 | 默认 | 语义 |
|---|---|---|---|
| `content` | `array<ContentBlock>` | `[]` | 内容块数组（线格式键为 `content`） |
| `structured` | `any` | `null` | 结构化结果；线格式键为 **`structuredContent`** |
| `error` | `string` | `""` | 错误消息**字符串**（非空即失败） |

- `is_error` = `bool(error)`；`unwrap()` 在 `error` 非空时抛 `ToolError(error)`，否则返回 `structured`。
- `text()` 把所有 `type == "text"` 块的 `text` 用 `"\n"` 连接；非文本块忽略。
- 接收 `tool_result` 时按 `content` / `structuredContent` / `error` 三键构造，缺省分别为 `[]` / `null` / `""`。
- **注意区分**：`ToolResult.error` 是**字符串**，`error` **信号**的 `payload` 是 `{"code": <integer>, "message": <string>}` 对象（见 §3.4），二者不可互相替代。

---

## 3. 报文与字段

### 核心模式载荷

| 报文 | `payload` 精确形态 | 约束 |
|---|---|---|
| `hello` / `ack` | `{"manifest": <Manifest>}` | `pattern` 为 `null`；无 `reqid` |
| `signal` | 任意对象；路径在信封的 `path` 字段 | 无 `reqid` |
| `tool_call` | `{"tool": <string>, "args": <object>}` | `reqid` **必填** |
| `tool_result`（成功） | `{"content": <array<ContentBlock>>, "structuredContent": <any>}` | **无** `error` 键；`reqid` **必须**回填 |
| `tool_result`（失败） | `{"content": [], "error": <string>}` | **无** `structuredContent` 键 |
| `manifest_update` | `{"manifest": <Manifest>}` | 接收方仅在 `version` 更大时替换 |
| `ping` / `pong` | `{}` | 空对象 |
| `error` | `{"code": <integer>, "message": <string>}` | `reqid` 可回填被拒报文的 `reqid` |

**工具返回值 → 线格式**（`_normalize_tool_result` 的投影规则）：

| Python 返回值 | `content` | `structuredContent` |
|---|---|---|
| `None` | `[]` | `null` |
| 内容块列表（非空，且每项带 `type` 键或有 `to_dict`） | 各块字典 | `null` |
| 单个内容块对象（有 `to_dict`） | `[块字典]` | `null` |
| `str` | `[{"type": "text", "text": <串>}]` | 该字符串 |
| 其他（`dict` / 非内容块列表 / 数字 / 布尔） | `[{"type": "text", "text": json.dumps(值)}]` | 原值 |
| **空列表 `[]`** | `[{"type": "text", "text": "[]"}]` | `[]`（空列表走结构化分支，**不是**空内容块列表） |

### msp/multi-round 载荷

模式 ID `msp/multi-round`（`fallback_to = "msp/request-reply"`）；所有报文**必须**带 `pattern: "msp/multi-round"`。

| 报文（`type`） | `payload` 精确形态 |
|---|---|
| `tool_call` | `{"tool": <string>, "args": <object>}`；`reqid` 由客户端生成（参考实现为 `mr-<自增计数>`） |
| `input_required` | `{"prompt": <string>}`；`reqid` 沿用该次调用的 `reqid` |
| `input_response` | `{"answer": <any>}`；`reqid` 沿用该次调用的 `reqid` |
| `tool_result` | `{"content": <工具原样返回值，falsy 值归一为 []>, "error": <string>}` |

**与核心模式的两处不一致（源码事实）**：① `tool_result.payload.content` 是**工具函数原样返回值**，**不**经 `_normalize_tool_result` 规范化，也**不**带 `structuredContent`；② `error` 键**总是**出现（成功为空串 `""`），而核心模式的成功结果**不含** `error` 键。

### msp/task 载荷

模式 ID `msp/task`（`fallback_to = "msp/request-reply"`）；所有报文**必须**带 `pattern: "msp/task"`。

| 报文（`type`） | `payload` 精确形态 | 备注 |
|---|---|---|
| `task_submit` | `{"task": <string>, "args": <object>, "contextId": <string \| null>}` | `reqid` 必填 |
| `task_submit_result`（接受） | `{"taskId": "task-…", "contextId": <string \| null>, "state": "submitted"}` | 传到「接受」为止，不等完成 |
| `task_submit_result`（失败） | `{"error": <string>}` | 未知任务名 |
| `task_status` | `{"taskId": <string>, "state": <string>, "message": <string>}` | 无 `reqid` |
| `task_artifact` | `{"taskId": <string>, "artifact": <Artifact>}` | 无 `reqid` |
| `task_result` | `{"taskId": <string>, "state": <string>, "message": <string>, "error": <string>, "artifacts": <array<Artifact>>}` | 终态 |
| `task_query` | `{"taskId": <string>}` | `reqid` 必填 |
| `task_query_result`（成功） | `{"taskId": …, "contextId": <string \| null>, "state": <string>, "message": <string>, "error": <string>, "artifacts": <array<Artifact>>}` | |
| `task_query_result`（失败） | `{"taskId": <string>, "error": <string>}` | 无 `state` 键，可据此区分成败 |
| `task_cancel` | `{"taskId": <string>}` | `reqid` 必填 |
| `task_cancel_result` | `{"taskId": <string>, "accepted": <boolean>}`；失败时另有 `error` | |
| `input_required`（本模式） | `{"taskId": <string>, "prompt": <string>}` | **不带 `reqid`**（与 `msp/multi-round` 不同） |
| `input_response`（本模式） | `{"taskId": <string>, "answer": <any>}` | **不带 `reqid`** |

- **`Artifact`**：`{"name": <string>, "description": <string>, "parts": <array<ContentBlock>>}`；`parts` 复用内容块格式。
- **状态取值**：`submitted` / `working` / `input-required` / `completed` / `failed` / `canceled`；终态集合为 `{completed, failed, canceled}`（注意 `input-required` 用**连字符**）。
- **观察者镜像广播**：状态 / 产物 / 终态同时 `publish` 到 `task.<taskId>.<kind>`，`kind` ∈ `status` / `artifact` / `result`，`payload` 与同名定向报文**相同**；第三方节点用 `on("task.**")` 旁观。
- 空的 `content` / `artifacts` **必须**保留键（`[]`），**不得**省略——「空」是有意义的语义。

### 错误对象

`error` 信号的 `payload` 固定两个键：

```json
{"code": -32600, "message": "未知信号类型: stream_start"}
```

错误码取 JSON-RPC 2.0 约定值，权威表见[规范索引 §5.4](index.md#54-错误码)。**源码事实**：MSP 协议核心只在「收到未知 `type`」时发出 `-32600`；`-32601` / `-32602` / `-32603` 仅定义于 `msp/mcp/jsonrpc.py`（JSON-RPC 桥），MSP 工具执行失败一律走 `tool_result.payload.error` 字符串通道。

---

## 4. 消息流

```text
node_a                                                     node_b
  │  Signal{type:"tool_call", source:"node_a", pattern:null,│
  │         target:"node_b", path:null, reqid:"9f2c…",      │
  │         payload:{tool:"get_weather", args:{location:"上海"}},
  │         timestamp:1791500000.0}                         │
  ├────────────────────────────────────────────────────────▶│  ① _on_tool_call(payload.tool / args)
  │                                                         │  ② 线程执行 → 返回值
  │                                                         │  ③ _normalize_tool_result(...)
  │  Signal{type:"tool_result", source:"node_b",            │
  │         target:"node_a", reqid:"9f2c…",                 │
  │         payload:{content:[{type:"text", text:"21℃"}],    │
  │                  structuredContent:{temp:21}}}          │
  ◀─────────────────────────────────────────────────────────┤  ④ reqid 原样回填
  │  ⑤ 按 reqid 命中 pending_calls → ToolResult(content, structured, error="")  │
```

能力清单交换：发起方 `hello` 与接受方 `ack` 的 `payload` 都是 `{"manifest": <完整 Manifest>}`；此后每次清单变化推送 `manifest_update{payload:{manifest:{version:N, …}}}`——**整份替换**，接收方只在 `version` 更大时接受。

---

## 5. 数据类型

### schema_from_func 的投影规则

`inputSchema` 缺省时由工具函数签名自省生成；**显式传入**的 `input_schema` 优先，自省只在缺省时兜底。函数级产出恒为 `{"type": "object", "properties": {...}}`，存在必填参数时追加 `required`（按参数声明顺序）。

| 注解形态 | JSON Schema 片段 |
|---|---|
| `str` / `int` / `float` / `bool` | `{"type":"string"}` / `{"type":"integer"}` / `{"type":"number"}` / `{"type":"boolean"}`（**类型对象精确相等**查表，`bool` 不会误判为 `int`） |
| 无注解 / `Any` / `inspect.Parameter.empty` | `{}`（无约束，但参数仍进 `properties`） |
| `None`（`type(None)`） | `{"type":"null"}` |
| `Annotated[str, "城市名"]` | `{"type":"string","description":"城市名"}` |
| `Annotated[int, Field(ge=0, le=100)]` | **仅 pydantic v1 形态成立**：`{"type":"integer","minimum":0,"maximum":100}`；**pydantic v2 形态下约束被静默丢弃**，只剩 `{"type":"integer"}`（见下方第 7 条） |
| `Field(gt=0)` / `Field(lt=10)` | 命中时 → `exclusiveMinimum` / `exclusiveMaximum` |
| `Field(min_length=1)` / `Field(max_length=64)` | 命中时 → `minLength` / `maxLength` |
| `Field(pattern="^a")` / `Field(description="…")` | 命中时 → `pattern` / `description`（`description` 在 v1/v2 均命中：v2 的 `FieldInfo.description` 仍是实例属性） |
| `enum.Enum` 子类 | `{"enum":[成员1.value, 成员2.value, …]}`（取 `.value`，**不**写 `type`） |
| `Literal["a", "b"]` | `{"enum":["a","b"]}`（取字面量本身） |
| `Optional[str]` / `str \| None` | `{"type":["string","null"]}` |
| `Optional[MyEnum]` / `Optional[Literal[...]]`（内层无标量 `type`） | `{"anyOf":[{…内层…},{"type":"null"}]}` |
| `Union[A, B]`（≥ 2 个非 `None` 成员） | `{"anyOf":[A 的片段, B 的片段]}`（**丢弃** `None` 成员） |
| `list[T]` / `set[T]` / `tuple[T]` | `{"type":"array","items":<T 的片段>}`；`tuple[T1, T2]` → `{"type":"array"}`（**无** `items`） |
| 裸 `list` / `set` / `tuple` | `{"type":"array"}` |
| `dict` | `{"type":"object"}` |
| `dict[str, T]` | `{"type":"object","additionalProperties":<T 的片段>}` |
| 其他（自定义类、`TypeVar`） | `{}`（无约束，不报错） |

**关键结论**：约束输出的是 **JSON Schema 关键字**（`minimum` / `exclusiveMinimum` / `maximum` / `exclusiveMaximum` / `minLength` / `maxLength` / `pattern`），**不是** pydantic 字段名（`ge` / `le` / `gt` / `lt` / `min_length` / `max_length`）。实现**不得**把 `ge` 之类直接透传进 `inputSchema`。

### 边界行为与脆弱性

1. **`get_type_hints(func, include_extras=True)` 是必需的**：默认调用会剥掉 `Annotated` 元数据，描述与约束全部丢失；`from __future__ import annotations` 使注解成为字符串，也必须经它解析。
2. **自省失败即「无约束」**：`get_type_hints` 抛异常时 hints 退化为空——所有参数变无约束但**仍**进 `properties`，`required` 仍按签名默认值判定；`inspect.signature` 失败时返回 `{"type":"object","properties":{}}`（**没有** `required` 键）。
3. **跳过与兜底**：`self` / `cls`、`*args` / `**kwargs` 跳过；无注解参数**不**丢弃，而是产出 `{}`。
4. **不产出 `default`**：`_field_extra` 明确**不**提取默认值——签名里的 Python 默认值只决定参数是否进 `required`，JSON Schema 的 `default` 关键字**从不**由本实现生成；`Field(default=...)` 也不被读取。
5. **零 pydantic 硬依赖的识别方式**：用 `type(meta).__name__ == "FieldInfo"` 做 duck-typing，避免 `import pydantic`（项目唯一第三方依赖是 `watchdog`）。
6. **脆弱性**：① 类名**字符串**匹配——pydantic 改名、包装或子类化会让约束**静默丢失**，同名自定义类会被**误识别**；② 非 pydantic 的约束载体（如 `annotated_types`）**不**被识别；③ 多个 `Annotated` 约束对象会依次 `update`，后者覆盖前者同名键；④ 自省结果**只用于对外宣告**，**不**参与运行时校验——协议层不按 `inputSchema` 校验 `args`，工具函数自身的 `TypeError` 只会变成 `tool_result.payload.error`。
7. **pydantic v2 下约束全部丢失（实测，重要）**：`_field_extra` 用 `getattr(field, "ge" / "gt" / "le" / "lt" / "min_length" / "max_length" / "pattern")` 取约束，这套属性是 **pydantic v1** 的 `FieldInfo` 形态。pydantic v2 把约束搬进了 `field.metadata`（形如 `Ge(ge=0)` / `Le(le=100)` 的对象），`FieldInfo` **不再有** `ge` / `le` 等属性，于是上述 `getattr` 全部返回 `None`，**约束被静默丢弃**；`description` 仍保留（它是 v2 的实例属性）。在 pydantic 2.13.4 上实测：`Annotated[int, Field(ge=0, le=100, description="pct")]` 产出 `{"type":"integer","description":"pct"}`——`minimum` / `maximum` **不出现**。因此：依赖约束宣告的实现**必须**自行读取 `field.metadata`（v2）或显式传入 `input_schema`；**不得**假定本函数会为 `Field(...)` 生成约束。

### Preset 与内置预设

| 字段 | 类型 | 默认 | 语义 |
|---|---|---|---|
| `name` | `string` | —（必填） | 预设名，同时是内置预设的属性名 |
| `discovery` | `set<string>` | `frozenset()` | 启用的发现机制（`directory` / `manual`） |
| `presence` | `set<string>` | `frozenset()` | 启用的宣告机制（`directory` / `manual`） |
| `transports` | `set<string>` | `frozenset()` | 启用的传输后端（`tcp` / `websocket` / `uds`） |
| `patterns` | `set<string>` | `frozenset()` | 启用的模式 ID（启动时并入 `Manifest.patterns`） |
| `primary_transport` | `string` | `"tcp"` | 对外宣告哪个后端；**必须**在 `transports` 中，否则 `start()` 抛错 |
| `capabilities` | `set<string>` | `frozenset()` | 能力位（启动时并入 `Manifest.capabilities`） |
| `connect_policy` | `string` | `"eager"` | `eager`（发现即连）/ `lazy`（仅接受入站，按需拨号） |

内置预设 **8** 个；模式列简写逐字对应源码 ID：`RR = msp/request-reply`、`PS = msp/publish-subscribe`、`MR = msp/multi-round`、`TK = msp/task`。

| 预设 | discovery | presence | transports | patterns | primary | capabilities | policy |
|---|---|---|---|---|---|---|---|
| `LOCAL_TOOL` | — | `directory` | `tcp` | RR, PS | `tcp` | pub, rep | `lazy` |
| `LOCAL_TOOL_ADVANCED` | — | `directory` | `tcp` | RR, PS, MR, TK | `tcp` | pub, rep | `lazy` |
| `LOCAL_AI` | `directory` | `directory` | `tcp` | RR, PS, MR, TK | `tcp` | pub, sub, req, rep | `eager` |
| `LOCAL_AI_UDS` | `directory` | `directory` | `uds` | RR, PS, MR, TK | `uds` | pub, sub, req, rep | `eager` |
| `CLOUD_SERVICE` | — | `directory` | `tcp` | RR, PS, MR, TK | `tcp` | pub, rep | `lazy` |
| `OBSERVER` | `directory` | — | `tcp` | PS | `tcp` | sub | `eager` |
| `FULL_PEER` | `directory` | `directory` | `tcp` | RR, PS, MR, TK | `tcp` | pub, sub, req, rep | `eager` |
| `MANUAL_PEER` | `manual` | `manual` | `websocket` | RR, PS | `websocket` | pub, sub, req, rep | `eager` |

`LOCAL_AI_UDS` 是 `LOCAL_AI` 换 UDS 传输（仅 Linux / macOS）；`OBSERVER` 只发现不宣告（presence 为空）且只有 `PS`；`MANUAL_PEER` 走 WebSocket 且**只**启用核心两个模式（要用 `MR` / `TK` 需显式 `register_pattern`）。

**授权（`grants`）🔵 尚未进入 `Preset`**：本修订把它定义为 `Preset` 的本地策略字段，字段形态与默认值见 [security.md §授权](./security.md#3-授权)。授权**不得**进入 `Manifest`，也**不得**随清单交换。

### JSON Schema 片段

```json
{"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "Signal",
 "type": "object", "required": ["type", "source"], "additionalProperties": true,
 "properties": {
   "type": {"type": "string"},
   "source": {"type": "string", "pattern": "^[a-z0-9_-]+$"},
   "pattern": {"type": ["string", "null"]}, "target": {"type": ["string", "null"]},
   "path": {"type": ["string", "null"]}, "reqid": {"type": ["string", "null"]},
   "payload": {"type": "object"}, "timestamp": {"type": "number"}}}
```

```json
{"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "Manifest",
 "type": "object", "additionalProperties": true,
 "required": ["version", "patterns", "patternMetadata", "capabilities", "signals", "tools", "resources", "prompts", "clientCapabilities"],
 "properties": {
   "version": {"type": "integer", "minimum": 0},
   "patterns": {"type": "array", "items": {"type": "string"}},
   "patternMetadata": {"type": "object"},
   "capabilities": {"type": "array", "items": {"enum": ["pub", "sub", "req", "rep"]}},
   "signals": {"type": "array", "items": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}, "schema": {"type": "object"}, "description": {"type": "string"}}}},
   "tools": {"type": "array", "items": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}, "description": {"type": "string"}, "inputSchema": {"type": "object"}, "outputTypes": {"type": "array", "items": {"type": "string"}}, "annotations": {"type": "object"}}}},
   "resources": {"type": "array", "items": {"type": "object", "required": ["uri"], "properties": {"uri": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"}, "mimeType": {"type": "string"}, "subscribable": {"type": "boolean"}}}},
   "prompts": {"type": "array", "items": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}, "description": {"type": "string"}, "arguments": {"type": "array", "items": {"type": "object"}}}}},
   "clientCapabilities": {"type": "object", "properties": {"sampling": {"type": "boolean"}, "elicitation": {"type": "boolean"}, "roots": {"type": "boolean"}}}}}
```

---

## 6. 错误处理与边界

| 情形 | 要求 |
|---|---|
| 缺 `type` 或 `source` | `from_dict` 抛 `KeyError` → 读循环异常 → **断开连接**；这两个字段是硬必填 |
| 缺 `payload` / `timestamp` / `target` / `path` / `reqid` / `pattern` | **必须**按默认值兜底（`{}` / 接收时刻 / `null`），**不得**报错 |
| 显式 `null` 与缺省 | 语义**必须**等价；发送方写出 `null` 是合规的 |
| 未知 `pattern` | **不得**断开；参考实现回退到核心处理路径 |
| 未知 `type`（且无可用 `pattern`） | **应当**回 `error`，`code = -32600`；**不得**静默丢弃而让对端永久等待 |
| 工具执行失败 | **必须**走 `tool_result.payload.error`（错误即值）；协议级失败才用 `error` 信号 |
| 未知内容块 `type` | **必须**原样保留并交给上层；**不得**丢弃整个 `content` |
| `Manifest` 四个列表写成对象 | 解析抛 `TypeError`、握手失败；发送方**不得**使用对象形态 |
| `manifest_update.version` 不大于当前值 | **必须**忽略（防止用旧清单回滚能力面） |
| `apply_diff` 收到更旧 `version` | 参考实现会直接覆盖；跨机增量同步的实现**必须**自行拒绝版本倒退 |
| 未知 `error.code` | 按实现自定义区间（`-32000`~`-32099`）记录；**不得**因未知错误码断开连接 |
| `tool_result.reqid` 不在等待表中 | **必须**忽略（可能已超时或为伪造），**不得**抛异常 |
| `content` 内混有类型化对象与原始字典 | **必须**都能处理（宽容读取的必然结果） |

---

## 7. 规范条文汇总（MUST / SHOULD 清单）

1. `Signal` **必须**使用 snake_case 字段名；`type` 与 `source` **必须**存在，其余字段缺省时按默认值语义处理。
2. 模式私有信号**必须**携带 `pattern`；接收方**必须**优先按 `pattern` 路由。
3. `type: "signal"` **必须**填写 `path`；`tool_call` / `tool_result` **必须**携带同一 `reqid`。
4. `Manifest` **必须**使用 camelCase；`signals` / `tools` / `resources` / `prompts` **必须**是数组，`capabilities` **必须**是字符串数组，`clientCapabilities` **必须**是含三个布尔的对象。
5. `Manifest.version` **必须**单调递增；接收方**必须**丢弃 `version` 不大于当前值的 `manifest_update`。
6. `SignalDescriptor` 的空 `schema` / `description` **可以**省略；其余 descriptor 的字段**应当**全部写出，读取侧**必须**以缺省值兜底。
7. 声明文件**必须**是 `{node_id}.json`，**必须**原子写入，**不得**写入本地策略或密钥。
8. `Endpoint.address` **不得**含嵌套对象（`address_key` 依赖可排序的简单值）。
9. 未知内容块类型**必须**原样保留；消费方**必须**同时接受类型化对象与原始字典。
10. 线格式用 `structuredContent`，内存模型叫 `structured`；实现**不得**把 `structured` 直接写上线。
11. `ToolResult.error`（字符串）与 `error.payload`（对象）**不得**混用；工具失败**必须**走 `tool_result.payload.error`。
12. `inputSchema` 缺省时**应当**由 `schema_from_func` 生成，且**必须**用 `get_type_hints(..., include_extras=True)`，输出**必须**是 JSON Schema 关键字而非 pydantic 字段名。
13. `schema_from_func` **不得**产出 `default` 关键字，**不得**因未识别注解而抛异常。
14. `grants` **不得**出现在 `Manifest`、声明文件或任何上线报文中。
15. 未识别的字段 / 信号类型 / 内容块类型 / 模式 ID **不得**被视为协议错误而断开连接。

---

## 8. 安全考量

- **清单是自述，不是承诺**：`capabilities` / `tools` / `patterns` 都可能虚报；授权判定**不得**引用清单（[security.md §授权](./security.md#3-授权)），清单只用于「要不要尝试」的本地优化。
- **自省不是校验**：`inputSchema` 是告示而非运行时闸门；参数校验**应当**在工具函数内完成，**不得**依赖 schema。
- **宽容读取的边界**：宽容读取要求不断开连接，**不**要求执行未识别语义；**不得**把「未知块原样保留」理解为「未知数据可进入执行路径」。
- **声明文件是本地策略禁入区**：`grants` / 密钥 / 白名单**不得**进入声明文件或 `Manifest`。
- **完整性字段是提示性的**：`blob_ref.size` / `checksum` **不得**作为内存预分配的唯一下界，其校验责任见 [security.md §8](./security.md#8-安全考量)。
- **`reqid` 必须不可预测**：它是 `tool_result` 唯一的关联依据（16 位十六进制），可预测的 `reqid` 会留下结果伪造面（[security.md §8](./security.md#8-安全考量)）。
- **`version` 是回滚防线**：拒绝更旧的 `manifest_update` 可防止对端用旧清单回滚本地能力视图；`apply_diff` 目前**没有**这层保护。

---

## 9. 已知缺口

1. **`Endpoint.address_key()` 无调用点**：端点去重实际由发现层的 `_known[node_id]` 声明哈希完成，`(transport_type, address)` 级去重「已定义未使用」。
2. **`diff()` / `apply_diff()` 未被协议层使用**：全仓仅在 `manifest.py` 内出现，清单更新走整份 `manifest_update`。
3. **`apply_diff` 无版本单调性保护**：会把 `version` 无条件覆盖为 diff 中的值，可能造成版本倒退。
4. **`schema` 不参与运行时校验**：协议层不按 `inputSchema` 校验 `args`，工具函数也不自动获得校验。
5. **`PromptDescriptor.arguments` 元素结构未定义**：源码为 `list[dict]`，内部字段本修订未规定（[capabilities.md](./capabilities.md) 🔵 补齐）。
6. **`add_tool` / `add_resource` / `add_prompt` 无去重短路**：与 `add_signal` 不对称，重复注册会产生无内容的 `version` 递增与多余的 `manifest_update`。
7. **`msp/multi-round` 的 `tool_result` 与核心模式不一致**：`content` 是原样返回值、**无** `structuredContent`、`error` 键总是存在。
8. **`msp/task` 的 `input_required` / `input_response` 不带 `reqid`**：只能靠 `taskId` 关联；跨模式复用的实现**不得**假定二者同构。
9. **缺失字段行为不对称**：缺 `type` / `source` 会断开连接，其他缺失字段静默兜底。
10. **无 schema 版本化**：`Manifest.version` 只是单调计数，不能表达「数据结构变了」，也没有兼容性声明字段。
11. **`quic` 传输未注册**：仅有注释占位，使用会抛 `ValueError`，其 `address` 形态未定义。

---

## 10. 参考实现映射

| 数据模型 / 规则 | 源码文件与符号 |
|---|---|
| `Signal` 字段、`to_dict` / `from_dict`、`new_reqid` | [src/msp/core/signal.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/signal.py) `Signal` |
| `SignalType` 9 个常量与请求 / 响应分类 | [src/msp/core/signal.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/signal.py) `SignalType`、`Signal.is_request`、`Signal.is_response` |
| `Manifest` 顶层字段与 camelCase 序列化 | [src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `Manifest.to_dict` / `from_dict` |
| 四个 descriptor 的字段与条件省略 | [src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `SignalDescriptor` / `ToolDescriptor` / `ResourceDescriptor` / `PromptDescriptor` |
| 变更操作与 `version` 规则 | [src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `add_signal` / `add_tool` / `add_resource` / `add_prompt` / `add_pattern` / `set_pattern_metadata` |
| `diff()` / `apply_diff()` 键名 | [src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `Manifest.diff` / `Manifest.apply_diff` |
| 清单推送与 `version` 比较 | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `push_manifest` / `_on_manifest_update` |
| 握手报文 `payload.manifest` | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `handshake_outbound` / `handshake_inbound` |
| `Endpoint` 与 `address_key` | [src/msp/discovery/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/base.py) `Endpoint` |
| 各后端 `address` 形态 | [tcp.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/tcp.py) / [websocket.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/websocket.py) / [uds.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/uds.py) 的 `listen` |
| 传输注册表（`quic` 占位） | [src/msp/core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `TRANSPORT_REGISTRY` |
| 声明文件形态与原子写入 | [src/msp/presence/directory.py](https://github.com/hxh230802/MSP/blob/master/src/msp/presence/directory.py) `DirectoryWrite._declaration` / `_write` |
| 声明扫描与租约判定 | [src/msp/discovery/directory.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/directory.py) `DirectoryScan._read_declaration` / `_full_scan` |
| 六种内容块与宽容读取 | [src/msp/core/content.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) `TextContent` / `ImageContent` / `AudioContent` / `EmbeddedResource` / `ResourceLink` / `BlobRef` / `block_from_dict` |
| `ToolResult` 与 `ToolError` | [src/msp/core/content.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) `ToolResult` / `ToolError` |
| 工具返回值规范化 | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `_normalize_tool_result` / `_is_content_block` |
| 核心载荷字段与错误回执 | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `call` / `_on_tool_result` / `_run_tool` / `_reply_error` |
| `msp/multi-round` 载荷 | [src/msp/patterns/multi_round.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/multi_round.py) `MultiRoundHandler._ask` / `_on_input_required` / `_reply_result` |
| `msp/task` 载荷、状态与镜像广播 | [src/msp/patterns/task.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/task.py) `TaskHandler._on_submit` / `_emit_status` / `_emit_artifact` / `_emit_result` / `_broadcast` / `Artifact` / `TaskSnapshot` |
| `schema_from_func` 与投影规则 | [src/msp/core/schema.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/schema.py) `schema_from_func` / `type_to_schema` / `_annotated_extra` / `_field_extra` |
| `Preset` 字段与 8 个内置预设 | [src/msp/core/preset.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/preset.py) `Preset` 及各 `Preset.*` 实例 |
| `Preset` 并入清单的时机 | [src/msp/core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `MSPNode.start` |

**相关页面**：[规范索引](index.md) · [architecture](./architecture.md) · [base-protocol](./base-protocol.md) · [transports](./transports.md) · [discovery](./discovery.md) · [patterns](./patterns.md) · [patterns/request-reply](./patterns/request-reply.md) · [patterns/publish-subscribe](./patterns/publish-subscribe.md) · [patterns/multi-round](./patterns/multi-round.md) · [patterns/task](./patterns/task.md) · [capabilities](./capabilities.md) · [security](./security.md) · [设计文档](../designs.md)
