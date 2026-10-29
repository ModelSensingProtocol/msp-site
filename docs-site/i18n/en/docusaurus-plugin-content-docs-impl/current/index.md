# Implementation

One wire format, several languages. The table below shows the **current real state**, including the parts that are not yet usable.

| Implementation | Language | Status | Location |
|---|---|---|---|
| **msp-py** | Python 3.10+ | Reference implementation, PyPI pre-release `0.1.0a1`, 272 tests passing | [PyPI](https://pypi.org/project/msp-py/) |
| **msp-ts** | TypeScript / Node ≥ 22.6 | Zero dependencies, byte-for-byte interop with msp-py, 24 tests passing | [msp-ts](https://github.com/ModelSensingProtocol/msp-ts) |
| **dsh-msp** | JavaScript | DeepSeek Harness plugin: turns each node's tools into agent tools | [dsh-msp](https://github.com/hxh230802/dsh-msp) |
| **msp-cpp** | C++20 | CMake + CI + interop tests, **repository not yet public** | Private |
| **msp-dotnet** | C# / .NET | `Msp.slnx` solution, **repository not yet public** | Private |

## What "interop" means

It does not mean "looks the same" but the same bytes:

- 4-byte big-endian length prefix + UTF-8 JSON, with 8 top-level fields constant
- Handshake messages are compared byte for byte between two implementations
- The `msp-ts` tests start a real Python node and use a real TCP connection

The interop cases between `msp-py` and `msp-ts` live under `msp-ts/test/`; when the tests run they look for a sibling
`ModelSensingProtocol/src` (or an installed `msp` package), and report an explicit error rather than skipping if it is missing.

## Consistency

`schema/2026-10-10/` in the specification is the **single** source of field definitions, and each implementation takes its manifest fields from it;
`tools/gen_schema.py` generates the JSON Schema and the field index from YAML, to avoid hand-copying.

## Adding a language

A minimal usable implementation needs only four things:

1. Framing: 4-byte big-endian length + JSON
2. Handshake: `HELLO` (with manifest) → `ACK`
3. Discovery: read and write the declaration file in the shared directory, and deduplicate by `node_id`
4. Heartbeat: `PING` every 15 seconds; no response for 45 seconds counts as liveness loss

Everything else (patterns, authorization, transport) can be added later — which is exactly what "every layer is extensible" means.
