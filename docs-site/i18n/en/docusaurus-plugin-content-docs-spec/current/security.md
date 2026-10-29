# MSP Security Model — Trust Boundary, Node Authentication and Authorization

| | |
|---|---|
| **Protocol revision** | `2026-10-10` |
| **Status** | 🟡 Partially implemented |
| **Defined on this page** | The rules for determining the trust boundary, the threat model, the TLS / node authentication / identity binding required for a cross-machine deployment, and the complete semantics and enforcement points of the authorization table `grants` |

> The definitions of the normative terms (**MUST** / **MUST NOT** / **SHOULD** / **SHOULD NOT** / **MAY**) and of the status markers (✅ implemented / 🟡 partially implemented / 🔵 planned) are in [Specification index §2](index.md#2-normative-language). Bold keywords in the body text carry normative force.

**Status distribution on this page**: the trust boundary = the reachable extent of the transport, which is the **factual posture of the current implementation** (✅); TLS, node authentication, identity binding and the authorization table are all 🔵 **planned** — the design is final, implementation is to be scheduled. For the planned provisions, "**an implementer MAY leave them unimplemented, but once implemented they MUST comply with the provisions**" ([README §7](index.md#7-conformance), item 6).


## 1. Overview

### 1.1 Core conclusion

> **The trust boundary is the reachable extent of the transport — whoever can connect in is inside the trust domain.**

Three corollaries:

1. The protocol layer therefore **MUST NOT** make TLS / authentication / authorization a default check carried by every message; security is decided by the **deployment shape**, not by each individual message.
2. Beyond "connected" there are two further layers: **authentication** (who you are) and **authorization** (what you may do). Neither can substitute for the other.
3. A security feature that cannot actually deliver security is more dangerous than none at all. This specification therefore **MUST NOT** make a false default security promise; conversely, as long as the declared boundary matches the implementation, **not implementing** the extension security mechanisms is conformant ([README §7](index.md#7-conformance), item 6).

The current reference implementation holds exactly this posture: no authentication or authorization code at all, and a successful connection is treated as a trusted peer (✅); every remaining mechanism on this page is 🔵 planned.

### 1.2 One-line comparison table

| Deployment shape | Trust boundary | What is needed |
|---|---|---|
| localhost self-organising network | The same OS user | No TLS / authentication / authorization |
| Cross-machine / public network | The reachable extent of the network | TLS + node authentication + authorization (by default only the reply channel is left open) |

> **Security is a deployment decision, not a protocol default.** MSP therefore chooses to state the boundary plainly, rather than make a false default security promise.


## 2. Model and contract

### 2.1 Authentication ≠ authorization

| | Question | Means | Limitation |
|---|---|---|---|
| **Authentication** | Who you are | Certificate / key | Can only prove "you are `node_b`" |
| **Authorization** | What you may do | Local policy table (`grants`) | Decides "whether `node_b` may call the `rm -rf` tool" |

A certificate **cannot** prove that `node_b` is entitled to call a particular dangerous tool: a trustworthy identity and trustworthy behaviour are two different things. **Passing authentication** only means "this connection really comes from `node_b`", and it **MUST NOT** be taken as grounds for "`node_b` may do anything"; conversely, the absence of authentication **MUST NOT** serve as an excuse for missing authorization either — the two **MUST** be configured independently and take effect independently.

### 2.2 Threat model

| Attacker | What they can do | Countermeasure |
|---|---|---|
| An eavesdropper / tamperer on the link | Read, modify and replay messages | TLS (§2.4.1) |
| A node that connects without authenticating | Impersonate any `node_id`, slip into discovery, disturb deduplication, freeload on broadcasts | Node authentication (§2.4.2) |
| An authenticated but untrusted node | Call tools that were not opened up, trigger side effects with `publish`, pry into broadcasts | Authorization (§3) |

The three classes of attacker are not parallel options but a depth relationship: TLS is needed only on an **untrusted link**; node authentication is needed only when **a peer outside the same trust domain is present**; authorization is needed as soon as a peer has connected in. **Being authenticated** only raises the cost of impersonation and does **not reduce** the necessity of any single authorization check.

### 2.3 Local self-organising network: why there is no authentication

The first class of scenario MSP targets is the **local self-organising network**: a group of processes / nodes on the same machine interconnected over localhost, each organising itself independently, sharing the discovery registry and broadcasting to one another. In this shape authentication is **meaningless**, because every node has the **same permission set**:

- All nodes run under the **same OS user**, so their reachable permissions on the file system, network ports, environment variables and process signals are exactly the same;
- Whatever one node can read, call or write, another node can equally read, call and write;
- An encrypted channel (TLS) protects confidentiality "in transit", while the localhost loopback **does not pass through an untrusted network segment**, so there is no man in the middle to intercept.

> **Authenticating a peer with the same permissions as yourself is authenticating yourself** — it adds no real security benefit, only handshake complexity and deployment cost.

The same reasoning applies to authorization: under the same OS user, "allowing `node_b` to read a certain file" confers no extra protection, because `node_b` can read it directly anyway. **The whole authorization table is therefore bypassed for local peers, with full trust** (see §3.5).

**Boundary conditions** (where this conclusion lapses): crossing OS users, container / sandbox isolation, virtualisation boundaries, and scenarios in which SSH forwarding or a proxy disguises remote traffic as loopback. In these shapes the premise "the permission sets are equal" does not hold, so they **MUST** be handled as cross-machine (§2.4).

### 2.4 Cross-machine: security follows the transport

**Status**: 🔵 planned (the design is final, implementation is to be scheduled).

Cross-machine exposure is a mode that is **explicitly enabled and off by default**: by default a node listens on localhost only (✅ fact), and whoever wants to go cross-machine listens on `0.0.0.0` themselves and configures all four items of this section at the same time. The security model is one where security "**follows the transport**" rather than "follows the protocol": when the trust boundary widens from the same OS user to the reachable extent of the network, the four items **MUST** be added **above the transport layer, with the protocol core untouched**; for the provisions below, **an implementer MAY leave them unimplemented, but once implemented they MUST comply with the provisions**.

#### 2.4.1 TLS

- TLS **MUST** be implemented by "wrapping `Transport` / `Connection`": the protocol layer only calls `Connection.send` / `receive`, so once wrapped in TLS there **MUST NOT** be any required change to `core` or the protocol layer.
- The client **MUST** verify the certificate chain and the host name (`hostname` verification); it **MUST NOT** bring `CERT_NONE` / verification-skipping debug switches into a production configuration.
- The server **SHOULD** require and verify client certificates (i.e. mTLS), used together with the first option in §2.4.2.
- The transport address forms extend accordingly: `ws://` for WebSocket corresponds to `wss://`, and bare TCP corresponds to `tls://` or a TLS mode explicitly enabled by the transport wrapper (🔵; for the concrete address forms see [transports.md](./transports.md)). The current `WebSocketTransport` accepts `ws://` only (`_parse_url` rejects other prefixes).

#### 2.4.2 Node authentication

Once a connection is established, the peer's identity **MUST** be verified, to prevent unauthorized nodes from slipping into the discovery registry or listening in on sensitive namespaces. Two options:

| Option | Mechanism | Applies to | Cost |
|---|---|---|---|
| **mTLS** | Certificate CN / SAN = `node_id`, mutual verification | Data centres that already have a PKI | Needs a certificate issuance and rotation process |
| **Signed HELLO** | An Ed25519 private key signs the node's own manifest, `node_id` bound to the public key, explicit pin / TOFU + manual confirmation | P2P, no PKI required | Needs key distribution and first-connection confirmation |

**The default preference is signed HELLO**: it fits P2P better, removes the burden of a PKI, and naturally overlaps with MSP's existing handshake of "a node describes its own capability manifest" — the signed object is the manifest itself, so no additional certificate semantics are needed.

**Message definition for signed HELLO** (fields in §5.2):

1. The initiator carries `scheme="ed25519"`, `nodeId`, `publicKey`, `nonce`, `timestamp` and `signature` in the `payload.auth` of `hello`.
2. The acceptor **MUST** **counter-sign** its own manifest (the same fields and signing rules) in the `payload.auth` of `ack`, making authentication **mutual**; an implementation that authenticates only one side is not regarded as conforming to this section in this specification.
3. **Signature coverage**: the signed object is the byte string below, and the receiver **MUST** reconstruct it in exactly the same canonical form (sorted keys, no extra whitespace, UTF-8):

   ```text
   signing_bytes = utf8(json.dumps(
       {"manifest": <payload.manifest>, "nodeId": <payload.auth.nodeId>,
        "nonce": <payload.auth.nonce>, "timestamp": <payload.auth.timestamp>},
       sort_keys=True, separators=(",", ":"), ensure_ascii=False))
   ```

    That is: the signature **covers the whole of the manifest**, preventing a man in the middle from tampering with the capability declaration after the handshake; `nodeId`, `nonce` and `timestamp` are signed alongside, preventing field substitution and replay.
4. **Replay protection**: `nonce` **MUST** be an unpredictable random value of at least 16 bytes (hex-encoded); `timestamp` is Unix seconds, and the receiver **MUST** reject messages that deviate from the local clock by more than **±60 s**; within the time window the receiver **MUST** cache `nonce` values already seen and reject repeats. A `nonce` cache beyond the time window **MAY** be discarded.
5. **TOFU storage**: on first seeing the public key of a `node_id`, it **SHOULD** be recorded per Trust On First Use and marked unconfirmed, and **SHOULD** require manual confirmation before being accepted (or be rejected outright under the deployment policy, fail-closed). When a confirmed `node_id` record receives a **different public key**, it **MUST** reject the connection and raise an alarm — this is the detection point for a key-substitution (impersonation) attack. For the storage shape see §5.3.

#### 2.4.3 Identity binding

- The `node_id` declared in `hello` (`Signal.source`) **MUST** coincide with the TLS certificate identity or the signing-key identity; on a mismatch, disconnect.
- Verification **MUST** take place **before the connection is registered**: a connection that fails identity binding **MUST NOT** enter `connections`, **MUST NOT** be written into `peer_manifests`, and **MUST NOT** produce discovery events.
- Not binding leads to two kinds of damage:
  1. **Discovery registry poisoning**: declaration files are named by `node_id`, and the scanning side uses `_known[node_id]` as the deduplication key. An impersonator can overwrite another party's declaration with that party's `node_id`, steering peer traffic to its own address, or causing the real node to be judged "declaration unchanged" and so never refreshed.
  2. **Deduplication disorder**: the "canonical direction" of duplicate-connection deduplication is decided by the lexicographic order of `node_id` (the side with `self.node_id < peer_id` is the initiator). By picking `node_id` freely, an impersonator can make the canonical direction flip back and forth between two connections, producing continuous reconnection and state flapping.

#### 2.4.4 Authorization

See §3.


## 3. Authorization

> **Status**: ✅ implemented (`src/msp/core/grants.py`). The two enforcement points are `MSPProtocol.authorized()` (inbound, the first statement of `_dispatch`) and `grant_sub()` (outbound fan-out). This section defines the authorization table `grants`.

### 3.1 Authorization is separate from capability

The capability bits (`pub` / `sub` / `req` / `rep`) live in the `Manifest` and are "**what I claim I can do**"; authorization lives in the **local policy** (landing point in §3.2) and is "**what I allow the peer to do**" ([README §5.5](index.md#55-role-capability-bits)).

- Authorization **MUST NOT** depend on what the peer reports: writing `capabilities` as `["pub","sub","req","rep"]` confers no permission at all.
- Authorization **MUST NOT** be exchanged with the manifest: `grants` is local policy, **MUST NOT** appear in any field of the `Manifest`, and **MUST NOT** be updated by `manifest_update`.
- Peer capability bits **MAY** be used for local optimisation (for example, knowing that a peer does not support `msp/task` means there is no point in trying), but **MUST NOT** be used for authorization decisions.

### 3.2 Where the authorization table is declared

The authorization table is **local policy**, injected when the node is constructed, and **MUST NOT** appear in any field of the `Manifest`. **There are only three normative requirements**: local policy, not in the manifest, and not influenced by what the peer reports about itself; **the landing point is the implementation's choice** — the reference implementation puts it in the node configuration `config["grants"]` (`node.py` → `MSPProtocol(grants=...)`), and putting it in a node role preset (in `Preset` style) is equally conformant.

Parsing **MUST** fail closed: if the configuration cannot be understood, the node **SHOULD** be made unable to start, and it **MUST NOT** be handled as "if unreadable, let it through"; the sole exception is the whole table being absent — that is handled by the default posture of §3.5 (deny everything + the `rep` channel).

```python
# Local policy (not exchanged with the manifest)
grants = {
    # Any peer not listed: by default only the reply channel is left open
    "*":      {"req": [],            "pub": False, "sub": False, "rep": True},
    # Per-peer override
    "node_b": {"req": True,          "pub": ["notify.**"], "sub": ["metric.**"], "rep": True},
    "node_c": {"req": ["read_file"], "pub": False, "sub": False, "rep": True},
}
```

Lookup rule: first match the peer's `node_id` exactly and use that entry if it hits; otherwise fall back to `"*"`. If `"*"` is absent too, it **MUST** be treated as deny-everything (`req=[]`, `pub=False`, `sub=False`, `rep=True`, i.e. the default posture of §3.5), and **MUST NOT** be treated as allow-everything. A per-peer override is a **whole-entry replacement**, not a field-by-field merge: when `node_c` omits `rep`, `rep` takes that entry's own default value, `True`.

### 3.3 The four actions

| Action | Semantics | Authorization subject | Matching | Default |
|---|---|---|---|---|
| `req` | Allow it to call my tools | List of tool names | Exact match (`True` = all) | `[]`: none at all |
| `pub` | Allow its `publish` to trigger my `on()` | List of path patterns | Reuses `pattern_matches` | `False` |
| `sub` | Allow it to receive my broadcasts | List of path patterns | Reuses `pattern_matches` | `False` |
| `rep` | Allow its replies (`tool_result`) in | Boolean | Not per tool | `True` |

Item by item:

- **`req`**: `True` means all tools; a list means a whitelist, matched **exactly** by tool name (`[a-z0-9_-]+`, see [README §5.3](index.md#53-naming-rules)) — a tool name **MUST NOT** be treated as a path for wildcard matching. An empty list means none at all. `req` does **not** affect `call()` initiated by this node itself.
- **`pub`**: the `path` of a peer's `signal` **MUST** match at least one pattern in the list before the callback is triggered; otherwise the signal is dropped (no `on()`). Pattern matching **MUST** reuse `pattern_matches(pattern, path)` as defined in [publish-subscribe](./patterns/publish-subscribe.md), and **MUST NOT** establish a separate matching algorithm. Note that `"notify.**"` also lets through a signal whose path is exactly `notify`.
- **`sub`**: when this node calls `publish()`, the decision is made peer by peer: a peer **MAY** receive this broadcast if and only if `path` matches at least one pattern in that peer's `sub` list. `False` means nothing is sent to it.
- **`rep`**: a boolean, not per tool and with no condition beyond `reqid` ownership; `True` means the peer's `tool_result` **MAY** enter the local `reqid` matching flow.

**Value-domain constraints**: the values of `pub` / `sub` **MUST** be `False` or a **non-empty list of strings**. List elements **MUST NOT** use a wildcard in the middle (only exact, `prefix.*` and `prefix.**` are allowed), because `pattern_matches` returns `False` for a middle wildcard; an implementation **SHOULD** validate and reject such a configuration when loading the policy (fail-closed). This revision does **not** define a "single pattern allows everything" spelling for `pub` / `sub`: `pattern_matches` requires a wildcard to carry a prefix, so bare `*` and bare `**` match no path, and allowing everything requires listing the domain prefixes one by one (such as `["notify.**", "metric.**"]`).

### 3.4 Why `rep` is not in the same class as the other three

**`req` / `pub` / `sub` are restrictions on it** — turning them off means it may not do anything to me on its own initiative; **`rep` is the channel I keep for myself** — interactions that I initiate and it answers (the return value of `call()`) are allowed by default.

So "rep-only by default" means precisely this: **by default the peer can only be a responder in my presence — I cannot rely on it to act on its own initiative, but I can rely on it at any time**.

Writing `rep` explicitly as `True` is deliberate, and serves two purposes:

1. It makes the "default posture" **visible** in the table: the reader sees at a glance that the default is not "deny everything" but "keep only the channel I initiate";
2. It prevents an implementation from mistaking "replies" for "requests" and rejecting them together — `tool_result` and `tool_call` are the two halves of one interaction, and simplifying the default posture into "unauthorized means deny everything" makes `call()` time out forever, showing up as a silent failure that is hard to trace.

### 3.5 Defaults and scope

- `"*"` is the default posture for **network peers**: `req` with an empty whitelist (nothing exposed; a tool is opened only by adding its name explicitly), `pub` denied, `sub` denied, `rep` allowed.
- **Local (loopback / UDS under the same user): the whole table is bypassed, with full trust**; only cross-machine peers go through this table.
- **Local determination rule** (🔵): an inbound connection **SHOULD** be judged local if and only if its transport backend is `uds`, or the host in its TCP / WebSocket address belongs to `127.0.0.0/8`, `::1` or `localhost`. The determination **MUST** be based on the **connection already established at the local end** and its peer address, and **MUST NOT** depend on any field the peer reports in `hello`.

### 3.6 Enforcement points: only two

Authorization checks have **only two** enforcement points, and every other path **MUST NOT** reimplement them and **MUST NOT** bypass them. `core` still recognises only `Signal`.

**Inbound** (`_dispatch(peer_id, sig)`, which **MUST** be the first statement of that function):

```python
def _dispatch(self, peer_id: str, msg: Signal) -> None:
    if not self._authorized(peer_id, msg):     # 🔵 authorization check: MUST be the first line
        self._reject(peer_id, msg)             # drop, or reply with error (see §6)
        return
    # ... core signal dispatch / pattern routing as before

def _authorized(self, peer_id: str, msg: Signal) -> bool:
    if self._is_local(peer_id):                # local bypass: the whole table is skipped
        return True
    g = self._grants_for(peer_id)              # per-peer override, otherwise "*"
    t = msg.type
    if t == SignalType.TOOL_CALL:              # req
        return g["req"] is True or msg.payload.get("tool") in g["req"]
    if t == SignalType.SIGNAL:                 # pub
        pats = g["pub"]
        return bool(pats) and any(pattern_matches(p, msg.path or "") for p in pats)
    if t == SignalType.TOOL_RESULT:            # rep
        return bool(g["rep"])
    return True                                # other signal types are outside this table
```

**Outbound** (the fan-out loop of `publish()`):

```python
def publish(self, path: str, payload: dict) -> None:
    msg = Signal.make(type=SignalType.SIGNAL, source=self.node_id,
                      path=path, payload=payload)
    for peer_id, conn in list(self.connections.items()):
        if not self._is_local(peer_id) and not self._grant_sub(peer_id, path):
            continue                           # 🔵 sub not authorized: skip this peer
        try:
            conn.send(self._encode(msg))
        except ConnectionClosed:
            self._handle_disconnect(peer_id, conn)
```

`sub` filters **recipients** only and **does not change** the message content: an implementation **MUST NOT** generate broadcast copies with different content for different peers, otherwise observers would see inconsistent signals at the same moment and the "broadcast" semantics would be broken.

### 3.7 Tension with the broadcast model

Under the broadcast model there is no subscription table — `publish` sends the signal to every connected peer, and the receiver does local matching with `on()`. `sub` authorization is a **sender-side fan-out filter**, so "broadcast = send to all" and "keep it from unauthorized eyes" conflict here.

It is **similar in shape but different in nature** from the deleted subscription table:

- The subscription table answered "who **wants** it"; its purpose was bandwidth optimisation, and a breach only meant a few more useless signals received;
- `sub` authorization answers "who **may** see it"; its purpose is security, and a breach means an information leak.

**Per-peer filtering is therefore added back for security, with no bandwidth optimisation mixed in**: the sole basis for a `sub` decision **MUST** be the authorization table, and a peer **MUST NOT** be skipped because it "never subscribed to this path" — that would degrade a security policy into a bandwidth policy, and would also make "broadcast" unpredictable in observation.

### 3.8 Ordering requirements

- The authorization check **MUST** be the **first statement** of `_dispatch`, **before** core signal dispatch, **before** `pattern` routing, and **before** any enqueueing or thread start.
- `_read_loop` **MUST NOT** process any message that changes local state before calling `_dispatch` (only refreshing the `_last_seen` heartbeat timestamp is allowed).
- When a signal type, communication pattern or transport backend is added, it **MUST NOT** bypass `_dispatch` to call pattern handlers or the tool table directly; otherwise authorization lapses — this is the most critical implementation constraint on this page.

### 3.9 Authorization ownership of pattern-private signals

The authorization table governs only three **core types**: `tool_call` (`req`), `signal` (`pub`) and `tool_result` (`rep`). The connection-mechanism messages (`hello` / `ack` / `ping` / `pong` / `error` / `manifest_update`) are not governed — they trigger no action.

The remaining signals (pattern-private types) have **no default channel**: their ownership **MUST** be declared explicitly by the registered pattern, and **whatever is not declared is rejected**. An implementation **MUST** provide `PatternHandler.authorize(entry, sig) -> bool` as the extension point, and its **default implementation returns `False`**.

The entire reason this section exists: when a new pattern or a new signal type is added, forgetting to classify it **MUST** result in "rejected" and **MUST NOT** result in "allowed by default". The reference implementation's mapping:

| Pattern | Signal | Channel |
|---|---|---|
| `msp/task` | `task_submit` | `req`: `payload.task` is treated like a tool name for **exact matching** (the same whitelist and the same matching semantics as `tool_call`) |
| `msp/task` | `task_query` / `task_cancel` | `req`: requires that peer to hold **any** `req` right; the specific ownership is additionally gated by the `client_id` on the record |
| `msp/task` | `task_status` / `task_artifact` / `task_result` / `input_required` / `input_response` / each `*_result` receipt | `rep`: all of them are the channel "I allow you to hand results back to me" |
| `msp/multi-round` | `input_required` / `input_response` | `rep` |
| `msp/multi-round` | `tool_call` / `tool_result` | Reuses the core type names; decided directly by the protocol layer as `req` / `rep`, without going through the pattern |

A pattern **MUST NOT** return `True` unconditionally: that would give any newly introduced signal type name an automatic "authorization-free" status, and the `req` whitelist would lapse with it. The protocol layer **MAY** still let through to core dispatch a type "that no handler acts on" (which replies `-32600`) — letting it through produces no side effect, yet it makes "I do not recognise this type" distinguishable from "you lack permission" when troubleshooting.

### 3.10 Source verification on the write direction

An authorization decision answers "**are you entitled to talk to me**"; it **cannot** substitute for "**is this message about your own business**".

- Transaction ownership **MUST** be decided by the **connection identity** (the `peer_id` determined locally after the handshake), and **MUST NOT** use `Signal.source` — the latter is a field the peer reports about itself, and an attacker who fills it with the victim's `node_id` gets around the check.
- A typical counter-example: `task_status` / `task_artifact` / `task_result` carry a `taskId`, while the `task.<id>.**` observer broadcast sends `task_id` to **every** connected peer (see [task](patterns/task.md) §7). So "the id cannot be guessed" is no defence: the sender **MUST** be verified to be that task's executor. The read direction (`client_id` checks on `task_query` / `task_cancel`) and the write direction (executor checks) **MUST** be symmetric.
- Likewise, in the reference implementation the `reqid` of `msp/multi-round` is `mr-<n>` (predictable), so its follow-up questions and replies **MUST** verify the source, and **MUST NOT** be accepted merely because the `reqid` hits. `reqid` **MUST NOT** be treated as a security token.


## 4. Message flows

### 4.1 Inbound `req` check stops tools that were not opened up (main diagram)

```text
node_b (node authenticated)  node_a (this node; grants["node_b"].req = ["read_file"])
        │                                      │
        │ ── tool_call {tool:"rm_rf"} ────────▶│  ① _read_loop: conn.receive() → Signal
        │    reqid="9f2c…"                     │  ② _dispatch("node_b", sig)  ← authorization checked on line 1
        │    pattern="msp/request-reply"       │  ③ _authorized: "rm_rf" ∉ ["read_file"]
        │                                      │     → rejected
        │                                      │  ④ not queued, no execution thread started
        │                                      │     (the tool function is never called, no side effects)
        │ ◀── error {code:-32000, reqid:…} ────│  (optional; may also be dropped silently, see §6)
        │                                      │
        │ ── tool_call {tool:"read_file"} ────▶│  ⑤ whitelist hit → pass → _on_tool_call
        │ ◀── tool_result {content:[…]} ───────│  ⑥ executes normally and replies
        │                                      │
    ── Authentication only answers "you are node_b"; in this diagram node_b really is node_b, yet rm_rf is still rejected ──
```

Contrast: if step ③ were deleted, step ④ would become "start a thread and execute `rm_rf`" — **passing authentication** does not reduce the necessity of this step in the slightest.

### 4.2 Outbound `sub` filtering

When `node_a.publish("metric.cpu", …)` fans out: `node_b`'s `sub=["metric.**"]` hits → sent; `node_c`'s `sub=False` → skipped (`node_c` never sees this broadcast); a local peer → bypasses the whole table and is sent to directly.

### 4.3 Cross-machine signed HELLO handshake (🔵)

The order is: TLS is established (§2.4.1) → `hello` carries `payload.auth` → the acceptor verifies the signature, checks the time window and `nonce` reuse, and decides identity binding (§2.4.3) → checks the TOFU store (a changed public key means rejection) → the connection is registered only after everything passes → `ack` counter-signs → the initiator verifies symmetrically. If any step fails: the connection **MUST** be closed, and `peer_id` **MUST NOT** be registered, **MUST NOT** be written into `peer_manifests`, and `on_connected` **MUST NOT** be triggered.


## 5. Data types

### 5.1 Grant entry

| Field | Type | Required | Default | Semantics |
|---|---|---|---|---|
| `req` | `boolean` \| `array<string>` | no | `[]` | `true` = all tools; array = tool-name whitelist |
| `pub` | `boolean` \| `array<string>` | no | `false` | `false` = deny all; array = path patterns allowed |
| `sub` | `boolean` \| `array<string>` | no | `false` | As above, for outbound fan-out |
| `rep` | `boolean` | no | `true` | Whether to accept that peer's `tool_result` |

The table's own type is `map<node_id, GrantEntry>`; the key `"*"` is reserved as the default entry, and every other key **MUST** be a valid `node_id` (`[a-z0-9_-]+`).

### 5.2 `payload.auth` of `hello` / `ack` (🔵)

| Field | Type | Required | Semantics |
|---|---|---|---|
| `scheme` | `string` | yes | Fixed `"ed25519"` (this revision defines only this one) |
| `nodeId` | `string` | yes | **MUST** equal `Signal.source`, and equal the identity bound to the certificate / key |
| `publicKey` | `string` | yes | Base64 encoding of the raw 32-byte Ed25519 public key |
| `nonce` | `string` | yes | Hex encoding of a random value ≥ 16 bytes, for replay protection |
| `timestamp` | `number` | yes | Unix seconds, used for the ±60 s time window |
| `signature` | `string` | yes | Base64 encoding of the Ed25519 signature over the `signing_bytes` defined in §2.4.2 |

An implementation that does not implement node authentication **SHOULD** ignore the `auth` field ([lenient reading](index.md#7-conformance)), and **MUST NOT** disconnect because an unknown field appears.

### 5.3 TOFU storage (🔵)

Default path `~/.msp/known_nodes.json` (a sibling of the shared directory `~/.msp/nodes/`):

```json
{
  "node_b": {
    "publicKey": "Qm9ndXNFZDI1NTE5UHVibGljS2V5MzJCeXRlc0Jhc2U2NA==",
    "firstSeen": 1791500000.0,
    "lastSeen": 1791503600.0,
    "confirmed": true
  }
}
```

`confirmed=false` means not yet manually confirmed (the TOFU first connection); an entry with `confirmed=true` that meets a different `publicKey` **MUST** reject the connection and raise an alarm.

### 5.4 Local determination (🔵)

A peer with the `uds` backend is always treated as local; a peer whose `tcp` / `websocket` backend address has a host belonging to `127.0.0.0/8`, `::1` or `localhost` is likewise treated as local. The determination **MUST** be based on the connection already established at the local end and its peer address.


## 6. Error handling and boundaries

| Situation | Requirement |
|---|---|
| Inbound `req` / `pub` / `rep` unauthorized | **MUST** drop the signal (**MUST NOT** enqueue it, **MUST NOT** start an execution thread); **MAY** reply with an `error` signal explaining the refusal, and **MUST NOT** reply with `tool_result` — a refusal is not a tool execution result |
| `code` used for an unauthorized refusal | If an `error` is returned, `code` **SHOULD** come from the implementation-defined range `-32000` ~ `-32099` ([README §5.4](index.md#54-error-codes)) and be documented in the implementation's documentation; `message` **MUST NOT** leak local policy details (such as the complete tool list or the contents of the authorization table) |
| Outbound `sub` unauthorized | Skip that peer silently and **MUST NOT** return any error (the sender should not expose to an unauthorized peer that "there is a broadcast here you are not entitled to see") |
| TLS verification failure | The connection fails to establish at the transport layer; the handshake **MUST NOT** start and the peer **MUST NOT** be registered |
| Node authentication failure / identity mismatch / inbound message from an unauthenticated connection | **MUST** close the connection; **MUST NOT** register `peer_id`, **MUST NOT** write into `peer_manifests`, **MUST NOT** trigger `on_connected`, **MUST NOT** enter `_dispatch` |
| `grants` missing or an entry missing fields | Fill in the defaults of §3.2 and §3.5; **MUST NOT** allow anything because the configuration is missing |
| Known peer's public key changed | **MUST** reject and raise an alarm (possible impersonation); **MUST NOT** accept the new public key automatically |
| A path pattern with a middle wildcard | `pattern_matches` always returns `False`, i.e. **silent deny-all**; an implementation **SHOULD** validate at load time and report an error (fail-closed) |

**Boundary cases**: `req: True` means "all tools", including tools added later — so it **MUST NOT** be used as a default configuration for temporary debugging; an unknown `node_id` with no corresponding authorization entry goes to `"*"`; the `"*"` entry itself **MUST NOT** be deleted and then handled as "no configuration = allow everything".


## 7. Summary of normative provisions (MUST / SHOULD list)

**Current position (✅)**

1. The protocol layer **MUST NOT** perform default encryption, authentication or authorization checks on every message. (§1.1)
2. A node **SHOULD** listen on localhost only by default; cross-machine exposure **MUST** be explicitly enabled by the deployer. (§1.2, §2.4)
3. Resolution of a `node_id` conflict **MUST** follow a deterministic rule (currently lexicographic order deciding the canonical connection direction). (§2.4.3)

**Cross-machine deployment**: items 4–9 (TLS / node authentication / identity binding) remain 🔵; among items 10–16, the parts relating to the **authorization table** have landed with `core/grants.py` (✅), while item 16, relating to **node authentication**, remains 🔵.

4. A cross-machine deployment **MUST** configure TLS, node authentication, identity binding and authorization together; missing any one of the four means non-conformance with this page. (§2.4)
5. TLS **MUST** verify the certificate chain and the host name, and **MUST NOT** skip verification in a production configuration. (§2.4.1)
6. Node authentication **MUST** be mutual: both `hello` and `ack` **MUST** carry verifiable proof of identity. (§2.4.2)
7. The signature coverage **MUST** be a canonical byte string containing the whole `manifest`; `nonce` **MUST** be ≥ 16 random bytes, the `timestamp` window **MUST** be ±60 s, and a repeated `nonce` **MUST** be rejected. (§2.4.2)
8. When the public key of a confirmed peer changes, the connection **MUST** be rejected and an alarm raised. (§2.4.2, §5.3)
9. The `node_id` declared in `hello` / `ack` **MUST** match the certificate / key identity; verification **MUST** precede connection registration. (§2.4.3)
10. Authorization **MUST NOT** depend on the capability bits a peer reports, and `grants` **MUST NOT** be exchanged with the `Manifest`. (§3.1)
11. The authorization check **MUST** be the first statement of `_dispatch`; any path **MUST NOT** bypass `_dispatch` to handle peer messages directly. (§3.8)
12. Pattern matching for `pub` / `sub` **MUST** reuse `pattern_matches`, and **MUST NOT** establish a separate algorithm. (§3.3)
13. `sub` filtering **MUST NOT** change the content of the broadcast message, and **MUST NOT** mix in bandwidth-optimisation semantics. (§3.6, §3.7)
14. Local peers **SHOULD** bypass the whole authorization table; the local determination **MUST NOT** depend on fields a peer reports about itself. (§3.5)
15. An unauthorized `req` **MUST NOT** enter the tool execution path; a refusal **MUST NOT** be returned in the form of a `tool_result`. (§6)
16. An implementation that does not implement node authentication **SHOULD** ignore the `auth` field rather than disconnect. (§5.2)
17. A pattern-private signal **MUST** have its authorization ownership explicitly declared by the registered pattern, and **MUST NOT** be let through as a fallback; the default implementation of the extension point **MUST** be to deny. (§3.9)
18. Transaction ownership **MUST** be decided by the connection identity, and **MUST NOT** use the peer-reported `Signal.source`; source verification on the read and write directions **MUST** be symmetric. (§3.10)


## 8. Security considerations

- **The knock-on effects of `node_id` impersonation**: impersonation → discovery registry poisoning (declaration files are named by `node_id`) → deduplication disorder (the canonical connection direction is decided by `node_id` order) → traffic is steered to the attacker. Identity binding (§2.4.3) is the only closure point decidable at the protocol layer.
- **The information-exposure surface of broadcast**: `publish` fans out to every connected peer by default, so any broadcast may be observed by a third-party node. In a cross-machine deployment the domain prefixes **SHOULD** be split by sensitivity (for example, putting sensitive notifications in a separate domain), because `sub` filtering takes effect only **on the sender** — the sender has to know in advance who may see it.
- **Tool execution = an arbitrary-code-execution entry point**: registering a tool is exposing a callable function to the outside, and its internals can reach the file system, the network and processes. The authorization table (the `req` whitelist) is the **only** gate; the default value of `req` **MUST** therefore be an empty list.
- **`0o600` on UDS**: `UDSTransport.listen` tightens the socket file permission so that only the current user can connect, consistent with "same-user local full trust" (✅). When cleaning up leftovers it deletes only files of type `stat.S_ISSOCK` (`_unlink_stale`), preventing ordinary files from being deleted by mistake — an implementation **MUST NOT** change this to an unconditional `unlink`.
- **Resource paths and URI over-reach (roots)**: once the `resources` / `roots` surface is implemented (🔵, see [capabilities.md](./capabilities.md)), URIs **MUST** be constrained to the root directory on the server side (prefix canonicalisation + rejection of `..`), and **MUST NOT** leave authorization entirely to what the caller declares.
- **Integrity of the large-object `blob_ref`**: `blob_ref.checksum` is a checksum over the content, and the receiver **SHOULD** verify it after reassembly; when it is missing or does not match, it **SHOULD** refuse to use the object rather than degrade to "trust the length field". Both `size` and `checksum` are **advisory** fields and **MUST NOT** be used as the sole lower bound for memory pre-allocation (the 16 MiB message limit in [transports.md](./transports.md) is the hard boundary).
- **~~No read timeout during the handshake (DoS surface)~~ ✅ fixed**: `receive()` in `handshake_outbound` / `handshake_inbound` is now bounded by `handshake_timeout` (10 s by default), so a peer that accepts TCP but never sends `ACK` is timed out and the connection closed, instead of occupying a connection thread forever (see §9). The pre-handshake verification of node authentication **SHOULD** reuse the same timeout.
- **The forgery surface of `rep`**: allowing `rep` means the peer **MAY** send arbitrary `tool_result` messages; locally they are matched only by `reqid`, and results not in `pending_calls` are ignored. `reqid` **SHOULD** therefore stay unpredictable (`Signal.new_reqid()` yields 16 hex digits); an incrementing-sequence `reqid` **SHOULD NOT** be used, otherwise an authorized peer can guess in order and inject forged results (the `mr-<n>` of `msp/multi-round` in the reference implementation is a case in point, see §9).
- **The reverse risk of false security**: an implementation that allows everything by default and also claims to "support authorization" is more dangerous than one that states plainly "no authorization". If an implementation has not implemented the provisions of this section, it **SHOULD** say so explicitly in its documentation, rather than leave a configuration option that can be misread.


## 9. Known gaps

1. ~~**The authorization check is not yet implemented**~~: ✅ implemented — `core/grants.py` parses the authorization table, `MSPProtocol.authorized()` is the first statement of `_dispatch`, `grant_sub()` filters during fan-out, and `_reject()` drops unauthorized signals (replying with `error`, `code = -32000`, when a `reqid` is present). Two points still hold: it **does not cover pattern-private signals** (see item 6), and the authorization table's landing point is the node configuration rather than a `Preset` — §3.2 has relaxed "landing point" into something normatively irrelevant, in line with the implementation.
2. **TLS / node authentication / identity binding are not yet implemented**: the protocol layer has no related code; `WebSocketTransport` accepts `ws://` only and has no TLS support.
3. **There is no configuration entry for cross-machine listening**: `TransportRegistry.listen_all()` calls the backend as `transport.listen({})`, while the host defaults to `127.0.0.1` in `TCPTransport.listen` / `WebSocketTransport.listen`; the node-level `config` supports only `connect_backoff` / `discovery` / `presence`, so **it is currently impossible to listen on `0.0.0.0` through configuration alone** — the transport layer or the registry needs to change.
4. ~~**No read timeout during the handshake**~~: ✅ fixed — `handshake_timeout` (10 s by default) together with `Connection.set_read_timeout()`; on timeout the connection is closed and counted as unreachable.
5. **`pub` / `sub` have no "single pattern allows everything" spelling**: `pattern_matches` requires a wildcard to carry a prefix, so bare `*` / `**` match no path; allowing everything can only be done by listing the domain prefixes one by one.
6. ~~**Pattern-private signals are outside the authorization table's jurisdiction**~~: ✅ **defined and implemented**. The protocol layer no longer lets "non-core types" through as a fallback; it hands them to the **registered pattern** to declare ownership (`PatternHandler.authorize`, **deny by default**), with the mapping table in §3.9. `task_submit` goes through `req` (`payload.task` is treated like a tool name for exact matching), `task_query` / `task_cancel` require that peer to hold any `req` right, and the remaining `task_*` and `input_*` go through `rep`. **A new signal type MUST be classified explicitly; unclassified means rejected.**
7. **The `reqid` of `msp/multi-round` is predictable**: `_next_reqid()` returns `mr-<an auto-increment counter>`, which together with `rep` allowed leaves an injection surface for forged `tool_result`.
8. **The `code` usage of the `error` signal is not uniform**: the reference implementation currently emits a code in only two cases — `-32600` for "unknown signal type", and `-32000` for an **authorization refusal** (and only when the signal carries a `reqid`; broadcast signals have no error object to reply to and are dropped silently). The `-32601` / `-32602` / `-32603` in [README §5.4](index.md#54-error-codes) are **never** emitted by the protocol core (they exist only in the JSON-RPC bridge in `msp/mcp/jsonrpc.py`), and tool failures always go into `tool_result.payload.error` as a string.
9. **UDS is Linux / macOS only**: Python on Windows does not expose `socket.AF_UNIX`, and `listen()` / `connect()` raise `RuntimeError`; on Windows neither `0o600` nor the socket file semantics are available.


## 10. Reference implementation map

| Provision | Status | Source files and symbols |
|---|---|---|
| Trust boundary = transport reach (no authorization branch) | ✅ | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._dispatch`, `_dispatch_core` |
| Connection registration and `node_id` deduplication | ✅ | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._finish_handshake` |
| Handshake messages (`payload.manifest`) | ✅ | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `handshake_outbound` / `handshake_inbound` |
| Handshake read timeout | ✅ fixed | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `handshake_outbound` / `_receive_handshake`; [src/msp/transport/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/base.py) `Connection.set_read_timeout` |
| localhost-only listening by default | ✅ | [src/msp/transport/tcp.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/tcp.py) `TCPTransport.listen`; [src/msp/transport/websocket.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/websocket.py) `WebSocketTransport.listen` |
| No configuration entry for the listen address | ✅ (gap) | [src/msp/transport/registry.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/registry.py) `TransportRegistry.listen_all` |
| UDS `0o600` and socket misdeletion protection | ✅ | [src/msp/transport/uds.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/uds.py) `UDSTransport.listen`, `UDSTransport._unlink_stale` |
| Path pattern matching (`pub` / `sub` reuse) | ✅ | [src/msp/protocol/matcher.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/matcher.py) `pattern_matches` |
| Broadcast fan-out (insertion point for `sub` filtering) | ✅ | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol.publish` |
| Local callback matching (insertion point for `pub` filtering) | ✅ | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._on_signal` |
| `reqid` generation | ✅ | [src/msp/core/signal.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/signal.py) `Signal.new_reqid`; [src/msp/patterns/multi_round.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/multi_round.py) `MultiRoundHandler._next_reqid` |
| Authorization table `grants` | ✅ | [src/msp/core/grants.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/grants.py) `grants_from_json` / `grants_for` / `is_local_host`; [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol.authorized` / `grant_sub` / `_reject`; [src/msp/core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `config["grants"]` → `MSPProtocol(grants=...)`; [src/msp/core/exposure.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/exposure.py) `exposure_warning` |
| TLS / node authentication / identity binding | 🔵 | None (planned; intended to land in the transport wrapper and pre-handshake verification) |
| Authorization ownership of pattern-private signals | ✅ | [src/msp/patterns/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/base.py) `PatternHandler.authorize` (deny by default); `_AUTHORIZATION_FREE_TYPES` and the pattern delegation in `MSPProtocol.authorized` in [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py); the `authorize` of [src/msp/patterns/task.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/task.py) / [src/msp/patterns/multi_round.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/multi_round.py) |
| Source verification on the write direction | ✅ | [src/msp/patterns/task.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/task.py) `TaskHandler._write_from_executor` (`_on_status` / `_on_artifact` / `_on_result` / `_on_input_required`); [src/msp/patterns/multi_round.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/multi_round.py) `_on_tool_result` / `_on_input_required` / `_on_input_response` |
| Peer manifest normalisation (foreign input) | ✅ | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `_sanitize_peer_manifest` (both entry points: the handshake and `manifest_update`); [src/msp/core/grants.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/grants.py) `normalize_grants` |

**See also**: [Specification index](index.md) · [base-protocol](./base-protocol.md#4-connection-lifecycle) · [transports](./transports.md) · [discovery](./discovery.md) · [patterns/publish-subscribe](./patterns/publish-subscribe.md) · [capabilities](./capabilities.md) · [Design document §Security model](/design) · [Technical whitepaper §6](https://github.com/hxh230802/MSP/blob/master/docs/whitepaper.md)
