# MSP Specification — Interoperability: MCP ⊆ MSP, the `msp.mcp` adapter layer, and JSON-RPC 2.0 semantic alignment

| | |
|---|---|
| **Protocol revision** | `2026-10-10` |
| **Status** | ✅ **Implemented (stdio + tools + Streamable HTTP carrier)** — the adapter source is verifiable; the Streamable HTTP `GET` SSE long stream and resources / prompts / sampling are 🔵 |
| **Upstream basis** | [../whitepaper.md](https://github.com/hxh230802/MSP/blob/master/docs/whitepaper.md) §5, [../DESIGN.md](/design) "Relationship to JSON-RPC 2.0" |
| **Defined on this page** | The conclusions and boundaries of the mapping from MCP behaviour to MSP, the real signatures and semantics of the `msp.mcp` adapter layer, JSON-RPC 2.0 semantic alignment and error-code conversion, the optional codec bridge (🔵), and pointers to A2A and Streamable HTTP |

This page turns "MCP ⊆ MSP" from a conclusion into a checkable mapping table and a runnable code contract. The ✅ provisions are word-for-word identical to `src/msp/mcp/`; for the 🔵 provisions **an implementer MAY leave them unimplemented, but once implemented they MUST comply with the provisions**.

## 1. Overview

The relationship between MSP and MCP has three layers: in **semantics**, MCP's behaviour in the tool-calling scenario can be mapped into MSP in a behaviour-preserving way, but not the other way round (§2); in **code**, `msp.mcp` provides three components — client / server / bridging — and does not enter the core layer (§3.1, §4); in **wire format**, the MSP encoding layer does **not** adopt the JSON-RPC envelope, it only performs semantic alignment on the tool-call subset, and interoperability rests on an optional bridge (§2 "Signal ↔ JSON-RPC mapping table", §3.3).

Three boundaries are declared up front: ① **the mapping is not a value judgement** — "MCP is a subset of MSP" is equivalent only to "MSP provides a more general framework that can accommodate MCP semantics"; the two are complementary rather than opposed ([../whitepaper.md](https://github.com/hxh230802/MSP/blob/master/docs/whitepaper.md) §5.1); ② **the interoperability surface is the tool-call subset** — the reference implementation covers only the tools capability (`initialize` / `tools/list` / `tools/call`), and the remaining **methods** are 🔵 (§9); the **transport** already has two carriers, stdio and Streamable HTTP; ③ **the adapter layer does not enter the core** — all MCP-related code is kept inside the `src/msp/mcp/` package, and the core layer knows no MCP concept ([../src/msp/mcp/__init__.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/__init__.py)).

## 2. Mapping and contract

### MCP ⊆ MSP

| MCP | MSP | Status |
|---|---|---|
| Handshake (`initialize` + capability exchange) | `hello` / `ack` + `Manifest` ([base-protocol](base-protocol.md) §4.2, §4.4) | ✅ |
| `notifications/initialized` | No counterpart; the handshake completes at once, and `hello`/`ack` have already exchanged manifests (absorbed by the adapter layer) | ✅ |
| `tools/call` | `tool_call` / `tool_result` of `msp/request-reply` ([patterns/request-reply](patterns/request-reply.md)) | ✅ |
| `tools/list` | No counterpart; tools live in `Manifest.tools`, and the handshake + `manifest_update` already amount to "listing" | ✅ |
| `ping` | `ping` / `pong` (same shape, different trigger mechanism, see §2 "JSON-RPC 2.0 semantic alignment") | ✅ (translated by the adapter layer) |
| `resources/list` | No counterpart; `Manifest.resources` is the list | 🔵 ([capabilities](capabilities.md) §2.2) |
| `resources/read` | `resource_read` → `resource_content` | 🔵 |
| `resources/subscribe` / `unsubscribe` + `notifications/resources/updated` | `resource_subscribe` / `resource_unsubscribe` → `resource_updated` | 🔵 |
| `resources/templates/list` | No counterpart (`ResourceDescriptor` has no template field) | 🔵 gap |
| `prompts/list` | No counterpart; `Manifest.prompts` is the list | 🔵 |
| `prompts/get` | `prompt_get` → `prompt_content` | 🔵 |
| `sampling/createMessage` | `sampling_request` → `sampling_result` (reverse direction) | 🔵 |
| `elicitation/create` | `elicitation_request` → `elicitation_result` (reverse direction) | 🔵 |
| `roots/list` + `notifications/roots/list_changed` | `roots_list` → `roots`; `roots_changed` | 🔵 |
| `notifications/cancelled` / `notifications/progress` | `cancel` / `progress` ([base-protocol](base-protocol.md) §6.3–6.4) | 🔵 |
| `logging/setLevel`, `completion/complete` | No counterpart | — |
| **(no counterpart)** | Publish/subscribe `msp/publish-subscribe`: any node broadcasts on any topic, and the receiver filters locally by wildcard | ✅ |
| **(no counterpart)** | Extensible patterns `msp/multi-round` / `msp/task`; manifest evolution driven by `manifest_update`; node peering (no client / server role is presupposed, either side may initiate) | ✅ |

Normative provision: the mapping **MUST** be behaviour-preserving — a mapped MSP interaction is identical to the original MCP interaction in reachable states, results and error semantics; an implementation **MUST NOT** require the peer to support MSP extension semantics before tool calls can interoperate, and the lowest common denominator for interoperability is TCP + the `Signal` envelope + `msp/request-reply` ([README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §7).

### The mapping is not surjective (this is not a value judgement)

**Every MCP behaviour can be expressed in MSP, but not the other way round.** The last two rows of the table (publish/subscribe, and the extensible patterns with node peering) have no counterpart in MCP, so the mapping is not surjective.

**This is not a value judgement.** It only states that MSP is a more general framework and that MCP semantics are one of its subsets; conversely, MCP holds positions that MSP does not try to replace — ecosystem maturity, SDK coverage and the "model host" role — and the very existence of `msp.mcp` is meant to **include** rather than **replace** ([../whitepaper.md](https://github.com/hxh230802/MSP/blob/master/docs/whitepaper.md) §5.5 item 2).

### JSON-RPC 2.0 semantic alignment

**Conclusion: at the encoding layer MSP does not adopt the JSON-RPC envelope, but it does align semantically with JSON-RPC 2.0 on the "tool call" subset; interoperability relies on an optional `Signal ↔ JSON-RPC` bridge and does not change the core.** ([../DESIGN.md](/design) "Relationship to JSON-RPC 2.0")

| MSP `Signal` | JSON-RPC 2.0 |
|---|---|
| `reqid` | `id` |
| `payload.tool` | `method` |
| `payload.args` | `params` |
| `payload.content` / `payload.structuredContent` | `result` |
| `payload.error` | `error.message` (`error.code` takes a conventional value, such as `-32603` for an internal error); **note**: MCP puts "unknown tool" in the **protocol-error** channel and its specification example uses `-32602`, whereas MSP puts every tool failure into `payload.error` (errors as values, the core never emits codes) — the two differ in the **channel** for this class, see §9 G10 |
| `type: "tool_call"` | request (has an `id`) |
| `type: "tool_result"` | response |

**Two reasons for not adopting the envelope wholesale**: ① **the envelope does not match** — `pattern` / `path` / `source` / `target` are first-class citizens of MSP ([base-protocol](base-protocol.md) §2.1 defines them as top-level fields): `pattern` is the pattern routing key, `path` is the logical address of publish/subscribe, and `source` / `target` are node addressing; squeezing them into `method` / `params` would either lose semantics or take a detour, since `method` is a single string and cannot carry both dimensions of "routing key + tool name". ② **the migration cost is high and the gain narrow** — a wholesale migration would touch `_encode` / `_decode`, `Signal` and the `on_signal` of every pattern, breaking the uniformity of "Everything is a signal", while the gain covers only about **20%** of messages.

**Direction is not a reason.** JSON-RPC 2.0 defines the **shape of a single message** (request / response / notification) and does **not** itself restrict which side initiates; MCP uses it for bidirectional communication, including server-side reverse requests (`sampling/createMessage`, `elicitation/create`, `roots/list`). The claim that "MSP is full-duplex and JSON-RPC is one-way" is therefore **wrong**: the difference between MSP and JSON-RPC lies in the **fields inside the envelope**, not in direction.

**What falls outside the scope of JSON-RPC**: `signal` (JSON-RPC has no publish/subscribe semantics; MCP notifications are a fixed set of protocol events, and applications **MUST NOT** define topics of their own such as "notify me when the timetable changes"); `input_required` / `input_response` (the callee follows up **within the `reqid` of the same call**, see [patterns/multi-round](patterns/multi-round.md) — MCP's `elicitation` can achieve a similar effect, but it starts a **separate** reverse request and **does not continue** the request identity of the original call); `hello` / `ack` (capability exchange carrying a `Manifest`); `manifest_update` (no "peer capability change" semantics); `ping` / `pong` (MSP's heartbeat is **periodic** liveness probing plus liveness-loss determination, see [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.6's `heartbeat_interval` / `heartbeat_timeout`; MCP also has a `ping` request, identical in shape but different in trigger mechanism, and the adapter layer translates each of them).

### The Signal ↔ JSON-RPC mapping table

The table above is the semantic alignment; for an actual **wire-format** conversion (the bridge of §3.3), the field-by-field rules are as follows:

| MSP field | JSON-RPC 2.0 field | Conversion rule |
|---|---|---|
| Envelope `type = "tool_call"` | An object with an `id` | Produce `{"jsonrpc":"2.0","id":…,"method":…,"params":…}` |
| Envelope `type = "tool_result"` | An object with `id` + `result` | Produce `{"jsonrpc":"2.0","id":…,"result":…}` |
| Envelope `reqid` | `id` | **MUST** correspond one-to-one. On the MSP side `reqid` is a string, whereas a JSON-RPC `id` **MAY** be a number, so the reverse mapping **MUST** normalise it to a string (`str(id)`); otherwise MSP's `pending_calls` correlation will mismatch |
| `payload.tool` | `method` | Copy verbatim |
| `payload.args` | `params` | Copy verbatim; when `args` is `{}`, `params` **MAY** be omitted |
| `payload.content` + `payload.structuredContent` | `result` | Put both into `result`; when mapping to MCP's CallToolResult, `content` ↔ `result.content` and `structuredContent` ↔ `result.structuredContent` |
| `payload.error` (a string) | `result.isError = true` | **MUST NOT** be mapped to a JSON-RPC `error` object: in MCP a failed tool execution is an **`isError` inside a successful response** (see §3.1 `MCPServer._run_tool`) |
| `payload.code` / `payload.message` of a `type = "error"` signal | `error.code` / `error.message` | The values on both sides come from the same JSON-RPC conventional values and **MUST** be copied unchanged (§6) |
| Envelope `pattern` / `path` / `source` / `target` / `timestamp` | No counterpart | See §3.3 for the degradation strategy |

### A2A mapping (pointer)

The detailed A2A mapping is in [patterns/task](patterns/task.md#9-equivalence-mapping-to-a2a); this page fixes only one contract: **the Agent Card is projected on demand from `Manifest.pattern_metadata["msp/task"]`**. The write path is `MSPNode.register_pattern("msp/task", metadata=agent_card)` → `Manifest.set_pattern_metadata()`, which appends the pattern ID to `patterns`, stores `metadata` into `pattern_metadata["msp/task"]` and increments `version` ([../src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py)); the serialized key is `patternMetadata`, propagated with `hello` / `ack` / `manifest_update`, and the `Manifest` core does **not** perceive and does **not** validate its format. Projection is the **consumer's** behaviour; it **MUST NOT** require every node to understand A2A, and an implementation that does not recognise the key ignores it by lenient reading ([base-protocol](base-protocol.md) §2.3).

## 3. Messages

### 3.1 The `msp.mcp` adapter layer: real signatures

Package export surface (`__all__` of [../src/msp/mcp/__init__.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/__init__.py)): `MCPClient` / `MCPError` / `MCPServer` / `mount_mcp_tools` / `PROTOCOL_VERSION` / `StdioConnection` / `spawn` / `current_stdio`.

| Component | Real signature / behaviour |
|---|---|
| `MCPClient(conn)` | `conn` only has to implement `send(bytes)` / `receive() -> bytes` / `close()` (the `Connection` of [../src/msp/transport/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/base.py)), and does not care whether the underlying layer is stdio or a future Streamable HTTP. Attributes: `protocol_version`, `server_info`, `capabilities`; the module constant `PROTOCOL_VERSION = "2025-11-25"` |
| `.initialize()` | `-> dict`. Sends `initialize` with `params = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "msp", "version": __version__}}`; stores `protocolVersion` / `serverInfo` / `capabilities`; then sends the **notification** `notifications/initialized`; returns the raw result |
| `.list_tools()` | `-> list`. Sends `tools/list` (`params = {}`) and returns `result["tools"]` (`[]` if absent); if not initialised, calls `initialize()` automatically first |
| `.call_tool(name, arguments)` | `-> dict`. Sends `tools/call` with `params = {"name": name, "arguments": arguments or {}}`; returns the **complete** result (`{content, structuredContent?, isError?}`) without unwrapping it in advance |
| `.close()` | `-> None`. Closes the underlying connection (terminating the child process under stdio); exceptions are swallowed |
| Correlation and errors | `_request()` holds one lock and **serialises** sends, with `reqid = self._counter` (an integer, incremented from `0`); in the read loop, messages whose `id` does not match are **ignored outright** (`continue`). When `error` appears in the result, `MCPError(code, message, data=None)` is raised, with `str(e)` shaped like `MCP error [-32601]: …` |
| `MCPServer(node, conn)` | `node` is an `MSPNode` and `conn` is a `Connection`; `run() -> None` is a sequential read loop: read a line → `jsonrpc.decode` → dispatch → write a line, exiting on `ConnectionClosed`; tools run on worker threads, so a slow tool does not block the read loop |
| `MCPServer` dispatch table | `initialize` (request) → `{"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": {"name": "msp", "version": __version__}}`, and sets `_initialized`; `notifications/initialized` and `ping` (request) → set the flag / reply `{}` respectively; `tools/list` → `{"tools": [...]}` (each item `{name, inputSchema}`, with `description` appended when non-empty); `tools/call` → a worker thread executes `node.protocol._tools[name](**args)` and replies with a CallToolResult; a **request** for any other method replies with `error` (`-32601`, `"unknown method: <method>"`), and any other **notification** is silently ignored; a line that cannot be parsed replies with `error` (`-32700`, `"Parse error"`, `id = null`) |
| Tool result conversion | Reuses the core `_normalize_tool_result()`: `{"sum": 3}` → `result.content = [{"type":"text","text":"{\"sum\": 3}"}]` **and** `structuredContent = {"sum": 3}`; `[{"type":"text","text":"hello"}]` → `content` unchanged, with **no** `structuredContent`; `[1, 2, 3]` → `content = [{"type":"text","text":"[1, 2, 3]"}]`, with **no** `structuredContent` (because it is not a `dict`); a tool raising an exception (including an unknown tool) → `result = {"content": [{"type":"text","text": <exception text>}], "isError": true}` — **a successful response, not a JSON-RPC error** |
| `mount_mcp_tools(node, client)` | `-> list`, returning the names of the tools mounted successfully (in `client.list_tools()` order). Each one goes through `node.tool(name, description=…, input_schema=…)(stub)`, so remote tools **MUST** appear in this node's `Manifest.tools`; `t["name"]` is taken by direct indexing (a missing key raises `KeyError`), and a missing `description` / `inputSchema` becomes `""` / `{}`. The stub passes the argument names through **verbatim** via `client.call_tool(tool_name, kwargs)` (the local side only declares, it does not validate); if `isError` is true → raise `ToolError(<the text blocks in content joined with "\n"> or "MCP tool execution failed")`, otherwise return `structuredContent` when it is not `None`, else return the `content` list. It does **not** close `client`; the lifecycle is the caller's responsibility |
| `spawn(command, args=None, env=None)` | `-> StdioConnection`. When `command` is a list / tuple it is used as argv verbatim (recommended, to avoid shell parsing); when it is a string it is joined with `args` into `[command, *args]`; `subprocess.Popen(argv, stdin=PIPE, stdout=PIPE, env=env)` — **stderr is not redirected**, so the child's stderr directly inherits the parent's; `env=None` inherits the parent environment |
| `StdioConnection(reader, writer, proc=None)` | Framing is **newline-delimited**: `send(data)` writes `data + b"\n"` then `flush()`; `receive()` reads one line and `rstrip(b"\r\n")`. `close()` is idempotent: while `proc` is alive it first `terminate()`s it, waits `2.0` s, `kill()`s it if it has not exited and waits `2.0` s more, then closes `writer` and `reader` in that order; when already closed, or on `OSError` / `ValueError`, `send` / `receive` raise `ConnectionClosed` |
| `current_stdio()` | `-> StdioConnection`. Wraps the **current process's** `sys.stdin.buffer` / `sys.stdout.buffer` into a connection (`proc=None`, `close()` only closes the streams and does not kill the process), for the case where "an MSP node is launched as a child process by an external MCP client" |
| `jsonrpc.py` | `PARSE_ERROR` / `INVALID_REQUEST` / `METHOD_NOT_FOUND` / `INVALID_PARAMS` / `INTERNAL_ERROR` = `-32700` / `-32600` / `-32601` / `-32602` / `-32603`; `encode(obj) -> bytes` uses compact separators + `ensure_ascii=False`; `decode(data) -> dict` only does `json.loads` and **does not validate** the `jsonrpc` member or the message shape; `make_request(reqid, method, params=None)` (`params` is attached only when not `None`), `make_result(reqid, result)`, `make_error(reqid, code, message, data=None)`, `make_notification(method, params=None)` (no `id`) |

Normative provisions: `MCPClient` **MUST** complete `initialize` before `tools/call` / `tools/list` (the reference implementation does it automatically via `_ensure_initialized()`), and **MUST NOT** be assumed able to answer reverse requests initiated by an MCP server (the reference implementation ignores them silently, see §9 gap G2); a tool failure in `MCPServer` **MUST** be expressed as `result.isError = true` and **MUST NOT** reply with a JSON-RPC `error`, while on success it **SHOULD** omit `isError`; when `spawn` is given a list / tuple it **MUST** use it as argv verbatim and **MUST NOT** perform shell parsing again.

### 3.2 A runnable example

Consistent with the "MCP interoperability (adapter)" subsection of [../../README.zh-CN.md](https://github.com/hxh230802/MSP/blob/master/README.zh-CN.md):

```python
from msp import MSPNode
from msp.mcp import MCPClient, spawn, mount_mcp_tools

# MSP → MCP: call a local MCP server (stdio child process)
client = MCPClient(spawn(["npx", "-y", "@modelcontextprotocol/server-filesystem"]))
print(client.list_tools())
print(client.call_tool("read_file", {"path": "/tmp/a.txt"}))

# Bridging: mount the tools of the MCP server above onto this node, so other MSP nodes can call them
node_a = MSPNode("node_a")
mount_mcp_tools(node_a, client)
node_b.call("node_a", "read_file", {"path": "/tmp/a.txt"})

# MCP → MSP: run the node as an MCP server; an external MCP client starts this process over stdio
#   from msp.mcp import MCPServer, current_stdio
#   MCPServer(node, current_stdio()).run()
```

### 3.3 Design of the optional codec bridge (🔵)

**Positioning**: the bridge sits **above the transport** and is pluggable just like a transport, **without changing the core** ([../DESIGN.md](/design) "The interoperability hook: optional codec bridge"). Its implementation form is a decorator wrapping a `Connection`: `send()` turns the JSON bytes of an MSP `Signal` into JSON-RPC bytes and `receive()` translates in the opposite direction; the core's `Signal`, `_encode` / `_decode` and every pattern's `on_signal` are not changed by a single line.

**Conversion rules**: move field by field according to §2's "Signal ↔ JSON-RPC mapping table". Mandatory provisions: ① `reqid` ↔ `id` **MUST** correspond one-to-one, and a JSON-RPC `id` that is not a string **MUST** be normalised to a string before being filled into `reqid`; ② `payload.tool` ↔ `method` and `payload.args` ↔ `params` **MUST** be moved verbatim, and **MUST NOT** be renamed or wrapped; ③ `payload.content` / `payload.structuredContent` ↔ `result` **MUST** be moved with their structure preserved; ④ the `jsonrpc` member **MUST** be produced by the bridge (`"2.0"`), and when a received message lacks it or its value is not `"2.0"` the bridge **SHOULD** log it but **MUST NOT** discard the message ([base-protocol](base-protocol.md) §2.3).

**Degradation strategy for fields with no counterpart**: `pattern` / `path` / `source` / `target` / `timestamp` have no place in the JSON-RPC envelope. The bridge **MUST** put them into the **top-level member `_msp`** of the JSON-RPC message (as one object), and **MUST NOT** mix them into `params` — `params` corresponds one-to-one with business arguments, and mixing them in would pollute the tool arguments. If the peer strictly rejects unknown top-level members, the bridge **MAY** be configured to drop `_msp`; when dropping, `source` / `target` **SHOULD** be inferred from the connection identity, `pattern` **SHOULD** take the core pattern `msp/request-reply`, and that pattern **MUST** be explicitly enabled in the bridge's configuration. **Message types** that cannot be mapped (`signal`, `manifest_update`, `input_required` / `input_response`, and the capability-surface signals defined by [capabilities](capabilities.md)): the bridge **MUST** drop them, **MUST** record them in a counter, and **MUST NOT** fabricate a `method` to force them into JSON-RPC; dropping is **silent** (no bytes are produced), because the JSON-RPC side has no error object to reply with. Exception: counterparts that do exist on the MCP side **SHOULD** be mapped — `notifications/cancelled` ↔ `cancel`, `notifications/progress` ↔ `progress`, `notifications/resources/updated` ↔ `resource_updated`, `notifications/roots/list_changed` ↔ `roots_changed` (the latter two depend on [capabilities](capabilities.md) being delivered).

**Error mapping**: in the MSP → JSON-RPC direction, the `payload.code` / `payload.message` of an `error` signal → `error.code` / `error.message`, and `payload.data` (if any) → `error.data`; a non-empty `tool_result.payload.error` → **`result` + `isError: true`** (consistent with `MCPServer._run_tool`), and **MUST NOT** be mapped to an `error` object. In the JSON-RPC → MSP direction, `error.code` ∈ `-32000` ~ `-32099` **MUST** be passed through unchanged and **MUST NOT** be rewritten to `-32603`; `error.data` **MAY** be placed in `error.payload.data`, and the receiver **SHOULD** ignore this unknown field.

**Testing approach** (runnable, reusing existing facilities): ① in-process pipes — `_pipe_pair()` in `tests/test_mcp.py` builds two unidirectional pipes joined into a full duplex, and with the bridge wrapped in between the bytes can be asserted directly; ② a fake subprocess peer — `spawn([sys.executable, "-c", script])` starts a script that only echoes JSON-RPC (`test_spawn_echo_roundtrip` uses exactly this mode); ③ round-trip invariants — for `tool_call` / `tool_result` / `error`, assert `decode(encode(bridge(x))) == x` (fields equal verbatim); ④ drop invariants — for `signal` / `manifest_update`, assert "no bytes + counter +1"; ⑤ no regression — with the bridge disabled, behaviour is verbatim identical to the status quo.

## 4. Message flow

### MSP node ←→ `MCPServer` ←→ external MCP client

```text
  external MCP client           child process (MSP node)           MSP network
   │ spawn([python, "-c", …]) ──▶ │ ← launched by the client
   │ ─ initialize ──────────────▶ │ MCPServer._initialize()
   │ ◀ {protocolVersion,          │
   │    capabilities:{tools:{}},  │
   │    serverInfo:{name:"msp"}}  │
   │ ─ notifications/initialized▶ │ sets _initialized
   │ ─ tools/list ──────────────▶ │ _list_tools()
   │ ◀ {tools:[{name,inputSchema,…}]} ← translates node.manifest.tools
   │ ─ tools/call ──────────────▶ │ worker thread _run_tool()
   │   {name, arguments}          │ func(**args) + _normalize_tool_result()
   │ ◀ {content:[…],              │
   │    structuredContent?:{…}}   │
   │  when the tool raises:       │
   │ ◀ {content:[{type:text,…}],  │ result.isError = true
   │    isError:true}             │ (not a JSON-RPC error)
```

### The bridging path of `mount_mcp_tools`

```text
  MSP node B            MSP node A                    MCP server (child process)
   │                     │ mount_mcp_tools(A, client)    │
   │                     │ ├ client.list_tools() ──────▶ │
   │                     │ │ ◀── tools:[{name,…}]        │
   │                     │ └ node.tool(name)(stub)       │
   │                     │    writes A.manifest.tools    │
   │ finds A (dir/direct)│                               │
   │ ─ tool_call ───────▶│ A's core request-reply path   │
   │   {tool:"read_file"}│ stub(**kwargs)                │
   │                     │ └ client.call_tool() ───────▶ │ tools/call
   │                     │    ◀── {content, …}           │
   │ ◀ tool_result ──────│ structuredContent first,      │
   │   {content,structured} else the content block list; │
   │                     │ isError → ToolError → payload.error
```

The point: bridging adds **no** new signal type or path on the MSP side — a remote tool is just an ordinary MSP tool, and `B` does not need to know at all that there is MCP behind it.

### The position of the codec bridge (🔵)

```text
  MSPProtocol ── Signal ──▶ _encode() ──▶ [ codec bridge ] ──▶ Connection ──▶ wire
                                            send: Signal JSON → JSON-RPC JSON
                                            recv: JSON-RPC JSON → Signal JSON
                                            no counterpart field → top-level _msp
                                            no counterpart type → drop + count
```

## 5. Data types

### 5.1 The MCP side (verbatim from the source and from MCP's established field names)

request = `{"jsonrpc": "2.0", "id": <int | str>, "method": <str>, "params"?: <object>}`; result = `{"jsonrpc": "2.0", "id": …, "result": <any>}`; error = `{"jsonrpc": "2.0", "id": …, "error": {"code": <int>, "message": <str>, "data"?: <any>}}`; notification = `{"jsonrpc": "2.0", "method": <str>, "params"?: <object>}` (no `id`).

| Name | Shape |
|---|---|
| Tool descriptor | `{"name": <str>, "inputSchema": <object>, "description"?: <str>}` |
| CallToolResult | `{"content": [<ContentBlock>], "structuredContent"?: <object>, "isError"?: <bool>}` |
| `initialize` result | `{"protocolVersion", "capabilities": {"tools": {}}, "serverInfo": {"name", "version"}}` |
| `initialize` parameters | `{"protocolVersion", "capabilities": {}, "clientInfo": {"name": "msp", "version": "0.1.0"}}` |

### 5.2 The MSP side

The `Signal` envelope is snake_case (`type` / `source` / `pattern` / `target` / `path` / `reqid` / `payload` / `timestamp`), with field-level provisions in [base-protocol](base-protocol.md) §2; inside `payload` it is mostly camelCase (such as `structuredContent`). The JSON shapes involved here: `ToolDescriptor` = `{"name", "description", "inputSchema", "outputTypes", "annotations"}`; `Manifest` = `{"version", "patterns", "patternMetadata", "capabilities", "signals", "tools", "resources", "prompts", "clientCapabilities": {"sampling", "elicitation", "roots"}}`; for content blocks see `text` / `image` / `audio` / `resource` / `resource_link` / `blob_ref` in [../src/msp/core/content.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py).

### 5.3 Transport-side interoperability: Streamable HTTP (✅ carrier / 🔵 SSE long stream)

Another MCP transport. **The carrier is implemented** (`src/msp/mcp/http.py`, in both the client and the server direction), and every provision in the table below is landed except the **`GET` SSE long stream**:

| Item | Provision |
|---|---|
| Endpoint | A single HTTP endpoint (such as `/mcp`); multiple paths **MUST NOT** be required to distinguish operations |
| Request | `POST` carries **one** JSON-RPC message; `Accept` **MUST** include both `application/json` and `text/event-stream` |
| Response | `Content-Type: application/json` returns a single response, or `text/event-stream` (SSE) carries the response to that request **and** subsequent server→client messages |
| Session | The `initialize` response **MAY** carry `Mcp-Session-Id`; subsequent requests **MUST** echo that header; `DELETE` terminates the session; `GET` **MAY** open an SSE stream carrying only server→client messages |
| Version and authentication | Requests **SHOULD** carry the `MCP-Protocol-Version` header; reply `401` when authentication is required, handled by MCP's OAuth flow — HTTP authentication **MUST NOT** be equated with MSP authorization ([security](security.md)) |

The real obstacle to plugging this into MSP (recorded as it is): `Connection` ([../src/msp/transport/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/base.py)) is a **single-message** abstraction of "one `send(bytes)` ↔ one `receive() -> bytes`", whereas one HTTP `POST` of Streamable HTTP may return several SSE frames, and server→client messages may arrive independently on another `GET` stream.

**What is already landed** ([../src/msp/mcp/http.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/http.py)): a single endpoint; one message per `POST`; `Accept` declaring both `application/json` and `text/event-stream`; `Mcp-Session-Id` and `MCP-Protocol-Version` filled back in; `DELETE` terminating the session; a 16 MiB limit on the request body plus an overall read deadline (a socket-level timeout alone cannot stop an "infinitely slow" sender).

**What is deliberately not done**: the `GET` SSE long stream — that is, server→client unsolicited messages. Its **precondition** is "a receive abstraction that dispatches by JSON-RPC `id`" (a read thread plus a pending table), or a multiplexing abstraction above `Connection`, and the send/receive model of this adapter layer cannot support it. `GET` therefore replies explicitly with **`405 + Allow: POST, DELETE`** — a clear refusal rather than pretending to accept and then sending nothing; if a `POST` response contains SSE frames that carry anything **other than this response**, only the frame for this response is taken, and the rest are dropped and counted (`dropped_sse_frames`).

The `Signal` envelope and the core routing **MUST NOT** be modified in order to plug in this transport. G4 in §9 has now narrowed to "the `GET` SSE long stream is unimplemented".

## 6. Error handling

### 6.1 The two error spaces and the conversion rules

On the MSP side the error space is `payload.code` / `payload.message` of the `error` signal, and tool failures go through `tool_result.payload.error` ([base-protocol](base-protocol.md) §6.1–6.2); on the MCP / JSON-RPC side it is `{"error": {"code", "message", "data"?}}`, and tool failures go through `result.isError = true` (§3.1). The two are **of the same origin**: MSP's error codes take JSON-RPC's conventional values directly ([README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.4), so `-32600` / `-32601` / `-32602` / `-32603` are synonymous on both sides **as numbers**, and conversion **MUST** copy them unchanged. **But numerical synonymy does not mean channel agreement**: MCP classifies "unknown tool" and "malformed request" as **protocol errors** (its specification examples use `-32602` for an unknown tool), whereas the MSP core always writes a failed tool execution as a `payload.error` string and never emits codes (the `MCPServer` of §3.1 also replies to an unknown tool with `result.isError = true`). An implementation **MUST NOT** assume "protocol errors never occur on the MSP side" or "every tool failure on the MCP side carries `isError`"; across a bridge it **MUST** explicitly decide which channel an unknown tool takes and record that in the implementation documentation (see §9 G10).

| Scenario | Rule |
|---|---|
| MCP `tools/call` raises | → `result = {"content": [{"type":"text","text": <exception text>}], "isError": true}`; **MUST NOT** reply with a JSON-RPC `error` (the actual behaviour of `MCPServer._run_tool`) |
| MSP `tool_result.payload.error` non-empty | → MCP `result` + `isError: true` (when the bridge runs in the MSP→MCP direction) |
| MSP `error` signal ↔ JSON-RPC `error` | `code` / `message` copied unchanged; in the reverse direction `reqid` fills back `id`; `-32000` ~ `-32099` passed through unchanged |
| `MCPClient` receives `error` | raises `MCPError(code, message, data)`, with `data` preserved as is |
| MSP unknown `type` | reply `error` (`-32600`); the connection **MUST NOT** be dropped ([base-protocol](base-protocol.md) §2.3) |
| MCP unknown method | the request form replies `error` (`-32601`, `"unknown method: <method>"`); the notification form is **silently ignored** |
| A line that cannot be parsed | reply `error` (`-32700`, `"Parse error"`, `id = null`) |
| Remote failure of `mount_mcp_tools` | remote `isError` → local `ToolError` → MSP-side `tool_result.payload.error` |

Normative provision: the adapter layer **MUST NOT** swallow errors — every failure **MUST** appear in one of the two spaces of the table above; and it **MUST NOT** reply with a JSON-RPC `error` while also returning a partial `result`.

## 7. Summary of normative provisions (MUST/SHOULD list)

**MUST**: ① `MCPClient` completes `initialize` before `tools/call` / `tools/list` and sends `notifications/initialized` (§3.1); ② `MCPServer` expresses a tool failure as `result.isError = true` and **MUST NOT** reply with a JSON-RPC `error`, and replies `-32601` to a request for an unknown method (§3.1, §6.1); ③ `structuredContent` is produced only when the normalised result is a `dict`, other types stay in the `content` block (§3.1); ④ every remote tool mounted by `mount_mcp_tools` is registered in this node's `Manifest.tools` (§3.1); ⑤ `spawn` uses a list / tuple as argv verbatim (§3.1); ⑥ `StdioConnection` frames as "one line, one message": sending appends `\n` and `flush`es, receiving strips `\r\n` (§3.1); ⑦ error codes are copied unchanged, and `-32000` ~ `-32099` **MUST NOT** be rewritten (§2 "Signal ↔ JSON-RPC mapping table", §6.1); ⑧ the codec bridge puts fields with no counterpart into the top-level `_msp` and **MUST NOT** mix them into `params`, and drops unmappable message types while counting them, and **MUST NOT** fabricate a `method` (§3.3); ⑨ the "MCP ⊆ MSP" mapping is behaviour-preserving, and "not surjective" **MUST NOT** be presented as a value judgement (§2).

**SHOULD**: ⑩ `MCPServer` omits `isError` in a successful response (§3.1); ⑪ the bridge logs a `jsonrpc` member that is missing or not `"2.0"` without dropping the message (§3.3); ⑫ a Streamable HTTP request carries the `MCP-Protocol-Version` header and fills back `Mcp-Session-Id` (§5.3); ⑬ the Agent Card is projected on demand by the consumer, and the whole network **MUST NOT** be required to understand it (§2 "A2A mapping").

**MUST NOT**: ⑭ adapter-layer code enters the core modules of `src/msp` (§1, §3.1); ⑮ assume that `MCPClient` can answer reverse requests from an MCP server (§3.1, §9); ⑯ use "MSP is full-duplex and JSON-RPC is one-way" as a reason for not adopting the envelope — direction is not a reason (§2 "JSON-RPC 2.0 semantic alignment"); ⑰ modify the `Signal` envelope or the core routing in order to plug in Streamable HTTP (§5.3); ⑱ `mount_mcp_tools` closes `client` on the caller's behalf (§3.1).

**MAY**: ⑲ the bridge omits `params` when `payload.args` is `{}` (§2 "Signal ↔ JSON-RPC mapping table"); ⑳ the bridge is configured to drop `_msp` to accommodate a strict peer, in which case `source`/`target` are inferred from the connection identity and `pattern` takes `msp/request-reply` (§3.3); ㉑ `MCPServer` keeps its read loop running while a tool executes (the reference implementation does this with worker threads) (§3.1); ㉒ `call_tool` returns the complete result and the caller unwraps it itself (§3.1).

## 8. Security considerations

1. **An MCP server is an external process.** What `spawn` executes is an **arbitrary external command**: the command and its arguments **MUST** come from trusted configuration and **MUST NOT** be supplied by a remote MSP peer; `env` **SHOULD** be minimal, and local credentials **MUST NOT** be passed through to the child process. The reference implementation does **not** redirect the child's stderr, so child errors go straight into the parent's stderr — **MUST NOT** print sensitive content on this path.
2. **Prompt injection arrives through the bridge.** `mount_mcp_tools` brings remote `content` back into MSP unchanged, and it may eventually enter a model context; the consumer **SHOULD** label it as external untrusted content (the same reasoning as [capabilities](capabilities.md) §8 item 2).
3. **Authorization is separate from self-description.** `Manifest` and `manifest_update` are self-description, and the adapter layer **MUST NOT** skip the local authorization decision just because a tool appears in the peer's manifest ([README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.5, [security](security.md)).
4. **Tool-name collisions.** `mount_mcp_tools` registers through `node.tool(name)` and **will** overwrite a local tool of the same name, and vice versa; an implementation **SHOULD** provide a namespace prefix or collision detection, and **MUST NOT** silently overwrite and then still claim that both sets of tools are available.
5. **Protocol version.** Since `2026-07-28`, MCP has moved to a stateless per-request envelope (no more `initialize`, `server/discover` instead); this adapter layer follows the classic `initialize` handshake and therefore pins `2025-11-25`, the latest version of the handshake series. It **MUST NOT** claim support for `2026-07-28` and later revisions while `server/discover` is unimplemented.
6. **The authentication surface of Streamable HTTP, and the observability of the bridge.** HTTP `401` / OAuth settles transport identity and **MUST NOT** be conflated with MSP authorization (§5.3); silently dropping `signal` / `manifest_update` creates the illusion that "the message looked as if it went out", so the bridge **MUST** expose a counter or a log, and operations **SHOULD** monitor it.

## 9. Known gaps

| # | Gap | Status | Description |
|---|---|---|---|
| G1 | Only the tools capability is covered (the transport is no longer stdio only) | 🟡 | Only 5 methods are supported: `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`; `resources/*`, `prompts/*`, `sampling/createMessage`, `elicitation/create`, `roots/list`, `logging/setLevel`, `completion/complete`, `resources/templates/list`, `notifications/tools/list_changed` are all unimplemented and reply `-32601` on receipt |
| G2 | `MCPClient` cannot answer reverse requests initiated by an MCP server | 🟡 | `_request()` ignores messages whose `id` does not match, so sampling / elicitation / roots requests are **silently dropped**; it also therefore **does not** report capabilities (`initialize` always sends `capabilities: {}`) |
| G3 | `MCPServer` handles only `notifications/initialized`; all other notifications are silently ignored | 🟡 | There is no generic handling of `notifications/*` |
| G4 | The **`GET` SSE long stream** of Streamable HTTP is unimplemented | 🔵 | **The `POST` / `DELETE` carrier is implemented** ([../src/msp/mcp/http.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/http.py)), including `Mcp-Session-Id` fill-back and `MCP-Protocol-Version`; `GET` explicitly replies `405 + Allow: POST, DELETE`, and surplus SSE frames in a response are dropped and counted (`dropped_sse_frames`). The precondition is still "a receive abstraction that dispatches by JSON-RPC `id`" (§5.3) |
| G5 | `jsonrpc.decode` performs no validation at all | 🟡 | The value is used directly after `json.loads`; the `jsonrpc` member is not validated and the request / response / notification shapes are not distinguished; `MCPServer` relies on `"id" in msg` to decide whether a message is a request |
| G6 | `mount_mcp_tools` has no namespace and no collision detection | 🟡 | Local tools of the same name overwrite each other (§8 item 4) |
| G7 | No codec bridge | 🔵 | The wire-format conversion `Signal ↔ JSON-RPC` is not implemented yet (§3.3 already defines it in full); current interoperability relies entirely on the `msp.mcp` adapter layer |
| G8 | `MCPClient` has no timeout parameter | 🟡 | `_request()` blocks on `receive()` with no timeout, so an unresponsive peer blocks it forever (MSP's `call(timeout=5.0)` does not apply on this path) |
| G9 | `resources` / `prompts` / `sampling` have no MCP converter; the A2A side provides only a pointer | 🔵 / ✅ | [capabilities](capabilities.md) defines the MSP-side signals, but `msp.mcp` does not translate them (the other face of G1); the Agent Card projection and the full mapping of `msp/task` are in [patterns/task](patterns/task.md), and while that page is not yet delivered the contract in §2 "A2A mapping" of this page governs |
| G10 | The **error channel** for "unknown tool" differs from MCP | 🟡 | MCP classifies "unknown tool" and "a request that does not satisfy the CallToolRequest schema" as **protocol errors** (JSON-RPC `error`; the MCP specification example available to MSP uses `-32602` for an unknown tool), whereas the MSP core always writes tool failures into `tool_result.payload.error` and **never emits codes**, and the `MCPServer` of §3.1 also replies to an unknown tool with `result.isError = true`. "Error codes copied unchanged" therefore covers only **numerical synonymy**, not channel choice: a cross-bridge implementation **MUST** explicitly decide which channel an unknown tool takes and state it in the documentation, and **MUST NOT** assume the two sides agree (§2 mapping table, §6.1) |
| G11 | MCP's tool-name character set is wider than MSP's | 🟡 | MCP recommends tool names of 1–128 characters, case-sensitive, allowing `A-Za-z0-9_-.` (all `SHOULD`); MSP's [naming rules](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#53-命名规范) restrict tool names to `[a-z0-9_-]+` (**MUST**, no upper case, no dot). `mount_mcp_tools` uses the remote `name` verbatim for registration, so mounting tools such as `getUser` / `admin.tools.list` produces local tool names that **violate MSP's own grammar** — the local dictionary lookup still hits them, but the manifest and other implementations cannot parse them according to the specification. An implementation **SHOULD** map names (lower-case uniformly, `.` → `_`, etc.) or refuse and document it, and **MUST NOT** silently register violating names |

## 10. Reference implementation map

| Provision | Status | Source file and symbol |
|---|---|---|
| §3.1 all signatures of `MCPClient` | ✅ | [../src/msp/mcp/client.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/client.py) `MCPClient` / `.initialize` / `.list_tools` / `.call_tool` / `.close` / `._request` / `._notify` / `._ensure_initialized`; `MCPError`; `PROTOCOL_VERSION` |
| §3.1 `MCPServer` dispatch and result conversion | ✅ | [../src/msp/mcp/server.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/server.py) `MCPServer` / `.run` / `._dispatch` / `._initialize` / `._list_tools` / `._on_tool_call` / `._run_tool` / `._reply` |
| §3.1 tool-result normalisation | ✅ | [../src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `_normalize_tool_result` |
| §3.1 `mount_mcp_tools` | ✅ | [../src/msp/mcp/bridge.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/bridge.py) `mount_mcp_tools` / `_content_text` |
| §3.1 `spawn` / `StdioConnection` / `current_stdio` | ✅ | [../src/msp/mcp/stdio.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/stdio.py) `spawn` / `StdioConnection` / `.send` / `.receive` / `.close` / `current_stdio` |
| §3.1 JSON-RPC encoding/decoding, error-code constants and export surface | ✅ | [../src/msp/mcp/jsonrpc.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/jsonrpc.py) `encode` / `decode` / `make_request` / `make_result` / `make_error` / `make_notification` and the five error-code constants; [../src/msp/mcp/__init__.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/__init__.py) `__all__` |
| §3.1 connection abstraction | ✅ | [../src/msp/transport/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/base.py) `Connection` / `ConnectionClosed` |
| §2 "MCP ⊆ MSP" (handshake and manifest exchange); MSP-side tool calls | ✅ | [../src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `handshake_outbound` / `handshake_inbound` / `push_manifest` / `_on_manifest_update` / `call` / `_on_tool_call` / `_run_tool` / `_on_tool_result` |
| §2 "A2A mapping" (`patternMetadata` and the Agent Card) | ✅ | [../src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `Manifest.set_pattern_metadata` / `to_dict`; [../src/msp/core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `MSPNode.register_pattern` |
| §2 "JSON-RPC 2.0 semantic alignment" (error codes from the same origin) | ✅ | [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.4; [base-protocol](base-protocol.md) §6.2; the five constants of `jsonrpc.py` |
| §3.3 codec bridge | 🔵 not implemented | The planned landing point is a decorator wrapping `Connection`, not entering `src/msp/protocol` or `src/msp/core` |
| §5.3 Streamable HTTP | ✅ carrier / 🔵 SSE long stream | [../src/msp/mcp/http.py](https://github.com/hxh230802/MSP/blob/master/src/msp/mcp/http.py) (client and server carriers); the `GET` SSE long stream is unimplemented |
| Behaviour verification | ✅ | [../tests/test_mcp.py](https://github.com/hxh230802/MSP/blob/master/tests/test_mcp.py) `StdioConnectionTest` / `MCPInProcessTest` / `MCPSubprocessTest` / `MCPBridgeTest` |

Behaviours already verified by the tests (usable as verifiable anchors for the provisions): `initialize` returns `protocolVersion == "2025-11-25"` with `capabilities` containing `tools`; `tools/list` returns `add` / `greet` / `nums`; `tools/call` gives `structuredContent` for a dict result, `content` for a list of content blocks, **no** `structuredContent` for a non-dict result (`[1, 2, 3]`), and `isError: true` for an unknown tool; the subprocess end-to-end path `MCPServer(node, current_stdio()).run()` + `MCPClient(spawn([...]))` completes `initialize` / `tools/list` / `tools/call`; `mount_mcp_tools(a, client)` returns `["add"]`, and MSP node `b` can do `b.call("A", "add", {"x": 1, "y": 2}).unwrap() == {"sum": 3}`.
