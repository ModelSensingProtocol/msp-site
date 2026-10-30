# Multi-round interactions

Request/reply gets you one answer. Some conversations need several: a clarification, a confirmation,
a stream of partial results. MSP has a **multi-round** pattern for that, and it is deliberately thin —
it does not invent a session object.

## The shape

The provider exposes a `round` tool that takes a `round` number and a payload; the caller drives the
loop. There is no server-side session state beyond what you keep yourself.

```
caller                          provider
  │  start(args) ────────────────▶ │  (round 1 begins)
  │ ◀──────────── {state, question}
  │  round(args + answer) ────────▶ │  (continues)
  │ ◀──────────── {state, answer}
```

Why not a session object? Because a session is state that must be timed out, garbage-collected, and
authenticated — three things MSP currently does badly. A round counter is a number you can put in a
request; a session is a service you have to run.

## When to use it

| Need | Use |
|---|---|
| one question, one answer | a plain tool call |
| several steps, caller drives each | multi-round |
| long job, caller wants to walk away | [task pattern](tasks.md) |
| a stream of events | signals, with a tool to read current state |

Multi-round is right when **the caller must decide between rounds** (confirm this, choose that).
If the provider can proceed on its own, it is a long task, not a conversation.

## Degradation is part of the contract

Not every peer speaks multi-round. The spec requires the provider to declare the pattern in its
manifest and to **degrade to a single round** when the caller does not advertise support: it runs the
first round as a normal call and returns its result. A caller that ignores this gets a plausible
answer, not an error — which is the friendlier failure, and the reason the pattern is declared rather
than negotiated.

## Cost

Each round is a full call: request, reply, `reqid` bookkeeping, timeout. A five-round conversation with
a 5 s timeout is a 25 s call from the caller's point of view if you set the timeout per round — so
budget the **whole** interaction, not each hop.

## See also

- [`spec/patterns/multi-round.md`](pathname:///msp-site/docs/spec/patterns/multi-round/) — normative rules, including the
  degradation requirement
- [Long tasks](tasks.md) — when the provider can proceed without asking
- [Signals](signals.md) — when the caller does not need to answer at all
