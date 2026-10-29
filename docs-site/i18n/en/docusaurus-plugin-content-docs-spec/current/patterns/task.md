# `msp/task` — Task Delegation

| | |
|---|---|
| **Protocol revision** | `2026-10-10` |
| **Pattern ID** | `msp/task` |
| **Status markers** | ✅ **Implemented** (submission, state machine, artifacts, cancellation, follow-up questions, query and observer broadcast are all verifiable on the reference implementation); the boundaries listed in §12 are 🟡 **Partially implemented** |
| **Fallback target** | `msp/request-reply` (`fallback_to`); `conflicts_with` is not declared |
| **Normative language** | RFC 2119, see the [specification index](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#2-规范性用语) |
| **Defined on this page** | Task delegation semantics: state machine + artifacts + observer broadcast + A2A equivalence mapping |

## 1. Overview

### 1.1 Pattern positioning

A2A (Agent2Agent) is a **protocol stack**, not a pattern: it brings its own transport (HTTP), encoding (JSON-RPC), discovery (Agent Card) and a whole family of interaction primitives. MSP carries over only the layer that is **genuinely new** — **task semantics**: a task has an identity, a state machine and artifacts, can be queried, can be cancelled, and can be watched by third parties; every other interaction reuses existing primitives.

| Capability needed | Reused from |
|---|---|
| Request/reply correlation | the `reqid` mechanism of [`msp/request-reply`](./request-reply.md) |
| Directed unicast | the protocol layer's `_send(peer_id, signal)` |
| Broadcast fan-out | `publish(path, payload)` of [`msp/publish-subscribe`](./publish-subscribe.md) |
| Follow-up questions during execution | `input_required` / `input_response` of [`msp/multi-round`](./multi-round.md) |
| Shape of artifact content | the content blocks of [`core/content.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) |

So this pattern introduces exactly two new abstractions: the **state machine** and the **artifact**.

### 1.2 Key trade-offs

1. `submit()` **blocks only until "accepted"**: it returns as soon as it has the `task_id` and the `submitted` state, which matches A2A `message/send` returning a non-terminal Task. A task may run for hours, so blocking until completion is an anti-pattern; use `handle.wait()` to wait for completion.
2. **Cancellation is cooperative**: set a flag and send the terminal state immediately, every subsequent emit by the worker is a no-op, and the thread is **not** killed by force (see ["Cancellation"](#8-cancellation), §12 G2).
3. **Observer broadcast is the capability that differentiates this pattern from A2A**: A2A's SSE / webhook are both single-subscriber, whereas MSP's publish/subscribe naturally supports multiple observers (see §6).
4. **`input-required` reuses the existing follow-up mechanism** instead of reinventing it (see §3.9).

## 2. Contract and state machine

### 2.1 Pattern identifier

```python
class TaskHandler(PatternHandler):
    pattern_id  = "msp/task"             # taken verbatim from the source
    fallback_to = "msp/request-reply"    # taken verbatim from the source
    # conflicts_with is not declared: inherits PatternHandler's default []
```

`pattern_id` is both an entry of `Manifest.patterns` and the routing key of `Signal.pattern`. **Fallback fact**: `fallback_to` is only declared and is read by no code anywhere in the repository, so **no automatic fallback happens today** (the same situation as [`msp/multi-round`](./multi-round.md#21-pattern-identity-and-fallback)). An implementer **MAY** implement fallback, but **MUST**: after falling back, complete the same call with `tool_call` / `tool_result` that carry no `pattern`; **MUST NOT** emit any `task_*` signal on the fallback path; and **SHOULD** make the caller explicitly aware that fallback has happened. **Mutual-exclusion fact**: `conflicts_with` is likewise consumed by no code and is always `[]`; this pattern **MAY** coexist with any other pattern, and redefining `input_required` / `input_response` internally is not a conflict either (for the reason see §3.9).

### 2.2 The six state constants

| Constant | String value | Terminal | Meaning |
|---|---|---|---|
| `STATE_SUBMITTED` | `"submitted"` | No | Accepted, execution not yet started |
| `STATE_WORKING` | `"working"` | No | Running |
| `STATE_INPUT_REQUIRED` | `"input-required"` | No | Waiting for the submitter to supply information |
| `STATE_COMPLETED` | `"completed"` | **Yes** | Finished normally |
| `STATE_FAILED` | `"failed"` | **Yes** | Failed |
| `STATE_CANCELED` | `"canceled"` | **Yes** | Cancelled |

The terminal set is `frozenset({"completed", "failed", "canceled"})`. **Spelling trap (checked verbatim against the source)**: the state value `input-required` uses a **hyphen** (aligned with A2A `TaskState`), whereas the signal type `input_required` uses an **underscore**; the two **MUST NOT** be interchanged and **MUST NOT** be normalised.

### 2.3 State machine (ASCII)

```text
  task_submit
       │
       ▼
 ┌─────────────┐  records the initial state at creation; announced by task_submit_result, no separate task_status
 │  submitted  │
 └──────┬──────┘
        │ worker thread starts: _transition(working, "")
        ▼
 ┌─────────────┐   ctx.status(state, message) can be entered again
 │   working   │◀────────────────────────────┐
 └──┬───────┬──┘                             │
    │       │ ctx.ask(prompt)                │ on input_response
    │       ▼                                │ or follow-up timeout
    │  ┌──────────────────┐                  │
    │  │  input-required  │──────────────────┘
    │  └──────────────────┘
    │  _finish(): returns normally, no cancel requested ─▶ completed
    │              raises a non-TaskCanceled exception ─▶ failed    the three terminal states: mutually
    └──────────────raises TaskCanceled / cancel already set ─▶ canceled  exclusive, irreversible, no further output
```

### 2.4 Transition legality and irreversibility of terminal states

| From | To | Trigger point | Signal emitted |
|---|---|---|---|
| (no record) | `submitted` | accept `task_submit`, create the record | announced by `task_submit_result.payload.state` |
| `submitted` | `working` | `_transition(working, "")` when the worker starts | `task_status` |
| `submitted` / `working` | `input-required` | before `ctx.ask()` asks | `task_status` + `input_required` |
| `input-required` | `working` | on `input_response`, or on follow-up timeout | `task_status` |
| `working` | `working` | `ctx.status("working", msg)` | `task_status` |
| `working` / `input-required` | `completed` | `_finish(completed)`: the function returns normally and `cancel_event` is not set | `task_result` |
| `working` / `input-required` | `failed` | `_finish(failed, error=…)`: the function raises a non-`TaskCanceled` exception | `task_result` |
| any non-terminal state | `canceled` | `_finish(canceled)`: `task_cancel` received, or the function raises `TaskCanceled`, or `cancel_event` is already set when the function returns | `task_result` (sent **immediately** on cancellation, without waiting for the worker) |

① A terminal state **MUST NOT** be reverted, and once the record is terminal `_transition` / `_push_artifact` / `_finish` **MUST** be no-ops; ② the same `task_id` **MUST** produce exactly one `task_result`; ③ `submitted` **MUST NOT** be announced with a separate `task_status`; ④ after accepting a task the executor **SHOULD** enter `working` first (or go through `input-required`); **exception**: when the cancellation arrives before the worker starts, `_on_cancel` sets `submitted` straight to `canceled` and skips `working` (see §7.5 and §12 G3); ⑤ state values **MUST** be taken from the six strings of §2.2 (the reference implementation does not validate the value; an implementer **MUST NOT** loosen this on that basis).

## 3. Messages (signal by signal)

### 3.1 Common envelope conventions

`Signal` envelope fields are always snake_case (`type` / `source` / `pattern` / `target` / `path` / `reqid` / `payload` / `timestamp`); inside `payload` the convention is always camelCase (`taskId` / `contextId`), and the two **MUST NOT** be mixed.

| Constraint | Provision |
|---|---|
| `pattern` | every directed signal of this pattern **MUST** carry `pattern = "msp/task"` |
| `target` | a directed signal **MUST** fill in the peer's `node_id`; an observer broadcast (`type = "signal"`) **MUST NOT** fill in `target` |
| `reqid` | carried only by request/reply signals; a push signal **MUST NOT** carry it |
| `path` | used only by observer broadcasts: `task.<task_id>.<kind>`, `kind ∈ {status, artifact, result}` |

| Signal `type` | Direction | `reqid` | Simultaneous broadcast |
|---|---|---|---|
| `task_submit` | caller → executor | Yes | No |
| `task_submit_result` | executor → caller | filled in | No |
| `task_status` | executor → caller | **No** | Yes, `.status` |
| `task_artifact` | executor → caller | **No** | Yes, `.artifact` |
| `task_result` | executor → caller | **No** | Yes, `.result` |
| `task_query` | caller → executor | Yes | No |
| `task_query_result` | executor → caller | filled in | No |
| `task_cancel` | caller → executor | Yes | No |
| `task_cancel_result` | executor → caller | filled in | No |
| `input_required` | executor → caller | **No** (correlated by `taskId`) | No |
| `input_response` | caller → executor | **No** (correlated by `taskId`) | No |

### 3.2 `task_submit`

| Field | Type | Required | Value |
|---|---|---|---|
| `payload.task` | string | **MUST** | task name (key of the executor's registry) |
| `payload.args` | object | **MUST** | task arguments; the reference implementation defaults to `{}` |
| `payload.contextId` | string \| null | **MUST** (may be `null`) | context identifier supplied by the caller, echoed back verbatim by the executor |

```json
{ "type": "task_submit", "source": "b", "pattern": "msp/task", "target": "a", "path": null,
  "reqid": "9f1c2d3e4a5b6c7d",
  "payload": { "task": "generate_report", "args": { "topic": "quarterly review" }, "contextId": "ctx-1" } }
```

### 3.3 `task_submit_result`

Success (accepted): `payload.taskId` (string, **MUST**, shaped like `task-<16 hex digits>`), `payload.contextId` (string\|null, **MUST**, echoed back verbatim), `payload.state` (string, **MUST**, always `"submitted"`).

Failure (unknown task): only `payload.error` (string, **MUST**, shaped like `"unknown task: <name>"`); it **MUST NOT** carry `taskId` or `state`. The caller **SHOULD** distinguish success from failure by whether `state` is present.

### 3.4 `task_status`

| Field | Type | Required | Value |
|---|---|---|---|
| `payload.taskId` | string | **MUST** | task identifier |
| `payload.state` | string | **MUST** | one of the non-terminal strings of §2.2 (the reference implementation does not validate it) |
| `payload.message` | string | **MUST** | state description; the empty string for `working` with no description |

When it appears: always once when the worker starts (`working` with an empty `message`); once per `ctx.status(...)` call; once on entering and once on leaving `input-required`. Apart from these, `task_status` **MUST NOT** be sent.

### 3.5 `task_artifact`

| Field | Type | Required | Value |
|---|---|---|---|
| `payload.taskId` | string | **MUST** | task identifier |
| `payload.artifact` | object | **MUST** | `{name, description, parts}`, see §5.4 |

**One message per artifact**: `ctx.artifact()` / `ctx.emit()` each send one, **not** batched together; none **MUST** be sent after the terminal state.

### 3.6 `task_result`

| Field | Type | Required | Value |
|---|---|---|---|
| `payload.taskId` | string | **MUST** | task identifier |
| `payload.state` | string | **MUST** | one of the three terminal states |
| `payload.message` | string | **MUST** | terminal state description; usually the empty string for `completed`, `"task cancelled"` for `canceled` |
| `payload.error` | string | **MUST** | failure text; the empty string when not `failed` |
| `payload.artifacts` | array | **MUST** | **all** artifact objects accumulated up to the terminal state (may be an empty array) |

```json
{ "type": "task_result", "source": "a", "pattern": "msp/task", "target": "b", "reqid": null,
  "payload": { "taskId": "task-3f2a9c1b4d5e6f70", "state": "completed", "message": "", "error": "",
    "artifacts": [ { "name": "text", "description": "", "parts": [{ "type": "text", "text": "first paragraph" }] } ] } }
```

`artifacts` is a **full snapshot**, not a delta: the receiver **SHOULD** use it to replace its local accumulated list and **MUST NOT** append-merge it (otherwise it duplicates the `task_artifact` messages already received).

### 3.7 `task_query` and `task_query_result`

`task_query` has a single payload field: `payload.taskId` (string, **MUST**).

`task_query_result` on success: `payload.taskId` (string, **MUST**), `payload.contextId` (string\|null, **MUST**), `payload.state` (string, **MUST**, any state including a terminal one), `payload.message` (string, **MUST**), `payload.error` (string, **MUST**, or the empty string), `payload.artifacts` (array, **MUST**, the accumulated artifacts).

Failure (unknown `taskId`): `payload.taskId` (**MUST**, echoes the requested value) + `payload.error` (**MUST**, `"unknown task: <taskId>"`); it **MUST NOT** carry `state`.

### 3.8 `task_cancel` and `task_cancel_result`

`task_cancel` has a single payload field: `payload.taskId` (string, **MUST**).

`task_cancel_result`: `payload.taskId` (string, **MUST**), `payload.accepted` (boolean, **MUST**), `payload.error` (string, **optional**, present only when `accepted = false`, shaped like `"unknown task: <taskId>"`).

**`accepted = true` does not mean "the state has become canceled".** For a task that is already terminal, the reference implementation likewise replies `accepted = true` (no `_finish`, no error), so the caller cannot tell "cancellation succeeded" from "the task had already finished"; when the distinction matters, the caller **SHOULD** read the real state with `task_query`.

### 3.9 `input_required` and `input_response`

This pattern **redefines** two signal types that share their names with [`msp/multi-round`](./multi-round.md), in order to reuse the same follow-up mechanism:

| Signal | Payload field | Type | Required | Difference from multi-round |
|---|---|---|---|---|
| `input_required` | `payload.taskId` | string | **MUST** | new in this pattern; multi-round has no such field |
| `input_required` | `payload.prompt` | string | **MUST** | same as multi-round |
| `input_response` | `payload.taskId` | string | **MUST** | new in this pattern |
| `input_response` | `payload.answer` | any | **MUST** | same as multi-round; `null` when `input_fn` is `None`, `{"error": "<exception text>"}` when it raises |

**The correlation key differs (the key difference)**: these two signals of this pattern **do not carry `reqid`**; the question and the answer are correlated solely by `payload.taskId`. An implementer **MUST NOT** correlate this pattern's follow-up chain by `reqid`, and **MUST NOT** assume that the two patterns' payloads are the same just because the names match.

**Why same-named signals do not conflict**: the routing key is `Signal.pattern` — [`_dispatch`](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) step 2 first looks up `self.patterns[msg.pattern]`, and the matching handler handles the whole signal exclusively; `input_required` is merely a value of the `type` field and takes no part in routing itself. A follow-up carrying `pattern = "msp/task"` goes to `TaskHandler`, one carrying `pattern = "msp/multi-round"` goes to `MultiRoundHandler`, and neither can see the other. The price is: **a pattern-private `type` without a `pattern` is a protocol error** and is answered with `error` (`code = -32600`) by the default branch. Patterns outside the `msp/` namespace **MUST** prefix their own types ([specification index §5.1](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#51-核心信号类型signaltype)).

## 4. Message flow

### 4.1 Normal path: submit → working → several artifacts → result

```text
  caller (b)                                                    executor (a)
   │ ① task_submit  reqid=r1  payload={task:"generate_report",             │
   │      args:{topic:"quarterly review"}, contextId:"ctx-1"}               │
   ├───────────────────────────────────────────────────────────────────────▶│
   │                            look up the task registry → create the record
   │                            (state="submitted"), send receipt ② first,
   │                            then start the worker thread                │
   │ ② task_submit_result  reqid=r1                                        │
   │    payload={taskId:"task-3f2a…",contextId:"ctx-1",state:"submitted"}  │
   │◀───────────────────────────────────────────────────────────────────────┤
   │ submit() returns TaskHandle(state=submitted)                          │ starts the worker
   ▼                                                                       ▼
   │                                          _transition(working,"")     │
   │ ③ task_status (reqid=null) payload={taskId,state:"working",message:""}│
   │◀───────────────────────────────────────────────────────────────────────┤
   │ also publish → signal path="task.task-3f2a….status"                    │
   │                                           ctx.emit("first paragraph") │
   │ ④ task_artifact (reqid=null) payload={taskId,artifact:{name:"text",   │
   │      description:"",parts:[{type:"text",text:"first paragraph"}]}}     │
   │◀───────────────────────────────────────────────────────────────────────┤
   │ also publish → path="task.task-3f2a….artifact"                         │
   │                                            ctx.artifact(name="chart",…)
   │ ⑤ task_artifact (reqid=null)                                          │
   │◀───────────────────────────────────────────────────────────────────────┤
   │                                 function returns → _finish(completed) │
   │ ⑥ task_result (reqid=null) payload={taskId,state:"completed",         │
   │      message:"",error:"",artifacts:[…all artifacts]}                   │
   │◀───────────────────────────────────────────────────────────────────────┤
   │ also publish → path="task.task-3f2a….result"                           │
   │ handle.wait() wakes up and returns the final TaskSnapshot             │
   ▼                                                                       ▼
```

Three ordering constraints: ② **MUST** precede ③ (announce `submitted` first, then start the worker); ③ **MUST** precede ④⑤; ⑥ **MUST** be the last directed message of the same `task_id`.

### 4.2 Follow-up question path

```text
   │ ③a task_status  state="input-required", message="which basis?"        │
   │◀──────────────────────────────────────────────┤ ctx.ask("which basis?")
   │ ③b input_required  payload={taskId,prompt:"which basis?"} (no reqid)  │
   │◀──────────────────────────────────────────────┤ ask() blocks, default 30s
   │ handle.input_fn(prompt) → "by calendar quarter" │                     │
   │ ③c input_response  payload={taskId,answer:"by calendar quarter"} (no reqid) │
   ├──────────────────────────────────────────────▶│ wakes ask()
   │ ③d task_status  state="working", message=""    │                     │
   │◀──────────────────────────────────────────────┤                     │
```

A follow-up question **MAY** happen any number of times within the same task; each entry into `input-required` sends `task_status` first and `input_required` second, and a further `task_status(working)` on the way out. A follow-up timeout also returns to `working`, but `ctx.ask()` raises `TimeoutError`, which usually makes the task `failed` shortly afterwards.

### 4.3 Query path

```text
   │ task_query  reqid=r3  payload={taskId}  ├────▶│ reads a snapshot of the task record
   │◀───────────────────────────────────────────────┤
   │ task_query_result  reqid=r3  payload={taskId, contextId, state, message, error, artifacts}
```

A task record is **not** cleaned up when the connection closes and remains queryable after reconnection; a query is read-only and **MUST NOT** change the task state.

## 8. Cancellation

```python
handle.cancel(timeout=5.0) -> bool        # delegates to handler.cancel
cancel(peer_id, task_id, timeout=5.0) -> bool
```

```text
   │ ⑦ task_cancel  reqid=r2  payload={taskId:"task-3f2a…"}               │
   ├──────────────────────────────────────────────▶│ _on_cancel:
   │                                cancel_event.set(); if blocked in ask(),
   │                                write the cancel sentinel and wake it;
   │                                immediately _finish(canceled)
   │ ⑧ task_result  payload={taskId,state:"canceled",                      │
   │      message:"task cancelled",error:"",artifacts:[…artifacts before cancellation]} │
   │◀──────────────────────────────────────────────┤
   │ also publish → path="task.task-3f2a….result"   │ the worker thread is still running:
   │ ⑨ task_cancel_result  reqid=r2                 │ later artifact/status/
   │    payload={taskId,accepted:true}              │ finish calls are all no-ops, until
   │◀──────────────────────────────────────────────┤ it observes
   │ handle.wait() returns with canceled            │ cancel_requested() itself
```

Note that ⑧ precedes ⑨: the reference implementation sends `task_result` first and `task_cancel_result` afterwards; the caller **MUST NOT** assume the opposite order.

The executor-side implementation has three steps: (1) set `cancel_event`, and if the worker is currently blocked in `ctx.ask()`, write the cancel sentinel and wake it; (2) send the terminal `task_result{state:"canceled", message:"task cancelled"}` **immediately**, without waiting for the worker to react; (3) from then on every `_transition` / `_push_artifact` / `_finish` of the worker is a no-op.

**Threads are not killed by force, and that is a Python limitation**: CPython has no safe thread-interruption primitive. The consequences must be stated plainly: the task function **is still running** until it discovers the signal by calling `ctx.cancel_requested()` itself, or ends naturally; artifacts produced after the cancellation are **silently discarded** and the caller never sees them; the side effects of the task function (writing files, sending requests) are **not** rolled back; if the task function never checks `cancel_requested()` (a tight CPU loop, for instance), the thread and the resources it holds persist until the function returns; when the cancellation arrives the worker may not have started yet, in which case the record has already been set to the terminal state, but **the thread still starts and runs the task function**, whose return value and exceptions are discarded.

A task function **SHOULD** therefore call `ctx.cancel_requested()` at interruptible points and return as soon as possible, and **MUST NOT** assume that cancellation stops computation at once. Task-level cancellation (`task_cancel`) and the core [`cancel` signal](../base-protocol.md#63-cancellation) are two separate mechanisms: the latter targets **a single in-flight call** and is correlated by `reqid`, whereas task cancellation targets a `taskId` and spans several requests. An implementer **MUST NOT** use the core `cancel` in place of `task_cancel`, and **MUST NOT** require the peer to implement the core `cancel` in order to cancel a task.

## 5. Data types and public API

### 5.1 `submit()` — blocks only until "accepted"

```python
submit(peer_id, task, args=None, context_id=None, input_fn=None, timeout=5.0) -> TaskHandle
submit_and_wait(peer_id, task, args=None, context_id=None,
                input_fn=None, timeout=None, submit_timeout=5.0) -> TaskSnapshot
handle.wait(timeout=None) -> TaskSnapshot     # blocks until the terminal state; raises TimeoutError on timeout
```

| Parameter | Default | Description |
|---|---|---|
| `peer_id` / `task` | required | executor `node_id` / task name |
| `args` | `None` → `{}` | task arguments |
| `context_id` | `None` | goes into `payload.contextId`; may be `null` |
| `input_fn` | `None` | answer function `(prompt) -> Any` used when the executor calls `ctx.ask()` |
| `timeout` (submit) | `5.0` | covers **only** the "accepted" phase, **not** execution |
| `timeout` (wait) | `None` | `None` means **wait indefinitely**; if omitted there is no timeout |

Pre-checks: first `ensure_connected(peer_id)` (an unknown node raises `UnknownPeer`, an unreachable one raises `PeerUnavailable`), then verify `peer(peer_id).supports("msp/task")`, raising `RuntimeError` if that is not satisfied. A failure response raises `RuntimeError(<error text>)`; waiting past the timeout raises `TimeoutError`. The returned `TaskHandle` has `state` equal to `submitted`.

**Returning does not mean execution has started, let alone succeeded**: the task may fail at once, and a failure can only be observed through `wait()` / `get()` / callbacks. `submit_and_wait` is merely sugar for `submit(..., timeout=submit_timeout).wait(timeout=timeout)` and **does not** change any message semantics.

### 5.2 `get()` and handle callbacks

```python
get(peer_id, task_id, timeout=5.0) -> TaskSnapshot    # sends task_query internally
handle.on_status(cb)     # cb(state: str, message: str) -> None, returns self
handle.on_artifact(cb)   # cb(artifact: Artifact) -> None, returns self
```

`get()` raises `RuntimeError` for an unknown `task_id`; the criterion is **whether the response carries `state`**, **not** an error code. `on_status` fires on every `task_status`, on `input_required` (where `state = "input-required"` and `message = prompt`) and on `task_result` (terminal); `on_artifact` fires on every `task_artifact` — `task_result` **does not** call back with artifacts, it only replaces `handle.artifacts`. Callbacks are **not** guaranteed to have finished before `wait()` returns (the terminal event is set first, then the callbacks are invoked in order), so a caller that needs strict ordering **SHOULD** synchronise inside the callback itself.

### 5.3 `TaskSnapshot`

| Field | Type | Description |
|---|---|---|
| `task_id` | string | task identifier |
| `state` | string | one of the six strings of §2.2 |
| `artifacts` | list[`Artifact`] | artifacts up to that moment |
| `message` | string | most recent state description |
| `error` | string | failure text or the empty string |
| `context_id` | string \| null | the context identifier passed at creation |
| `is_terminal()` | method | `state in {"completed","failed","canceled"}` |

The on-wire form (the keys read by `from_dict`) is camelCase: `taskId` / `state` / `artifacts` / `message` / `error` / `contextId`.

### 5.4 `Artifact` and `parts`

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | `""` | artifact name; `ctx.emit()` defaults to `"text"`, a task function return value defaults to `"result"` |
| `description` | string | `""` | artifact description |
| `parts` | list | `[]` | list of content blocks, reusing [`core/content.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) |

Elements of `parts` are content-block objects or bare dicts, with `type` values: `text` / `image` / `audio` / `resource` / `resource_link` / `blob_ref`. A block of unknown `type` **MUST** be preserved as it is (lenient reading). `Artifact.to_dict()` does not convert elements that are already dicts; `Artifact.from_dict()` runs `block_from_dict` on dict elements and keeps non-dict elements as they are.

### 5.5 `TaskContext` and exceptions

If the signature of the task function contains a parameter named `ctx`, the executor **MUST** inject a `TaskContext` (injected as `func(ctx=ctx, **args)`; if `args` already contains `ctx`, **a `TypeError` is raised**, the task is therefore recorded as `failed` and the exception text goes into `task_result.payload.error` — this differs from the **overwrite** semantics `{**args, "ctx": ctx}` of `msp/multi-round`, so an implementer **MUST NOT** pass `ctx` inside `args`).

| Member | Semantics |
|---|---|
| `task_id` / `context_id` / `peer_id` / `args` | attributes: task identifier, context identifier, submitter `node_id`, original arguments |
| `status(state, message="")` | report one state transition; **accepts only** `working` / `input-required` (terminal states are produced by the protocol itself, see §2.4 rule ③) |
| `emit(text, name="")` | produce a text artifact (equivalent to a single `text` part) |
| `artifact(name="", parts=None, description="")` | produce an arbitrary artifact |
| `ask(prompt, timeout=30.0)` | ask a follow-up question and block for the answer; raises `TaskCanceled` when the task is already terminal; raises `TimeoutError` on timeout and returns to `working` |
| `cancel_requested()` | whether cancellation has been requested (the checkpoint of cooperative cancellation) |

The `state` argument of `status()` is validated (originally a defect, see §12 G5): it accepts only `working` / `input-required`, and passing a terminal state (such as `"completed"`) or `submitted` raises `ValueError` — previously a terminal state bypassed the protocol and changed the record state directly, **without** emitting `task_result`, leaving the client's `wait()` hanging until its timeout; the exception follows the task function's exception path and is recorded as `failed`, so the caller gets a definite error at once. Among the exceptions a task function raises, `TaskCanceled` (a subclass of `TaskError`) is recorded as `canceled`, and **all others** are recorded as `failed` with `str(e)` going into `task_result.payload.error`. Exception text crosses the wire verbatim, so a task function **MUST NOT** write credentials, keys, absolute paths or similar information into its exception messages.

## 6. Observer broadcast and Agent Card projection

### 6.1 Observer broadcast

Besides sending the three kinds of message directly to the submitter, the executor **also** publishes the same `payload` to dotted paths:

```text
task.<task_id>.status      ← the payload of task_status
task.<task_id>.artifact    ← the payload of task_artifact (one per artifact)
task.<task_id>.result      ← the payload of task_result
```

Publication goes through [`publish()`](./publish-subscribe.md), so the message `type` is the core `signal`, it carries `path`, and it carries **no** `pattern`, `target` or `reqid`. Any already-connected peer can watch the progress with `on("task.**")`, **without** registering `msp/task` and **without** being authorised as a submitter. The fan-out target is "all established connections", so an observer **MUST** first establish a connection to the executor; the executor **does not** deliver to itself, and local callbacks inside the same node **cannot see** the broadcasts. The submitter receives both the directed message and the broadcast copy, so an implementer **SHOULD** deduplicate by `Signal.type` and **MUST NOT** count the broadcast copy as "one extra state change".

**This is the capability that differentiates the pattern from A2A**: both SSE and webhook in A2A are **single-subscriber** models — one task stream can have only one receiver, and a third party that wants to watch must be forwarded to by that receiver. MSP's publish/subscribe naturally supports **multiple observers**, and each observer filters by path wildcard itself (see the wildcard matching algorithm in [publish-subscribe](./publish-subscribe.md)). Security note: the broadcast **does not** distinguish observer identity; task identifiers, state descriptions and artifact contents are visible to **all** connected peers; sensitive tasks **SHOULD** instead be collected point-to-point or have the broadcast turned off (the reference implementation provides **no** switch, see §12 G9).

### 6.2 Agent Card projection

An A2A Agent Card describes "who this agent is and what it can do". In MSP it is **not** a core protocol concept but **pattern-specific metadata**: `node.register_pattern("msp/task", metadata={...})` → `Manifest.pattern_metadata["msp/task"]`.

| Item | Fact |
|---|---|
| Carrier | `Manifest.pattern_metadata["msp/task"]`; the on-wire key is `patternMetadata` (camelCase) |
| Core attitude | The Manifest core neither **sees** nor **validates** this metadata; it is exchanged verbatim with the manifest |
| Side effect | `set_pattern_metadata()` also adds `"msp/task"` to `Manifest.patterns` and increments `version`, thereby triggering a manifest push |
| Content format | Defined by the pattern itself; this specification **does not** prescribe fields |
| Relation to A2A | If an A2A adapter is built in future, it **MAY** project this into a conformant Agent Card as needed; this pattern only provides the **foundation** |

**Provision**: an implementer **MUST NOT** require the peer to parse `pattern_metadata["msp/task"]` in order to complete a task delegation; missing metadata **MUST NOT** be treated as a protocol error; an implementation **MAY** not use that metadata at all.

## 7. Error handling and boundaries

**7.1 Unknown `task_id`** — when `task_query` / `task_cancel` points at a non-existent task, the executor replies with a response carrying `error` (`task_cancel_result` also carries `accepted: false`), on which the caller raises `RuntimeError`. **No** `error` signal is sent: "unknown task" is a tool-level failure, not a protocol-level failure ([errors as values](../base-protocol.md#6-error-handling)).

**7.2 Duplicate submissions and duplicate signals** — this pattern has **no** idempotency key: submitting the same task name with the same `args` twice yields two independent `task_id`s and two independent executions; where idempotency is needed the caller **SHOULD** deduplicate itself with `context_id` or a business key in `args`. A duplicate `task_submit` **MUST** be treated as a new task and produce a new `task_id`; the same `task_id` **MUST** produce exactly one `task_result`; a `task_cancel` for an already terminal task still replies `accepted: true` but **MUST NOT** produce a second `task_result`.

**7.3 The peer does not announce the pattern** — `submit()` / `get()` / `cancel()` check `peer(peer_id).supports("msp/task")` first and raise `RuntimeError("peer <id> does not support msp/task")` when that is not satisfied; this is the **only** place where this pattern's capability is checked. If a signal is sent anyway, the peer has no handler, falls into the default branch and replies `error{code:-32600}`; that `error` carries the original `reqid`, but the wait table accepts **only** `task_submit_result`, so the `error` **does not** wake the waiter — `submit()` blocks until the 5-second acceptance timeout and then raises `TimeoutError`. Fallback does **not** happen automatically (§2.1).

**7.4 Task timeouts** — `submit(timeout=5.0)` covers only "accepted"; `get()` / `cancel()` default to 5.0 s; `handle.wait(timeout=None)` has no timeout; `ctx.ask(timeout=30.0)` covers a single follow-up question. The executor has **no** task-level timeout: a task function may run for as long as it likes, and the record stays in memory until the process exits; callers **SHOULD** always pass a `timeout` to `wait()`.

**7.5 Cancellation races** — when the cancellation precedes the worker's start, the record becomes `canceled` at once, but the worker still starts and runs the task function, and its artifacts and terminal state are all discarded; when a cancellation and `_finish` race, the first terminal state wins and the later one is a no-op; when a cancellation and `_push_artifact` race, the artifact may already be enqueued under the lock while the terminal state is emitted first, so the artifact message arrives **after** the terminal state (see §7.6); when the cancellation arrives while the worker is blocked in `ctx.ask()`, the sentinel wakes it and `_ask` raises `TaskCanceled`; cancelling an already terminal task replies `accepted: true` with the state unchanged. The caller **SHOULD** treat `task_result.payload.state` as the sole authority and **MUST NOT** infer the final state from `accepted`.

**7.6 Signals arrive out of order at observers** — `send` on a single connection is lock-protected, so frames are **never** byte-interleaved, but ordering **across threads is not guaranteed**: `_emit_*` updates the record under the lock and **sends only after releasing it**, while the cancellation path sends `task_result` on **another thread** (the read loop). Consequently both observers and the submitter may receive `task_result{state:"canceled"}` first and a `task_artifact` afterwards; a wildcard observer also receives the three kinds of path interleaved, and the arrival order **is not** guaranteed to be the same for different observers. The receiver **MUST NOT** assume that "no further message for that task follows `task_result`", and **SHOULD** ignore `task_status` / `task_artifact` of the same `task_id` after receiving the terminal state, using `task_result.payload.artifacts` as the authoritative full set of artifacts. Known regression: if a handle receives a late `task_artifact` after the terminal state, it **appends** it to the list that `task_result` has already replaced, double-counting (§12 G6).

**7.7 `context_id` pass-through semantics** — `contextId` is an **opaque** value: the executor **MUST** store it verbatim and echo it back in `task_submit_result` / `task_query_result`, and **MUST NOT** parse, normalise or rewrite it. Its use is agreed by the caller (typically "several tasks of the same session"); this pattern **does not** define ordering, concurrency or dependency semantics among the tasks within a context; when it is absent, `null` **MUST** be used rather than an empty string.

**7.8 Callback exceptions** — the `on_status` / `on_artifact` callbacks are invoked **on the read-loop thread**, and exceptions are **not** caught: they propagate up to `_read_loop`, are recorded as that connection's "read-loop exception" and **close the connection**, after which callbacks registered later are not invoked. Callbacks therefore **MUST NOT** raise and **SHOULD** catch all exceptions themselves; on the submitter side a callback exception also affects **every** other interaction on that connection. All directed sends on the executor side go through `_send_to()`, which catches `RuntimeError` / `ConnectionClosed` and downgrades them to a log entry — **the task keeps running**, artifacts keep accumulating, only nobody receives them any more; once the submitter loses the peer, `handle.wait()` can only wait until its timeout, and the handle is **not** set to `failed` automatically.

**7.9 Process restart** — task records and handles **both** exist only in memory and are lost on a restart; after reconnecting, `task_query` replies "unknown task". This pattern **does not** define resumption after a disconnection, `task_result` retransmission or artifact replay.

## 9. Equivalence mapping to A2A

Consistent with the [design document](/design#task-pattern-msptask-and-the-a2a-equivalence-mapping):

| A2A | `msp/task` | Difference |
|---|---|---|
| `message/send` | `task_submit` → `task_submit_result` | likewise blocks until "accepted" and returns a non-terminal task, without waiting for completion |
| `message/stream` (SSE) | the three directed pushes `task_status` / `task_artifact` / `task_result` | MSP pushes signals rather than holding an HTTP long connection; it **additionally** supports multi-observer broadcast |
| `tasks/get` | `task_query` → `task_query_result` | returns a `TaskSnapshot` carrying the accumulated artifacts |
| `tasks/cancel` | `task_cancel` → `task_cancel_result` | cooperative; it does not forcibly terminate execution |
| the `input-required` state | `ctx.ask()` (`input_required` / `input_response`) | reuses the follow-up mechanism of [`msp/multi-round`](./multi-round.md); this pattern correlates by `taskId` and carries no `reqid` |
| `TaskState` | the `state` string, 1:1 | `submitted` / `working` / `input-required` / `completed` / `failed` / `canceled` |
| `Artifact` + `Part` | `Artifact(name, description, parts=[content blocks])` | `parts` reuses the block types of `content.py` |
| `contextId` | optional `context_id` pass-through | opaque value, echoed back verbatim |
| Agent Card | `Manifest.pattern_metadata["msp/task"]` | the Manifest core neither sees nor validates it; a future adapter projects it as needed |
| webhook push (single subscriber) | **observer broadcast**: an extra publish to `task.<id>.<kind>` | A2A's SSE / webhook are both single-subscriber, whereas MSP is naturally multi-observer |

**A2A is a protocol stack, not a pattern**: this pattern carries only its **task semantics** (state machine + artifacts). Transport, encoding, discovery and authorisation are all outside this pattern; an HTTP / JSON-RPC adapter for the A2A ecosystem is the job of an **adapter**, and those requirements **MUST NOT** be pushed back into this pattern's messages.

## 10. Summary of provisions

**MUST**: ① every directed signal **MUST** carry `pattern = "msp/task"`; ② state values **MUST** be taken from the six strings of §2.2 (`input-required` with a hyphen); ③ `task_submit_result` **MUST** precede `task_result` and carry `state = "submitted"`; ④ the same `task_id` **MUST** produce exactly one `task_result`, and that message **MUST** be the last directed message of the task; ⑤ a terminal state **MUST** be irreversible, and any transition or artifact after it **MUST** be discarded; ⑥ `task_result.payload.artifacts` **MUST** be a full snapshot of the accumulated artifacts; ⑦ `contextId` **MUST** be echoed back verbatim, using `null` when absent; ⑧ request/reply signals **MUST** echo the request's `reqid`, and push signals **MUST NOT** carry `reqid`; ⑨ `input_required` / `input_response` **MUST** correlate by `payload.taskId` and **MUST NOT** rely on `reqid`; ⑩ unrecognised fields, signal types and content-block types **MUST NOT** cause the connection to drop.

**SHOULD**: ⑪ a task function **SHOULD** check `ctx.cancel_requested()` at interruptible points and return as soon as possible; ⑫ the caller **SHOULD** set a timeout for `wait()` and treat `task_result.payload.state` as the authority on the terminal state; ⑬ the receiver **SHOULD** ignore `task_status` / `task_artifact` of the same `task_id` that arrive after the terminal state; ⑭ status and artifact callbacks **SHOULD** catch all exceptions themselves; ⑮ the broadcast of a sensitive task **SHOULD** be replaced by directed collection or turned off; ⑯ when `task_cancel_result.accepted` is `true`, the caller **SHOULD** confirm the final state with `task_query`.

**MUST NOT**: ⑰ the executor **MUST NOT** send `task_status` / `task_artifact` for that task after the terminal state; ⑱ a task function **MUST NOT** write credentials, keys or other sensitive information into exception messages; ⑲ patterns outside the `msp/` namespace **MUST NOT** reuse the types `task_*` and `input_required` / `input_response`; ⑳ a fallback implementation **MUST NOT** emit any `task_*` signal on the fallback path; ㉑ requiring the peer to parse `pattern_metadata["msp/task"]` **MUST NOT** become a precondition for completing a delegation.

**MAY**: ㉒ an implementation **MAY** not implement this pattern; once implemented it **MUST** conform to the provisions of this page. ㉓ an implementation **MAY** put arbitrary metadata in `pattern_metadata["msp/task"]`, and **MAY** not use it at all.

## 11. Security considerations

- **Observer broadcast is an exposure surface**: any node connected to the executor **MAY** watch the identifier, state description and **full artifact content** of any task, without authorisation and without registering this pattern. A sensitive task **MUST NOT** rely on the default broadcast behaviour; implementers **SHOULD** provide a switch that turns the broadcast off or authorises by path (the reference implementation provides **none**, §12 G9).
- ~~**Source not validated**~~ ✅ **Fixed**: `_on_status` / `_on_artifact` / `_on_result` / `_on_input_required` now check by **connection identity** that the sender is that task's executor, and `_on_input_response` that it is the submitter, dropping anything that does not match ([security](../security.md) §3.10). This correction is necessary: `task_id` is handed to **all** connected peers by the `task.<id>.**` observer broadcast, so it **MUST NOT** be treated as a security token.
- **`input_fn` is a data entry point**: the `prompt`, controlled by the executor, is handed to the submitter's `input_fn`; the `answer`, controlled by the submitter, goes straight into the task function's control flow. Both sides **MUST** treat the other's data as untrusted input (length, type, value range).
- **Denial of service**: this pattern has **no** priority, no quota and no cap on the number of tasks. Any connected peer **MAY** submit unlimited tasks, each starting a worker thread and each record resident in memory; a deployer **SHOULD** rate-limit at the connection or application layer.
- **Authorisation ownership is defined**: who may submit / query / cancel and who may reply and ask is decided by the mapping in [security](../security.md) §3.9 (`task_submit` goes through `req`, everything else through `rep`); **watching** is still undecided — the broadcast goes to all connected peers, see G9.

## 12. Known gaps

Paths the reference implementation does **not** handle (overall 🟡 **partially implemented**); planned fixes are marked 🔵:

| No. | Gap | Current state |
|---|---|---|
| G1 | No task timeout; no cancellation history | The executor sets no deadline for a task; the record keeps **no** trace of "cancellation was requested" |
| G2 | Threads cannot be interrupted | Cancellation is cooperative; a function that does not check `cancel_requested()` cannot be stopped (a Python limitation) |
| G3 | Cancellation does not prevent startup | When the cancellation precedes the worker's start, the function still runs and its result is silently discarded |
| G4 | Cancelling a terminal task replies `accepted: true` | The caller cannot distinguish "cancellation succeeded" from "already finished long ago" |
| G5 | ~~`ctx.status()` does not validate the state value~~ ✅ **Fixed** | It now accepts only `working` / `input-required`; any other value raises `ValueError` (the task then goes `failed`, so the caller sees the error at once instead of hanging until the timeout) |
| G6 | Artifacts arriving late after the terminal state are double-counted | §7.6 |
| G7 | A callback exception closes the connection | §7.8; it drags down every other interaction on that connection |
| G8 | ~~Source `node_id` not validated~~ ✅ **Fixed** | The write direction checks the executor and the read direction the submitter, both by **connection identity** rather than `sig.source` (§11, [security](../security.md) §3.10). Remaining: the observer broadcast still hands `task_id` to every connected peer (G9) |
| G9 | No switch and no authorisation for the broadcast | Every connected peer watches permanently, with no exemption mechanism for sensitive tasks |
| G10 | No priority / quota / concurrency cap | Any connected peer **MAY** submit unlimited tasks, each starting one worker thread; there is no task scheduling or backpressure. (Persistence and recovery do exist, see G14) |
| G11 | ~~The `error` signal does not wake the waiter~~ ✅ **Fixed** | The protocol layer's `_on_error` now wakes the waiting request by `reqid` (same as [multi-round G3](./multi-round.md#9-known-gaps)) |
| G12 | No error-code semantics | A failed task has only a free-text `error`, with no error code to branch on |
| G13 | `Signal.is_request()` / `is_response()` do not recognise this pattern's types | Both cover core types only; there is no consumer anywhere in the repository yet, so the impact is zero, but the semantics are already incomplete |
| G14 | ~~🔵 Planned: task persistence and recovery~~ ✅ **Implemented** | `config["task_store"]` enables a JSONL append-only store; recovery follows "collapse by `task_id` first, then judge the terminal state, mark everything failed and write back". Two hard requirements: **bad bytes MUST NOT prevent the node from starting** (lenient decoding, skip bad lines), and **when the store is unavailable it degrades to "no persistence + a warning"** — persistence is an optional capability, so it **MUST NOT** be a reason to refuse startup, and **MUST NOT** kill the worker |
| G15 | Authorisation implemented / quota still missing | Authorisation is decided by the mapping in [security](../security.md) §3.9 (`task_submit` goes through `req`, the rest through `rep`) and **does not** depend on the peer's self-declared capability bits; quotas and backpressure are still missing (see G10) |
| G16 | 🔵 Planned: A2A HTTP / JSON-RPC adapter | If implemented, it **MUST** map according to the "equivalence mapping to A2A" table and **MUST NOT** change this pattern's message shapes |
| G17 | ~~A non-serialisable artifact kills the worker~~ ✅ **Fixed** | `ctx.artifact()` validates JSON serialisability **before** the parts enter the record, raising `ValueError` on failure → the task ends as `failed` (a failure is a terminal state too, so the submitter gets it); a persistence failure no longer changes task semantics and no longer kills the worker |

## 13. Reference implementation map

| Provision | Source file and symbol |
|---|---|
| §2.1 `pattern_id` / `fallback_to` / `conflicts_with` | [`src/msp/patterns/task.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/task.py) `TaskHandler.pattern_id` / `.fallback_to`; [`src/msp/patterns/base.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/base.py) `PatternHandler.conflicts_with` |
| §2.2–§2.4 state constants, state machine, irreversibility of terminal states | `task.py` `STATE_SUBMITTED` … `STATE_CANCELED`, `TERMINAL_STATES`, `TaskHandler._transition` / `._finish` / `._ask` / `._run_task` |
| §3.2–§3.3 `task_submit` / `task_submit_result` | `task.py` `TaskHandler.submit` / `._on_submit` / `._on_submit_result` |
| §3.4–§3.6 `task_status` / `task_artifact` / `task_result` | `task.py` `._emit_status` / `._emit_artifact` / `._emit_result` |
| §3.7–§3.8 `task_query` / `task_cancel` and their results | `task.py` `TaskHandler.get` / `._on_query` / `.cancel` / `._on_cancel` |
| §3.9 follow-up reuse and why same-named signals do not conflict | `task.py` `TaskHandler.INPUT_REQUIRED` / `.INPUT_RESPONSE` / `._ask` / `._on_input_required` / `._on_input_response`; routing in [`protocol.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._dispatch` |
| §4 message flow | `task.py` module docstring; for end-to-end behaviour see [`tests/test_task.py`](https://github.com/hxh230802/MSP/blob/master/tests/test_task.py) |
| §5.1–§5.2 `submit` / `wait` / `submit_and_wait` / `get` / callbacks | `task.py` `TaskHandler.submit` / `._prepare` / `._send_to` / `.submit_and_wait` / `.get` / `._request`; `TaskHandle.wait` / `.on_status` / `.on_artifact` |
| "Cancellation": cooperative cancellation | `task.py` `TaskHandler._on_cancel`; `TaskContext.cancel_requested`; the sentinel `_CANCEL_SENTINEL` |
| §5.3–§5.4 `TaskSnapshot` / `Artifact` | `task.py` `TaskSnapshot`, `Artifact` (`from_dict` reads `taskId` / `contextId`); block types in [`src/msp/core/content.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) `_BLOCK_TYPES` / `block_from_dict` |
| §5.5 `TaskContext` and exceptions | `task.py` `TaskContext.status` / `.emit` / `.artifact` / `.ask` / `.cancel_requested`; `TaskError` / `TaskCanceled` |
| §6 observer broadcast / Agent Card projection | `task.py` `TaskHandler._broadcast` (`publish(f"task.{id}.{kind}", payload)`); [`manifest.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `Manifest.pattern_metadata` / `set_pattern_metadata` (on-wire key `patternMetadata`); [`node.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `MSPNode.register_pattern`; [`protocol.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol.publish` / `._on_signal` |
| §7.3 capability check / §7.8 callback exception path | `task.py` `TaskHandler._prepare`; [`peer.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/peer.py) `Peer.supports`; `protocol.py` `MSPProtocol._read_loop` (an exception closes the connection) |
| Equivalence mapping to A2A | [`docs/DESIGN.md`](/design#task-pattern-msptask-and-the-a2a-equivalence-mapping), [`docs/whitepaper.md`](https://github.com/hxh230802/MSP/blob/master/docs/whitepaper.md) |
| Pattern activation and syntactic sugar / preset declaration | `task.py` `TaskHandler.install_api` (attaches `node.task`); `node.py` `MSPNode._activate_pattern`; [`preset.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/preset.py) `Preset.FULL_PEER` / `LOCAL_AI` / `LOCAL_TOOL_ADVANCED` / `CLOUD_SERVICE` |
