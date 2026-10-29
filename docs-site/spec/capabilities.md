# MSP Specification — Capability Surface: resources / prompts / sampling / elicitation / roots

| | |
|---|---|
| **Specification revision** | `2026-10-10` |
| **Status** | 🔵 **Planned** — the messages are fully defined; the reference implementation has not landed |
| **Upstream basis** | [../DESIGN.md](/design) "Capability surface: resources / prompts / sampling", [../whitepaper.md](https://github.com/hxh230802/MSP/blob/master/docs/whitepaper.md) §5 |
| **What this page defines** | The complete mapping of the MCP capability surface (resources / prompts / sampling / elicitation / roots) onto MSP signals, the message shapes, the message flows, the attribution of errors and the security provisions |

This page translates the MCP capability surface beyond tools into MSP signals. Every provision is marked 🔵: an implementer **MAY** leave it unimplemented, but once implemented it **MUST** comply with the provision.

## 1. Overview

### 1.1 Scope

Beyond tools, MCP (Model Context Protocol) has five further groups of capabilities. Following "Everything is a signal" ([README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §4), they are not five mechanisms in MSP but several new groups of `Signal.type`:

| MCP capability | Problem it solves | Where it lands in MSP |
|---|---|---|
| resources | the peer exposes context data as URIs, and the local node reads it on demand | `resource_read` / `resource_content`; on the subscription side `resource_subscribe` / `resource_unsubscribe` / `resource_updated` |
| prompts | the peer predefines reusable prompt templates; the local node fetches one and the peer renders it | `prompt_get` / `prompt_content` |
| sampling | during execution the local node needs "some model to generate a passage" and sends a reverse request to the peer that holds the LLM | `sampling_request` / `sampling_result` |
| elicitation | the local node needs a user decision or input and asks the peer that holds the user interface | `elicitation_request` / `elicitation_result` |
| roots | a node unidirectionally declares the filesystem roots it allows to be accessed, so that peers can narrow their scope | `roots_list` / `roots` / `roots_changed` |

MCP's `*/list` round trips (`resources/list`, `prompts/list`, `resources/templates/list`) have **no** corresponding signal in MSP; see §2.2.

### 1.2 Relationship to the index and the envelope

This page defines a **planned new capability surface**: it belongs to **no** registered pattern (the pattern table in [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.2 remains unchanged) and it does not alter the core signal types already frozen in [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.1.

- **Signal naming**: the `type` values on this page are taken verbatim from the mapping table in [../DESIGN.md](/design) and are always bare snake_case; the `msp/` prefix is the namespace of **pattern IDs** and of pattern-private signal types ([README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §1.4, §5.3, [base-protocol](base-protocol.md) §2.2), and does **not** appear in the `type` values on this page.
- **Routing**: every signal on this page **carries no** `pattern` (`pattern = null`) and is handled by the default core dispatch of the protocol layer; the argument is in §3.1.
- **Relationship to `cancel` / `progress`**: the core already lists both as 🔵 planned core signals in [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.1 (provisions in [base-protocol](base-protocol.md) §6.3–6.4). This page does not redefine their messages; it states only two interactions: a requester **MAY** use `cancel` to cancel an in-flight `resource_read` / `sampling_request` / `elicitation_request` (correlated by the `reqid` of the cancelled request, cooperative, and it does not remove the obligation to reply); an executor **MAY** report progress with `progress` when the requester supplied `payload.progressToken`.
- **Difference from the index**: the signal types on this page have **not yet** entered the table in [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.1. Merging them into the core table **MUST** follow the evolution process of README §8 and add a new revision row; this page does not modify the index.

On receiving a signal type that this page does not recognise, an implementation **MUST NOT** drop the connection and **SHOULD** handle it by lenient reading as in [base-protocol](base-protocol.md) §2.3; the current behaviour of the reference implementation is to reply with `error` (`code = -32600`, see §9.1).

### 1.3 Content carriage

Resource contents, prompt messages and sampling results all reuse the content blocks of [../src/msp/core/content.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) (§5.1); no new data types are introduced.

## 2. Mapping and contract

### 2.1 MSP mapping table

The table below matches "MSP mapping: everything is a signal" in [../DESIGN.md](/design) row for row:

| MCP operation | MSP signal | Direction |
|---|---|---|
| `resources/read` | `resource_read` → `resource_content` | reader → resource holder, request / response |
| `resources/subscribe` | `resource_subscribe` / `resource_unsubscribe` → `resource_updated` | subscriber → resource holder, request; holder → subscriber, notification |
| `prompts/get` | `prompt_get` → `prompt_content` | caller → prompt holder, request / response |
| `sampling/createMessage` | `sampling_request` → `sampling_result` | generation requester → generation provider, reverse request / response |
| `elicitation/create` | `elicitation_request` → `elicitation_result` | asker → user host, reverse request / response |
| `roots/list` | `roots_list` → `roots` / `roots_changed` | inquirer → roots host, request / response; host → all connected peers, notification |

"Reverse" means the requester is the server role in MCP; MSP presets no roles, and the direction is decided by capability declarations (§2.3).

### 2.2 Trade-off 1: the manifest is the list, so the `list` round trip is dropped

MCP's "list what is there" is an extra round trip: `resources/list` (optionally paginated with `cursor`), `prompts/list`, `resources/templates/list`. MSP defines no such signals, because the manifest is itself the list: ① the `ResourceDescriptor` (`uri` / `name` / `description` / `mimeType` / `subscribable`) and `PromptDescriptor` (`name` / `description` / `arguments`) of `Manifest.resources` / `Manifest.prompts` **MUST** be exchanged with HELLO / ACK ([base-protocol](base-protocol.md) §4.4); ② when the manifest changes, `manifest_update` pushes the new manifest and the receiver discards stale entries by `version`; ③ "listing" is therefore a **by-product** of the handshake and the push. This page defines only **value-fetching** operations such as read / get; their input parameters (`uri` / `name`) **MUST** come from the peer's manifest, and the fetching side **SHOULD** validate them locally first, so that fetching requests are not used to probe the manifest.

Two corollaries: on receiving a `uri` / `name` that is not in the manifest, the holder **SHOULD** explain the failure in the `error` field of the response payload and **SHOULD NOT** treat it as a protocol error (§6.1); MCP's `resources/templates/list` (URI templates) has **no** counterpart — `ResourceDescriptor` has no template field, so when template semantics are needed an implementation **MUST** add manifest fields and a new revision number as in [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §8, and **MUST NOT** extend `uri` syntax on its own within this revision. Pagination is the same: manifest exchange in MSP has no `cursor` / `nextCursor`, and the full manifest **SHOULD** be given in one go (§9.3).

### 2.3 Trade-off 2: reverse capabilities are the natural advantage of full duplex

This expands item 2 of "three key trade-offs" in [../DESIGN.md](/design). In MCP, sampling / elicitation are "inverted" because of **roles**: `initialize` freezes the two ends into client and server, the client declares `sampling` / `elicitation` / `roots` in its own `capabilities`, and so "request a generation" and "ask the user" **MUST** be initiated by the server side and answered by the client side, with the capability bits attached to the client. MSP has no such role fixation: both sides can send signals proactively, and `sampling_request` is fully isomorphic to `tool_call` at the protocol layer — the same connection, the same `reqid` correlation mechanism ([base-protocol](base-protocol.md) §5), the same timeout rules; only `type`, direction and payload shape differ. Hence no "role flip" mechanism is needed, and there is no need to establish at handshake time who is the client; but capability bits are still required (§2.5), and one implementation **MAY** both provide tools (`rep`) and request generations (`clientCapabilities.sampling = true`).

Note: **direction is not the reason**. JSON-RPC 2.0 defines only the shape of a single message and does not restrict which side initiates; the difference between MSP and it lies in the envelope fields, not in direction (see [interop](interop.md#json-rpc-20-semantic-alignment)).

### 2.4 Trade-off 3: resource subscription and path filtering are two dimensions

This expands item 3 of "three key trade-offs" in [../DESIGN.md](/design). MSP already has publish/subscribe: `publish(path, payload)` fans `signal` out to all connected peers, and the receiver does local wildcard matching with `node.on(path)` ([patterns/publish-subscribe](patterns/publish-subscribe.md), [../src/msp/protocol/matcher.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/matcher.py)). A natural idea is to route resource changes the same way, so that "subscribe to a resource" degenerates into "subscribe to some path". This page does **not** adopt it, because the two are different dimensions: the addressing unit of path filtering is the path (dot-separated segments, domain first, [base-protocol](base-protocol.md) §2.4), the matching mode is sender broadcast plus local `*` / `**` filtering at the receiver, and the fan-out goes to all connected peers; the addressing unit of resource subscription is a URI (`file://`, `db://`, containing `/`, `:`, `.`), the matching mode is request-and-confirm point-to-point subscription with the holder maintaining a subscription table, and the fan-out goes only to the peers that subscribed to that URI.

Squeezing URIs into paths would stop the path from carrying "domain-first functional classification" and would require escapes for `/`, `:` and `.`, breaking the grammar of [base-protocol](base-protocol.md) §2.4 (`segment = 1*( ALPHA / DIGIT / "_" / "-" )`; neither `/` nor `:` is legal). Hence a separate `resource_subscribe`, addressed by URI. The two **MAY** coexist: the holder **MAY** additionally `publish` a path signal on a resource change for the benefit of bystanders, but `resource_updated` **MUST NOT** depend on it, and a subscriber **MUST NOT** substitute path filtering for a subscription declaration.

### 2.5 Capability declaration and authorization

A capability declaration is self-description ("what I claim I can do") and is strictly separated from authorization ("what I allow you to do") ([README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.5). Therefore: a provider **MUST** declare the resources it can serve and the prompts it can render in the `Manifest`, and a `uri` / `name` that is not declared **MUST NOT** be fetched successfully; a resource with `subscribable = false` **MUST NOT** be subscribed successfully; a declaration **MUST NOT** serve as a basis for authorization (a receiver **MUST NOT** relax local authorization because a peer declared some capability, and a sender **MUST NOT** assume that a peer will certainly respond because it declared `clientCapabilities.sampling = true`); on receiving a request for an undeclared capability bit, the receiver **SHOULD** reply with `error` (`code = -32601`, §6.2), isomorphic to "calling an unregistered tool". For authorization see [security](security.md).

## 3. Messages

### 3.1 Common rules

Every signal on this page uses the `Signal` envelope of [base-protocol](base-protocol.md) §2, and the field-level provisions on that page prevail. **`pattern` value**: the `pattern` of every signal on this page **MUST** be `null` (or absent), that is, they **belong to no pattern**. Reasons: ① the remedy in [../DESIGN.md](/design) is explicitly "add a branch to `_dispatch_core` (isomorphic to `tool_call`)", and `_dispatch` hands only signals **that carry a `pattern`** to pattern handlers ([../src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._dispatch`), with everything else going to `_dispatch_core`; [base-protocol](base-protocol.md) §2.1 also sets the default of `pattern` to `null`. ② The **declarations** of these five capability groups already live in `Manifest` (the `resources` / `prompts` descriptors and the three boolean bits of `clientCapabilities`), and introducing pattern IDs as well would declare the same thing in two places. ③ Each signal is a one-shot operation of fixed shape and does not constitute "a semantic set of one class of interaction" ([README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §4's definition of "pattern"); the precedent is `tool_call` / `tool_result` — they are core types, while `msp/multi-round` overrides routing with the **same** `type` plus a `pattern` when needed. ④ Therefore the signals on this page are neither the 9 core types of [base-protocol](base-protocol.md) §2.2 (8 rows in the index table, because `ping` / `pong` share one row) nor "pattern-private types" (the latter **MUST** carry a non-empty `pattern`), but **additional types** of a planned capability surface, given under the addition rule of [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §1.2 item 2.

The remaining common provisions:

- `source` **MUST** be the sender's own `node_id`; for `target`, requests and responses **MUST** carry the receiver's `node_id` (directed unicast), while `roots_changed` **MUST** be `null` (broadcast to all connected peers, consistent with `signal`). On receiving a signal whose `target` is non-empty and differs from its own `node_id`, the receiver **SHOULD** ignore it (the current core branch does not check `target`; this is a new provision).
- `path` **MUST** be `null`: the signals on this page **MUST NOT** carry a URI in `path`.
- `reqid`: requests and responses **MUST** carry it, and the `reqid` of a response **MUST** echo the request value unchanged; `reqid` **MUST** be a non-empty string unique to the sender within the lifetime of this connection; `resource_updated` (`event = "changed"`) and `roots_changed` are notifications and **MUST NOT** carry `reqid`. The classification rules match [base-protocol](base-protocol.md) §2.2: an empty `reqid` means a notification, and the receiver **MUST NOT** reply to it.
- A request **MAY** carry `payload.progressToken` (string), so that the executor can report progress with the core `progress` ([base-protocol](base-protocol.md) §6.4).

Signal summary (categories follow the trichotomy of [base-protocol](base-protocol.md) §2.2):

| `type` | Category | Has `reqid` | Direction |
|---|---|---|---|
| `resource_read` | request | yes | reader → resource holder |
| `resource_content` | response | yes | resource holder → reader |
| `resource_subscribe` / `resource_unsubscribe` | request | yes | subscriber → resource holder |
| `resource_updated` | response (`subscribed` / `unsubscribed`) / notification (`changed`) | the former yes, the latter no | resource holder → subscriber |
| `prompt_get` | request | yes | caller → prompt holder |
| `prompt_content` | response | yes | prompt holder → caller |
| `sampling_request` / `sampling_result` | request / response | yes | generation requester ↔ generation provider (reverse) |
| `elicitation_request` / `elicitation_result` | request / response | yes | asker ↔ user host (reverse) |
| `roots_list` / `roots` | request / response | yes | inquirer ↔ roots host |
| `roots_changed` | notification | no | roots host → all connected peers |

The wire format of one request (envelope field names as in [base-protocol](base-protocol.md) §2.1):

```json
{"type": "resource_read", "source": "agent_a", "pattern": null, "target": "file_monitor",
 "path": null, "reqid": "9f2c1ab34d5e6078", "payload": {"uri": "file:///tmp/report.md"},
 "timestamp": 1786000000.0}
```

### 3.2 `resource_read` / `resource_content`

| Signal | Field | Type | Required | Notes |
|---|---|---|---|---|
| `resource_read` | `payload.uri` | string | yes | **MUST** be a `ResourceDescriptor.uri` already declared in the peer's manifest |
| `resource_content` | `payload.uri` | string | yes | echoes the request's `uri` |
| `resource_content` | `payload.content` | array&lt;ContentBlock&gt; | yes | **MAY** be an empty array; block types see §5.1 |
| `resource_content` | `payload.mimeType` | string | no | **MAY** be omitted when it matches the `mimeType` of the manifest |
| `resource_content` | `payload.error` | string | no | non-empty means the read failed; in that case `content` **SHOULD** be an empty array |

Failure shape: `payload.error` non-empty (error as value, §6.1). Binary resources **SHOULD** be embedded with a `resource` block (small objects) or `blob_ref` (large objects, §5.2); bytes exceeding the receiver's buffer ceiling **MUST NOT** be inlined in `resource_content`.

### 3.3 `resource_subscribe` / `resource_unsubscribe` / `resource_updated`

Subscription and unsubscription are both requests; acceptance or rejection is confirmed with the **same** `resource_updated`, with `event` telling the three events apart, so that no signal type is added merely for an empty ACK.

| Signal | Field | Type | Required | Notes |
|---|---|---|---|---|
| `resource_subscribe` | `payload.uri` | string | yes | **MUST** point at a resource with `subscribable = true` |
| `resource_subscribe` | `payload.ttl` | number | no | subscription lifetime in seconds; absent means until the connection closes or an explicit unsubscribe |
| `resource_unsubscribe` | `payload.uri` | string | yes | unsubscribe target |
| `resource_updated` | `payload.uri` | string | yes | URI of the subscribed resource |
| `resource_updated` | `payload.event` | string | yes | `"subscribed"` / `"changed"` / `"unsubscribed"` |
| `resource_updated` | `payload.content` | array&lt;ContentBlock&gt; | depends on `event` | **MUST** be carried for `subscribed` and `changed`; **MUST NOT** be carried for `unsubscribed` |
| `resource_updated` | `payload.version` | integer | no | resource version, monotonically non-decreasing, used to detect reordering and loss |

The wire format of a confirmation and of a change (envelope as in §3.1):

```json
// subscription acknowledgement (response, reqid = the request's reqid)
{"type": "resource_updated", "source": "file_monitor", "target": "agent_a",
 "reqid": "5b1e77c0a9d34f21",
 "payload": {"uri": "file:///tmp/report.md", "event": "subscribed",
             "content": [{"type": "text", "text": "# Report\n..."}], "version": 7}}
// change notification (notification, reqid absent)
{"type": "resource_updated", "source": "file_monitor", "target": "agent_a",
 "payload": {"uri": "file:///tmp/report.md", "event": "changed",
             "content": [{"type": "text", "text": "# Report\n... (v8)"}], "version": 8}}
```

Provisions: when the holder accepts a subscription it **MUST** immediately reply with `event = "subscribed"` under the same `reqid`, serving as the confirmation and the initial snapshot, and when it rejects the subscription it **MUST** reply with `error` (§6.2) and **MUST NOT** stay silent; when it accepts an unsubscribe it **MUST** reply with `event = "unsubscribed"` under the same `reqid`, and afterwards it **MUST NOT** send that peer any further `resource_updated` for that `uri`; a change notification **MUST NOT** carry `reqid`, and when `version` is not monotonic the receiver **SHOULD** overwrite with the latest value and **MUST NOT** treat it as a protocol error; when a connection closes, all subscriptions on that connection **MUST** become void, and after reconnecting the peer **MUST** subscribe again (a subscription is connection-level state and is not exchanged with the `Manifest`); when `ttl` expires the holder **SHOULD** stop pushing and **MAY** stop silently; `ttl` **MUST NOT** be used as authorization.

### 3.4 `prompt_get` / `prompt_content`

| Signal | Field | Type | Required | Notes |
|---|---|---|---|---|
| `prompt_get` | `payload.name` | string | yes | **MUST** be a `PromptDescriptor.name` declared in `Manifest.prompts` |
| `prompt_get` | `payload.arguments` | object | no | keys are `PromptDescriptor.arguments[].name`, values are string |
| `prompt_content` | `payload.name` | string | yes | echoes the request's `name` |
| `prompt_content` | `payload.messages` | array&lt;object&gt; | yes | elements are `{"role": "user"\|"assistant", "content": ContentBlock}`; **MAY** be an empty array |
| `prompt_content` | `payload.description` / `payload.error` | string | no | rendered description (absent means the manifest value is used) / non-empty means rendering failed, in which case `messages` **SHOULD** be an empty array |

When `arguments` does not satisfy the parameters declared in the manifest, the holder **SHOULD** explain this in `error` (rather than as a protocol error). Rendering is the provider's responsibility, and the caller **MUST NOT** assume that the rendered result matches the manifest description word for word.

### 3.5 `sampling_request` / `sampling_result`

`sampling_request.payload` (field names align with MCP `sampling/createMessage`, to ease interoperability):

| Field | Type | Required | Notes |
|---|---|---|---|
| `messages` | array&lt;object&gt; | yes | elements are `{"role": "user"\|"assistant", "content": ContentBlock}` |
| `systemPrompt` | string | no | system prompt |
| `includeContext` | string | no | `"none"` / `"thisServer"` / `"allServers"` (MCP semantics; an implementation **MAY** ignore it and treat it as `"none"`) |
| `modelPreferences` | object | no | `{"hints": [{"name": string}], "costPriority", "speedPriority", "intelligencePriority"}`, priorities in the range 0~1 |
| `maxTokens` / `temperature` / `stopSequences` | integer / number / array&lt;string&gt; | no | generation ceiling, sampling temperature, stop sequences |
| `metadata` | object | no | implementation-defined metadata |
| `progressToken` | string | no | progress token (§3.1) |

`sampling_result.payload`: `role` (string, **MUST** be `"assistant"`), `content` (ContentBlock, a single block, consistent with MCP `CreateMessageResult.content`), `model` (string, identifier of the model actually used, so that the requester can account for it and reproduce the result), `stopReason` (string, optional, such as `"endTurn"` / `"maxTokens"`), `error` (string, optional, non-empty means the host refused or generation failed). When `error` is empty, `role` / `content` / `model` **MUST** be present; when `error` is non-empty, the three **SHOULD** be omitted. A host **MAY** refuse (quota, privacy, policy), but a refusal **MUST** be expressed through the `error` field or an `error` signal and **MUST NOT** be dropped silently.

### 3.6 `elicitation_request` / `elicitation_result`

| Signal | Field | Type | Required | Notes |
|---|---|---|---|---|
| `elicitation_request` | `payload.message` | string | yes | text of the question presented to the user; **MUST** be handled as untrusted input (§8) |
| `elicitation_request` | `payload.requestedSchema` | object | yes | restricted JSON Schema: `type` **MUST** be `"object"`; the values of `properties` **MUST** be primitive types or `enum`; `required` is an array of property names |
| `elicitation_result` | `payload.action` | string | yes | `"accept"` / `"decline"` / `"cancel"` |
| `elicitation_result` | `payload.content` | object | depends on `action` | **MUST** be present when `action = "accept"` and **MUST** satisfy `requestedSchema`; **MUST NOT** be carried for the other values |

`action = "decline"` / `"cancel"` is a **successful response**, not an error: the request was handled correctly, the user simply disagreed or withdrew the operation. A host **MUST NOT** send an `error` signal for these two values.

### 3.7 `roots_list` / `roots` / `roots_changed`

`roots_list.payload` is the empty object `{}` (reserved to carry future extensions). The `payload.roots` of `roots` and `roots_changed` **MUST** be an array whose elements are `{"uri": string, "name": string}`: `uri` **MUST** be an absolute URI, and `name` **MAY** be the empty string.

A note on direction: [../DESIGN.md](/design) labels that row as "client→server notification", which describes it in terms of the MCP client / server roles. MSP presets no roles ([README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §4), so this page uses a decidable formulation instead: the roots are held by **a node that declares `clientCapabilities.roots = true`** (hereafter the roots host); `roots_list` is sent to the host by any connected peer; `roots` and `roots_changed` are sent by the host. This matches the shape of "the server requests roots from the client" in MCP.

Provisions: the host **SHOULD** send one `roots_changed` proactively after accepting the handshake (no `reqid`, `target = null`); when the roots change it **MUST** send `roots_changed`; on receiving it the inquirer **SHOULD** overwrite its local cache with the latest value and **MUST NOT** drop the connection because `roots` and `roots_changed` disagree; on receiving `roots_list` while its own `clientCapabilities.roots = false` it **MUST** reply with `error` (`code = -32601`); `roots` **MUST NOT** be treated as access control — it is a **declaration**, not authorization, and a receiver **MUST NOT** conclude that a peer allows access to the remaining paths merely because some path is absent from `roots` ([README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.5).

## 4. Message flows

### 4.1 Resource subscription + change notification

```text
 agent_a (subscriber)                           file_monitor (resource holder)
   │ HELLO / ACK: exchange the Manifest       │
   │ ← resources[file:///tmp/report.md]       │
   │    .subscribable = true                  │
   │ ─ resource_subscribe ──────────────────▶ │ reqid=r1 {uri, ttl}
   │                                          │ register the subscription table
   │ ◀ resource_updated ───────────────────── │ reqid=r1 event=subscribed
   │   {uri, event:"subscribed", content:[…]} │ ack + initial snapshot
   │ (the file is written)                    │
   │ ◀ resource_updated ───────────────────── │ no reqid event=changed
   │   {uri, event:"changed", version:8}      │
   │ ─ resource_unsubscribe ────────────────▶ │ reqid=r2 {uri}
   │ ◀ resource_updated ───────────────────── │ reqid=r2 event=unsubscribed
   │ (no further update for this uri arrives) │
```

### 4.2 Reverse sampling request

```text
 worker (generation requester)                  llm_host (generation provider)
   │ HELLO / ACK: the Manifest carries        │
   │ clientCapabilities.sampling = true       │
   │ ─ sampling_request ────────────────────▶ │ reqid=s1
   │   {messages, systemPrompt, maxTokens}    │ handed to the local LLM
   │ ◀ sampling_result ────────────────────── │ reqid=s1
   │   {role:"assistant", content, model}     │
   │ (the host refuses: payload.error         │
   │  non-empty, or an error signal           │
   │  -32601)                                 │
   │ isomorphic to tool_call: the same        │
   │ connection, the same reqid               │
   │ correlation, the same timeout rules;     │
   │ only the direction is reversed.          │
```

### 4.3 Elicitation and cancellation

The message flow of `elicitation` is isomorphic to §4.2, only replacing `sampling_request` / `sampling_result` with `elicitation_request` / `elicitation_result`, and `action = "decline"` / `"cancel"` are successful responses. Their combination with the core `cancel` / `progress` ([base-protocol](base-protocol.md) §6.3–6.4) is as follows:

```text
 agent_a (requester)                            file_monitor (executor)
   │ ─ resource_read ───────────────────────▶ │ reqid=r3 {uri:"file:///big.bin",
   │                                          │ progressToken:"p-num-1"}
   │ ◀ progress ───────────────────────────── │ reqid=r3 (notification, MUST NOT be answered)
   │   {progressToken, progress:40, total:100}
   │ ─ cancel ──────────────────────────────▶ │ reqid=r3 {reason:"user cancelled"}
   │ ◀ resource_content ───────────────────── │ reqid=r3 terminal {uri, content:[],
   │                                          │ error:"cancelled"} — cancellation
   │                                          │ changes the result, not the
   │                                          │ obligation to reply
```

## 5. Data types

### 5.1 Content blocks

Resource contents, `prompt_content.messages[].content`, `sampling_request.messages[].content` and `sampling_result.content` **MUST** use the content block types already defined in [../src/msp/core/content.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py):

| `type` | Key fields | Purpose |
|---|---|---|
| `text` | `text` (required), `annotations` (optional) | text resources and prompts |
| `image` / `audio` | `data` (Base64, required), `mimeType` (required) | images / audio |
| `resource` | `resource: {uri, mimeType, text?, blob?}` | embedded text or binary resource |
| `resource_link` | `uri`, `name`, `mimeType`, `description` | a reference only; the receiver fetches the content itself |
| `blob_ref` | `blobId`, `mimeType`, `size`, `checksum` | MSP extension: points at a separate blob channel (§5.2) |

On encountering an unknown block type the receiver **MUST** preserve it unchanged (lenient reading, [base-protocol](base-protocol.md) §2.3; the behaviour of `block_from_dict()`) and **MUST NOT** treat it as a protocol error.

### 5.2 `blob_ref` and large objects

A `resource` block embeds bytes in the signal, which is bounded by transport framing and memory. A resource above an implementation-defined threshold (**SHOULD** be declared in the documentation, for example 1 MiB) **SHOULD** use `blob_ref` instead: `blob_ref` carries only `blobId` / `mimeType` / `size` / `checksum`, and the bytes travel on a separate blob signal stream (`msp/streaming`, planned, see [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.2); `checksum` **SHOULD** be the digest of the full content, and the receiver **SHOULD** verify it after retrieval; `blobId` **MUST** be unique within the current connection; on receiving a `blob_ref` without having implemented the blob channel, the receiver **SHOULD** reply with `resource_content.payload.error` explaining the failure and **MUST NOT** drop it silently.

### 5.3 Manifest declaration slots

| Declaration slot | Source form | Use on this page |
|---|---|---|
| `Manifest.resources` | `array<ResourceDescriptor>`, serialised key `resources` | the only source for "list what is there"; `subscribable` decides whether it can be subscribed |
| `Manifest.prompts` | `array<PromptDescriptor>`, serialised key `prompts` | as above; `arguments` describes the input parameters of `prompt_get` |
| `Manifest.clientCapabilities.sampling` | boolean, serialised key `clientCapabilities.sampling` | whether `sampling_request` is accepted |
| `Manifest.clientCapabilities.elicitation` | boolean, serialised key `clientCapabilities.elicitation` | whether `elicitation_request` is accepted |
| `Manifest.clientCapabilities.roots` | boolean, serialised key `clientCapabilities.roots` | whether the node holds and announces roots |

These three client capability bits already exist in the source (`supports_sampling` / `supports_elicitation` / `supports_roots`, serialised as `clientCapabilities`), but the "role capability bits" table in [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.5 lists only `pub` / `sub` / `req` / `rep` and does **not** include them. This page therefore records the three as "declaration slots that already exist in the source", and does **not** modify the index, nor squeeze new semantics into `pub`/`sub`/`req`/`rep` (the difference is in §9.3).

## 6. Error handling

### 6.1 Two failure channels

Following [base-protocol](base-protocol.md) §6.1: **error as value** means the request has been parsed correctly and routed to the right provider, and a business-level failure (a URI that does not exist, a resource that cannot be subscribed, a prompt name that does not exist, parameters that do not satisfy the declaration, a failed generation) puts a string in the `payload.error` of the **response signal**, with `reqid` unchanged, and **MUST NOT** send an `error` signal as well; a **protocol-layer failure** (an unimplemented signal, a missing `reqid`, a `payload` that is not an object, an undeclared capability bit) sends an `error` signal whose `payload` is `{"code": <int>, "message": <string>}` ([base-protocol](base-protocol.md) §6.2). An `elicitation_result.action` of `decline` / `cancel` counts as success and **MUST NOT** take either failure channel (§3.6).

### 6.2 Attribution of error codes

| Failure | Channel | `code` / field |
|---|---|---|
| An unimplemented capability-surface signal type is received, or `reqid` is missing, or `payload` is not an object | `error` signal | `-32600` |
| This node does not declare the capability (the manifest has no `resources` / `prompts`, or the corresponding `clientCapabilities` bit is `false`) | `error` signal | `-32601` (isomorphic to "calling an unregistered tool") |
| `uri` / `name` is not in the peer's manifest, or the resource has `subscribable = false` | response payload `error` | no `code` |
| `prompt_get.arguments` does not satisfy `PromptDescriptor.arguments`, or `elicitation_result.content` does not satisfy `requestedSchema` | response payload `error` | no `code` |
| The provider throws an unexpected exception while rendering / generating the response | `error` signal | `-32603` |
| No response within the timeout | local timeout (implementation-defined exception) | **MUST NOT** send `error` |
| `target` is non-empty and is not this node | ignore and log | **MUST NOT** reply with `error` (to avoid a loop) |
| A `cancel` with an unknown `reqid` is received | ignore silently ([base-protocol](base-protocol.md) §6.3) | — |

`-32000` ~ `-32099` are reserved for the pattern layer ([README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.4). The signals on this page carry no `pattern` and **MUST NOT** use that range; an `error` in that range **SHOULD** be passed through to the upper layer unchanged rather than rewritten (see the bridge downgrade strategy in [interop](interop.md)).

### 6.3 Timeouts, cancellation and progress

Unless stated explicitly, the requester **SHOULD** use the default timeout of `call`, `5.0` s ([README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.6); `sampling_request` and `elicitation_request` depend on a model or a person and **SHOULD** use a longer timeout, but this page does **not** freeze that value (`ctx.ask()` of `msp/multi-round` uses `30.0` s as a reference; it is not in the frozen default parameter table of [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.6, and an implementation **MAY** define its own). After a timeout the requester **MUST** discard a late response for that `reqid` and **MUST NOT** take it as the result of the next request; the specification has **no** notion of a server-side deadline ([base-protocol](base-protocol.md) §6.5), so the executor **need not** know that the caller has given up. Explicit cancellation **MUST** use the core `cancel` signal (cooperative, correlated by the `reqid` of the cancelled request, and a terminal response **MUST** still be sent after it arrives); the signals on this page **MUST NOT** define their own cancellation messages, and cancellation in `msp/task` goes through the pattern's own `task_cancel`. When a request carries `payload.progressToken` the executor **MAY** report progress with the core `progress` and **MUST NOT** treat `progress` as reliable transport.

### 6.4 Relationship to `msp/multi-round`

`elicitation_request` / `elicitation_result` and `input_required` / `input_response` of `msp/multi-round` can both achieve a "follow-up question", but their semantics differ (per-signal differences are also in [patterns/multi-round](patterns/multi-round.md) §6.8):

| | `msp/multi-round` | `elicitation_request` |
|---|---|---|
| Request identity | **MUST** reuse the `reqid` of the original `tool_call`; the whole interaction uses one `reqid` | opens a `reqid` of its own; the original call is not continued |
| Where it is triggered | only while one tool call is executing (`ctx.ask()`) | at any time, including when no tool call is in progress |
| Precondition | the peer **MUST** have the `msp/multi-round` pattern active (the `pattern` field) | the peer **MUST** declare `clientCapabilities.elicitation = true` |
| Payload | `{"prompt": string}` / `{"answer": arbitrary JSON}` | `{message, requestedSchema}` / `{action, content}`; `content` can be checked by a machine |
| Where it is declared | `Manifest.patterns` | `Manifest.clientCapabilities.elicitation` |

Basis for the choice: when a follow-up question is about "**this one tool call** missing a parameter", `msp/multi-round` **SHOULD** be used (the same `reqid`, the caller has an `input_fn` taking part, and the fallback target on failure is `msp/request-reply`); when a question needs to be put to the user **outside a tool call** (policy confirmation before execution, choosing the scope of resources), or the peer has not activated `msp/multi-round`, `elicitation_request` **SHOULD** be used; when the answer needs to be structured and checkable, `elicitation_request` **SHOULD** be used (`content` is constrained by `requestedSchema`, whereas the `answer` of multi-round is merely arbitrary JSON); when content needs to be **generated** by a model rather than a question put to a person, both **MUST NOT** be used and `sampling_request` **MUST** be used.

## 7. Summary of normative provisions (MUST/SHOULD list)

**MUST**: ① the `pattern` of every signal is `null`, `source` is the sender's `node_id`, requests and responses carry `reqid` and a response echoes it unchanged (§3.1); ② the `uri` of `resource_read` comes from the peer's manifest, and `resource_content` carries `uri` and `content` (§3.2); ③ an accepted subscription is answered immediately with `event = "subscribed"` and the initial snapshot, and a rejected one with `error` (§3.3); ④ an accepted unsubscribe is answered with `event = "unsubscribed"`, after which nothing more is pushed for that URI (§3.3); ⑤ a `resource_updated` with `event = "changed"` and a `roots_changed` carry no `reqid`, and `unsubscribed` carries no `content` (§3.1, §3.3); ⑥ when a connection closes, all subscriptions on that connection become void, and the peer resubscribes after reconnecting (§3.3); ⑦ on receiving `roots_list` while its own `clientCapabilities.roots = false`, reply with `-32601` (§3.7); ⑧ the `type` of `requestedSchema` is `"object"` and the values of `properties` are primitive types or `enum` (§3.6); ⑨ a capability-surface failure takes the corresponding channel per §6.1, and the two channels **MUST NOT** be used together; ⑩ unknown block types and unrecognised signal types **MUST NOT** be treated as protocol errors or cause a disconnect (§5.1, §1.2); ⑪ cancellation uses the core `cancel`, and a terminal response is still sent after it arrives (§6.3).

**SHOULD**: ⑫ validate locally whether `uri` / `name` is in the peer's manifest before fetching (§2.2); ⑬ the `checksum` of `blob_ref` is present and verified after retrieval, and the large-object threshold is declared in the implementation's documentation (§5.2); ⑭ the timeout of sampling / elicitation is longer than the default of `call`, and a late response is discarded after a timeout (§6.3); ⑮ the roots host sends one `roots_changed` proactively after the handshake (§3.7).

**MUST NOT**: ⑯ carry a URI in `path` (§3.1); ⑰ treat `roots` or `ResourceDescriptor.subscribable` as a basis for authorization (§2.5, §3.7); ⑱ use the `-32000` ~ `-32099` error-code range (§6.2); ⑲ use payload fields such as `ttl` / `maxTokens` for access control (§3.3).

**MAY**: ⑳ publish an extra path signal when a resource changes, but `resource_updated` **MUST NOT** depend on it (§2.4); ㉑ ignore `includeContext` and treat it as `"none"` (§3.5); ㉒ stop pushing silently when `ttl` expires (§3.3); ㉓ a request carries `payload.progressToken` and the executor reports progress with `progress` (§3.1, §6.3).

## 8. Security considerations

The trust boundary is the reachable range of the transport; authentication is not authorization ([security](security.md)).

1. **Data exfiltration surface**: `resource_read` and `resource_subscribe` let a peer obtain local data continuously or on demand. The provider **MUST** decide at the authorization layer by URI prefix and **MUST NOT** rely only on the manifest declaration (the manifest is self-description); a subscription is a **continuous** data stream, so the default `ttl` **SHOULD** be short and permit immediate unsubscribe.
2. **Prompt injection surface**: the text of `prompt_content.messages` enters the requester's model context; the requester **SHOULD** label it as external untrusted content and **MUST NOT** execute it as a system instruction.
3. **Reverse generation surface**: `sampling_request` sends **the peer's prompts** into the local LLM, which carries the risk of prompt injection and quota abuse. The host **MUST** be able to refuse and **SHOULD** decide policy by source node; the host **MUST NOT** relax policy because of an identity that `source` reports about itself ([README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.5).
4. **Human-facing elicitation surface**: `elicitation_request.message` is external untrusted text, and the host **MUST** state the source `sig.source` when presenting it; `requestedSchema` **MUST NOT** be used to construct executable actions (for example "enter the command to execute"), and **SHOULD** be used only for structured choices.
5. **Misuse of roots and of the fan-out surface**: any implementation that treats `roots` as a whitelist or a blacklist departs from the provisions of §3.7; `roots_changed` is broadcast to all connected peers and the subscription table is maintained per peer, and both carry an amplification risk. An implementation **SHOULD** set ceilings on the number of subscriptions, the size of a single `content`, and the number of pushes per unit time, and when a ceiling is exceeded it **SHOULD** reply with `error` rather than degrade silently.

## 9. Known gaps

### 9.1 Current state

The current state **MUST** be stated plainly: `Manifest` already declares the "bits" of these capabilities, but the protocol layer has no corresponding operation, so a peer that receives the manifest **sees a promise it cannot use**.

| Fact | Source location |
|---|---|
| The `Manifest.resources` / `Manifest.prompts` fields and `add_resource()` / `add_prompt()` already exist and are exchanged with `to_dict()` | [../src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `ResourceDescriptor` / `PromptDescriptor` / `Manifest.add_resource` / `Manifest.add_prompt` / `Manifest.to_dict` |
| The client capability bits already exist and are serialised as `clientCapabilities` | same as above, `Manifest.supports_sampling` / `supports_elicitation` / `supports_roots` |
| Manifest push and diffing are already available | [../src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol.push_manifest()` / `_on_manifest_update()`; the diff `Manifest.diff()` / `Manifest.apply_diff()` is written but unused by the protocol layer |
| **No** signal type from this page exists | [../src/msp/core/signal.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/signal.py) `SignalType` has only `hello` / `ack` / `signal` / `tool_call` / `tool_result` / `manifest_update` / `ping` / `pong` / `error` |
| **No** dispatch branch from this page exists | [../src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._dispatch_core()` has no matching `elif`; signals from this page fall to `else` and are answered with `error` (`-32600` "unknown signal type") |
| **No** node-layer API exists | [../src/msp/core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) has no `resource()` / `prompt()` / `sample()` / `elicit()` / `roots()`, only `tool()` / `on()` / `publish()` / `call()` |
| The signals on this page have **not yet** entered the core signal type table of [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.1 | the index §5.1 currently holds only the 9 implemented core types (8 rows in the table) plus the 🔵 `cancel` / `progress` |

### 9.2 How to close the gaps

1. Append to `SignalType` the 14 type names listed in the summary table of §3.1 (matching the number of entries in the single authoritative source `schema/2026-10-10/msp.yaml`).
2. Append branches to `MSPProtocol._dispatch_core()`, **isomorphic** to `tool_call` / `tool_result`: the request branch parses `payload` and correlates by `reqid`, and the response branch wakes the waiting side. Every operation that may take time (resource read, prompt rendering, model generation, asking a person) **MUST** run in a separate thread and **MUST NOT** run synchronously in the read-loop thread — for the same reason as the comment in `MSPProtocol._on_tool_call()`: a slow operation blocks message reception on that connection, and if the operation calls back into the peer internally, it deadlocks.
3. Append decorators and methods at the `MSPNode` layer: `@node.resource(uri, ...)`, `@node.prompt(name, ...)`, `node.read_resource(peer, uri)`, `node.get_prompt(peer, name, arguments)`, `node.subscribe_resource(peer, uri)`, `node.sample(peer, ...)`, `node.elicit(peer, ...)`, `node.set_roots([...])`, and on the receiving side `node.on_resource_updated(...)`. These names are a **planned API** and do not constitute normative constants; the provisions constrain only the message shapes of §3.
4. Reuse existing facilities, invent nothing new: content blocks use `core/content.py` and `block_from_dict()`; result normalisation can reuse `_normalize_tool_result()`; the wait / wake structure of request–reply can follow `_pending_calls` / `_active_asks` of `MultiRoundHandler`; cancellation and progress reuse the core `cancel` / `progress` directly ([base-protocol](base-protocol.md) §6.3–6.4), and **MUST NOT** build a second set for the capability surface.

### 9.3 Gap list

| # | Gap | Status | Impact |
|---|---|---|---|
| 1 | no signal on this page exists in the reference implementation; one is answered with `-32600` as soon as it arrives | 🔵 | the manifest has announced it, the operation is unusable (§9.1) |
| 2 | the signal types on this page have not entered the core signal table of [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.1 | index gap | merging into the core table **MUST** follow README §8; this page does not modify the index |
| 3 | the three `clientCapabilities` bits are not in the frozen capability-bit table of [README](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) §5.5 | index gap | this page records them only as declaration slots that already exist in the source, and does not modify the index |
| 4 | no counterpart for URI templates (MCP `resources/templates/list`) | 🔵 | dynamic URIs need the specification evolution process (§2.2) |
| 5 | manifest exchange has no pagination | 🔵 | at large scale a single `manifest_update` is very big; `Manifest.diff()` is written, but `push_manifest()` sends the **full manifest** and the protocol layer does not use it for incrementality |
| 6 | subscriptions and roots are both connection-level state; and there is no server-side deadline | design choice / 🔵 | after a reconnect the peer **MUST** subscribe again; after the caller times out the executor need not know, and can only stop cooperatively through `cancel` ([base-protocol](base-protocol.md) §6.5) |
| 7 | the blob channel (`msp/streaming`) is planned | 🔵 | `blob_ref` can only point at a channel that has not landed yet |
| 8 | the MCP adapter implements only stdio + tools | 🔵 | there is no converter yet between MCP resources / prompts / sampling and the signals on this page (see [interop](interop.md)) |

## 10. Reference implementation map

| Provision | Status | Source file and symbols |
|---|---|---|
| §2.1 mapping table, all messages in §3 | 🔵 not implemented | the planned landing points are `SignalType` in `src/msp/core/signal.py` and `MSPProtocol._dispatch_core` in `src/msp/protocol/protocol.py` |
| §3.1 envelope fields; `pattern = null` takes the default dispatch, an unknown signal is answered with `-32600`, `target` is currently not checked; directed send and broadcast | ✅ / 🔵 | [../src/msp/core/signal.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/signal.py) `Signal` / `Signal.make` / `Signal.to_dict` / `Signal.from_dict` / `Signal.new_reqid`; [../src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._dispatch` (step 3), the `else` branch of `_dispatch_core`, `_reply_error`, `_send`, `publish` |
| §5.1 content blocks and result normalisation (reusable) | ✅ | [../src/msp/core/content.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/content.py) `TextContent` / `ImageContent` / `AudioContent` / `EmbeddedResource` / `ResourceLink` / `BlobRef` / `block_from_dict` / `blocks_from_list`; `_normalize_tool_result` |
| §5.2 `blob_ref` and the blob channel | 🔵 | `BlobRef` as above; the blob channel is not implemented |
| §5.3 manifest declaration slots | ✅ (declaration and exchange only) | [../src/msp/core/manifest.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/manifest.py) `ResourceDescriptor` / `PromptDescriptor` / `Manifest.add_resource` / `add_prompt` / `to_dict` (`clientCapabilities`) / `from_dict` |
| §2.2 manifest push and version filtering / manifest diffing | ✅ / 🟡 | `MSPProtocol.push_manifest` / `_on_manifest_update`; `Manifest.diff` / `apply_diff` (unused by the protocol layer) |
| §2.4 path wildcard filtering | ✅ | [../src/msp/protocol/matcher.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/matcher.py) `pattern_matches`; [../src/msp/core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `MSPNode.on` |
| §6.3 worker-thread execution, cancellation / progress; §6.4 follow-up on the same `reqid` | ✅ reusable / 🔵 | `MSPProtocol._on_tool_call` / `_run_tool`; [../src/msp/patterns/multi_round.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/multi_round.py) `MultiRoundHandler._run_tool` / `INPUT_REQUIRED` / `INPUT_RESPONSE` / `RoundContext.ask` / `call_multiround`; for `cancel` / `progress` see [base-protocol](base-protocol.md) §6.3–6.4 |
| §9.2 node-layer API | 🔵 not implemented | [../src/msp/core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) currently has `tool` / `on` / `publish` / `call` / `pattern` |
