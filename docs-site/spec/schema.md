# MSP Data Model Reference — Complete Field Definitions in JSON Form

| | |
|---|---|
| **Protocol revision** | `2026-10-10` |
| **Status** | ✅ Implemented (all fields and serialized forms of `Signal` / `Manifest` / `Endpoint` / content blocks / `Preset`; planned fields such as `grants` are marked 🔵) |
| **Defined on this page** | All data models used by the messages on the various pages: the `Signal` envelope, `Manifest` and the four descriptors, `Endpoint`, the declaration file, content blocks, `ToolResult`, the core and pattern-private payloads, the projection rules of `schema_from_func`, `Preset` and the built-in presets |

> For normative terminology and status markers see [Specification Index §2](index.md#2-normative-language); **bold** keywords in the body carry normative force.
>
> **The authoritative source of fields is [`schema/2026-10-10/msp.yaml`](https://github.com/hxh230802/MSP/blob/master/schema/2026-10-10/msp.yaml)** — field names, types, requiredness, defaults, constraints, and the binding from `Signal.type` (+`pattern`) to payload are defined only in that one file; [`msp.schema.json`](https://github.com/hxh230802/MSP/blob/master/schema/2026-10-10/msp.schema.json) (JSON Schema 2020-12) is generated from it for third-party implementations and validators to consume, and the generated artifact **MUST NOT** be edited by hand.
>
> **This page is its explanatory view**: it is responsible for explaining "why it is designed this way" and "which pitfalls exist when serializing"; the field list **MUST NOT** be copied again elsewhere. When the two disagree, **the YAML prevails**, and that is treated as a defect in this page — `tools/check_schema_drift.py` reports inconsistencies across "authoritative source ↔ reference implementation ↔ this page", and `tests/test_schema_source.py` turns them into test failures.

---

## 1. Overview

### Type notation conventions

| Notation | Meaning |
|---|---|
| `string` / `integer` / `number` / `boolean` | JSON scalars: string / integer / number (including floating point) / boolean |
| `object` | JSON object (a map with string keys) |
| `array<T>` | JSON array whose element type is `T`; `array<string>` is an array of strings |
| `map<K, V>` | object keyed by `K` with values `V` (still an `object` after serialization) |
| `A \| B` | union type: the value is one of `A` or `B` |
| `null` | JSON `null` |
| `T?` (e.g. `string?`) | optional field: the message **MAY** omit it or set it to `null` |
| `any` | any JSON value (object, array, scalar or `null`) |

The "Required" column describes requiredness in the **message**; the "Default" column describes the semantics the **reader** **MUST** adopt when the field is absent — it does not require the sender to omit the field: the reference implementation's `Signal.to_dict()` writes all 8 keys (including `null`), and the receiver **MUST** tolerate both an explicit `null` and absence.

### General serialization rules

1. **Naming-style zoning**: the 8 fields of the `Signal` envelope are **snake_case**; fields inside `payload`, `Manifest` and its descriptors, and most MSP extension fields in content blocks are **camelCase** (e.g. `structuredContent`, `inputSchema`, `taskId`, `blobId`). Field names **MUST** be identical verbatim and **MUST NOT** be mixed.
2. **Encoding**: JSON text, UTF-8; the reference implementation uses `json.dumps(..., ensure_ascii=False)`, so non-ASCII is transmitted as-is.
3. **Framing**: TCP / UDS use a 4-byte big-endian length prefix + payload; WebSocket uses binary frames; the per-message limit is 16 MiB.
4. **Lenient reading**: unrecognised fields, signal types, content block types and pattern IDs **MUST NOT** be treated as protocol errors that drop the connection ([README §7](index.md#7-conformance)).
5. **Key order is meaningless**: except that `Manifest.capabilities` is implemented as `sorted`, key order carries no semantics.

---

## 2. Models and contracts

### Signal envelope

`Signal` is the unified data atom of "everything is a signal": handshake, broadcast, tool call, task and heartbeat are all its instances, differing only in `type`.

| Field | Type | Required | Default | Semantics and constraints |
|---|---|---|---|---|
| `type` | `string` | yes | — | Signal type: one of the 9 core values of `SignalType`, or a pattern-private type (**MUST** carry `pattern` as well) |
| `source` | `string` | yes | — | Sender `node_id`, `[a-z0-9_-]+` ([README §5.3](index.md#53-naming-rules)) |
| `pattern` | `string?` | no | `null` | **Routing key**: the pattern ID. Usually `null` for core signals; pattern-private signals **MUST** carry it |
| `payload` | `object` | no | `{}` | Type-dependent payload; the structure is determined by `type` + `pattern` (see §3) |
| `target` | `string?` | no | `null` | Target `node_id`, an advisory field; not set for broadcast and handshake |
| `path` | `string?` | no | `null` | Logical path of the signal, dot-separated, domain first (`notify.web.download`); **MUST** be filled for the `signal` type |
| `reqid` | `string?` | no | `null` | Request correlation ID; `tool_call` and `tool_result` **MUST** carry the same value |
| `timestamp` | `number` | no | time of sending | Unix seconds (floating point) |

- `type` and `source` are the **only two** fields without defaults: if either is missing, `Signal.from_dict` raises `KeyError` → read-loop exception → the connection is dropped.
- `pattern` is a **routing key**, not a recipient: `_dispatch` first checks whether `type` is a core signal, then whether `pattern` hits a registered pattern handler, and finally falls back to core handling (an unknown `pattern` **MUST NOT** cause a disconnect, see §6).
- `payload` **MUST** be an object; array or scalar payloads **MUST NOT** be placed directly in `payload` and need a wrapper layer (e.g. `{"items": [...]}`).
- Core patterns **MAY** omit `pattern` (the reference implementation uses `null`), and **MAY** also carry `msp/request-reply` / `msp/publish-subscribe`; both forms **MUST** be accepted.

```json
{"type": "tool_call", "source": "node_a", "pattern": null, "target": "node_b",
 "path": null, "reqid": "9f2c1a4b7e0d3856",
 "payload": {"tool": "get_weather", "args": {"location": "Shanghai"}}, "timestamp": 1791500000.0}
```

### SignalType enumeration and extension rules

`SignalType` defines **9** string constants ([Specification Index §5.1](index.md#51-core-signal-types-signaltype) merges `ping` / `pong` into one row, so that table has only 8 rows):

| `type` | Has `reqid` | `payload` form (authoritative definition in §3) |
|---|---|---|
| `hello` | no | `{"manifest": {...}}` |
| `ack` | no | `{"manifest": {...}}` |
| `signal` | no | any object; the path is in the `path` field |
| `tool_call` | **yes** | `{"tool": <string>, "args": <object>}` |
| `tool_result` | **yes** | `{"content": [...], "structuredContent": <any>}` or `{"content": [], "error": <string>}` |
| `manifest_update` | no | `{"manifest": {...}}` |
| `ping` / `pong` | no | `{}` (empty object) |
| `error` | depends | `{"code": <integer>, "message": <string>}` |

Classification predicates: the request class is `tool_call` / `hello` / `ping`, the response class is `tool_result` / `ack` / `pong`; `signal` / `manifest_update` / `error` belong to neither class.

**Extension rules for pattern-private types**:

- A pattern **MAY** define private types (current ones: `input_required` / `input_response`, and the 9 `task_*`), sharing the same `type` field space with core types.
- A pattern-private message **MUST** carry `pattern` (with a value equal to that pattern's ID), otherwise the receiver cannot route it; the receiver **MUST NOT** drop the connection because `type` is unknown, and **SHOULD** follow the unknown-pattern rules in [patterns.md](./patterns.md).
- The `msp/` prefix is reserved by this specification; third-party patterns **MUST** add their own prefix to private types (e.g. `acme_stream_chunk`).
- The same type name **MAY** have different semantics in different patterns: `input_required` is defined in both `msp/multi-round` and `msp/task`, distinguished by `pattern`.

### Manifest

`Manifest` is a node's self-described capability manifest; it belongs to the node rather than to the protocol; the protocol layer only exchanges it during the handshake and pushes it when it changes.

#### Top-level fields

**The serialized form is camelCase**; the four capability lists are **arrays**, not objects; `capabilities` is an **ordered** (`sorted`) array of strings; `clientCapabilities` is an object with three booleans.

| Field | Internal type | Wire format type | Default | Semantics |
|---|---|---|---|---|
| `version` | `int` | `integer` | `0` | Monotonically increasing version number, incremented only when the content changes (see below) |
| `patterns` | `list[str]` | `array<string>` | `[]` | Pattern IDs supported by this node |
| `patternMetadata` | `dict[str, dict]` | `object` | `{}` | `pattern_id` → arbitrary object; the format is defined by the pattern, and the manifest neither interprets nor validates it |
| `capabilities` | `set[str]` | `array<string>` | `[]` | Capability bits, values `pub` / `sub` / `req` / `rep`; `sorted` on serialization |
| `signals` | `dict[str, SignalDescriptor]` | `array<object>` | `[]` | Published signal paths (internally keyed by `path`) |
| `tools` | `dict[str, ToolDescriptor]` | `array<object>` | `[]` | Tools provided (internally keyed by `name`) |
| `resources` | `dict[str, ResourceDescriptor]` | `array<object>` | `[]` | Readable / subscribable resources (internally keyed by `uri`) |
| `prompts` | `dict[str, PromptDescriptor]` | `array<object>` | `[]` | Predefined prompt templates (internally keyed by `name`) |
| `clientCapabilities` | three `bool` | `object` | three `false` | `{"sampling": …, "elicitation": …, "roots": …}` |

- `signals` / `tools` / `resources` / `prompts` **MUST** be arrays. `from_dict` **iterates them item by item**: if the peer writes them as an object map, iteration yields the string keys and raises `TypeError`, and the handshake then fails.
- The `sorted` on `capabilities` is only normalisation: its value has set semantics, so the reader **MUST NOT** rely on the order, and **MUST NOT** disconnect on seeing capability bits that are not listed.
- `clientCapabilities` **MUST** be an object (three booleans) and **MUST NOT** be written as an array.
- The keys of `patternMetadata` **SHOULD** also appear in `patterns` (`set_pattern_metadata` fills them in automatically).

```json
{"version": 3, "patterns": ["msp/publish-subscribe", "msp/request-reply", "msp/task"],
 "patternMetadata": {}, "capabilities": ["pub", "rep", "req", "sub"],
 "signals": [{"path": "notify.web.download", "description": "Download complete notification"}],
 "tools": [{"name": "get_weather", "description": "Look up the weather",
            "inputSchema": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]},
            "outputTypes": [], "annotations": {}}],
 "resources": [], "prompts": [],
 "clientCapabilities": {"sampling": false, "elicitation": false, "roots": false}}
```

#### Exact fields of the four descriptors

**`SignalDescriptor`** (keyed by `path`): `path` (`string`, required, always present), `schema` (`object`, present **only when non-empty**), `description` (`string`, present **only when non-empty**).

**`ToolDescriptor`** (keyed by `name`, five fields **always present**): `name` (`string`, `[a-z0-9_-]+`), `description` (`string`, may be `""`), `inputSchema` (`object`, may be `{}`; generated by `schema_from_func` when absent), `outputTypes` (`array<string>`, may be `[]`), `annotations` (`object`, may be `{}`).

**`ResourceDescriptor`** (keyed by `uri`, five fields **always present**): `uri` (`string`), `name` (`string`), `description` (`string`), `mimeType` (`string`), `subscribable` (`boolean`, default `false`).

**`PromptDescriptor`** (keyed by `name`, three fields **always present**): `name` (`string`), `description` (`string`), `arguments` (`array<object>`, may be `[]`; the internal structure of the elements is **not** defined by this revision, and the reference implementation passes it through verbatim).

**Form differences**: only `SignalDescriptor` performs **conditional omission** for an empty `schema` / `description`; the other three descriptors write all fields unconditionally. The reading side always falls back to defaults.

#### Manifest changes and version

`version` is a monotonically increasing **change counter**, not a timestamp and not a content hash.

| Operation | When `version` is incremented |
|---|---|
| `add_signal(path, schema, description)` | If `path` already exists and the new descriptor is **equal** → return immediately, **no** increment (deduplication short-circuit); otherwise write and `+1` (a content change also counts as a change) |
| `remove_signal(path)` | Delete and `+1` only when present |
| `add_tool(descriptor)` | Write **unconditionally** and `+1` (even when identical to the existing descriptor) |
| `remove_tool(name)` | `+1` only when present |
| `add_resource(descriptor)` / `remove_resource(uri)` | Same as above: writing is unconditionally `+1`, removal is `+1` only when present |
| `add_prompt(descriptor)` / `remove_prompt(name)` | Same as above |
| `add_pattern(pattern_id)` | Append and `+1` only when not already in `patterns` |
| `set_pattern_metadata(pattern_id, metadata)` | **Two change tests**: ① `pattern_id` is not in `patterns` (append); ② the current value differs from `metadata` (replace). If either holds → `+1` (added only once) |
| `apply_diff(diff)` | Does **not** increment; **overwrites** `version` with `diff["version"]` (keeps the original value when the key is missing) |

- `add_tool` / `add_resource` / `add_prompt` have **no** deduplication short-circuit (asymmetric with `add_signal`): registering a descriptor with the same name twice produces a version increment with no content change and a superfluous `manifest_update`.
- `MSPNode.start()` merges `preset.patterns` into `manifest.patterns` (`sorted(set(preset) | set(current))`) and merges `preset.capabilities` into the capability bits (set union). This step does **not** go through the change operations, so it does **not** increment `version`; the whole manifest is then pushed directly.
- Manifest push is a **whole replacement**: `manifest_update.payload.manifest` is the complete `Manifest`; the receiver **MUST** discard pushes whose `version` is not greater than the current value.

#### diff() and apply_diff()

The **exact key names** of `Manifest.diff(old)` are as follows (added / updated entries are descriptor **dictionaries**, removed entries are **sorted arrays of key names**):

| Key | Type | Meaning |
|---|---|---|
| `signals_added` / `signals_updated` | `array<SignalDescriptor>` | present now but not before / present in both but unequal |
| `signals_removed` | `array<string>` | `path` present before but not now (`sorted`) |
| `tools_added` / `tools_removed` / `tools_updated` | same as above (keyed by `name`) | tools |
| `resources_added` / `resources_removed` / `resources_updated` | same as above (keyed by `uri`) | resources |
| `prompts_added` / `prompts_removed` / `prompts_updated` | same as above (keyed by `name`) | prompt templates |
| `version` | `integer` | the `version` of the **new** manifest (not the old value, and not a delta) |

`apply_diff(diff)`: overwrite-writes by `*_added` / `*_updated`, deletes by `*_removed` (a missing key is treated as an empty array), and finally `version = diff.get("version", version)`.

- `diff()` **does not include** `patterns` / `patternMetadata` / `capabilities` / `clientCapabilities`: when those changes need to be transmitted, a full `manifest_update` **MUST** be used.
- `apply_diff` **unconditionally** sets `version` to the value in the diff, lacking the "reject older versions" protection; implementations of cross-machine incremental sync **MUST** add their own version-monotonicity check.
- **Current state (source fact)**: `diff()` / `apply_diff()` have **no call sites** in the reference implementation (they appear only as definitions and implementations inside `manifest.py` across the whole repository). Incremental sync is a **defined but unwired** capability; implementations **MAY** leave it unimplemented.

### Endpoint

| Field | Type | Required | Default | Semantics |
|---|---|---|---|---|
| `transport_type` | `string` | yes | — | Transport backend identifier: `tcp` / `websocket` / `uds` (`quic` is reserved for implementation) |
| `address` | `object` | yes | — | Address object; the keys vary with `transport_type` (see the table below) |
| `node_id` | `string?` | no | `null` | Node identity; may still be unknown at manual discovery |

- `Endpoint` has **no** `to_dict()` / `from_dict()`: it does not go on the wire directly; it is produced by the discovery layer and manually assembled into the declaration file by the announce layer.
- `address_key()` returns `(transport_type, tuple(sorted(address.items())))`; **source fact**: that method has **no call sites**; actual duplicate-discovery suppression is done by the discovery layer's `_known[node_id]` declaration hash. Calling `address_key()` itself does not raise (`sorted` only compares distinct keys); but its **return value**, when used as a `set` / `dict` key, requires the values of `address` to be hashable, so the values of `address` **SHOULD** be simple orderable types (strings / numbers) and **MUST NOT** hold nested objects.

| `transport_type` | `address` form | Notes |
|---|---|---|
| `tcp` | `{"host": "127.0.0.1", "port": 45678}` | `listen` defaults to `host="127.0.0.1"`, `port=0` (dynamic); the actual port is taken from `getsockname` |
| `websocket` | `{"url": "ws://127.0.0.1:45678/msp"}` | `listen` defaults to host `127.0.0.1`, port `0`, path `/msp`; the parser accepts only `ws://` |
| `uds` | `{"path": "/tmp/msp-1234-abcd.sock"}` | Linux / macOS only; by default generates `msp-<pid>-<rand>.sock` in the temp directory with mode `0o600` |
| `quic` 🔵 | undefined | only a comment placeholder in `TRANSPORT_REGISTRY` |

### Declaration file (shared-directory announce)

A node writes its `Endpoint` into a shared directory (default `~/.msp/nodes`), and the scanning side discovers it from there. **Exact JSON form** (three top-level keys, and `endpoint` with exactly two sub-keys):

```json
{"node_id": "node_a",
 "endpoint": {"transport_type": "tcp", "address": {"host": "127.0.0.1", "port": 45678}},
 "timestamp": 1791500000.0}
```

1. **File naming rule**: `{node_id}.json`, located in `nodes_dir` (default `~/.msp/nodes`, and `~` **MUST** be expanded); the scanning side **MUST NOT** read files that are not `*.json`.
2. **`endpoint` contains no `node_id`**: node identity appears only at the top level; the reading side takes only `transport_type` and `address`.
3. **`timestamp` is a lease**: the sender overwrites it per `renew_interval` (default `10.0` s, see [README §5.6](index.md#56-default-parameters)); the receiver discards declarations with `time.time() - timestamp > stale_after` (`DirectoryScan` defaults to `stale_after = 30.0` s). A **missing** `timestamp` is treated as **never expiring**.
4. **Atomic writes**: `{file name}.tmp` **MUST** be written first, then overwritten via `os.replace`, so that a scanning side never reads half a JSON document; the reference implementation uses `json.dump(..., ensure_ascii=False, indent=2)`.
5. **Withdrawal**: `withdraw()` stops renewing the lease and calls `unlink`; a missing file **MUST NOT** raise an error.
6. **Endpoint information only**: local policy (`grants`), keys and any local security configuration **MUST NOT** be written; identity material is exchanged only through handshake messages.
7. **Scan-side validation**: declarations that lack `node_id`, lack `endpoint`, have a `node_id` equal to the scanner itself, or fail JSON parsing **MUST** be skipped without raising an error; unchanged declarations (judged by content hash) **MUST NOT** trigger the added event again.

### Content blocks (ContentBlock)

Content blocks appear in `tool_result.payload.content`, `Artifact.parts` and other places. `annotations` is an optional annotation object that appears in the message **only when non-empty**.

| `type` | Fields | Notes |
|---|---|---|
| `text` | `text`, `annotations?` | Plain text |
| `image` | `data`, `mimeType`, `annotations?` | Image; `data` is Base64-encoded bytes |
| `audio` | `data`, `mimeType`, `annotations?` | Audio; `data` is Base64-encoded bytes |
| `resource` | `resource` (nested object), `annotations?` | Embedded resource; the content is in the nested object |
| `resource_link` | `uri`, `name`, `mimeType`, `description` | Resource reference (URI only); **no** `annotations` field |
| `blob_ref` | `blobId`, `mimeType`, `size`, `checksum` | **MSP extension**: a reference into the separate blob channel |

The nested object of `resource`: `resource.uri` (`string`, required), `resource.mimeType` (`string`, **always present**, may be `""`), `resource.text` (**only when non-empty**), `resource.blob` (Base64, **only when non-empty**).

```json
{"type": "text", "text": "Shanghai 21°C partly cloudy"}
{"type": "resource", "resource": {"uri": "file:///etc/hosts", "mimeType": "text/plain", "text": "127.0.0.1 localhost"}}
{"type": "resource_link", "uri": "file:///var/log/app.log", "name": "app.log", "mimeType": "text/plain", "description": "Application log"}
{"type": "blob_ref", "blobId": "b-7f3a1c", "mimeType": "video/mp4", "size": 104857600, "checksum": "sha256:…"}
```

**Lenient reading rule**: `block_from_dict` looks up `type` to construct a typed object; when `type` is unrecognised it **returns that dictionary as-is**. Consumers therefore **MUST** accept both forms — "typed object" and "raw dictionary" (`ToolResult.text()` handles both paths).

### ToolResult

| Field | Type | Default | Semantics |
|---|---|---|---|
| `content` | `array<ContentBlock>` | `[]` | Array of content blocks (the wire format key is `content`) |
| `structured` | `any` | `null` | Structured result; the wire format key is **`structuredContent`** |
| `error` | `string` | `""` | Error message **string** (non-empty means failure) |

- `is_error` = `bool(error)`; `unwrap()` raises `ToolError(error)` when `error` is non-empty, otherwise returns `structured`.
- `text()` joins the `text` of all blocks with `type == "text"` using `"\n"`; non-text blocks are ignored.
- When a `tool_result` is received, it is constructed from the three keys `content` / `structuredContent` / `error`, defaulting to `[]` / `null` / `""` respectively.
- **Note the distinction**: `ToolResult.error` is a **string**, whereas the `payload` of the `error` **signal** is a `{"code": <integer>, "message": <string>}` object (see §3.4); the two are not interchangeable.

---

## 3. Messages and fields

### Core pattern payloads

| Message | Exact `payload` form | Constraints |
|---|---|---|
| `hello` / `ack` | `{"manifest": <Manifest>}` | `pattern` is `null`; no `reqid` |
| `signal` | any object; the path is in the envelope's `path` field | no `reqid` |
| `tool_call` | `{"tool": <string>, "args": <object>}` | `reqid` **required** |
| `tool_result` (success) | `{"content": <array<ContentBlock>>, "structuredContent": <any>}` | **no** `error` key; `reqid` **MUST** be echoed back |
| `tool_result` (failure) | `{"content": [], "error": <string>}` | **no** `structuredContent` key |
| `manifest_update` | `{"manifest": <Manifest>}` | the receiver replaces only when `version` is greater |
| `ping` / `pong` | `{}` | empty object |
| `error` | `{"code": <integer>, "message": <string>}` | `reqid` may echo the `reqid` of the rejected message |

**Tool return value → wire format** (the projection rules of `_normalize_tool_result`):

| Python return value | `content` | `structuredContent` |
|---|---|---|
| `None` | `[]` | `null` |
| list of content blocks (non-empty, each item has a `type` key or has `to_dict`) | each block's dictionary | `null` |
| single content block object (has `to_dict`) | `[block dictionary]` | `null` |
| `str` | `[{"type": "text", "text": <string>}]` | that string |
| other (`dict` / non-content-block list / number / boolean) | `[{"type": "text", "text": json.dumps(value)}]` | the original value |
| **empty list `[]`** | `[{"type": "text", "text": "[]"}]` | `[]` (an empty list takes the structured branch, **not** the empty content block list) |

### msp/multi-round payloads

Pattern ID `msp/multi-round` (`fallback_to = "msp/request-reply"`); all messages **MUST** carry `pattern: "msp/multi-round"`.

| Message (`type`) | Exact `payload` form |
|---|---|
| `tool_call` | `{"tool": <string>, "args": <object>}`; `reqid` is generated by the client (the reference implementation uses `mr-<auto-increment counter>`) |
| `input_required` | `{"prompt": <string>}`; `reqid` reuses the `reqid` of that call |
| `input_response` | `{"answer": <any>}`; `reqid` reuses the `reqid` of that call |
| `tool_result` | `{"content": <the tool's raw return value, with falsy values normalised to []>, "error": <string>}` |

**Two inconsistencies with the core pattern (source fact)**: ① `tool_result.payload.content` is the **tool function's raw return value**, **not** normalised through `_normalize_tool_result`, and carries **no** `structuredContent`; ② the `error` key **always** appears (an empty string `""` on success), whereas a successful result in the core pattern **does not contain** the `error` key.

### msp/task payloads

Pattern ID `msp/task` (`fallback_to = "msp/request-reply"`); all messages **MUST** carry `pattern: "msp/task"`.

| Message (`type`) | Exact `payload` form | Remarks |
|---|---|---|
| `task_submit` | `{"task": <string>, "args": <object>, "contextId": <string \| null>}` | `reqid` required |
| `task_submit_result` (accept) | `{"taskId": "task-…", "contextId": <string \| null>, "state": "submitted"}` | returns once accepted, without waiting for completion |
| `task_submit_result` (failure) | `{"error": <string>}` | unknown task name |
| `task_status` | `{"taskId": <string>, "state": <string>, "message": <string>}` | no `reqid` |
| `task_artifact` | `{"taskId": <string>, "artifact": <Artifact>}` | no `reqid` |
| `task_result` | `{"taskId": <string>, "state": <string>, "message": <string>, "error": <string>, "artifacts": <array<Artifact>>}` | terminal state |
| `task_query` | `{"taskId": <string>}` | `reqid` required |
| `task_query_result` (success) | `{"taskId": …, "contextId": <string \| null>, "state": <string>, "message": <string>, "error": <string>, "artifacts": <array<Artifact>>}` | |
| `task_query_result` (failure) | `{"taskId": <string>, "error": <string>}` | no `state` key, which distinguishes success from failure |
| `task_cancel` | `{"taskId": <string>}` | `reqid` required |
| `task_cancel_result` | `{"taskId": <string>, "accepted": <boolean>}`; on failure an additional `error` | |
| `input_required` (this pattern) | `{"taskId": <string>, "prompt": <string>}` | **no `reqid`** (unlike `msp/multi-round`) |
| `input_response` (this pattern) | `{"taskId": <string>, "answer": <any>}` | **no `reqid`** |

- **`Artifact`**: `{"name": <string>, "description": <string>, "parts": <array<ContentBlock>>}`; `parts` reuses the content block format.
- **State values**: `submitted` / `working` / `input-required` / `completed` / `failed` / `canceled`; the terminal set is `{completed, failed, canceled}` (note that `input-required` uses a **hyphen**).
- **Observer mirror broadcast**: status / artifacts / terminal state are also `publish`ed to `task.<taskId>.<kind>`, with `kind` ∈ `status` / `artifact` / `result`, and the `payload` **identical** to the directed message of the same name; third-party nodes observe via `on("task.**")`.
- Empty `content` / `artifacts` **MUST** keep the key (`[]`) and **MUST NOT** be omitted — "empty" is meaningful semantics.

### Error object

The `payload` of the `error` signal has exactly two keys:

```json
{"code": -32600, "message": "Unknown signal type: stream_start"}
```

Error codes take the JSON-RPC 2.0 conventional values; the authoritative table is in [Specification Index §5.4](index.md#54-error-codes). **Source fact**: the MSP protocol core emits `-32600` only when it "receives an unknown `type`"; `-32601` / `-32602` / `-32603` are defined only in `msp/mcp/jsonrpc.py` (the JSON-RPC bridge), and MSP tool execution failures always go through the `tool_result.payload.error` string channel.

---

## 4. Message flow

```text
node_a                                                     node_b
  │  Signal{type:"tool_call", source:"node_a", pattern:null,│
  │         target:"node_b", path:null, reqid:"9f2c…",      │
  │         payload:{tool:"get_weather", args:{location:"Shanghai"}},
  │         timestamp:1791500000.0}                         │
  ├────────────────────────────────────────────────────────▶│  ① _on_tool_call(payload.tool / args)
  │                                                         │  ② run on a thread → return value
  │                                                         │  ③ _normalize_tool_result(...)
  │  Signal{type:"tool_result", source:"node_b",            │
  │         target:"node_a", reqid:"9f2c…",                 │
  │         payload:{content:[{type:"text", text:"21°C"}],    │
  │                  structuredContent:{temp:21}}}          │
  ◀─────────────────────────────────────────────────────────┤  ④ echo reqid back as-is
  │  ⑤ match pending_calls by reqid → ToolResult(content, structured, error="")  │
```

Manifest exchange: the `payload` of both the initiator's `hello` and the responder's `ack` is `{"manifest": <complete Manifest>}`; thereafter each manifest change pushes `manifest_update{payload:{manifest:{version:N, …}}}` — a **whole replacement**, and the receiver accepts it only when `version` is greater.

---

## 5. Data types

### The projection rules of schema_from_func

When `inputSchema` is absent it is generated by introspecting the tool function signature; an **explicitly passed** `input_schema` takes precedence, and introspection is only a fallback when it is absent. The function-level output is invariably `{"type": "object", "properties": {...}}`, with `required` appended when required parameters exist (in parameter declaration order).

| Annotation form | JSON Schema fragment |
|---|---|
| `str` / `int` / `float` / `bool` | `{"type":"string"}` / `{"type":"integer"}` / `{"type":"number"}` / `{"type":"boolean"}` (**exact type-object equality** lookup, so `bool` is not mistaken for `int`) |
| no annotation / `Any` / `inspect.Parameter.empty` | `{}` (no constraints, but the parameter still goes into `properties`) |
| `None` (`type(None)`) | `{"type":"null"}` |
| `Annotated[str, "city name"]` | `{"type":"string","description":"city name"}` |
| `Annotated[int, Field(ge=0, le=100)]` | **holds only in the pydantic v1 form**: `{"type":"integer","minimum":0,"maximum":100}`; **under the pydantic v2 form the constraints are silently dropped**, leaving only `{"type":"integer"}` (see item 7 below) |
| `Field(gt=0)` / `Field(lt=10)` | when matched → `exclusiveMinimum` / `exclusiveMaximum` |
| `Field(min_length=1)` / `Field(max_length=64)` | when matched → `minLength` / `maxLength` |
| `Field(pattern="^a")` / `Field(description="…")` | when matched → `pattern` / `description` (`description` matches in both v1 and v2: v2's `FieldInfo.description` is still an instance attribute) |
| `enum.Enum` subclass | `{"enum":[member1.value, member2.value, …]}` (takes `.value`, does **not** write `type`) |
| `Literal["a", "b"]` | `{"enum":["a","b"]}` (takes the literals themselves) |
| `Optional[str]` / `str \| None` | `{"type":["string","null"]}` |
| `Optional[MyEnum]` / `Optional[Literal[...]]` (the inner type has no scalar `type`) | `{"anyOf":[{…inner…},{"type":"null"}]}` |
| `Union[A, B]` (≥ 2 non-`None` members) | `{"anyOf":[A's fragment, B's fragment]}` (**discards** `None` members) |
| `list[T]` / `set[T]` / `tuple[T]` | `{"type":"array","items":<T's fragment>}`; `tuple[T1, T2]` → `{"type":"array"}` (**no** `items`) |
| bare `list` / `set` / `tuple` | `{"type":"array"}` |
| `dict` | `{"type":"object"}` |
| `dict[str, T]` | `{"type":"object","additionalProperties":<T's fragment>}` |
| other (custom class, `TypeVar`) | `{}` (no constraints, no error) |

**Key conclusion**: constraints are emitted as **JSON Schema keywords** (`minimum` / `exclusiveMinimum` / `maximum` / `exclusiveMaximum` / `minLength` / `maxLength` / `pattern`), **not** pydantic field names (`ge` / `le` / `gt` / `lt` / `min_length` / `max_length`). Implementations **MUST NOT** pass `ge` and the like straight through into `inputSchema`.

### Boundary behaviour and fragility

1. **`get_type_hints(func, include_extras=True)` is required**: a default call strips the `Annotated` metadata, losing all descriptions and constraints; `from __future__ import annotations` turns annotations into strings, which must also be resolved through it.
2. **Introspection failure means "no constraints"**: when `get_type_hints` raises, the hints degrade to empty — all parameters become unconstrained but **still** go into `properties`, and `required` is still decided by the signature's defaults; when `inspect.signature` fails it returns `{"type":"object","properties":{}}` (**without** a `required` key).
3. **Skipping and fallbacks**: `self` / `cls` and `*args` / `**kwargs` are skipped; unannotated parameters are **not** dropped but produce `{}`.
4. **No `default` is emitted**: `_field_extra` explicitly does **not** extract default values — a Python default in the signature only decides whether the parameter goes into `required`; the JSON Schema `default` keyword is **never** generated by this implementation, and `Field(default=...)` is not read either.
5. **How pydantic is recognised without a hard dependency**: duck-typing via `type(meta).__name__ == "FieldInfo"` avoids `import pydantic` (the project's only third-party dependency is `watchdog`).
6. **Fragility**: ① **string** class-name matching — renaming, wrapping or subclassing in pydantic makes constraints **silently disappear**, and a custom class with the same name is **misidentified**; ② constraint carriers that are not pydantic (e.g. `annotated_types`) are **not** recognised; ③ multiple `Annotated` constraint objects are `update`d in turn, and the later one overrides same-named keys of the earlier; ④ introspection results are **only used for outward announcement** and do **not** take part in runtime validation — the protocol layer does not validate `args` against `inputSchema`, and a `TypeError` from the tool function itself only becomes `tool_result.payload.error`.
7. **Under pydantic v2 all constraints are lost (measured, important)**: `_field_extra` reads constraints with `getattr(field, "ge" / "gt" / "le" / "lt" / "min_length" / "max_length" / "pattern")`, and that attribute set is the **pydantic v1** `FieldInfo` form. pydantic v2 moved constraints into `field.metadata` (objects shaped like `Ge(ge=0)` / `Le(le=100)`), and `FieldInfo` **no longer has** `ge` / `le` and the like, so all the `getattr` calls above return `None` and **the constraints are silently dropped**; `description` is still kept (it is an instance attribute in v2). Measured on pydantic 2.13.4: `Annotated[int, Field(ge=0, le=100, description="pct")]` produces `{"type":"integer","description":"pct"}` — `minimum` / `maximum` **do not appear**. Therefore implementations that rely on constraint announcement **MUST** read `field.metadata` themselves (v2) or pass `input_schema` explicitly; they **MUST NOT** assume this function generates constraints for `Field(...)`.

### Preset and built-in presets

| Field | Type | Default | Semantics |
|---|---|---|---|
| `name` | `string` | — (required) | Preset name, which is also the attribute name of the built-in preset |
| `discovery` | `set<string>` | `frozenset()` | Enabled discovery mechanisms (`directory` / `manual`) |
| `presence` | `set<string>` | `frozenset()` | Enabled announce mechanisms (`directory` / `manual`) |
| `transports` | `set<string>` | `frozenset()` | Enabled transport backends (`tcp` / `websocket` / `uds`) |
| `patterns` | `set<string>` | `frozenset()` | Enabled pattern IDs (merged into `Manifest.patterns` at startup) |
| `primary_transport` | `string` | `"tcp"` | Which backend to announce externally; **MUST** be in `transports`, otherwise `start()` raises |
| `capabilities` | `set<string>` | `frozenset()` | Capability bits (merged into `Manifest.capabilities` at startup) |
| `connect_policy` | `string` | `"eager"` | `eager` (connect on discovery) / `lazy` (accept inbound only, dial on demand) |

There are **8** built-in presets; the pattern-column abbreviations correspond verbatim to the source IDs: `RR = msp/request-reply`, `PS = msp/publish-subscribe`, `MR = msp/multi-round`, `TK = msp/task`.

| Preset | discovery | presence | transports | patterns | primary | capabilities | policy |
|---|---|---|---|---|---|---|---|
| `LOCAL_TOOL` | — | `directory` | `tcp` | RR, PS | `tcp` | pub, rep | `lazy` |
| `LOCAL_TOOL_ADVANCED` | — | `directory` | `tcp` | RR, PS, MR, TK | `tcp` | pub, rep | `lazy` |
| `LOCAL_AI` | `directory` | `directory` | `tcp` | RR, PS, MR, TK | `tcp` | pub, sub, req, rep | `eager` |
| `LOCAL_AI_UDS` | `directory` | `directory` | `uds` | RR, PS, MR, TK | `uds` | pub, sub, req, rep | `eager` |
| `CLOUD_SERVICE` | — | `directory` | `tcp` | RR, PS, MR, TK | `tcp` | pub, rep | `lazy` |
| `OBSERVER` | `directory` | — | `tcp` | PS | `tcp` | sub | `eager` |
| `FULL_PEER` | `directory` | `directory` | `tcp` | RR, PS, MR, TK | `tcp` | pub, sub, req, rep | `eager` |
| `MANUAL_PEER` | `manual` | `manual` | `websocket` | RR, PS | `websocket` | pub, sub, req, rep | `eager` |

`LOCAL_AI_UDS` is `LOCAL_AI` with the UDS transport (Linux / macOS only); `OBSERVER` only discovers and never announces (empty presence) and has only `PS`; `MANUAL_PEER` uses WebSocket and enables **only** the two core patterns (using `MR` / `TK` requires an explicit `register_pattern`).

**Authorization (`grants`) 🔵 not yet part of `Preset`**: this revision defines it as a local policy field of `Preset`; for the field form and defaults see [security.md §Authorization](./security.md#3-authorization). Authorization **MUST NOT** enter `Manifest`, and **MUST NOT** be exchanged with the manifest.

### JSON Schema fragments

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

## 6. Error handling and boundaries

| Situation | Requirement |
|---|---|
| Missing `type` or `source` | `from_dict` raises `KeyError` → read-loop exception → **drop the connection**; these two fields are hard-required |
| Missing `payload` / `timestamp` / `target` / `path` / `reqid` / `pattern` | **MUST** fall back to defaults (`{}` / receive time / `null`), and **MUST NOT** raise an error |
| Explicit `null` versus absence | the semantics **MUST** be equivalent; a sender writing `null` is compliant |
| Unknown `pattern` | **MUST NOT** disconnect; the reference implementation falls back to the core handling path |
| Unknown `type` (and no usable `pattern`) | **SHOULD** reply with `error`, `code = -32600`; **MUST NOT** silently discard and leave the peer waiting forever |
| Tool execution failure | **MUST** go through `tool_result.payload.error` (error as value); only protocol-level failures use the `error` signal |
| Unknown content block `type` | **MUST** be preserved as-is and handed to the upper layer; **MUST NOT** drop the whole `content` |
| The four `Manifest` lists written as objects | parsing raises `TypeError` and the handshake fails; senders **MUST NOT** use the object form |
| `manifest_update.version` not greater than the current value | **MUST** be ignored (to prevent rolling back the capability surface with an old manifest) |
| `apply_diff` receives an older `version` | the reference implementation overwrites directly; implementations of cross-machine incremental sync **MUST** reject version regression themselves |
| Unknown `error.code` | record it per the implementation-defined range (`-32000`~`-32099`); **MUST NOT** disconnect because of an unknown error code |
| `tool_result.reqid` not in the pending table | **MUST** be ignored (it may have timed out or be forged), and **MUST NOT** raise |
| `content` mixing typed objects and raw dictionaries | **MUST** handle both (an inevitable consequence of lenient reading) |

---

## 7. Summary of normative provisions (MUST / SHOULD list)

1. `Signal` **MUST** use snake_case field names; `type` and `source` **MUST** be present, and every other missing field is handled with default-value semantics.
2. Pattern-private signals **MUST** carry `pattern`; the receiver **MUST** route by `pattern` first.
3. `type: "signal"` **MUST** fill in `path`; `tool_call` / `tool_result` **MUST** carry the same `reqid`.
4. `Manifest` **MUST** use camelCase; `signals` / `tools` / `resources` / `prompts` **MUST** be arrays, `capabilities` **MUST** be an array of strings, and `clientCapabilities` **MUST** be an object with three booleans.
5. `Manifest.version` **MUST** increase monotonically; the receiver **MUST** discard a `manifest_update` whose `version` is not greater than the current value.
6. Empty `schema` / `description` of `SignalDescriptor` **MAY** be omitted; the fields of the other descriptors **SHOULD** all be written, and the reading side **MUST** fall back to defaults.
7. The declaration file **MUST** be `{node_id}.json`, **MUST** be written atomically, and **MUST NOT** contain local policy or keys.
8. `Endpoint.address` **MUST NOT** contain nested objects (`address_key` relies on simple orderable values).
9. Unknown content block types **MUST** be preserved as-is; consumers **MUST** accept both typed objects and raw dictionaries.
10. The wire format uses `structuredContent`, while the in-memory model is called `structured`; implementations **MUST NOT** write `structured` onto the wire directly.
11. `ToolResult.error` (a string) and `error.payload` (an object) **MUST NOT** be mixed up; tool failures **MUST** go through `tool_result.payload.error`.
12. When `inputSchema` is absent it **SHOULD** be generated by `schema_from_func`, and it **MUST** use `get_type_hints(..., include_extras=True)`; the output **MUST** be JSON Schema keywords rather than pydantic field names.
13. `schema_from_func` **MUST NOT** emit the `default` keyword and **MUST NOT** raise because of an unrecognised annotation.
14. `grants` **MUST NOT** appear in `Manifest`, in the declaration file, or in any message on the wire.
15. Unrecognised fields / signal types / content block types / pattern IDs **MUST NOT** be treated as protocol errors that drop the connection.

---

## 8. Security considerations

- **The manifest is self-description, not a promise**: `capabilities` / `tools` / `patterns` may all be misreported; authorization decisions **MUST NOT** cite the manifest ([security.md §Authorization](./security.md#3-authorization)), and the manifest serves only for the local optimisation of "whether to try".
- **Introspection is not validation**: `inputSchema` is a notice, not a runtime gate; parameter validation **SHOULD** be done inside the tool function and **MUST NOT** rely on the schema.
- **The boundary of lenient reading**: lenient reading requires not dropping the connection, and does **not** require executing unrecognised semantics; "preserve unknown blocks as-is" **MUST NOT** be read as "unknown data may enter the execution path".
- **The declaration file is a no-go zone for local policy**: `grants` / keys / allowlists **MUST NOT** enter the declaration file or `Manifest`.
- **Integrity fields are advisory**: `blob_ref.size` / `checksum` **MUST NOT** serve as the sole lower bound for memory preallocation; see [security.md §8](./security.md#8-security-considerations) for their verification responsibility.
- **`reqid` MUST be unpredictable**: it is the only correlation basis for `tool_result` (16 hex digits), and a predictable `reqid` leaves a surface for result forgery ([security.md §8](./security.md#8-security-considerations)).
- **`version` is a rollback defence line**: rejecting older `manifest_update` prevents the peer from rolling back the local capability view with an old manifest; `apply_diff` currently has **no** such protection.

---

## 9. Known gaps

1. **`Endpoint.address_key()` has no call sites**: endpoint deduplication is actually done by the discovery layer's `_known[node_id]` declaration hash; `(transport_type, address)`-level deduplication is "defined but unused".
2. **`diff()` / `apply_diff()` are not used by the protocol layer**: they appear only inside `manifest.py` across the whole repository, and manifest updates use a whole `manifest_update`.
3. **`apply_diff` has no version-monotonicity protection**: it unconditionally overwrites `version` with the value in the diff, which may cause a version regression.
4. **`schema` does not take part in runtime validation**: the protocol layer does not validate `args` against `inputSchema`, and tool functions do not automatically gain validation either.
5. **The element structure of `PromptDescriptor.arguments` is undefined**: the source is `list[dict]`, and the internal fields are not specified by this revision ([capabilities.md](./capabilities.md) 🔵 to be completed).
6. **`add_tool` / `add_resource` / `add_prompt` have no deduplication short-circuit**: asymmetric with `add_signal`, duplicate registration produces a content-free `version` increment and a superfluous `manifest_update`.
7. **The `tool_result` of `msp/multi-round` is inconsistent with the core pattern**: `content` is the raw return value, there is **no** `structuredContent`, and the `error` key is always present.
8. **The `input_required` / `input_response` of `msp/task` carry no `reqid`**: they can only be correlated via `taskId`; implementations that reuse them across patterns **MUST NOT** assume the two are isomorphic.
9. **Missing-field behaviour is asymmetric**: a missing `type` / `source` drops the connection, while other missing fields fall back silently.
10. **No schema versioning**: `Manifest.version` is only a monotonic counter; it cannot express "the data structure changed", and there is no compatibility declaration field.
11. **The `quic` transport is not registered**: there is only a comment placeholder; using it raises `ValueError`, and its `address` form is undefined.

---

## 10. Reference implementation map

| Data model / rule | Source file and symbol |
|---|---|
| `Signal` fields, `to_dict` / `from_dict`, `new_reqid` | [src/msp/core/signal.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/signal.py) `Signal` |
| The 9 `SignalType` constants and the request / response classification | [src/msp/core/signal.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/signal.py) `SignalType`, `Signal.is_request`, `Signal.is_response` |
| `Manifest` top-level fields and camelCase serialization | [src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `Manifest.to_dict` / `from_dict` |
| Fields and conditional omission of the four descriptors | [src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `SignalDescriptor` / `ToolDescriptor` / `ResourceDescriptor` / `PromptDescriptor` |
| Change operations and the `version` rules | [src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `add_signal` / `add_tool` / `add_resource` / `add_prompt` / `add_pattern` / `set_pattern_metadata` |
| `diff()` / `apply_diff()` key names | [src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `Manifest.diff` / `Manifest.apply_diff` |
| Manifest push and `version` comparison | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `push_manifest` / `_on_manifest_update` |
| Handshake message `payload.manifest` | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `handshake_outbound` / `handshake_inbound` |
| `Endpoint` and `address_key` | [src/msp/discovery/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/base.py) `Endpoint` |
| `address` form of each backend | [tcp.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/tcp.py) / [websocket.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/websocket.py) / [uds.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/uds.py) `listen` |
| Transport registry (`quic` placeholder) | [src/msp/core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `TRANSPORT_REGISTRY` |
| Declaration file form and atomic writes | [src/msp/presence/directory.py](https://github.com/hxh230802/MSP/blob/master/src/msp/presence/directory.py) `DirectoryWrite._declaration` / `_write` |
| Declaration scanning and lease decisions | [src/msp/discovery/directory.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/directory.py) `DirectoryScan._read_declaration` / `_full_scan` |
| The six content blocks and lenient reading | [src/msp/core/content.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) `TextContent` / `ImageContent` / `AudioContent` / `EmbeddedResource` / `ResourceLink` / `BlobRef` / `block_from_dict` |
| `ToolResult` and `ToolError` | [src/msp/core/content.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) `ToolResult` / `ToolError` |
| Tool return value normalisation | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `_normalize_tool_result` / `_is_content_block` |
| Core payload fields and error receipts | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `call` / `_on_tool_result` / `_run_tool` / `_reply_error` |
| `msp/multi-round` payloads | [src/msp/patterns/multi_round.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/multi_round.py) `MultiRoundHandler._ask` / `_on_input_required` / `_reply_result` |
| `msp/task` payloads, states and mirror broadcast | [src/msp/patterns/task.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/task.py) `TaskHandler._on_submit` / `_emit_status` / `_emit_artifact` / `_emit_result` / `_broadcast` / `Artifact` / `TaskSnapshot` |
| `schema_from_func` and the projection rules | [src/msp/core/schema.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/schema.py) `schema_from_func` / `type_to_schema` / `_annotated_extra` / `_field_extra` |
| `Preset` fields and the 8 built-in presets | [src/msp/core/preset.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/preset.py) `Preset` and each `Preset.*` instance |
| When `Preset` is merged into the manifest | [src/msp/core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `MSPNode.start` |

**Related pages**: [Specification Index](index.md) · [architecture](./architecture.md) · [base-protocol](./base-protocol.md) · [transports](./transports.md) · [discovery](./discovery.md) · [patterns](./patterns.md) · [patterns/request-reply](./patterns/request-reply.md) · [patterns/publish-subscribe](./patterns/publish-subscribe.md) · [patterns/multi-round](./patterns/multi-round.md) · [patterns/task](./patterns/task.md) · [capabilities](./capabilities.md) · [security](./security.md) · [design document](/design)
