# Security and trust

MSP's current trust model is one sentence: **if you can reach the socket, you are trusted.** There is
no authentication, no encryption, and no per-tool permission. This page says what that means in
practice, where the line actually is, and what to do before you cross it.

Being blunt about this is cheaper than discovering it in production.

## What is enforced today

| Mechanism | What it does | What it does not do |
|---|---|---|
| **Local peer allow-list** | loopback TCP and UDS peers are treated as the same user, so their calls and subscriptions are allowed without grants | nothing about other machines |
| **Path grants** | a publisher may refuse to send `a.b.c` to a given peer; a provider may refuse calls from a peer | it is *publisher-side* bookkeeping, not a capability system: the peer already has a connection |
| **Tool name checks** | unknown tool → error, no dispatch | no argument validation — `input_schema` is a declaration, not a guard |
| **Bind address** | the node listens on what you tell it to | it defaults to listening, and a node that listens is a node that is reachable |

Notice what is missing: there is no "who are you", so there is no "are you allowed". Grants are
filters, not identity.

## The line: same machine vs anything else

- **Same machine, same user** — treat MSP like a local IPC mechanism. Any process you can already
  debug can already do worse. This is the supported, sensible case.
- **Another machine on the LAN** — anyone who can route to your port can call your tools. If that is
  not acceptable, do not bind to `0.0.0.0`.
- **Anything wider** — do not. There is no TLS in the WebSocket transport (no `wss://`), so a network
  you do not control sees every payload in clear text.

## What a hostile local process can do

Assume the worst and be specific, because "an attacker" is not actionable:

- Call any tool you expose, with any arguments, as fast as it likes.
- Subscribe to any signal path and read the payloads.
- Publish signals to you; if your handler trusts the payload, it can steer your behaviour.
- Refuse to answer, or answer slowly, to stall your calls (there is a timeout, but the timeout is
  yours to set).
- Claim any node id — including one that already exists, which will evict the real node.

The last one is worth repeating: **node ids are not authenticated**. A duplicate id is not just a
collision, it is a way to impersonate.

## Practical rules

1. **Expose the smallest surface.** A widget needs `media_status` and `media_control`, not
   `run_command`. The [NotchPeninsula case](pathname:///msp-site/docs/case/notchpeninsula/) is a good example of a deliberately
   small surface.
2. **Treat every payload as untrusted input.** Validate `taskId`, paths, and sizes in the tool body.
   The schema you advertised is documentation for well-behaved callers.
3. **Keep long-running nodes on loopback**, and put anything cross-machine behind a tunnel you
   control — the protocol will not protect the bytes for you.
4. **Do not put secrets in signals.** Broadcast goes to every subscribed peer, including the one you
   forgot about.
5. **Default new integration features to off.** That is what NotchPeninsula does with its MSP toggle,
   and it is the right default for a feature that opens a listening socket.

## What would change this page

Authentication at the handshake, per-tool capability grants bound to an identity, and TLS on the
WebSocket transport. All three are design work, not implementation detail; until they exist, this page
is the honest description of the boundary.

## See also

- [`spec/security.md`](pathname:///msp-site/docs/spec/security/) — the normative statement of the trust model
- [Running across machines](lan.md) — what to do when you actually need it
- [Positioning](why-not-mcp.md) — why "reachable means trusted" was chosen, and what it costs
