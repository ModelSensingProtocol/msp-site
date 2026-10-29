---
sidebar_label: Overview
---

# Case studies

Adoption is the only claim a protocol cannot talk its way out of. These are applications that put
an MSP node inside a **real, shipping program** — not demos.

| Case | What kind of program | What MSP gave it |
|---|---|---|
| [NotchPeninsula](notchpeninsula.md) | A Windows notch / dynamic-island widget with visible state | An integration surface: other programs can ask it what is playing, control it, and push a notification — without anyone writing an MCP server |

## What makes a good case

A case is interesting when the program is **not a server**. A widget, an editor, a player — these
have state a user is looking at right now. Two things follow:

- The program already exists; nobody is going to rewrite it around your protocol. The node has to be
  a thin layer over what it already does.
- The interesting calls are the ones that need *its* state: "what is playing", "show this now",
  "pause". A model asking in prose gets a stale answer; a node answers from the live object.

That is the shape MSP was designed for, and it is exactly the shape a stdio transport cannot hold:
the process is already running, under a logged-in user, with a window on screen.

## Adding your own

Send a pull request with a page next to the one above. Keep to what is checkable:

- the node id it registers,
- the tools it exposes and their arguments,
- how it is enabled, and whether it is on by default,
- and what it does **not** do.

A case page that only lists strengths is advertising, not a case study.
