# Testing a node

Three levels, cheapest first. Do not skip to the third one — the first two catch most of the bugs and
run in milliseconds.

## 1. Assert on the manifest — no network

The manifest is built from what you registered, so it can be checked before anything starts:

```python
node = MSPNode("weather", preset=Preset.LOCAL_TOOL)

@node.tool("get_weather", "Look up the weather")
def get_weather(location: str) -> dict: ...

node.start()
bindings = node.exposed_bindings()
assert any("get_weather" in str(b) for b in bindings)
```

This catches the classic mistake: registering a tool **after** `start()` in a path that never runs, or
declaring a signal path nobody publishes.

## 2. Two nodes in one process — real connections, no flakiness

Two `MSPNode`s in the same test process, sharing a temporary `nodes_dir`, is enough to exercise
discovery, handshake, calls and signals:

```python
def test_call(tmp_path):
    provider = MSPNode("p", preset=Preset.LOCAL_TOOL, nodes_dir=str(tmp_path))
    consumer = MSPNode("c", preset=Preset.FULL_PEER, nodes_dir=str(tmp_path))

    @provider.tool("echo", "echo")
    def echo(text: str) -> dict:
        return {"text": text}

    provider.start(); consumer.start()
    try:
        assert "p" in consumer.connections()
        result = consumer.call("p", "echo", {"text": "hi"}, timeout=5)
        assert result.unwrap()["text"] == "hi"
    finally:
        consumer.stop(); provider.stop()
```

Two rules that keep such tests honest:

- **Assert on `connections()`, not `neighbors()`.** A neighbour is a lease that has not expired; a
  connection is a socket that exists. Only the second one means you can call.
- **Always give a timeout**, and make it generous (5 s). A flaky test with a 0.1 s timeout teaches you
  nothing.

This is the pattern the repository's own examples use — see
`docs-site/tools/check_examples.py`, which starts real subprocesses for the same reason.

## 3. Cross-implementation interop — bytes on a socket

If you are writing a second implementation, the interesting test is not "does my client work with my
server" but "do my bytes match theirs". The `msp-ts` suite does this by starting a **Python** node as a
subprocess and talking to it:

```
msp-ts/test/support/py_node.py   starts a Python node, resolves `msp` in three tiers
msp-ts/test/*.test.ts            handshake, call, broadcast, dedup, framing
```

Sample of what it pins down: 4-byte big-endian length prefix, all eight top-level keys always present
(`null` rather than omitted), unknown fields preserved in `extras`, and the dedup direction chosen by
`node_id` ordering.

Run it against a local checkout:

```bash
cd msp-ts
MSP_PY_SRC=../ModelSensingProtocol/src npm test
```

## What to assert about failure, not just success

- **Unknown tool** returns an error result — it must not throw and must not hang.
- **A tool that raises** surfaces as an error with the message, not as an empty success.
- **Timeout** returns an error; `resultsDropped` goes up on the provider side.
- **Peer killed mid-call** fails fast instead of waiting for the full timeout.
- **Duplicate node id** evicts, and `replaced` in `metrics_line()` goes up — that is the observable
  symptom of a naming collision.

## See also

- [Debugging](debugging.md) — what the counters mean when a test fails
- [Long tasks](tasks.md) — how to test `start_task` / `get_task` without sleeping for minutes
- [`spec/interop.md`](pathname:///msp-site/docs/spec/interop/) — the normative interoperability requirements
