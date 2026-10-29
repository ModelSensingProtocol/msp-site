# Discovery and Presence

| | |
|---|---|
| **Protocol revision** | `2026-10-10` |
| **Status markers** | ✅ Implemented (shared directory, manual registry); 🔵 Planned (DHT) |
| **Defined on this page** | The contract of the two orthogonal interfaces `Discovery` and `Presence`, the structure of `Endpoint`, the exact format of the shared-directory declaration file and its lease semantics, the message shape and polling rules of the manual registry (file / HTTP), the hook for injecting discovery sources at runtime, and the complete planned provisions for DHT. |

## 1. Overview

The discovery layer answers "how do I find others"; the announce layer answers "how do others find me". They are **two orthogonal interfaces**, not two halves of one thing: a node may have discovery only (observer), announce only (it provides capabilities but does not actively look for others), or both.

| Interface | Input | Output | Reference implementation |
|---|---|---|---|
| `Discovery` | Shared channel (directory / registry / DHT) | `Endpoint` | [directory.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/directory.py) `DirectoryScan`, [manual.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/manual.py) `ManualConnect` |
| `Presence` | `Endpoint` | One declaration in the shared channel | [directory.py](https://github.com/hxh230802/MSP/blob/master/src/msp/presence/directory.py) `DirectoryWrite`, [manual.py](https://github.com/hxh230802/MSP/blob/master/src/msp/presence/manual.py) `ManualAdvertise` |

The common data unit of the two is `Endpoint`: discovery produces it, announce consumes it, and the transport layer (see [transports.md](./transports.md)) selects a backend by its `transport_type`. The node layer ([core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py)) depends only on these two interfaces and is unaware of the concrete mechanism.

| Component | Reference implementation key | Status |
|---|---|---|
| Shared-directory discovery | `directory` / `DirectoryScan` | ✅ Implemented |
| Shared-directory announce | `directory` / `DirectoryWrite` | ✅ Implemented |
| Manual-registry discovery | `manual` / `ManualConnect` | ✅ Implemented |
| Manual-registry announce | `manual` / `ManualAdvertise` | ✅ Implemented |
| DHT discovery + announce | `dht` (planned) | 🔵 Planned |

## 2. Contracts

### 2.1 `Discovery`

```
list_endpoints() -> list[Endpoint]
watch(on_add: Callable[[Endpoint], None],
      on_remove: Callable[[str], None] | None = None) -> None
stop() -> None
```

- `list_endpoints()` **MUST** return all currently known endpoints, for the initial snapshot at startup; it **MUST NOT** fail as a whole because one declaration is corrupt (skipping the bad entry is enough).
- `watch(on_add, on_remove)` **MUST** complete at least one full scan before returning, so that the caller can already see existing neighbours when `watch()` returns (the reference implementation runs `_full_scan()` / `_scan()` synchronously first, then starts the background thread).
- `on_add` **MUST** be called both when a new endpoint is discovered and when the declaration of an already-discovered endpoint changes; the argument of `on_remove` **MUST** be the `node_id` string and **MUST NOT** be an `Endpoint`.
- `on_remove=None` **MUST** be tolerated; a discovery source **MUST NOT** treat this node itself as a neighbour (declarations matching `self_node_id` **MUST** be skipped).
- Callbacks **MAY** be invoked on any thread (file-event thread, polling thread); an implementation **MUST NOT** assume it runs on the thread that called `watch()`; the callback owner **SHOULD** move time-consuming work out of the callback (the reference implementation's `node._on_endpoint` starts its own dialling thread).
- `stop()` **MUST** be idempotent and **SHOULD** return within one polling period, and **MUST NOT** trigger new callbacks after returning.
- The abstract base class declares only `list_endpoints` and `watch`; `stop()` is a **convention method** (both implemented mechanisms provide it and `MSPNode.stop()` calls it by duck typing), see §9-12.

### 2.2 `Presence`

```
announce(endpoint: Endpoint) -> None
withdraw(node_id: str) -> None
update(endpoint: Endpoint) -> None      # default implementation = withdraw + announce
```

- `announce` **MUST** require `endpoint.node_id` to be non-empty.
- `withdraw(node_id)` **MUST** be idempotent: no error when the declaration does not exist (the reference implementation swallows `FileNotFoundError`).
- `update` **MAY** be overridden as a more efficient incremental update; both implemented mechanisms override it as "overwrite directly" rather than delete-then-write.
- Announce **MUST NOT** produce or modify the semantics of `Endpoint` (**MUST NOT** fill in `node_id`, **MUST NOT** rewrite `address`); it only serialises and writes. It **MUST NOT** read other nodes' declarations from the shared channel — reading is the job of `Discovery`.
- `announce` failures **MUST** be raised explicitly (announce should fail fast): a declaration that cannot be written means this node cannot be discovered, and a silent failure makes the fault hard to locate.

### 2.3 Orthogonality of the Two Interfaces

| Combination | Meaning | Preset example |
|---|---|---|
| `Discovery` only | Only finds others, does not announce itself | `OBSERVER` (only subscribes to signals) |
| `Presence` only | Only found, does not actively look for others (accept-only) | `LOCAL_TOOL`, `CLOUD_SERVICE` |
| Both | Full peer | `FULL_PEER`, `LOCAL_AI`, `MANUAL_PEER` |

A node **MAY** enable several discovery mechanisms and several announce mechanisms (`Preset.discovery` / `Preset.presence` are sets). When several discovery sources point at the same `node_id`, **the last processed source wins** (the reference implementation overwrites the dictionary in source order); implementations **SHOULD** document this precedence.

The `DirectoryScan` constructor actively creates `nodes_dir`: a pure scanning node (with no announce layer) also needs the directory to exist, otherwise the file-event watcher cannot be attached.

### 2.4 Injecting Discovery Sources at Runtime (`install_api`)

Any layer component **MAY** define `install_api(node)`; `MSPNode` calls it immediately after constructing that component (if present), so the component can attach convenience methods to the node without changing the core.

- The only discovery component implementing this hook is `ManualConnect`: it attaches

```
node.add_manual_source(source: str) -> None
```

- The value rules for `source` are the same as for the constructor argument (file path / `file://` / `http(s)://`, see §3.3); the call **MUST** work both before and after `start()`: a call before `start()` only registers, and the scan happens in `watch()`; a call after `start()` **MUST** immediately append one scan, and a failure **SHOULD** only log and not interrupt the node.
- In the reference implementation `DirectoryScan` / `DirectoryWrite` / `ManualAdvertise` do **not** implement `install_api` (see §9-12).

## 3. Messages and Formats

### 3.1 The Shared-Directory Declaration File

Each node writes its declaration as "one file in a directory"; other nodes scan that directory. This is the zero-configuration mechanism for the local-machine scenario.

- **Location**: `nodes_dir`, default `~/.msp/nodes` (`os.path.expanduser` at construction).
- **Filename rule**: `{self_node_id}.json` — the filename uses the **announcer's own** node_id, unrelated to the `endpoint.node_id` passed to `announce(endpoint)`.
- **Atomic write**: **MUST** first write a temporary file `{self_node_id}.json.tmp` in the same directory, then `os.replace` over the target. The temporary filename **MUST NOT** end with `.json`, otherwise the scanning side would take a half-written file for a declaration (both scanning and event filtering decide by the `.json` suffix).
- **File content** (verbatim, `json.dump(..., ensure_ascii=False, indent=2)`, no trailing newline after writing):

```json
{
  "node_id": "node_a",
  "endpoint": {
    "transport_type": "tcp",
    "address": {
      "host": "127.0.0.1",
      "port": 45678
    }
  },
  "timestamp": 1712345678.0
}
```

- Field semantics: `node_id` is the announcer's identity; `endpoint.transport_type` / `endpoint.address` come straight from `Endpoint` (shapes in [transports.md §3.2](./transports.md#32-address-formats)); `timestamp` is Unix epoch seconds (float), i.e. the **lease** (see §3.2).
- **Lenient reading**: the scanning side **MUST** ignore unrecognised top-level and nested fields (**MAY** add fields without issuing a new revision); when `node_id` is missing, `endpoint` is missing, JSON parsing fails, or the file is unreadable, it **MUST** skip that file and **MUST NOT** abort the scan because of it.
- **Which one wins**: `node_id` comes from the **file content** (used to produce the `Endpoint` and for deduplication); a file **deletion** event can only infer `node_id` from the **filename** (strip the `.json` suffix), so implementations **SHOULD** keep the two consistent — a manually placed file that is renamed may make the removal notification point at the wrong identifier (see §9-5).
- A declaration **MUST NOT** carry a tool/capability manifest: the manifest is exchanged only during the handshake (see [base-protocol.md](./base-protocol.md)); the discovery phase exposes endpoints only.

### 3.2 Lease and TTL

`timestamp` is a lease, not metadata: a declaration not renewed in time **MUST** be treated as "the node is dead" and dropped from discovery results.

| Parameter | Default | Owner | Meaning |
|---|---|---|---|
| `renew_interval` | `10.0` s | `DirectoryWrite` | Renewal period (interval for rewriting `timestamp`) |
| `stale_after` | `30.0` s | `DirectoryScan` | Expiry threshold: `now - timestamp > stale_after` means expired |
| `poll_interval` | `30.0` s | `DirectoryScan` (`5.0` s for `ManualConnect`; `DirectoryWrite` has no such parameter) | Interval of the periodic full rescan |

Rules:

- Expiry **MUST** be strictly greater: only `now - timestamp > stale_after` expires; exactly equal to the threshold is still valid.
- When `timestamp` is missing (`null` or field absent) it **MUST** be treated as **never expiring** — this is backward compatibility for old and hand-written declarations, so they do not take part in lease eviction.
- An expired or corrupt declaration **MUST** count as "absent" during a scan: it **MUST NOT** produce an `Endpoint` **and** **MUST** trigger `on_remove` (this is "hard clean-up": the neighbour entry of a crashed node is deleted rather than marked suspect).
- The announcer **MUST** ensure `renew_interval < stale_after` (default 10 s < 30 s), otherwise its own declaration would periodically expire.
- Time **MUST** be taken from the local clock. On a cross-machine network filesystem, clock skew between announcer and scanner shows up directly as misjudgement (see §9-7).
- The upper bound on the disappearance delay of a crashed node is `stale_after + poll_interval` (60 s by default): expiry is only noticed on the next scan; the event channel does not report that "the declaration has gone stale".

### 3.3 Manual Registry (Local File / HTTP)

Cross-machine / cloud scenarios do not rely on file events; they read the endpoint list from a "shared registry". The registry is **single-carrier, multiple-node**: one file or one URL carries several declarations.

**Carrier selection** (resolution rules for the `source` argument; `nodes_dir` defaults to `~/.msp/nodes`):

| `source` | Carrier | Description |
|---|---|---|
| `None` | File | `{nodes_dir}/manual_peers.json` |
| `file://<path>` | File | strip the `file://` prefix, then `expanduser` |
| Bare path | File | `expanduser` directly |
| `http://…` / `https://…` | HTTP | `base_url = source.rstrip("/")`; both schemes go through the same implementation |

**Entry format** (JSON array; entry fields are the same as the declaration file):

```json
[
  {
    "node_id": "node_a",
    "endpoint": {"transport_type": "tcp", "address": {"host": "127.0.0.1", "port": 45678}},
    "timestamp": 1712345678.0
  }
]
```

- File carrier read: when the file does not exist, the JSON is invalid, there is no read permission, or the top level is not an array, it **MUST** return an empty list and **MUST NOT** throw.
- File carrier write: **MUST** be read–modify–write with atomic replacement (`{path}.tmp` in the same directory + `os.replace`) and **MUST NOT** append in place.
- `upsert(entry)` **MUST** replace the existing entry by `node_id` (replace when present, append when absent); `remove(node_id)` **MUST** remove all occurrences of that entry. A `node_id` **SHOULD** appear at most once in the registry.
- The file carrier's `timestamp` **currently takes no part in any expiry decision**: `ManualConnect` deduplicates only by entry content hash and never reads `timestamp`. Entries therefore **do not** expire automatically; if the announcer does not `withdraw`, zombie entries remain forever (see §9-8).

**HTTP registry messages** (implementation-defined parts are marked):

| Operation | Request | Expected response |
|---|---|---|
| Read all entries | `GET {base_url}` | 2xx + JSON array (**MUST** be an array; a non-array or a parse failure counts as empty) |
| Report / update | `PUT {base_url}/{node_id}`, `Content-Type: application/json`, body is the **whole entry** JSON | any 2xx; response body ignored |
| Withdraw | `DELETE {base_url}/{node_id}` | any 2xx; response body ignored |

- Timeouts **MUST** be bounded (all three are 5 s in the reference implementation); **MUST NOT** wait indefinitely. `node_id` is **not** URL-encoded; its character set is constrained by the index to `[a-z0-9_-]+`, so it can safely be concatenated into the path.
- Read failures **MUST** degrade to an empty result (network jitter should not crash the discovery layer); report and withdraw failures **MUST** be raised (`urllib` raises `HTTPError` on 4xx/5xx).
- **Implementation-defined** (not specified by the source): authentication method (**no** authentication header in requests), concurrency control (**no** `ETag` / `If-Match`, so two nodes upserting concurrently can lose updates), pagination and incremental fetch (a full GET every time), error response body format, `POST` semantics, cache headers, TLS certificate verification policy (the `urllib` default context is used).

### 3.4 DHT Records (🔵 Planned)

**An implementer MAY not implement this, but once implemented it MUST comply with this provision.**

- **Positioning**: decentralised wide-area discovery, replacing the centralised HTTP registry (a registry can only be a single point). The DHT serves as both discovery and announce channel: announcers `put` records and discoverers `get` them.
- **Key design**: the record key **MUST** be `SHA-256(UTF-8("msp/dht/1:" + node_id))` (32-byte digest, used directly as the ID in the Kademlia key space). The plaintext `node_id` **MUST NOT** be used as the key — that would make the whole table enumerable by name.
- **Record shape** (the first three fields are **verbatim identical** to the shared-directory declaration, reusing the same parser and `Endpoint` mapping):

```json
{
  "node_id": "node_a",
  "endpoint": {"transport_type": "quic", "address": {"host": "203.0.113.7", "port": 4433}},
  "timestamp": 1712345678.0,
  "expires_at": 1712349278.0,
  "public_key": "<base64(Ed25519 public key, 32 bytes)>",
  "signature": "<base64(Ed25519 signature)>"
}
```

- `expires_at` **MUST** satisfy `timestamp < expires_at <= timestamp + TTL`; the TTL **SHOULD** be between 300 and 3600 s.
- `signature` **MUST** be produced by `public_key` over "the canonical JSON of the four fields `node_id` / `endpoint` / `timestamp` / `expires_at`", with the same canonicalisation rule as deduplication: `json.dumps(..., sort_keys=True)` with no extra whitespace, UTF-8 encoded; `signature` itself **MUST NOT** be included in the signed range.
- **Registration flow**: the announcer performs `put` on `record_key` with replication factor `k = 20`; it republishes every `renew_interval` (or one third of the TTL, whichever is smaller); on `withdraw` it sends `delete` to the nearest nodes. Intermediate nodes **MUST** verify the signature before storing or forwarding, and **MUST NOT** forward unsigned records.
- **Lookup flow**: the requester performs `get` on `record_key` and **SHOULD** use an iterative lookup (parallel α = 3 paths); after obtaining the record set it verifies each record's signature and checks `expires_at`, maps the passing ones to `Endpoint` and reports them via `on_add`. Results **SHOULD** be cached for `min(TTL, 60 s)`, and it **MUST NOT** hit the whole network on every `poll_interval`.
- **Expiry and lease**: records with `expires_at <= now` **MUST** be dropped and trigger `on_remove(node_id)`; storing nodes **MUST NOT** keep serving the record after `expires_at`. A republish rate lower than the TTL causes records to disappear early (expiry semantics isomorphic to the directory lease).
- **Mapping to `Endpoint`**: `node_id` → `Endpoint.node_id`, `endpoint.transport_type` → `Endpoint.transport_type`, `endpoint.address` → `Endpoint.address`; the remaining fields (`expires_at` / `public_key` / `signature`) **MUST NOT** leak into `Endpoint`.
- **Wiring into the Registry**: register as `DISCOVERY_REGISTRY["dht"] = DHTDiscovery`, `PRESENCE_REGISTRY["dht"] = DHTAdvertise`; parameters pass through `config`, for example `config={"discovery": {"dht": {"bootstrap": [{"host": "h", "port": 6881}], "ttl": 600}}}`. A node enables it by adding `"dht"` to `Preset.discovery` / `presence`; the core needs no change. A single record **SHOULD** be ≤ 4096 bytes, and implementations **SHOULD** bound the hop count and concurrency of a single lookup so as not to turn the discovery layer into an amplification surface.

## 4. Message Flows

### 4.1 Shared Directory: announce → scan → dial

```
Node A (announcer)           filesystem ~/.msp/nodes/           Node B (scanner)
  | start()                                                       | start()
  |  listen_all() -> get A's listen address                        |  listen_all()
  |  Endpoint(A)                                                   |
  |  DirectoryWrite.announce(Endpoint(A))                          |
  |   write A.json.tmp (json.dump indent=2)                        |
  |   os.replace(A.json.tmp, A.json) ------> [A.json]              |
  |   start renewal thread (rewrite timestamp every 10 s)          |
  |                                                               |  DirectoryScan.watch(on_add, on_remove)
  |                                                               |   1) _full_scan() synchronous pass: listdir -> only *.json
  |                                                               |      _read_declaration: bad file/expired -> skip
  |                                                               |      skip self_node_id, missing node_id, missing endpoint
  |                                                               |      hash(json.dumps(decl, sort_keys=True)) dedup
  |                                                               |   2) start event thread + poll_loop (poll_interval=30 s)
  |<==== on_add(Endpoint(A)) ===== node._on_endpoint():          |
  |                               _neighbors["a"] = Endpoint,     |
  |                               connect_policy=eager -> dial  |
  |<===== TCP / UDS / WebSocket connection + HELLO / ACK =========|
  | stop() -> DirectoryWrite.withdraw("a") -> unlink A.json        |
  |                                                               |  event or poll finds A.json gone
  |                                                               |  -> on_remove("a") -> _neighbors.pop("a")
```

Note the division of labour between the two channels: `watchdog` file events handle **real time**, periodic polling handles **fallback** (it still converges when the watchdog fails, events are lost, or across filesystems). Polling **MUST NOT** be omitted — it is the only guaranteed discovery path.

### 4.2 Lease Renewal and Expiry Clean-up

```
t=0    A writes the declaration, timestamp=T0, renewal thread starts
t=10   A renews -> timestamp=T10 (renews again at t=20 -> T20)
t=25   A crashes (SIGKILL, no time to withdraw, the file remains)
t=30   B scans: now-T20 = 10, not greater than stale_after(30) -> still valid
t=55   B scans: now-T20 = 35 > 30 -> _read_declaration returns None
       -> A is not in this round's current_nodes, but _known still remembers A
       -> judged "gone" -> on_remove("a") (hard clean-up) -> _neighbors.pop("a")
       disappearance delay upper bound = stale_after + poll_interval (60 s by default)
```

### 4.3 Manual Registry: Polling and Reporting

```
Node A (ManualAdvertise)       registry (file / HTTP)         Node B (ManualConnect)
  | announce(Ep)                                                  |
  |  PUT /nodes/a {node_id, endpoint, timestamp} ---------------->|  stores a
  |  (no renewal thread: timestamp is written once on announce/update)
  |                                                              | poll (poll_interval=5 s): GET /nodes -> [ {...} ]
  |                                                              |  _to_endpoint: skip self, validate fields
  |                                                              |  hash(entry) dedup -> on_add
  |                                                              |  entry gone from all sources -> on_remove
  | stop(): withdraw("a") -> DELETE /nodes/a ------------------->|  deletes a
```

`list_endpoints()` and polling share the same parsing (`_to_endpoint`), so the startup snapshot and the runtime increments cannot diverge in field validation.

### 4.4 DHT: Registration and Lookup (🔵 Planned)

```
announcer A                                          requester B
  | key = SHA256("msp/dht/1:a")                      |
  | sign the record (Ed25519)                        |
  |-- put(key, record), iteratively converge to k=20 nearest nodes -->|  DHT network
  |   republish every TTL/3 or renew_interval        |
  |                                                  |-- get(key) iterative lookup (α=3) -->|
  |                                                  |<-- record set (multiple replicas) ---|
  |                                                  |   verify signature per record + check expires_at -> Endpoint -> on_add
  |                                                  |   cache min(TTL, 60 s)
  | withdraw(): delete(key) ------------------------>|
  |                                                  | expires_at reached -> on_remove
```

## 5. Data Types

### 5.1 `Endpoint`

| Field | Type | Required | Description |
|---|---|---|---|
| `transport_type` | `str` | yes | Transport backend identifier: `tcp` / `websocket` / `uds` / `quic` (see [transports.md §3.2](./transports.md#32-address-formats)) |
| `address` | `dict` | yes | Address; the structure varies with `transport_type` |
| `node_id` | `str \| None` | no (default `None`) | The peer identity may not be known yet during manual discovery |

- `address` shape per backend: `tcp` → `{"host": str, "port": int}`; `websocket` → `{"url": "ws://host:port/path"}`; `uds` → `{"path": str}`; `quic` → `{"host": str, "port": int, …}` (🔵).
- **Deduplication key**: `(transport_type, tuple(sorted(address.items())))` — the same `transport_type` + the same `address` counts as the same endpoint, regardless of `node_id`.
- An `Endpoint` whose `node_id` is `None` **MAY** exist (a hand-filled address), but it **MUST NOT** be produced by the shared-directory / registry mechanisms (both mechanisms require a `node_id` in the declaration).
- The values of `address` **SHOULD** be hashable: `address_key()` itself does not throw (`sorted` only compares keys), but when its **return value** is used as a `set` / `dict` key, an `address` containing a nested `dict` / `list` throws `TypeError` (see §9-15).

### 5.2 Implementation Parameters of Discovery and Announce

| Component | Constructor parameters (defaults) |
|---|---|
| `DirectoryScan` | `self_node_id` (required), `nodes_dir="~/.msp/nodes"`, `poll_interval=30.0`, `stale_after=30.0` |
| `DirectoryWrite` | `self_node_id` (required), `nodes_dir="~/.msp/nodes"`, `renew_interval=10.0` |
| `ManualConnect` | `self_node_id` (required), `nodes_dir="~/.msp/nodes"`, `source=None`, `poll_interval=5.0` |
| `ManualAdvertise` | `self_node_id` (required), `nodes_dir="~/.msp/nodes"`, `source=None` (same resolution rules as `ManualSource`) |

Registry names (the keys used in `Preset.discovery` / `Preset.presence`): `"directory"` for the DIRECTORY mechanism and `"manual"` for the manual mechanism (keys of `DISCOVERY_REGISTRY` / `PRESENCE_REGISTRY`). `config` is passed through grouped by layer, for example `config={"presence": {"manual": {"source": "http://registry:8080/nodes"}}}`.

### 5.3 Declaration and Registry Entry Fields

| Field | Type | Skip rule (discoverer) |
|---|---|---|
| `node_id` | `str` | missing / empty / equal to `self_node_id` → skip |
| `endpoint` | `dict` | missing → skip |
| `endpoint.transport_type` | `str` | the registry carrier **MUST** have it (when missing or of the wrong type, skip that entry as a "corrupt declaration", see §6; it is no longer reported as an error by the transport layer) |
| `endpoint.address` | `dict` | same as above |
| `timestamp` | `float` (epoch seconds) | shared directory: missing counts as never expiring; manual registry: ignored |

`timestamp` has **different force** in the two mechanisms (lease vs decorative field), and implementations **MUST NOT** treat the manual registry's `timestamp` as a TTL.

## 6. Error Handling and Boundaries

| Scenario | Behaviour |
|---|---|
| Declaration file missing / no permission / invalid JSON | Skip (count as absent), **MUST NOT** throw; `on_remove` is not triggered (unless it was previously in `_known`) |
| Declaration missing `node_id` or `endpoint` | Skip |
| Declaration belongs to itself | Skip, **MUST NOT** notify |
| Declaration expired (`now - timestamp > stale_after`) | Count as absent; if previously known, trigger `on_remove(node_id)` |
| Polling scan throws / file-event thread fails to attach | Polling logs a warning and carries on (**MUST NOT** terminate the polling thread); event-thread exceptions are not caught (see §9-13), leaving only the polling fallback |
| `stop()` called repeatedly / watcher not yet created | Idempotent; a watcher-creation race may leak a thread (see §9-13) |
| Declaration file missing during `withdraw` | Swallow `FileNotFoundError`, no error |
| Registry file top level is not an array | Count as empty |
| HTTP `GET` fails / times out / returns non-JSON | Count as an empty result, do not throw |
| HTTP `PUT` / `DELETE` fails (4xx/5xx/network error) | Throw (announce is fail-fast) |
| The same `node_id` appears in several sources | The last processed entry wins; `list_endpoints()` returns duplicate entries while polling deduplicates them |
| Scan immediately after `add_manual_source` fails | Log a warning, do not interrupt the node |

## 7. Summary of Normative Provisions (MUST/SHOULD Checklist)

1. `Discovery.watch()` **MUST** complete one full scan before returning.
2. The argument of `on_remove` **MUST** be a `node_id`; it **MUST NOT** be an `Endpoint`.
3. A discovery source **MUST** skip `self_node_id`; `Discovery.stop()` **MUST** be idempotent and **MUST NOT** trigger new callbacks after returning.
4. `Presence.announce` **MUST** require a non-empty `node_id`; `withdraw` **MUST** be idempotent.
5. Announce **MUST NOT** read other nodes' declarations in the shared channel; discovery **MUST NOT** write to the shared channel.
6. An `announce` failure **MUST** be raised explicitly; a read failure on the discovery side **MUST** degrade to "count as absent".
7. The declaration file **MUST** use the fields of §3.1 and the `{self_node_id}.json` naming, and **MUST** be written atomically; the temporary filename **MUST NOT** end with `.json`.
8. The discoverer **MUST** ignore unknown fields; it **MUST NOT** abort the scan because a single declaration is corrupt.
9. Renewal **MUST** satisfy `renew_interval < stale_after` (default 10 s < 30 s).
10. The expiry test **MUST** be `now - timestamp > stale_after` (strictly greater); a missing `timestamp` **MUST** count as never expiring.
11. An expired declaration **MUST** trigger `on_remove` (hard clean-up) and **MUST NOT** merely be marked suspect.
12. Periodic polling **MUST NOT** be omitted; it is the only guaranteed discovery path; file events are only a latency optimisation.
13. Manual registry entries **MUST** follow the fields of §3.3; file carrier writes **MUST** be atomic replacements.
14. HTTP `GET` **MUST** degrade "non-array / non-2xx / parse failure" to an empty result; timeouts **MUST** be bounded.
15. DHT (🔵) **MUST** use hashed keys, **MUST** verify signatures before accepting or forwarding records, and **MUST** drop records once `expires_at` is reached.
16. A discovery source added at runtime **SHOULD** reuse the same `source` resolution rules as the constructor argument.

## 8. Security Considerations

- **Declarations can be forged**: any process that can write `nodes_dir` can announce any `node_id`; there is no binding between `node_id` and process identity. The trust boundary of the discovery layer equals "the writability of the shared channel"; this agrees with [security.md](./security.md): authentication is not in the discovery layer but after the connection is established.
- **Directory permissions are not tightened**: `nodes_dir` is created with the default umask and implementations do **not** set permissions explicitly. Other users on the same machine may therefore read declarations — the exposure is limited to endpoints and `node_id` (no tools or manifest, which are exchanged only during the handshake). UDS's `0o600` is a tightening of the **connection** layer, not of the declaration files. Declaration files also continuously expose "which nodes are running on this machine", and renewal and polling frequencies leak node activity (10 s / 30 s by default).
- **HTTP registries can be poisoned**: the registry is a single plaintext trust point with no authentication and no integrity check; whoever can modify the registry can steer discoverers to arbitrary endpoints. Using it on the public internet therefore **MUST** come with TLS and authentication (see §3.3, "implementation-defined"), and it **SHOULD NOT** be exposed directly to untrusted networks.
- **Additional DHT threats**: Sybil / Eclipse (an attacker enclosing the neighbourhood of a key can answer with a forged neighbour list) — the mitigations are record signatures + multipath lookup + cross-validation of results; unsigned records **MUST NOT** be trusted. Key hashing only hides the plaintext of `node_id`; the record body still contains the endpoint address, so announcements on a DHT **SHOULD** be treated as public information. UDP transport **MUST** prevent amplification (a response **MUST NOT** be larger than the request).
- **Denial-of-service surface**: a discovery callback triggers dialling (`connect_policy=eager`), so malicious declarations can continuously inject new `node_id` values and manufacture connection attempts and threads. The node layer's `connect_backoff` (5 s by default) only cools down peers that have already failed; it does not limit the number of new identities.

## 9. Known Gaps

1. **Atomic writes are not seen by the event channel**: `os.replace` is a rename within the same directory; on Linux `watchdog` merges the paired renames into a `FileMovedEvent` and dispatches it to `on_moved`, while the event handler implements only `on_created` / `on_modified` / `on_deleted`. A new node's **first announcement is therefore only discovered on the next poll (30 s by default)**; the event mechanism does not work for this main path, whereas the unlink in `withdraw` does trigger in real time. Manual in-place modification (opening an existing `.json` for writing) does trigger in real time.
2. **Renewal defeats deduplication**: the dedup key is `hash(json.dumps(decl, sort_keys=True))`, which includes the ever-changing `timestamp`. Every scan after a renewal therefore triggers `on_add` again (once per 30 s by default) — idempotency rests on the node layer's `_neighbors` overwrite and the protocol layer's "return immediately if already connected", not on discovery-layer deduplication.
3. ~~**Renewal cannot be restarted**~~ ✅ **Fixed**: `DirectoryWrite.withdraw()` now resets the stop event and the renewal thread handle, so a further `announce` / `update` restarts renewal (idempotency is guaranteed by `is_alive()`).
4. 🟡 **`withdraw` still ignores the `node_id` argument**: the path is always `{self_node_id}.json`, so passing a different `node_id` also deletes its own declaration. **The half that is fixed**: `announce` always writes content using `self_node_id`, so declarations where "the filename and the content node_id differ" are no longer produced (a warning is logged when `endpoint.node_id` does not match).
5. **Removal notifications infer identity from the filename**: `_handle_file_removed` takes `basename[:-5]` directly, so if a file is renamed or its content and filename disagree, `on_remove` points at the wrong `node_id` (whereas the add path goes by content).
6. **Hard neighbour deletion vs soft cooldown**: `on_remove` deletes the entry from `_neighbors` **immediately** (consistent with [DESIGN.md](/design): connection failure is a soft cooldown, declaration expiry is a hard clean-up). However, the cooldown timestamp `_unavailable` recorded for connection failures is **not** cleared by `on_remove`, so a node that "crashes → restarts quickly → is rediscovered" first hits one fast failure within `connect_backoff` (5 s), and that table only grows.
7. **Expiry timescales are tight**: `renew_interval=10 s`, `stale_after=30 s`, `poll_interval=30 s` mean that a single GC pause or scheduling starvation of more than 30 s makes a healthy node be misjudged as dead (false positive), while the disappearance delay upper bound for a genuinely dead node is 60 s. Cross-machine network-drive scenarios additionally add clock skew (the lease depends entirely on both sides' local clocks).
8. **The manual registry has no expiry mechanism** (**by design, not a defect**): `ManualAdvertise` does not renew and `ManualConnect` does not read `timestamp`, so entries never expire automatically — §3.4 and §10 explicitly require that implementations **MUST NOT** treat the manual registry's `timestamp` as a TTL; withdrawal relies on an explicit `withdraw`, and an announcer that crashes without withdrawing leaves zombie endpoints behind.
9. **The manual registry has no concurrency control**: the file carrier is read–modify–write, so two processes upserting at the same time lose updates; the HTTP carrier likewise has no `ETag`.
10. ~~**The file carrier is not robust to a bare filename**~~ ✅ **Fixed**: `makedirs` is called only when `dirname` is non-empty, so writing works normally when `source` is a bare filename.
11. **`list_endpoints()` returns duplicate endpoints**: when the same `node_id` appears in several sources, all of them are returned in source order, while the polling path deduplicates with "last source wins"; the two paths have inconsistent semantics.
12. **The abstract base class declares neither `stop()` nor `install_api`**: `Discovery` declares only `list_endpoints` / `watch`, and `stop()` and `install_api(node)` rest entirely on convention and duck typing; `DirectoryScan` / `DirectoryWrite` / `ManualAdvertise` do not implement `install_api`, so "change the announce target at runtime" currently has no hook.
13. ~~**The event watcher thread has no exception handling and suffers a stop race**~~ ✅ **Fixed**: the watcher's "register + start" is placed inside a `_lock` critical section, so `stop()` can only see either "not registered" (no leak) or "registered and started" (stoppable); a failed `schedule()` degrades to a warning (leaving only polling). Before the fix, `stop()` could miss an already-created non-daemon Observer thread, preventing the process from exiting.
14. **`stop()` does not wait for in-flight scans**: callbacks executing at the instant of stopping still arrive; after `ManualConnect.stop()` the polling thread lives at most another `poll_interval + 5 s` (HTTP timeout).
15. **`Endpoint.address_key()`'s return value requires hashable address values**: calling it does not throw (`sorted` only compares distinct keys), but using the return value as a `set` / `dict` key throws `TypeError` when `address` contains a nested `dict` / `list` (QUIC's `bootstrap` list-style address). The method currently has no call sites, so there is no actual trigger path.
16. **Declaration reads have no size limit**: `_read_declaration` reads the whole file with `json.load`, so an oversized file occupies the scan thread for a long time.
17. **DHT is not implemented**: there is no `dht` entry in `DISCOVERY_REGISTRY` / `PRESENCE_REGISTRY`.
18. ~~**A bad declaration makes the whole scan fail**~~ ✅ **Fixed**: the original implementation indexed `ep_data["transport_type"]` directly in three places, so a declaration missing a field threw `KeyError`, and the first full scan in `watch()` was outside a `try`, letting the exception pass straight through `node.start()` — **violating §6 "MUST NOT fail as a whole because a single declaration is corrupt"**. Everything now goes through `_endpoint_of()`, which validates the presence and type of `node_id` / `endpoint` / `transport_type` / `address` and skips entry by entry.
19. ~~**Bad declarations do not trigger hard clean-up**~~ ✅ **Fixed**: the event channel now treats a corrupt declaration as "the file has disappeared", satisfying §3.2 "a corrupt or expired declaration **MUST** trigger `on_remove`".
20. ~~**Valid JSON that is not an object / non-numeric `timestamp`**~~ ✅ **Fixed**: the former counts as corrupt (returns `None`; it previously threw `AttributeError`); the latter is treated as "no lease", the same rule as "a missing `timestamp` counts as never expiring".
21. ~~**Non-object entries in the manual registry**~~ ✅ **Fixed**: `ManualSource.read()` filters non-object elements and `ManualConnect._to_endpoint()` validates field types; previously `["x"]` made scanning and `upsert()` throw `AttributeError` (the two paths at the same layer were inconsistent in fault tolerance).
22. ~~**`Presence.announce`'s non-empty node_id MUST had no implementation**~~ ✅ **Fixed**: `require_node_id()` in `presence/base.py` fails fast (`ValueError`) in the `announce()` of `DirectoryWrite` / `ManualAdvertise`; previously `DirectoryWrite` wrote `"node_id": null` and `ManualAdvertise` silently substituted `self_node_id`.

## 10. Reference Implementation Map

| Provision / contract | Source file and symbol |
|---|---|
| `Discovery` abstract interface (`list_endpoints` / `watch`) | [discovery/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/base.py) `Discovery` |
| `Endpoint` fields and `address_key()` | [discovery/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/base.py) `Endpoint` |
| `Presence` abstract interface (`announce` / `withdraw` / default `update`) | [presence/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/presence/base.py) `Presence` |
| Declaration file path, `_declaration` fields, atomic write, renewal, withdraw; `_declaration_path` always uses `self_node_id` | [presence/directory.py](https://github.com/hxh230802/MSP/blob/master/src/msp/presence/directory.py) `DirectoryWrite` |
| Scanning, events + polling, hash deduplication, expiry decision | [discovery/directory.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/directory.py) `DirectoryScan._full_scan` / `_poll_loop` / `_read_declaration` |
| Event handler (implements created / modified / deleted only), removal events infer node_id from the filename | [discovery/directory.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/directory.py) `_DirectoryHandler` / `_handle_file_removed` |
| Manual discovery polling, `add_source`, `install_api` | [discovery/manual.py](https://github.com/hxh230802/MSP/blob/master/src/msp/discovery/manual.py) `ManualConnect` |
| Manual announce upsert / remove | [presence/manual.py](https://github.com/hxh230802/MSP/blob/master/src/msp/presence/manual.py) `ManualAdvertise` |
| `file://` / bare path / `http(s)://` carrier resolution, atomic writes, HTTP `GET` / `PUT` / `DELETE` with a 5 s timeout | [utils/manual_source.py](https://github.com/hxh230802/MSP/blob/master/src/msp/utils/manual_source.py) `ManualSource` |
| Registry names and component instantiation, `config` pass-through | [core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `DISCOVERY_REGISTRY` / `PRESENCE_REGISTRY` |
| `install_api` hook call site | [core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `_install_layer_api` |
| Discovery callbacks, neighbour table, `on_remove` hard delete, eager dialling, division of labour between soft cooldown and hard clean-up | [core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `_on_endpoint` / `_on_endpoint_removed` / `_eager_connect` / `_unavailable`, [DESIGN.md](/design) |
| Discovery / announce combinations in presets | [core/preset.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/preset.py) `Preset.OBSERVER` / `LOCAL_TOOL` / `MANUAL_PEER` |

Related pages: [transports.md](./transports.md) (consumer of `Endpoint`) · [base-protocol.md](./base-protocol.md) (handshake exchanges the manifest) · [security.md](./security.md) (trust boundary and authentication) · [architecture.md](./architecture.md) (layered architecture) · [patterns.md](./patterns.md) (another class of `install_api` users).
