# `msp/task` — 任务委托

| | |
|---|---|
| **协议修订** | `2026-10-10` |
| **模式 ID** | `msp/task` |
| **状态标记** | ✅ **已实现**（提交、状态机、产物、取消、追问、查询、观察者广播均可在参考实现上验证）；§12 列出的边界为 🟡 **部分实现** |
| **降级目标** | `msp/request-reply`（`fallback_to`）；`conflicts_with` 未声明 |
| **规范性用语** | RFC 2119，见[规范索引](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#2-规范性用语) |
| **本页定义** | 任务委托语义：状态机 + 产物 + 观察者广播 + A2A 等价映射 |

## 1. 概述

### 1.1 模式定位

A2A（Agent2Agent）是**协议栈**而非一种模式：它自带传输（HTTP）、编码（JSON-RPC）、发现（Agent Card）与一整套交互原语。MSP 只搬其中**真正新增**的那一层——**任务语义**：任务有身份、有状态机、有产物、可查询、可取消、可被第三方旁观；其余交互复用现有原语。

| 需要的能力 | 复用谁 |
|---|---|
| 请求—响应关联 | [`msp/request-reply`](./request-reply.md) 的 `reqid` 机制 |
| 定向单播 | 协议层 `_send(peer_id, signal)` |
| 广播扇出 | [`msp/publish-subscribe`](./publish-subscribe.md) 的 `publish(path, payload)` |
| 执行中追问 | [`msp/multi-round`](./multi-round.md) 的 `input_required` / `input_response` |
| 产物内容形态 | [`core/content.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) 的内容块 |

因此本模式新增的抽象只有两个：**状态机**与**产物**。

### 1.2 关键取舍

1. `submit()` **只阻塞到「接受」**：拿回 `task_id` + `submitted` 态即返回，与 A2A `message/send` 返回非终态 Task 一致。任务可能跑几小时，阻塞到完成是反模式；等完成用 `handle.wait()`。
2. **取消是协作式的**：置标志 + 立即发终态，worker 后续 emit 全部 no-op，**不**强行杀线程（见[「取消」](#8-取消)、§12 G2）。
3. **观察者广播是相对 A2A 的差异化能力**：A2A 的 SSE / webhook 都是单订阅者，MSP 的发布订阅天然支持多观察者（见 §6）。
4. **`input-required` 复用既有追问机制**，不重造（见 §3.9）。

## 2. 契约与状态机

### 2.1 模式标识

```python
class TaskHandler(PatternHandler):
    pattern_id  = "msp/task"             # 逐字取自源码
    fallback_to = "msp/request-reply"    # 逐字取自源码
    # conflicts_with 未声明：继承 PatternHandler 的默认值 []
```

`pattern_id` 既是 `Manifest.patterns` 的条目，也是 `Signal.pattern` 的路由键。**降级事实**：`fallback_to` 在全仓库只被声明、没有任何代码读取，**当前不发生自动降级**（与 [`msp/multi-round`](./multi-round.md#21-模式标识与降级) 处境相同）。实现者**可以**实现降级，但**必须**：降级后改用不带 `pattern` 的 `tool_call` / `tool_result` 完成同一次调用；**不得**在降级路径上发出任何 `task_*` 信号；**应当**让调用方显式感知降级已发生。**互斥事实**：`conflicts_with` 同样无任何代码消费，恒为 `[]`；本模式**可以**与任何其它模式共存，内部重复定义 `input_required` / `input_response` 也不构成冲突（理由见 §3.9）。

### 2.2 六个状态常量

| 常量 | 字符串值 | 终态 | 含义 |
|---|---|---|---|
| `STATE_SUBMITTED` | `"submitted"` | 否 | 已被接受，尚未开始执行 |
| `STATE_WORKING` | `"working"` | 否 | 执行中 |
| `STATE_INPUT_REQUIRED` | `"input-required"` | 否 | 等待提交者补充信息 |
| `STATE_COMPLETED` | `"completed"` | **是** | 正常结束 |
| `STATE_FAILED` | `"failed"` | **是** | 执行失败 |
| `STATE_CANCELED` | `"canceled"` | **是** | 已取消 |

终态集合为 `frozenset({"completed", "failed", "canceled"})`。**拼写陷阱（逐字核对源码）**：状态值 `input-required` 用**连字符**（对齐 A2A `TaskState`），而信号类型 `input_required` 用**下划线**；两者**不得**互换、**不得**归一化。

### 2.3 状态机（ASCII）

```text
  task_submit
       │
       ▼
 ┌─────────────┐  记录创建时的初始态，由 task_submit_result 通告，不单独发 task_status
 │  submitted  │
 └──────┬──────┘
        │ worker 线程启动：_transition(working, "")
        ▼
 ┌─────────────┐   ctx.status(state, message) 可再次进入
 │   working   │◀────────────────────────────┐
 └──┬───────┬──┘                             │
    │       │ ctx.ask(prompt)                │ 收到 input_response
    │       ▼                                │ 或追问超时
    │  ┌──────────────────┐                  │
    │  │  input-required  │──────────────────┘
    │  └──────────────────┘
    │  _finish()：正常返回且未请求取消 ─▶ completed
    │              抛非 TaskCanceled 异常 ─▶ failed     三个终态：互斥、
    └──────────────抛 TaskCanceled / 已置取消 ─▶ canceled   不可逆、不再产出
```

### 2.4 迁移合法性与终态不可逆

| 从 | 到 | 触发点 | 发出的信号 |
|---|---|---|---|
| （无记录） | `submitted` | 接受 `task_submit`，创建记录 | 由 `task_submit_result.payload.state` 通告 |
| `submitted` | `working` | worker 启动时的 `_transition(working, "")` | `task_status` |
| `submitted` / `working` | `input-required` | `ctx.ask()` 发问之前 | `task_status` + `input_required` |
| `input-required` | `working` | 收到 `input_response`，或追问超时 | `task_status` |
| `working` | `working` | `ctx.status("working", msg)` | `task_status` |
| `working` / `input-required` | `completed` | `_finish(completed)`：函数正常返回且 `cancel_event` 未置位 | `task_result` |
| `working` / `input-required` | `failed` | `_finish(failed, error=…)`：函数抛非 `TaskCanceled` 异常 | `task_result` |
| 任意非终态 | `canceled` | `_finish(canceled)`：收到 `task_cancel`，或函数抛 `TaskCanceled`，或函数返回时 `cancel_event` 已置位 | `task_result`（取消时**立即**发，不等 worker） |

① 终态**不得**回退，记录已终态时 `_transition` / `_push_artifact` / `_finish` **必须**是 no-op；② 同一 `task_id` **必须**只产生一个 `task_result`；③ `submitted` **不得**用独立的 `task_status` 通告；④ 接受任务后**应当**先进入 `working`（或经 `input-required`）；**例外**：取消早于 worker 启动时 `_on_cancel` 会把 `submitted` 直接置为 `canceled` 并跳过 `working`（见 §7.5 与 §12 G3）；⑤ 状态值**必须**取自 §2.2 的六个字符串（参考实现不校验取值，实现者**不得**据此放宽）。

## 3. 报文（逐信号）

### 3.1 信封公共约定

`Signal` 信封字段一律 snake_case（`type` / `source` / `pattern` / `target` / `path` / `reqid` / `payload` / `timestamp`）；`payload` 内部一律 camelCase（`taskId` / `contextId`），**不得**混用。

| 约束 | 条文 |
|---|---|
| `pattern` | 本模式全部定向信号**必须**携带 `pattern = "msp/task"` |
| `target` | 定向信号**必须**填对端 `node_id`；观察者广播（`type = "signal"`）**不得**填 `target` |
| `reqid` | 仅请求—响应型信号携带；推送型信号**不得**携带 |
| `path` | 仅观察者广播使用：`task.<task_id>.<kind>`，`kind ∈ {status, artifact, result}` |

| 信号 `type` | 方向 | `reqid` | 同步广播 |
|---|---|---|---|
| `task_submit` | 调用方 → 执行者 | 有 | 否 |
| `task_submit_result` | 执行者 → 调用方 | 回填 | 否 |
| `task_status` | 执行者 → 调用方 | **无** | 是，`.status` |
| `task_artifact` | 执行者 → 调用方 | **无** | 是，`.artifact` |
| `task_result` | 执行者 → 调用方 | **无** | 是，`.result` |
| `task_query` | 调用方 → 执行者 | 有 | 否 |
| `task_query_result` | 执行者 → 调用方 | 回填 | 否 |
| `task_cancel` | 调用方 → 执行者 | 有 | 否 |
| `task_cancel_result` | 执行者 → 调用方 | 回填 | 否 |
| `input_required` | 执行者 → 调用方 | **无**（按 `taskId` 关联） | 否 |
| `input_response` | 调用方 → 执行者 | **无**（按 `taskId` 关联） | 否 |

### 3.2 `task_submit`

| 字段 | 类型 | 必填 | 值 |
|---|---|---|---|
| `payload.task` | string | **必须** | 任务名（执行者注册表键） |
| `payload.args` | object | **必须** | 任务实参；参考实现缺省为 `{}` |
| `payload.contextId` | string \| null | **必须**（可为 `null`） | 调用方提供的上下文标识，执行者原样回填 |

```json
{ "type": "task_submit", "source": "b", "pattern": "msp/task", "target": "a", "path": null,
  "reqid": "9f1c2d3e4a5b6c7d",
  "payload": { "task": "generate_report", "args": { "topic": "季度复盘" }, "contextId": "ctx-1" } }
```

### 3.3 `task_submit_result`

成功（被接受）：`payload.taskId`（string，**必须**，形如 `task-<16 位十六进制>`）、`payload.contextId`（string\|null，**必须**，原样回填）、`payload.state`（string，**必须**，恒为 `"submitted"`）。

失败（未知任务）：只有 `payload.error`（string，**必须**，形如 `"未知任务: <name>"`）；**不得**携带 `taskId` 或 `state`。调用方**应当**以「是否存在 `state`」区分成功与失败。

### 3.4 `task_status`

| 字段 | 类型 | 必填 | 值 |
|---|---|---|---|
| `payload.taskId` | string | **必须** | 任务标识 |
| `payload.state` | string | **必须** | §2.2 的非终态字符串（参考实现不校验） |
| `payload.message` | string | **必须** | 状态描述；`working` 且无描述时为空串 |

出现时机：worker 启动时必发一次（`working` + 空 `message`）；`ctx.status(...)` 每次调用发一次；进入与离开 `input-required` 各发一次。除此以外**不得**发 `task_status`。

### 3.5 `task_artifact`

| 字段 | 类型 | 必填 | 值 |
|---|---|---|---|
| `payload.taskId` | string | **必须** | 任务标识 |
| `payload.artifact` | object | **必须** | `{name, description, parts}`，见 §5.4 |

**每个产物一条报文**：`ctx.artifact()` / `ctx.emit()` 各发一条，**不**批量合并；终态之后**必须**不再发。

### 3.6 `task_result`

| 字段 | 类型 | 必填 | 值 |
|---|---|---|---|
| `payload.taskId` | string | **必须** | 任务标识 |
| `payload.state` | string | **必须** | 三个终态之一 |
| `payload.message` | string | **必须** | 终态描述；`completed` 时通常为空串，`canceled` 时为 `"任务已取消"` |
| `payload.error` | string | **必须** | 失败文本；非 `failed` 时为空串 |
| `payload.artifacts` | array | **必须** | 截至终态**累计的全部**产物对象（可为空数组） |

```json
{ "type": "task_result", "source": "a", "pattern": "msp/task", "target": "b", "reqid": null,
  "payload": { "taskId": "task-3f2a9c1b4d5e6f70", "state": "completed", "message": "", "error": "",
    "artifacts": [ { "name": "text", "description": "", "parts": [{ "type": "text", "text": "第一段" }] } ] } }
```

`artifacts` 是**全量快照**而非增量：接收方**应当**用它替换本地累计列表，**不得**追加合并（否则与已收到的 `task_artifact` 重复）。

### 3.7 `task_query` 与 `task_query_result`

`task_query` 载荷只有一个字段：`payload.taskId`（string，**必须**）。

`task_query_result` 成功：`payload.taskId`（string，**必须**）、`payload.contextId`（string\|null，**必须**）、`payload.state`（string，**必须**，可为任一状态含终态）、`payload.message`（string，**必须**）、`payload.error`（string，**必须**，或空串）、`payload.artifacts`（array，**必须**，累计产物）。

失败（未知 `taskId`）：`payload.taskId`（**必须**，回显请求值）+ `payload.error`（**必须**，`"未知任务: <taskId>"`）；**不得**携带 `state`。

### 3.8 `task_cancel` 与 `task_cancel_result`

`task_cancel` 载荷只有一个字段：`payload.taskId`（string，**必须**）。

`task_cancel_result`：`payload.taskId`（string，**必须**）、`payload.accepted`（boolean，**必须**）、`payload.error`（string，**可选**，仅 `accepted = false` 时出现，形如 `"未知任务: <taskId>"`）。

**`accepted = true` 不等于「状态已变为 canceled」。** 对已处于终态的任务，参考实现同样回 `accepted = true`（不做 `_finish`，也不报错），调用方无法据此区分「取消成功」与「任务早已结束」；需要区分时**应当**再用 `task_query` 读取真实状态。

### 3.9 `input_required` 与 `input_response`

本模式**重复定义**了与 [`msp/multi-round`](./multi-round.md) 同名的两个信号类型，以复用同一套追问机制：

| 信号 | 载荷字段 | 类型 | 必填 | 与 multi-round 的差异 |
|---|---|---|---|---|
| `input_required` | `payload.taskId` | string | **必须** | 本模式新增，multi-round 无此字段 |
| `input_required` | `payload.prompt` | string | **必须** | 同 multi-round |
| `input_response` | `payload.taskId` | string | **必须** | 本模式新增 |
| `input_response` | `payload.answer` | any | **必须** | 同 multi-round；`input_fn` 为 `None` 时为 `null`，抛异常时为 `{"error": "<异常文本>"}` |

**关联键不同（关键差异）**：本模式的这两个信号**不携带 `reqid`**，一问一答全靠 `payload.taskId` 关联。实现者**不得**按 `reqid` 关联本模式的追问链，也**不得**因同名就假定两种模式的载荷一致。

**为什么同名信号不冲突**：路由键是 `Signal.pattern`——[`_dispatch`](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) 第 2 步先查 `self.patterns[msg.pattern]`，命中的 handler 独占地处理整条信号；`input_required` 只是 `type` 字段的取值，本身不参与路由。带 `pattern = "msp/task"` 的追问进 `TaskHandler`，带 `pattern = "msp/multi-round"` 的进 `MultiRoundHandler`，两者互不可见。代价是：**不带 `pattern` 的模式私有 `type` 是协议错误**，会被默认分支回 `error`（`code = -32600`）。`msp/` 命名空间外的模式**必须**为自己的类型加前缀（[规范索引 §5.1](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md#51-核心信号类型signaltype)）。

## 4. 消息流

### 4.1 正常路径：submit → working → 多次 artifact → result

```text
  调用方 (b)                                                    执行者 (a)
   │ ① task_submit  reqid=r1  payload={task:"generate_report",             │
   │      args:{topic:"季度复盘"}, contextId:"ctx-1"}                       │
   ├───────────────────────────────────────────────────────────────────────▶│
   │                            查任务注册表 → 建记录（state="submitted"），
   │                            先回执②，再起 worker 线程                   │
   │ ② task_submit_result  reqid=r1                                        │
   │    payload={taskId:"task-3f2a…",contextId:"ctx-1",state:"submitted"}  │
   │◀───────────────────────────────────────────────────────────────────────┤
   │ submit() 返回 TaskHandle(state=submitted)                             │ 起 worker
   ▼                                                                       ▼
   │                                          _transition(working,"")     │
   │ ③ task_status（reqid=null）payload={taskId,state:"working",message:""}│
   │◀───────────────────────────────────────────────────────────────────────┤
   │ 同时 publish → signal path="task.task-3f2a….status"                    │
   │                                                    ctx.emit("第一段") │
   │ ④ task_artifact（reqid=null）payload={taskId,artifact:{name:"text",   │
   │      description:"",parts:[{type:"text",text:"第一段"}]}}              │
   │◀───────────────────────────────────────────────────────────────────────┤
   │ 同时 publish → path="task.task-3f2a….artifact"                         │
   │                                            ctx.artifact(name="chart",…)
   │ ⑤ task_artifact（reqid=null）                                         │
   │◀───────────────────────────────────────────────────────────────────────┤
   │                                       函数返回 → _finish(completed)   │
   │ ⑥ task_result（reqid=null）payload={taskId,state:"completed",         │
   │      message:"",error:"",artifacts:[…全量产物]}                        │
   │◀───────────────────────────────────────────────────────────────────────┤
   │ 同时 publish → path="task.task-3f2a….result"                           │
   │ handle.wait() 唤醒，返回最终 TaskSnapshot                              │
   ▼                                                                       ▼
```

三条时序约束：② **必须**早于③（先通告 `submitted`，再起 worker）；③ **必须**早于④⑤；⑥ **必须**是同一 `task_id` 的最后一条定向报文。

### 4.2 追问路径

```text
   │ ③a task_status  state="input-required", message="用哪个口径？"        │
   │◀──────────────────────────────────────────────┤ ctx.ask("用哪个口径？")
   │ ③b input_required  payload={taskId,prompt:"用哪个口径？"}（无 reqid） │
   │◀──────────────────────────────────────────────┤ ask() 阻塞，默认 30s
   │ handle.input_fn(prompt) → "按自然季度"         │                     │
   │ ③c input_response  payload={taskId,answer:"按自然季度"}（无 reqid）   │
   ├──────────────────────────────────────────────▶│ 唤醒 ask()
   │ ③d task_status  state="working", message=""    │                     │
   │◀──────────────────────────────────────────────┤                     │
```

追问**可以**在同一任务内发生任意多次；每次进入 `input-required` 都先发 `task_status`、再发 `input_required`，离开时再发一条 `task_status(working)`。追问超时也回 `working`，但 `ctx.ask()` 抛 `TimeoutError`，通常导致任务随即 `failed`。

### 4.3 查询路径

```text
   │ task_query  reqid=r3  payload={taskId}  ├────▶│ 读任务记录快照
   │◀───────────────────────────────────────────────┤
   │ task_query_result  reqid=r3  payload={taskId, contextId, state, message, error, artifacts}
```

任务记录**不**随连接关闭而清理，重连后仍可查询；查询只读，**不得**改变任务状态。

## 8. 取消

```python
handle.cancel(timeout=5.0) -> bool        # 委托给 handler.cancel
cancel(peer_id, task_id, timeout=5.0) -> bool
```

```text
   │ ⑦ task_cancel  reqid=r2  payload={taskId:"task-3f2a…"}               │
   ├──────────────────────────────────────────────▶│ _on_cancel:
   │                                cancel_event.set()；若正阻塞在 ask() 则
   │                                写取消哨兵并唤醒；立即 _finish(canceled)
   │ ⑧ task_result  payload={taskId,state:"canceled",                     │
   │      message:"任务已取消",error:"",artifacts:[…取消前的产物]}          │
   │◀──────────────────────────────────────────────┤
   │ 同时 publish → path="task.task-3f2a….result"   │ worker 线程仍在跑：
   │ ⑨ task_cancel_result  reqid=r2                 │ 后续 artifact/status/
   │    payload={taskId,accepted:true}              │ finish 全部 no-op，直到
   │◀──────────────────────────────────────────────┤ 它自己观察到
   │ handle.wait() 以 canceled 返回                  │ cancel_requested()
```

注意 ⑧ 先于 ⑨：参考实现先发 `task_result`，再发 `task_cancel_result`；调用方**不得**假定相反的顺序。

执行者侧的实现分三步：（1）置 `cancel_event`，若 worker 正阻塞在 `ctx.ask()` 则写入取消哨兵并唤醒它；（2）**立即**发终态 `task_result{state:"canceled", message:"任务已取消"}`，不等 worker 响应；（3）之后 worker 的任何 `_transition` / `_push_artifact` / `_finish` 全部 no-op。

**不强行杀线程，这是 Python 的限制**：CPython 没有安全的线程中断原语。后果必须明说：任务函数**仍在运行**，直到它自己调用 `ctx.cancel_requested()` 发现信号、或自然结束；取消后产生的产物被**静默丢弃**，调用方永远看不到；任务函数的副作用（写文件、发请求）**不**回滚；若任务函数从不检查 `cancel_requested()`（例如紧的 CPU 循环），线程与它占用的资源会持续到函数返回；取消到达时 worker 可能尚未启动，此时记录已被置为终态，但**线程仍会启动并执行任务函数**，其返回值与异常被丢弃。

因此任务函数**应当**在可中断点调用 `ctx.cancel_requested()` 并尽快返回，**不得**假定取消会立刻停止计算。任务级取消（`task_cancel`）与[核心 `cancel` 信号](../base-protocol.md#63-取消)是两套机制：后者面向**单次在途调用**、按 `reqid` 关联；任务取消以 `taskId` 为对象、跨越多条请求。实现者**不得**用核心 `cancel` 替代 `task_cancel`，也**不得**要求对端实现核心 `cancel` 才能取消任务。

## 5. 数据类型与对外 API

### 5.1 `submit()` — 只阻塞到「接受」

```python
submit(peer_id, task, args=None, context_id=None, input_fn=None, timeout=5.0) -> TaskHandle
submit_and_wait(peer_id, task, args=None, context_id=None,
                input_fn=None, timeout=None, submit_timeout=5.0) -> TaskSnapshot
handle.wait(timeout=None) -> TaskSnapshot     # 阻塞到终态；超时抛 TimeoutError
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `peer_id` / `task` | 必填 | 执行者 `node_id` / 任务名 |
| `args` | `None` → `{}` | 任务实参 |
| `context_id` | `None` | 进入 `payload.contextId`，可为 `null` |
| `input_fn` | `None` | 执行者 `ctx.ask()` 时的应答函数 `(prompt) -> Any` |
| `timeout`（submit） | `5.0` | **只**覆盖「接受」阶段，**不**覆盖执行 |
| `timeout`（wait） | `None` | `None` 表示**无限期**等待，不传则不会超时 |

前置检查：先 `ensure_connected(peer_id)`（未知节点抛 `UnknownPeer`，不可达抛 `PeerUnavailable`），再校验 `peer(peer_id).supports("msp/task")`，不满足抛 `RuntimeError`。失败响应抛 `RuntimeError(<error 文本>)`；等待超时抛 `TimeoutError`。返回的 `TaskHandle` 其 `state` 为 `submitted`。

**返回不等于执行已开始，更不等于成功**：任务可能立刻失败，失败只能通过 `wait()` / `get()` / 回调观察。`submit_and_wait` 只是 `submit(..., timeout=submit_timeout).wait(timeout=timeout)` 的糖，**不**改变任何报文语义。

### 5.2 `get()` 与句柄回调

```python
get(peer_id, task_id, timeout=5.0) -> TaskSnapshot    # 内部发 task_query
handle.on_status(cb)     # cb(state: str, message: str) -> None，返回 self
handle.on_artifact(cb)   # cb(artifact: Artifact) -> None，返回 self
```

`get()` 在未知 `task_id` 时抛 `RuntimeError`；判据是**响应里有没有 `state`**，而**不是**错误码。`on_status` 在每次 `task_status`、`input_required`（此时 `state = "input-required"`、`message = prompt`）以及 `task_result`（终态）时触发；`on_artifact` 在每次 `task_artifact` 时触发，`task_result` **不**回调产物，它只替换 `handle.artifacts`。回调**不**保证在 `wait()` 返回前执行完（终态事件先置位，回调再依次调用），需要严格顺序的调用方**应当**在回调内自行同步。

### 5.3 `TaskSnapshot`

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` | string | 任务标识 |
| `state` | string | §2.2 的六个字符串之一 |
| `artifacts` | list[`Artifact`] | 截至该时刻的产物 |
| `message` | string | 最近一次状态描述 |
| `error` | string | 失败文本或空串 |
| `context_id` | string \| null | 创建时传入的上下文标识 |
| `is_terminal()` | method | `state in {"completed","failed","canceled"}` |

线上形态（`from_dict` 读取的键）是 camelCase：`taskId` / `state` / `artifacts` / `message` / `error` / `contextId`。

### 5.4 `Artifact` 与 `parts`

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `name` | string | `""` | 产物名；`ctx.emit()` 缺省用 `"text"`，任务函数返回值缺省用 `"result"` |
| `description` | string | `""` | 产物描述 |
| `parts` | list | `[]` | 内容块列表，复用 [`core/content.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) |

`parts` 的元素是内容块对象或裸 dict，`type` 取值：`text` / `image` / `audio` / `resource` / `resource_link` / `blob_ref`。未知 `type` 的块**必须**原样保留（宽容读取）。`Artifact.to_dict()` 对已是 dict 的元素不做转换；`Artifact.from_dict()` 对 dict 元素走 `block_from_dict`，非 dict 元素原样保留。

### 5.5 `TaskContext` 与异常

任务函数若签名中含名为 `ctx` 的参数，执行者**必须**注入 `TaskContext`（以 `func(ctx=ctx, **args)` 注入；`args` 中若已含 `ctx` **会抛 `TypeError`**，任务因此记为 `failed`、异常文本进入 `task_result.payload.error`——这与 `msp/multi-round` 的 `{**args, "ctx": ctx}` 覆盖语义**不同**，实现者**不得**在 `args` 中传 `ctx`）。

| 成员 | 语义 |
|---|---|
| `task_id` / `context_id` / `peer_id` / `args` | 属性：任务标识、上下文标识、提交方 `node_id`、原始实参 |
| `status(state, message="")` | 报告一次状态迁移；**只接受** `working` / `input-required`（终态由协议自动产生，见 §2.4 规则③） |
| `emit(text, name="")` | 产出一段文本产物（等价于单 `text` part） |
| `artifact(name="", parts=None, description="")` | 产出一个任意产物 |
| `ask(prompt, timeout=30.0)` | 追问并阻塞等待回答；任务已终态时抛 `TaskCanceled`；超时抛 `TimeoutError` 并回 `working` |
| `cancel_requested()` | 是否已被请求取消（协作式取消的检查点） |

`status()` 的 `state` 参数受校验（原为缺陷，见 §12 G5）：只接受 `working` / `input-required`，传入终态（例如 `"completed"`）或 `submitted` 会抛 `ValueError`——此前传终态会绕过协议直接改记录状态、**不**发出 `task_result`，让客户端的 `wait()` 挂到超时；异常沿任务函数的异常路径记 `failed`，因此调用方立刻拿到明确的错误。任务函数抛出的异常中，`TaskCanceled`（继承 `TaskError`）记 `canceled`，**其它**一律记 `failed` 且 `str(e)` 进入 `task_result.payload.error`。异常文本原样过网，任务函数**不得**把凭据、密钥、绝对路径等信息写进异常消息。

## 6. 观察者广播与 Agent Card 投影

### 6.1 观察者广播

执行者除把三类报文定向发给提交者外，**同时**把同一份 `payload` 发布到点号路径：

```text
task.<task_id>.status      ← task_status   的载荷
task.<task_id>.artifact    ← task_artifact 的载荷（每次产物一条）
task.<task_id>.result      ← task_result   的载荷
```

发布走 [`publish()`](./publish-subscribe.md)，因此报文 `type` 是核心 `signal`，带 `path`，**不带** `pattern`、`target`、`reqid`。任何已连对端都能用 `on("task.**")` 旁观进度，**无需**注册 `msp/task`、**无需**被授权为提交者。扇出对象是「所有已建立的连接」，因此观察者**必须**先与执行者建连；执行者**不**投递给自己，同节点内的本地回调**看不到**广播。提交者会**同时**收到定向报文与广播副本，实现者**应当**按 `Signal.type` 去重，**不得**把广播副本计入「额外一次状态变更」。

**这是相对 A2A 的差异化能力**：A2A 的 SSE 与 webhook 都是**单订阅者**模型——一个任务流只能有一个接收方，第三方要旁观必须由接收方二次转发。MSP 的发布订阅天然支持**多观察者**，且观察者按路径通配符自行过滤（见 [publish-subscribe](./publish-subscribe.md) 的通配符匹配算法）。安全提示：广播**不**区分观察者身份，任务标识、状态描述、产物内容对**所有**已连对端可见；敏感任务**应当**改由点对点定向领取或关闭广播（参考实现**未**提供开关，见 §12 G9）。

### 6.2 Agent Card 投影

A2A 的 Agent Card 描述「这个 agent 是谁、会什么」。在 MSP 中它**不是**协议核心概念，而是**模式的专属元数据**：`node.register_pattern("msp/task", metadata={...})` → `Manifest.pattern_metadata["msp/task"]`。

| 项 | 事实 |
|---|---|
| 承载位置 | `Manifest.pattern_metadata["msp/task"]`；线上键为 `patternMetadata`（camelCase） |
| 核心态度 | Manifest 核心**不感知、不校验**该元数据，原样随清单交换 |
| 副作用 | `set_pattern_metadata()` 同时把 `"msp/task"` 加入 `Manifest.patterns` 并递增 `version`，从而触发清单推送 |
| 内容格式 | 由模式自己定义；本规范**不**规定字段 |
| 与 A2A 的关系 | 未来若做 A2A 适配器，**可以**按需投影成合规 Agent Card；本模式只提供**地基** |

**规范条文**：实现者**不得**要求对端解析 `pattern_metadata["msp/task"]` 才能完成一次任务委托；元数据缺失**不得**被当作协议错误；实现**可以**完全不使用该元数据。

## 7. 错误处理与边界

**7.1 未知 `task_id`**——`task_query` / `task_cancel` 指向不存在的任务时，执行者回带 `error` 的响应（`task_cancel_result` 另带 `accepted: false`），调用方据此抛 `RuntimeError`。**不**发 `error` 信号：「未知任务」是工具级失败，不是协议级失败（[错误即值](../base-protocol.md#6-错误处理)）。

**7.2 重复提交与重复信号**——本模式**无**幂等键：同一任务名用相同 `args` 提交两次会得到两个独立 `task_id`、两个独立执行；需要幂等时调用方**应当**自行用 `context_id` 或 `args` 中的业务键去重。收到重复 `task_submit` **必须**当作新任务处理并生成新 `task_id`；同一 `task_id` **必须**只产生一个 `task_result`；已终态的任务再收 `task_cancel` 仍回 `accepted: true`，但**不得**产生第二个 `task_result`。

**7.3 对端不宣告该模式**——`submit()` / `get()` / `cancel()` 前会校验 `peer(peer_id).supports("msp/task")`，不满足抛 `RuntimeError("对端 <id> 不支持 msp/task")`；这是**唯一**检查本模式能力的地方。若信号仍被发出，对端因没有 handler 而落入默认分支，回 `error{code:-32600}`；该 `error` 携带原 `reqid`，但等待表**只**接受 `task_submit_result`，`error` **不**唤醒等待——`submit()` 会一直阻塞到 5 秒接受超时后抛 `TimeoutError`。降级**不**自动发生（§2.1）。

**7.4 任务超时**——`submit(timeout=5.0)` 仅覆盖「接受」；`get()` / `cancel()` 默认 5.0 s；`handle.wait(timeout=None)` 无超时；`ctx.ask(timeout=30.0)` 覆盖单次追问。执行者**没有**任务级超时：任务函数跑多久都行，记录常驻内存直到进程退出；调用方**应当**总是给 `wait()` 传 `timeout`。

**7.5 取消竞态**——取消早于 worker 启动时记录立即 `canceled`，但 worker 仍会启动并执行任务函数，产物与终态全部被丢弃；取消与 `_finish` 同时则终态先到者胜、后者 no-op；取消与 `_push_artifact` 同时可能让产物已在锁内入列而终态先发出，导致产物报文在终态**之后**到达（见 §7.6）；取消正阻塞在 `ctx.ask()` 时哨兵唤醒，`_ask` 抛 `TaskCanceled`；取消已终态任务回 `accepted: true`、状态不变。调用方**应当**以 `task_result.payload.state` 为唯一权威，**不得**以 `accepted` 推断最终状态。

**7.6 观察者收到的信号乱序**——同一条连接上的 `send` 有锁保护，帧**不会**字节交错，但**不保证**跨线程的先后：`_emit_*` 先在锁内更新记录、**释放锁后才发送**，而取消路径在**另一个线程**（读循环）里发 `task_result`。因此观察者与提交者都可能先收到 `task_result{state:"canceled"}`、后收到一条 `task_artifact`；通配符观察者还会收到三类路径的交错，且不同观察者的到达顺序**不**保证一致。接收方**不得**假定「`task_result` 之后不再有该任务的任何报文」，**应当**在收到终态后忽略同一 `task_id` 的 `task_status` / `task_artifact`，并以 `task_result.payload.artifacts` 作为产物的权威全量。已知退化：句柄若在终态后收到迟到的 `task_artifact`，会把它**追加**到已被 `task_result` 替换过的列表里，造成重复计数（§12 G6）。

**7.7 `context_id` 透传语义**——`contextId` 是**不透明**值：执行者**必须**原样保存并在 `task_submit_result` / `task_query_result` 中回填，**不得**解析、归一化或改写。用途由调用方约定（典型是「同一会话的多个任务」）；本模式**不**定义上下文内任务的排序、并发或依赖语义；缺失时**必须**用 `null` 而非空串。

**7.8 回调异常**——`on_status` / `on_artifact` 的回调在**读循环线程**里被调用，异常**未**被捕获：会上抛到 `_read_loop`，被记为该连接的「读循环异常」并**断开连接**，其后注册的回调不再执行。因此回调**不得**抛异常、**应当**自行捕获全部异常；提交者侧的回调异常会连带影响该连接上的**所有**其它交互。执行者侧所有定向发送都经 `_send_to()`，其中捕获 `RuntimeError` / `ConnectionClosed` 并降级为日志——**任务继续执行**，产物照常累加，只是不再有人收到；提交者侧失联后 `handle.wait()` 只能等到超时，句柄**不会**被自动置为 `failed`。

**7.9 进程重启**——任务记录与句柄**都**只存在于内存，进程重启即丢，重连后 `task_query` 回「未知任务」。本模式**不**定义断线续传、`task_result` 重发或产物重放。

## 9. 与 A2A 的等价映射

与 [设计文档](../../designs.md#任务模式msptask与-a2a-等价映射) 保持一致：

| A2A | `msp/task` | 差异说明 |
|---|---|---|
| `message/send` | `task_submit` → `task_submit_result` | 同样阻塞到「接受」，返回非终态任务，不等到完成 |
| `message/stream`（SSE） | `task_status` / `task_artifact` / `task_result` 三条定向推送 | MSP 是信号推送而非 HTTP 长连接；**额外**支持多观察者广播 |
| `tasks/get` | `task_query` → `task_query_result` | 返回 `TaskSnapshot`，含累计产物 |
| `tasks/cancel` | `task_cancel` → `task_cancel_result` | 协作式，不强行终止执行 |
| `input-required` 态 | `ctx.ask()`（`input_required` / `input_response`） | 复用 [`msp/multi-round`](./multi-round.md) 的追问机制；本模式按 `taskId` 关联且不带 `reqid` |
| `TaskState` | `state` 字符串 1:1 | `submitted` / `working` / `input-required` / `completed` / `failed` / `canceled` |
| `Artifact` + `Part` | `Artifact(name, description, parts=[内容块])` | `parts` 复用 `content.py` 的块类型 |
| `contextId` | 可选 `context_id` 透传 | 不透明值，原样回填 |
| Agent Card | `Manifest.pattern_metadata["msp/task"]` | Manifest 核心不感知、不校验；未来 adapter 按需投影 |
| webhook 推送（单订阅者） | **观察者广播**：额外 publish 到 `task.<id>.<kind>` | A2A 的 SSE / webhook 都是单订阅者，MSP 天然多观察者 |

**A2A 是协议栈而非一种模式**：本模式只搬其**任务语义**（状态机 + 产物）。传输、编码、发现、授权一律不在本模式内；对接 A2A 生态的 HTTP / JSON-RPC 适配器是**适配器**的工作，**不得**把这些要求反向压进本模式的报文。

## 10. 规范条文汇总

**必须**：① 全部定向信号**必须**携带 `pattern = "msp/task"`；② 状态值**必须**取自 §2.2 的六个字符串（`input-required` 用连字符）；③ `task_submit_result` **必须**早于 `task_result` 且携带 `state = "submitted"`；④ 同一 `task_id` **必须**只产生一个 `task_result`，且该报文**必须**是该任务的最后一条定向报文；⑤ 终态**必须**不可逆，终态之后的迁移与产物**必须**被丢弃；⑥ `task_result.payload.artifacts` **必须**是累计产物的全量快照；⑦ `contextId` **必须**原样回填，缺失时用 `null`；⑧ 请求—响应型信号**必须**回填请求的 `reqid`，推送型信号**不得**携带 `reqid`；⑨ `input_required` / `input_response` **必须**用 `payload.taskId` 关联，**不得**依赖 `reqid`；⑩ 未识别的字段、信号类型、内容块类型**不得**导致连接中断。

**应当**：⑪ 任务函数**应当**在可中断点检查 `ctx.cancel_requested()` 并尽快返回；⑫ 调用方**应当**为 `wait()` 设定超时，并以 `task_result.payload.state` 为终态权威；⑬ 接收方**应当**忽略终态之后到达的同一 `task_id` 的 `task_status` / `task_artifact`；⑭ 状态回调与产物回调**应当**自行捕获全部异常；⑮ 敏感任务的广播**应当**改用定向领取或关闭广播；⑯ `task_cancel_result.accepted` 为 `true` 时，调用方**应当**再用 `task_query` 确认最终状态。

**不得**：⑰ 执行者**不得**在终态之后再发该任务的 `task_status` / `task_artifact`；⑱ 任务函数**不得**把凭据、密钥等敏感信息写入异常消息；⑲ `msp/` 命名空间外的模式**不得**复用 `task_*` 与 `input_required` / `input_response` 这些 `type`；⑳ 降级实现**不得**在降级路径上发出任何 `task_*` 信号；㉑ 要求对端解析 `pattern_metadata["msp/task"]` **不得**成为完成委托的前提。

**可以**：㉒ 实现**可以**不实现本模式；一旦实现**必须**符合本页条文。㉓ 实现**可以**在 `pattern_metadata["msp/task"]` 中放任意元数据，也**可以**完全不用。

## 11. 安全考量

- **观察者广播是信息暴露面**：任何与执行者建连的节点都**可以**旁观任意任务的标识、状态描述与**完整产物内容**，无需授权、无需注册本模式。敏感任务**不得**依赖默认广播行为；实现者**应当**提供关闭广播或按路径授权的开关（参考实现**未**提供，§12 G9）。
- ~~**来源未校验**~~ ✅ **已修复**：`_on_status` / `_on_artifact` / `_on_result` / `_on_input_required` 现在按**连接身份**核对发送方就是该任务的执行者，`_on_input_response` 核对就是提交者，不匹配即丢弃（[security](../security.md) §3.10）。这条修正是必需的：`task_id` 会随 `task.<id>.**` 旁观广播发给**所有**已连对端，所以它**不得**被当作安全令牌。
- **`input_fn` 是数据入口**：执行者控制的 `prompt` 交给提交者的 `input_fn`；提交者控制的 `answer` 直接进入任务函数的控制流。两侧都**必须**把对方的数据当作不可信输入处理（长度、类型、取值范围）。
- **拒绝服务**：本模式**无**优先级、无配额、无任务计数上限。任意已连对端**可以**提交无限任务，每个任务起一个 worker 线程且记录常驻内存；部署方**应当**在连接层或应用层限流。
- **授权归属已定义**：谁能提交 / 查询 / 取消、谁能回执与追问，由 [security](../security.md) §3.9 的映射判定（`task_submit` 走 `req`，其余走 `rep`）；**旁观**仍不做判定——广播发给所有已连对端，见 G9。

## 12. 已知缺口

参考实现**未**处理的路径（整体 🟡 **部分实现**）；规划中的补法标 🔵：

| 编号 | 缺口 | 现状 |
|---|---|---|
| G1 | 无任务超时；无取消历史 | 执行者不为任务设时限；记录里**不**保存「曾被请求取消」的痕迹 |
| G2 | 线程不可中断 | 取消是协作式的；函数不检查 `cancel_requested()` 就无法停止（Python 限制） |
| G3 | 取消不阻止启动 | 取消早于 worker 启动时，函数仍会执行，结果被静默丢弃 |
| G4 | 取消已终态任务回 `accepted: true` | 调用方无法区分「取消成功」与「早已结束」 |
| G5 | ~~`ctx.status()` 不校验状态值~~ ✅ **已修复** | 现在只接受 `working` / `input-required`，其它取值抛 `ValueError`（任务随即 `failed`，调用方立刻看到错误而不是挂到超时） |
| G6 | 终态后迟到的产物重复计数 | §7.6 |
| G7 | 回调异常断开连接 | §7.8；会拖垮整条连接上的其它交互 |
| G8 | ~~来源 `node_id` 不校验~~ ✅ **已修复** | 写方向核对执行者、读方向核对提交者，均按**连接身份**而非 `sig.source`（§11、[security](../security.md) §3.10）。残留：旁观广播仍把 `task_id` 发给所有已连对端（G9） |
| G9 | 广播无开关、无授权 | 所有已连对端永久旁观，无敏感任务豁免机制 |
| G10 | 无优先级 / 配额 / 并发上限 | 任意已连对端**可以**提交无限任务，每个任务起一个 worker 线程；无任务排程与背压。（落盘与恢复已有，见 G14） |
| G11 | ~~`error` 信号不唤醒等待~~ ✅ **已修复** | 协议层 `_on_error` 现在按 `reqid` 唤醒等待中的请求（同 [multi-round G3](./multi-round.md#9-已知缺口)） |
| G12 | 无错误码语义 | 任务失败只有自由文本 `error`，没有可分支的错误码 |
| G13 | `Signal.is_request()` / `is_response()` 不认识本模式类型 | 两者只覆盖核心类型；全仓库尚无消费方，影响面为零，但语义已不完整 |
| G14 | ~~🔵 规划中：任务持久化与恢复~~ ✅ **已实现** | `config["task_store"]` 开启 JSONL 追加存储；恢复遵循「先按 `task_id` 折叠、再判终态、一律标记 failed 并写回」。两条硬性要求：**坏字节不得让节点起不来**（宽松解码、坏行跳过），**存储不可用时降级为「不持久化 + 告警」**——落盘是可选能力，不得因此拒绝启动，也不得杀死 worker |
| G15 | 授权已实现 / 配额仍缺 | 授权按 [security](../security.md) §3.9 的映射判定（`task_submit` 走 `req`，其余走 `rep`），且**不**依赖对端自报能力位；配额与背压仍缺（见 G10） |
| G16 | 🔵 规划中：A2A HTTP / JSON-RPC 适配器 | 若实现，**必须**按「与 A2A 的等价映射」表格映射，**不得**改动本模式的报文形态 |
| G17 | ~~产物不可序列化会杀死 worker~~ ✅ **已修复** | `ctx.artifact()` 在部件进入记录**之前**即校验可 JSON 序列化，失败抛 `ValueError` → 任务以 `failed` 收场（失败也是终态，提交方拿得到）；落盘失败也不再改变任务语义、不再杀死 worker |

## 13. 参考实现映射

| 条文 | 源码文件与符号 |
|---|---|
| §2.1 `pattern_id` / `fallback_to` / `conflicts_with` | [`src/msp/patterns/task.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/task.py) `TaskHandler.pattern_id` / `.fallback_to`；[`src/msp/patterns/base.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/base.py) `PatternHandler.conflicts_with` |
| §2.2–§2.4 状态常量、状态机、终态不可逆 | `task.py` `STATE_SUBMITTED` … `STATE_CANCELED`、`TERMINAL_STATES`、`TaskHandler._transition` / `._finish` / `._ask` / `._run_task` |
| §3.2–§3.3 `task_submit` / `task_submit_result` | `task.py` `TaskHandler.submit` / `._on_submit` / `._on_submit_result` |
| §3.4–§3.6 `task_status` / `task_artifact` / `task_result` | `task.py` `._emit_status` / `._emit_artifact` / `._emit_result` |
| §3.7–§3.8 `task_query` / `task_cancel` 及其结果 | `task.py` `TaskHandler.get` / `._on_query` / `.cancel` / `._on_cancel` |
| §3.9 追问复用与同名信号不冲突 | `task.py` `TaskHandler.INPUT_REQUIRED` / `.INPUT_RESPONSE` / `._ask` / `._on_input_required` / `._on_input_response`；路由见 [`protocol.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._dispatch` |
| §4 消息流 | `task.py` 模块 docstring；端到端行为见 [`tests/test_task.py`](https://github.com/hxh230802/MSP/blob/master/tests/test_task.py) |
| §5.1–§5.2 `submit` / `wait` / `submit_and_wait` / `get` / 回调 | `task.py` `TaskHandler.submit` / `._prepare` / `._send_to` / `.submit_and_wait` / `.get` / `._request`；`TaskHandle.wait` / `.on_status` / `.on_artifact` |
| 「取消」协作式取消 | `task.py` `TaskHandler._on_cancel`；`TaskContext.cancel_requested`；哨兵 `_CANCEL_SENTINEL` |
| §5.3–§5.4 `TaskSnapshot` / `Artifact` | `task.py` `TaskSnapshot`、`Artifact`（`from_dict` 读 `taskId` / `contextId`）；块类型见 [`src/msp/core/content.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) `_BLOCK_TYPES` / `block_from_dict` |
| §5.5 `TaskContext` 与异常 | `task.py` `TaskContext.status` / `.emit` / `.artifact` / `.ask` / `.cancel_requested`；`TaskError` / `TaskCanceled` |
| §6 观察者广播 / Agent Card 投影 | `task.py` `TaskHandler._broadcast`（`publish(f"task.{id}.{kind}", payload)`）；[`manifest.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `Manifest.pattern_metadata` / `set_pattern_metadata`（线上键 `patternMetadata`）；[`node.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `MSPNode.register_pattern`；[`protocol.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol.publish` / `._on_signal` |
| §7.3 能力校验 / §7.8 回调异常路径 | `task.py` `TaskHandler._prepare`；[`peer.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/peer.py) `Peer.supports`；`protocol.py` `MSPProtocol._read_loop`（异常即断连） |
| 与 A2A 的等价映射 | [`docs/DESIGN.md`](../../designs.md#任务模式msptask与-a2a-等价映射)、[`docs/whitepaper.md`](https://github.com/hxh230802/MSP/blob/master/docs/whitepaper.md) |
| 模式激活与语法糖 / 预设声明 | `task.py` `TaskHandler.install_api`（挂 `node.task`）；`node.py` `MSPNode._activate_pattern`；[`preset.py`](https://github.com/hxh230802/MSP/blob/master/src/msp/core/preset.py) `Preset.FULL_PEER` / `LOCAL_AI` / `LOCAL_TOOL_ADVANCED` / `CLOUD_SERVICE` |
