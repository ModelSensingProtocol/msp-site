---
sidebar_label: NotchPeninsula
---

# NotchPeninsula — a widget becomes a node

[NotchPeninsula](https://github.com/GEORGEWWWU/NotchPeninsula) is a notch / dynamic-island widget
for Windows 10/11 (C#, .NET 10, Win32 + SkiaSharp + NAudio, Apache-2.0). It shows what is playing,
renders lyrics, visualises the system audio output, and shows toast notifications.

It is also an MSP node.

That combination is the point: a program with **state on screen** — the kind of program a stdio
transport cannot reach, because the instance you care about is the one already running under your
logged-in user, not a process spawned for a session.

## What it registers

| | |
|---|---|
| Node id | `notchpeninsula` |
| Enabled in | **General settings → MSP access (experimental)** |
| Default | **off** — you turn it on; it takes effect immediately |
| Direction | both: it is callable, and it broadcasts its own events |

## What you can call

The tools it advertises are deliberately small — they are the operations a widget actually has:

| Tool | Purpose |
|---|---|
| `ping` | health check; returns the node identity and its connected peers |
| `media_status` | read-only: what is playing right now (title, artist, progress, state) |
| `media_control` | `play` / `pause` / `toggle` / `next` / `prev` |
| `notify` | pop a notification; accepts an icon and an avatar as content blocks with `annotations.role` of `"icon"` / `"avatar"` |

Notice what is *not* here: no `open_settings`, no `install_plugin`, no arbitrary UI automation. The
surface is the part a neighbouring program has a legitimate reason to touch.

## Calling it from Python

```python
from msp import MSPNode, Preset

me = MSPNode("my-agent", preset=Preset.FULL_PEER)
me.start()

if "notchpeninsula" not in me.neighbors():
    raise SystemExit("node not visible — is MSP access enabled in the widget's settings?")

print(me.call("notchpeninsula", "media_status", {}).unwrap())
me.call("notchpeninsula", "media_control", {"action": "next"})
```

A notification with an image, using the same content-block shape MCP uses:

```python
me.call("notchpeninsula", "notify", {
    "kind": "info",
    "title": "Download finished",
    "body": "report.pdf is ready in ~/Downloads",
    "content": [{
        "type": "image",
        "data": "<base64 png>",
        "mimeType": "image/png",
        "annotations": {"role": "icon"},
    }],
})
```

## What this case actually demonstrates

1. **The node is a thin layer.** The widget already had media sessions and a notification pipeline;
   the MSP side is one bridge file. Nobody rewrote the app.
2. **Push works.** The widget broadcasts local events and subscribes to notifications from peers —
   the app speaks up instead of being polled.
3. **State stays where it belongs.** `media_status` answers from the live object the user is
   looking at, not from a snapshot someone cached.

## What it does not do

- **Windows only.** There is no macOS or Linux build.
- **Experimental.** The MSP integration is labelled as such, and it is **off by default** — that is
  the honest default for a feature that opens a listening socket.
- **No authentication beyond reachability.** Like every MSP node today, it trusts anything that can
  reach it on the machine. Do not expose it across a network you do not control.
- **Not a general automation surface.** If you need to drive the widget arbitrarily, a UI automation
  tool is the right answer, not this node.
