# Long tasks with the task pattern

A tool call that blocks for two minutes is a bad tool: the caller has no idea whether it is alive, and
the transport has to hold the connection the whole time. The **task pattern** is MSP's answer — the
call returns a handle, and the work continues on the provider's side.

This is the shape behind the [downloader example](examples/downloader.md), and the shape a DeepSeek
Harness long-running tool call expects.

## The contract

Three tool names, by convention:

| Tool | Purpose |
|---|---|
| `start_task(args…)` | begins work, returns `{ taskId, state: "running", … }` immediately |
| `get_task({taskId})` | returns the current snapshot: state, progress, result or error |
| `list_tasks()` | optional; the queue, for a human or an agent that lost a handle |

Plus at least one signal path for transitions — `download.progress`, `download.completed`,
`task.failed` — so the caller does not have to poll.

## Provider side

```python
TASKS: dict[str, dict] = {}

@node.tool("start_task", "Begin work, return a taskId immediately")
def start_task(url: str) -> dict:
    task_id = uuid.uuid4().hex[:8]
    TASKS[task_id] = {"taskId": task_id, "state": "running", "progress": 0}

    def work() -> None:
        try:
            for pct in run_job(url):
                TASKS[task_id]["progress"] = pct
                node.publish("task.progress", {"taskId": task_id, "progress": pct})
            TASKS[task_id].update(state="completed", result={...})
            node.publish("task.completed", {"taskId": task_id})
        except Exception as exc:
            TASKS[task_id].update(state="failed", error=str(exc))
            node.publish("task.failed", {"taskId": task_id, "error": str(exc)})

    threading.Thread(target=work, daemon=True).start()
    return TASKS[task_id]

@node.tool("get_task", "Read a task's current state")
def get_task(taskId: str) -> dict:
    return TASKS.get(taskId, {"taskId": taskId, "state": "unknown"})
```

Two rules that matter more than the code:

- **Never report success you have not verified.** `state` must not become `completed` until the work
  actually finished. A preallocated 100 MB file is not a finished download.
- **Keep the snapshot cheap.** `get_task` is called often, including by monitoring; it should return a
  dict you already have, not recompute anything.

## Consumer side

The good consumer does both halves — waits for the signal, and polls as a fallback:

```python
started = node.call("downloader", "start_task", {"url": url}).unwrap()
task_id = started["taskId"]

done = threading.Event()
@node.on("task.completed")
def on_done(sig):
    if sig.payload.get("taskId") == task_id:
        done.set()

# wake on the signal, but do not hang forever if it was dropped
if not done.wait(timeout=300):
    log.info("no completion signal; polling")
    while node.call("downloader", "get_task", {"taskId": task_id}).unwrap()["state"] == "running":
        time.sleep(2)
```

That is 15 lines to make a dropped signal survivable. Skipping it is how "it worked in the demo" turns
into "it hangs in production".

## Failure is a state, not an exception

`task.failed` is a normal outcome. Report it through the snapshot **and** the signal, and let the caller
decide. Do not raise inside `start_task` for a failure that happens later — the caller is long gone by
then.

## Where this lives

- Signal paths and tool names are a **convention**, not protocol: MSP does not know what a task is.
- The [spec's task pattern chapter](pathname:///msp-site/docs/spec/patterns/task/) describes the same shape normatively.
- DeepSeek Harness's `msp_call_wait` uses exactly this contract: it waits for the completion signal,
  polls `get_task` as a fallback, and turns a timeout into a background task you can walk away from.
