# `msp/multi-round` — Follow-ups during execution

| | |
|---|---|
| **Protocol revision** | `2026-10-10` |
| **Pattern ID** | `msp/multi-round` |
| **Status markers** | ✅ **Implemented** (main path verifiable); the boundaries listed in §9 are 🟡 **partially implemented** |
| **Fallback target** | `msp/request-reply` (`fallback_to`) |
| **Normative language** | RFC 2119, see [specification index](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#2-规范性用语) |
| **Defined by this page** | The callee asks the caller for supplementary information several times **within the same `reqid`** of one `tool_call`, and only then returns the final result |

## 1. Overview

### 1.1 The engineering problem it solves

Tool arguments often become known only **during execution**: a booking tool discovers the departure date is missing only when it is about to place the order, and a search tool discovers the time range is missing only when it assembles the query string. Without this pattern both sides have only two clumsy options:

1. The tool fails once and encodes "what is missing" into `tool_result.payload.error`; the caller parses it and calls again — one interaction is split into two, the server has to rebuild its context, the `reqid` changes, and all intermediate state in `ctx` is lost.
2. The tool simply demands every argument up front, forcing the caller to stuff all details into `args`, even though half of them go unused.

`msp/multi-round` offers a third choice: **fill the gaps in place within the `reqid` of the same call**. A tool function is halfway through executing on its own thread when it calls `ctx.ask(...)` and blocks; the caller receives the follow-up, answers it and sends it back; the tool continues with the answer. The callee's execution stack, local variables and already-emitted intermediate side effects all stay where they were.

### 1.2 Relation to existing patterns

- This pattern is a **superset** of `msp/request-reply`: the opening message is still `tool_call`, the closing message is still `tool_result`, and the correlation key is still `reqid`. The only difference is that **the callee MAY interject in the reverse direction** during the round trip.
- "Multi-round" does not mean "a human is involved". The answering party is the `input_fn` supplied by the caller; it can consult local configuration, take defaults, derive by rule, or read a local model — there **MAY** be no human in the loop at all.
- This pattern adds only **two** pattern-private signal types (`input_required` / `input_response`); the core `SignalType` is unchanged. The only cost the protocol layer pays for this is one table lookup in [pattern routing](../patterns.md#3-routing-contract).

## 2. Contract

### 2.1 Pattern identity and fallback

| Item | Value | Source location |
|---|---|---|
| `pattern_id` | `"msp/multi-round"` | `MultiRoundHandler.pattern_id` |
| `fallback_to` | `"msp/request-reply"` | `MultiRoundHandler.fallback_to` |
| `conflicts_with` | `[]` (inherited from the `PatternHandler` default; not declared by this pattern) | `PatternHandler.conflicts_with` |

**Fallback semantics**: the intent declared by `fallback_to` is that, when the peer does not support this pattern, the request is resent using `msp/request-reply` (degrading to an ordinary tool call, with the follow-up capability gone). **No automatic fallback happens in the current reference implementation**: `fallback_to` is only declared across the whole repository and no code reads it. However, `call_multiround()` now **establishes the connection before checking** `peer(peer_id).supports("msp/multi-round")`, and raises `RuntimeError` immediately when the peer has not announced this pattern (it no longer sends the request out and relies on the overall timeout as a backstop; see §12 G2) — **the check** is implemented, **the fallback** is not.

An implementer **MAY** implement automatic fallback, but once implemented it **MUST** satisfy: no `input_required` **MUST** be sent before the fallback; after the fallback the message shapes of this interaction **MUST** conform exactly to [`msp/request-reply`](./request-reply.md) (they **MUST NOT** carry a `pattern` field); the fallback **SHOULD** be signalled in a way the caller can explicitly see (such as a return value or an exception) and **MUST NOT** change semantics silently.

> Factual clarification: when the peer has not registered a handler for this pattern, a `tool_call` carrying `pattern` falls into the protocol layer's default branch ([`_dispatch`](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) step 3) and is handled by the core tool registry as an ordinary tool call. This is not fallback in the normative sense but a **backstop for unrouted patterns**: if a tool of the same name is registered only in the pattern's own registry, the core registry cannot find it and returns a `tool_result` whose `error` is "unknown tool: X". See §6.1.

### 2.2 Signal types

| Signal `type` | Direction | Has `reqid` | Semantics |
|---|---|---|---|
| `tool_call` | caller → callee | **Yes** | opening request; shared with the core type of the same name, distinguished by `pattern` |
| `input_required` | callee → caller | **Yes** | follow-up question; `reqid` **MUST** be the same as that of the opening `tool_call` |
| `input_response` | caller → callee | **Yes** | answer; `reqid` **MUST** be the same as that of the follow-up question |
| `tool_result` | callee → caller | **Yes** | terminal result; `reqid` **MUST** be the same as that of the opening request |

`input_required` / `input_response` are `type` values private to this pattern. Every signal of this pattern **MUST** carry `pattern = "msp/multi-round"` — it is the routing key at the protocol layer (see §6.1 and [pattern-layer contract](../patterns.md#3-routing-contract)).

### 2.3 Threading and blocking model

| Side | Constraint | Rationale |
|---|---|---|
| callee | **MUST** execute the tool function on a separate thread | the tool's `ctx.ask()` is a blocking call; if it ran on the thread executing the read loop, the `input_response` sent back by the caller would never be read and deadlock is certain |
| callee | **MAY** call `ctx.ask()` several times within one tool execution | each call produces a new pair of follow-up and answer with the same `reqid` |
| caller | on receiving `input_required`, **SHOULD** complete the blocking question outside the thread that received it | the reference implementation calls `input_fn` synchronously inside the read-loop thread; see §9 |
| both sides | **MUST NOT** assume any upper bound on the number of follow-ups | the specification sets no limit on the count; the caller uses the overall timeout as a backstop |

`ctx.ask(prompt, timeout=30.0)`: `prompt` (`str`, required) goes verbatim into `input_required.payload.prompt`; `timeout` (`float`, default `30.0`) is the upper bound on waiting for a single follow-up; it returns the raw value of `input_response.payload.answer`; on timeout it raises `TimeoutError` (message `"timed out waiting for client input"`). The caller's overall timeout is controlled independently by `call_multiround(..., timeout=60.0)`; it is **not** the same value as the single follow-up timeout, and the two **MUST NOT** be derived from each other.

## 3. Messages (signal by signal)

General rules for envelope fields are in [the `Signal` envelope](../base-protocol.md#2-the-signal-envelope). In the examples below the envelope is snake_case (`type` / `source` / `pattern` / `target` / `path` / `reqid` / `payload` / `timestamp`), and the field names inside `payload` are taken verbatim from the source.

### 3.1 `tool_call`

| Field | Location | Type | Required | Value |
|---|---|---|---|---|
| `type` | envelope | string | **MUST** | `"tool_call"` |
| `pattern` | envelope | string | **MUST** | `"msp/multi-round"` |
| `source` / `target` | envelope | string | **MUST** | caller / callee `node_id` |
| `reqid` | envelope | string | **MUST** | correlation identifier of this interaction, carried by all four message types |
| `payload.tool` | payload | string | **MUST** | tool name |
| `payload.args` | payload | object | **MUST** | tool arguments; `{}` when the reference implementation cannot obtain them |

```json
{ "type": "tool_call", "source": "client_node", "pattern": "msp/multi-round", "target": "server_node",
  "path": null, "reqid": "mr-1", "payload": { "tool": "book_flight", "args": { "destination": "Paris" } } }
```

How `reqid` is generated is left to the implementation. The reference implementation generates `mr-<n>` from a per-handler-instance counter (`n` incrementing from 1), unlike the core patterns, which use `Signal.new_reqid()` (a 16-character hexadecimal random string). Concurrent interactions within the same node **SHOULD** have distinct `reqid` values.

### 3.2 `input_required`

| Field | Location | Type | Required | Value |
|---|---|---|---|---|
| `type` | envelope | string | **MUST** | `"input_required"` |
| `pattern` | envelope | string | **MUST** | `"msp/multi-round"` |
| `source` / `target` | envelope | string | **MUST** | callee / caller `node_id` |
| `reqid` | envelope | string | **MUST** | same as the opening `tool_call` |
| `payload.prompt` | payload | string | **MUST** | follow-up question text |

```json
{ "type": "input_required", "source": "server_node", "pattern": "msp/multi-round", "target": "client_node",
  "path": null, "reqid": "mr-1", "payload": { "prompt": "departure date?" } }
```

**The payload has exactly one field, `prompt`.** Argument names, expected types, value ranges, candidate options and context fragments **do not exist at all** in the reference implementation; the receiver **MUST NOT** assume they are present, and a sender that extends the payload itself **SHOULD** add new fields and **MUST NOT** change the meaning of `prompt` (for the lenient reading see [base-protocol §2.3](../base-protocol.md#23-lenient-reading)). When the receiver cannot obtain `prompt`, it **SHOULD** treat it as an empty string.

### 3.3 `input_response`

| Field | Location | Type | Required | Value |
|---|---|---|---|---|
| `type` | envelope | string | **MUST** | `"input_response"` |
| `pattern` | envelope | string | **MUST** | `"msp/multi-round"` |
| `source` / `target` | envelope | string | **MUST** | caller / callee `node_id` |
| `reqid` | envelope | string | **MUST** | same as that `input_required` |
| `payload.answer` | payload | any | **MUST** | answer value, any JSON-serialisable type |

```json
{ "type": "input_response", "source": "client_node", "pattern": "msp/multi-round", "target": "server_node",
  "path": null, "reqid": "mr-1", "payload": { "answer": "2026-10-15" } }
```

The type of `answer` is not constrained by this specification: strings, numbers, booleans, objects, arrays and `null` are all acceptable, and the callee **MUST NOT** assume it is a scalar. When `input_fn` raises, the reference implementation sets `answer` to `{"error": "<exception text>"}` — this is an **implementation convention, not protocol semantics**, and the callee **MUST NOT** treat it as a signal of cancellation or timeout.

### 3.4 `tool_result`

| Field | Location | Type | Required | Value |
|---|---|---|---|---|
| `type` | envelope | string | **MUST** | `"tool_result"` |
| `pattern` | envelope | string | **MUST** | `"msp/multi-round"` |
| `reqid` | envelope | string | **MUST** | same as the opening `tool_call` |
| `payload.content` | payload | any | **MUST** | the **raw value** returned by the tool; falsy values (`None` / `""` / `0` / `False` / `{}` / `[]`) are normalised to `[]` |
| `payload.error` | payload | string | **MUST** | `""` on success; the exception text on failure |

```json
{ "type": "tool_result", "source": "server_node", "pattern": "msp/multi-round", "target": "client_node",
  "path": null, "reqid": "mr-1",
  "payload": { "content": { "destination": "Paris", "date": "2026-10-15", "airline": "Air China" }, "error": "" } }
```

There are **three substantive differences** from the `tool_result` of the core [`msp/request-reply`](./request-reply.md), and implementers **MUST** handle this pattern's shape: ① this pattern **does not produce** `structuredContent`, and return values appear only in `content`; ② this pattern's `content` is the **raw value** returned by the tool (it may be an object, a string or an array, though falsy values are normalised to `[]` by `content or []`), **not** a normalised array of content blocks (the core pattern passes through `_normalize_tool_result` before writing `content`); ③ this pattern **always** carries both `content` and `error`, with `error` being the empty string on success, so the caller **SHOULD** test `error != ""` and **MUST NOT** decide success or failure by whether a field is present.

## 4. Message flow

### 4.1 Normal path: two follow-ups plus the final result (same `reqid`)

```text
   caller (client_node)                                  callee (server_node)
        │ ① tool_call  reqid=mr-1  payload={tool:"book_flight",args:{…}}            │
        ├──────────────────────────────────────────────────────────────────────────▶│
        │                                      the read loop only dispatches; a separate thread runs the tool
        │                                      the tool runs and finds an argument missing
        │ ② input_required  reqid=mr-1  payload={prompt:"departure date?"}          │
        │◀──────────────────────────────────────────────────────────────────────────┤
        │                                      ctx.ask("departure date?") blocks, <=30s
        │ input_fn("departure date?") → "2026-10-15"
        │ ③ input_response  reqid=mr-1  payload={answer:"2026-10-15"}               │
        ├──────────────────────────────────────────────────────────────────────────▶│
        │                                      wakes ask(); the tool keeps running
        │ ④ input_required  reqid=mr-1  payload={prompt:"preferred airline?"}       │
        │◀──────────────────────────────────────────────────────────────────────────┤
        │                                      ctx.ask("preferred airline?") blocks
        │ ⑤ input_response  reqid=mr-1  payload={answer:"Air China"}                │
        ├──────────────────────────────────────────────────────────────────────────▶│
        │                                      the tool returns; the worker thread ends
        │ ⑥ tool_result  reqid=mr-1  payload={content:{…},error:""}                 │
        │◀──────────────────────────────────────────────────────────────────────────┤
        │ wakes call_multiround() and returns content                               │
        ▼                                                                           ▼
```

Four key invariants: ① the envelope `reqid` of ②③④⑤⑥ **MUST** equal that of ①; ② the same `reqid` **MUST** produce only one `tool_result`; ③ follow-ups are unrelated to the callee's thread count and **MAY** occur several times in sequence within one thread; ④ the caller need not announce that it supports this pattern, nor know the number of follow-ups in advance.

### 4.2 Error path comparison

```text
  (a) follow-up timeout      callee: ask() raises TimeoutError → tool_result{content:[],error:"timed out waiting for client input"}
  (b) tool exception         callee: tool_result{content:[],error:"<exception text>"}
  (c) unknown tool           callee: tool_result{content:[],error:"unknown tool: <name>"}  ← returned immediately, no thread started
  (d) caller overall timeout caller: TimeoutError (drops the wait entry for that reqid) → input_required arriving later is silently discarded
  (e) peer has no handler    peer: error{code:-32600,message:"unknown signal type: input_required"} (carries the original reqid)
                             caller: does not recognise that error and keeps waiting until the overall timeout
```

## 5. Data and type conventions

| Concept | Type | Constraint |
|---|---|---|
| answer | `Any` | any JSON-serialisable value; the return value of `input_fn` goes into `answer` verbatim |
| follow-up text | `string` | a single block of text, with no structured schema |
| tool return value | `Any` | goes verbatim into `tool_result.payload.content`; a falsy value (`None` / `""` / `0` / `False` / `{}` / `[]`) → `[]` |
| error text | `string` | human-readable; this pattern does **not** define numeric error codes |

This pattern does **not** define new error codes. Tool execution failures go through `tool_result.payload.error` (the error is a value), while protocol-level failures reuse the [error code table](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#54-错误码) (for example `-32600`). When arguments do not match the `inputSchema` declared by the tool, the failure **SHOULD** be expressed as a tool failure with `-32602` semantics rather than by sending an `error` signal.

## 6. Error handling and boundaries

**6.1 The peer does not announce / has not activated this pattern** — the caller **SHOULD** check `peer(peer_id).supports("msp/multi-round")` before calling; `call_multiround()` in the reference implementation now does this **itself**: it calls `ensure_connected()` first, then queries `supports()`, and raises `RuntimeError` when the pattern has not been announced (the caller still **SHOULD** check on its own to decide whether to take a fallback path). If the peer has not registered a handler for this pattern: signals carrying `pattern` are not found in the routing table and fall into the protocol layer's default branch. `tool_call` is handled as an **ordinary tool call** (it may wrongly hit a tool of the same name in the core registry); `input_required` / `input_response` hit the "unknown signal type" branch and reply with `error` (`code = -32600`). That `error` carries the original `reqid`, and the protocol layer's `_on_error` **will** wake the waiting call by `reqid` and return `ToolResult(error=...)` (the original implementation only logged it and had to wait out the whole overall timeout; see §12 G3).

**6.2 Nothing answers the `input_required`** — the wait entry for the callee's `ctx.ask()` is registered **only locally on the callee**. If the caller has dropped the wait entry for that `reqid` (overall timeout, process exit, a missed branch), an arriving `input_required` is silently ignored and **no** `input_response` is sent; the callee can only wait for the single follow-up timeout. The specification does **not** define a "follow-up refused" message; an implementer that needs one **SHOULD** express "no answer" with `input_response.payload.answer = null`.

**6.3 Timeouts** — a single follow-up (the callee's `ctx.ask`) defaults to `30.0` s; on expiry it raises `TimeoutError` and pops the wait entry, and the tool usually fails at once and returns `error`; the whole call (the caller's `call_multiround`) defaults to `60.0` s; on expiry it raises `TimeoutError`, pops the `reqid` entry, and **does not** send a cancellation to the peer. The two are unrelated: the number of follow-ups × the single timeout **MAY** exceed the overall timeout. The caller **SHOULD** make the overall timeout ≥ the expected number of follow-ups × the single follow-up timeout; the reference implementation performs no such check.

**6.4 Connection loss** — the callee's response signals (`tool_result` / `input_response`) all go out through `_send()`, which catches `(RuntimeError, ConnectionClosed)` and degrades to a log entry; once the connection is down that result is lost with **no** compensation, side effects the tool function has already produced are not rolled back, but **no** exception is allowed to escape the worker thread any longer (the original implementation let the worker thread exit with an exception; see §12 G8). When the connection drops while the caller is waiting, the wait entry is woken by the protocol layer's disconnection cleanup (`ToolResult(error="connection closed")`). This pattern does **not** define resumption after reconnection.

**6.5 `reqid` mismatch** — the callee's `_on_input_response` looks up the wait entry by `reqid` and silently discards the message when it finds none; the caller's `_on_tool_result` / `_on_input_required` likewise look up by `reqid` and silently discard on a miss. ~~**Neither side checks the source `node_id`**~~ ✅ **Fixed**: both sides now verify, by **connection identity** (rather than the forgeable `sig.source`), whether "this answer comes from the peer I called", and discard it on a mismatch. This one is necessary — the reference implementation's `reqid` values are **predictable**, such as `mr-1` and `mr-2`, and **MUST NOT** be treated as a security token ([security](../security.md) §3.10). See §8.

**6.6 Re-entrancy and concurrency** — concurrent calls **MAY** happen: each call has its own `reqid` and its own event and result slots. But **two concurrent `ctx.ask()` calls within the same `reqid` are not supported**: the wait entry is keyed by `reqid` and has a single slot. A tool function **MUST NOT** call `ask()` for the same `reqid` from several threads at once; the reference implementation detects re-entrancy and raises `RuntimeError` (the original implementation silently overwrote the entry, so the earlier call was bound to time out; see §12 G6). **Re-entrancy hazard**: `input_fn` runs on the caller's read-loop thread, so if `input_fn` itself starts a call to the **same peer** and waits for the reply, the reply is never read and both sides wait until timeout.

**6.7 Callback exceptions** — any exception raised by `input_fn` is caught by the caller and turned into `answer = {"error": "<exception text>"}`, then sent back as usual, so **the follow-up is not interrupted by it**; the callee **MUST** decide for itself whether that object follows the "failure" convention.

### 6.8 Differences from MCP `elicitation`

| Dimension | MCP `elicitation` | `msp/multi-round` |
|---|---|---|
| request correlation | **starts a separate reverse request** with its own request identifier, not shared with the original call | continues the original call's `reqid`, one correlation key throughout |
| state of the original call | whether the original call is still waiting is maintained by the application layer | the original call **blocks in place** on the callee; the execution stack is preserved |
| number of follow-ups | one reverse request per elicitation | **MAY** follow up unlimited times within the same `reqid` |
| payload | a constrained structure with a JSON Schema (field names, types, enums) | one piece of `prompt` text only, no schema |
| direction of permission | by convention the server elicits from the client | both directions: either side can start one as long as it holds the connection (here the callee starts it) |
| reuse of existing primitives | needs a new reverse request channel | reuses the `reqid` correlation of `tool_call`; no change to the core |

Conclusion: `elicitation` solves "can the server ask a question", whereas this pattern solves "can the context of this one call stay alive until the answer arrives". The two can coexist; to express `elicitation` semantics in MSP it should be a separate capability surface (see [capabilities](../capabilities.md)) rather than a reuse of this pattern.

## 7. Summary of normative provisions

**MUST**: ① the four signal types of this pattern **MUST** carry `pattern = "msp/multi-round"`; ② within one interaction the `reqid` of `input_required`, `input_response` and `tool_result` **MUST** be the same as that of the opening `tool_call`; ③ the callee **MUST** execute the tool function on a separate thread (or an equivalent execution body outside the read loop); ④ `input_required.payload.prompt` and `input_response.payload.answer` **MUST** be present; ⑤ the same `reqid` **MUST** produce only one `tool_result`; ⑥ unrecognised fields and signal types **MUST NOT** cause the connection to drop ([lenient reading](../base-protocol.md#23-lenient-reading)).

**SHOULD**: ⑦ the caller **SHOULD** confirm before calling that the peer has announced this pattern; ⑧ the caller **SHOULD** make the overall timeout cover every expected follow-up; ⑨ the callee **SHOULD** express failures as `tool_result.payload.error` rather than an `error` signal; ⑩ an implementer that wants to skip a follow-up **SHOULD** reply with `answer = null` rather than not replying.

**MUST NOT**: ⑪ the caller **MUST NOT** assume the number of follow-ups, the type of `answer` or the structure of `prompt`; ⑫ the callee **MUST NOT** call `ctx.ask()` inside the read-loop thread; ⑬ patterns outside the `msp/` namespace **MUST NOT** reuse the two `type` values `input_required` / `input_response`; ⑭ a fallback implementation **MUST NOT** silently change semantics already emitted (see §2.1).

**MAY**: ⑮ an implementation **MAY** not implement this pattern; once it does, it **MUST** conform to the provisions on this page. ⑯ an implementation **MAY** extend the fields of `input_required.payload` beyond this page.

## 8. Security considerations

- **Source not verified**: both sides correlate only by `reqid` and do not verify `source`. The reference implementation's `reqid` is predictable (`mr-<n>`), so "receiving an `input_response`" **SHOULD** be treated as **unauthenticated input**, and it **MUST NOT** under any circumstances be the sole basis for high-value decisions such as authorization, identity or amount. Implementers **SHOULD** switch to an unpredictable `reqid` and verify the source node.
- **Every follow-up is a data entry point**: `answer` goes straight into the control flow of the tool function. The tool **MUST** validate it as ordinary untrusted input (length, type, value range) and **MUST NOT** interpolate it into commands, paths or queries without escaping.
- **Information leakage**: `prompt` is controlled by the callee and is handed verbatim to the caller's `input_fn`. The caller **SHOULD** render or log `prompt` as untrusted text, to avoid injecting into local log formats or terminal control sequences.
- **No authorization layer**: this pattern makes no authorization decisions; who may call a tool is decided by the connection and deployment policy, see [security](../security.md).

## 9. Known gaps

The following paths are **not handled** in the reference implementation (counted as 🟡 **partially implemented**; planned fixes are marked 🔵):

| ID | Gap | Current state |
|---|---|---|
| G1 | automatic fallback not implemented | `fallback_to` is only declared, never consumed; when the peer does not support the pattern it neither falls back nor errors, relying on the overall timeout as a backstop |
| G2 | ~~the caller does not check peer capability and does not connect automatically~~ ✅ **Fixed** | `call_multiround()` now calls `ensure_connected()` before querying `peer.supports(pattern_id)`; it raises `RuntimeError` immediately when the peer has not announced this pattern, and an initial request that fails to send also clears the wait table and reports an error |
| G3 | ~~the `error` signal does not wake a waiting call~~ ✅ **Fixed** | the protocol layer's `_on_error` now wakes the waiting call by `reqid` (`ToolResult(error=...)`, including `code`) and no longer waits out the overall timeout (fixed together with task G11) |
| G4 | no cancellation mechanism | the caller sends no cancellation after a timeout; the callee does not know the other side has given up, and the tool keeps running until its own timeout |
| G5 | `input_required` payload has no structure | only `prompt` text, with no argument names/types/enums/context; machine-checkable follow-ups are impossible |
| G6 | ~~concurrent `ask()` within the same `reqid` overwrites itself~~ ✅ **Fixed** | the wait table is still keyed by `reqid` with a single slot, but a second `ask()` now raises `RuntimeError` explicitly (the constraint that the caller **MUST NOT** follow up concurrently is now enforced by the implementation) |
| G7 | `input_fn` runs on the read-loop thread | a blocking `input_fn` blocks all message processing on that connection; re-entering the same peer makes both sides wait for each other |
| G8 | ~~the sender does not catch disconnection exceptions~~ ✅ **Fixed** | `_reply_result()` / `input_response` are all sent through `_send()`, which catches `(RuntimeError, ConnectionClosed)` and degrades to a log entry |
| G9 | source `node_id` not verified | see §8 |
| G10 | ~~`inspect.signature(func)` outside the try~~ ✅ **Fixed** | the introspection in `_run_tool()` is now inside the `try` too, so a function that cannot be introspected returns a `tool_result{error}` instead of dying silently |
| G11 | no progress notification mid-flight | there is no "still running" heartbeat beyond the follow-ups; during a long tool the caller can only judge by the connection staying alive |
| G12 | 🔵 planned: structured schema for follow-ups | if implemented, it **MUST** add separate fields and **MUST NOT** change the meaning of `prompt` |
| G13 | 🔵 planned: cancellation within the pattern | if implemented, it **MUST** be expressed within the same `reqid`, and the callee **SHOULD** respond at the next interruptible point |

## 10. Reference implementation map

| Provision | Source file and symbol |
|---|---|
| §2.1 pattern identity / fallback declaration / no automatic fallback | [`src/msp/patterns/multi_round.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/multi_round.py) `MultiRoundHandler.pattern_id` / `.fallback_to`; [`src/msp/patterns/base.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/base.py) `PatternHandler.fallback_to` |
| §2.2 private signal type constants / `pattern` routing key | `multi_round.py` `MultiRoundHandler.INPUT_REQUIRED` / `.INPUT_RESPONSE` / `.TOOL_CALL` / `.TOOL_RESULT`; [`protocol.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._dispatch` |
| §2.3 tool executed on a separate thread / `ctx.ask` signature and blocking | `multi_round.py` `MultiRoundHandler._on_tool_call` / `._run_tool` / `_ask`; `RoundContext.ask` |
| §3.1–§3.4 payloads of the four message types | `multi_round.py` `call_multiround` (`{"tool":…,"args":…}`), `_ask` (`{"prompt":…}`), `_on_input_required` (`{"answer":…}`), `_reply_result` (`{"content":…,"error":…}`) |
| §3.4 differences from the core shape | `protocol.py` `_normalize_tool_result` / `MSPProtocol._run_tool` (core path) |
| §4 message flow | the sequence diagram in the `multi_round.py` module docstring; the end-to-end example [`src/examples/multi_round_demo.py`](https://github.com/hxh230802/MSP/blob/master/src/examples/multi_round_demo.py) |
| §6.1 backstop routing (unknown types reply `-32600`) | `protocol.py` `MSPProtocol._dispatch` / `._dispatch_core` |
| §6.7 callback exceptions turned into answers | the `try/except` in `multi_round.py` `_on_input_required` |
| §9 G6/G7/G9 | the key and slot design of `multi_round.py` `_active_asks` / `_pending_calls` |
| pattern activation and syntactic sugar / preset declarations | [`src/msp/core/node.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `MSPNode.register_pattern` / `._activate_pattern`; `multi_round.py` `install_api`; [`src/msp/core/preset.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/preset.py) `Preset.FULL_PEER` / `LOCAL_AI` / `CLOUD_SERVICE` |
