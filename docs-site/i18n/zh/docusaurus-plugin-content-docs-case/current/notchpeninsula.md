---
sidebar_label: NotchPeninsula
---

# NotchPeninsula —— 一个组件变成一个节点

[NotchPeninsula](https://github.com/GEORGEWWWU/NotchPeninsula) 是面向 Windows 10/11 的
刘海 / 灵动岛组件（C#、.NET 10、Win32 + SkiaSharp + NAudio，Apache-2.0）。
它显示当前播放、渲染歌词、做系统音频可视化、弹 Toast 通知。

它同时也是一个 MSP 节点。

这个组合正是重点：一个**屏幕上有状态**的程序——正是 stdio 传输够不着的那类。因为你在意的实例
是登录用户下**已经跑着的那个**，不是为某次会话新拉起来的进程。

## 它注册了什么

| | |
|---|---|
| 节点 id | `notchpeninsula` |
| 在哪开启 | **通用设置 → MSP 接入（实验性）** |
| 默认 | **关闭**——你自己打开，开启即时生效 |
| 方向 | 双向：既可以被调，也会广播自己的事件 |

## 能调什么

它宣告的工具刻意很少——都是一个组件真正拥有的操作：

| 工具 | 用途 |
|---|---|
| `ping` | 健康检查，返回节点标识与已连接对端 |
| `media_status` | 只读：现在在放什么（标题、歌手、进度、状态） |
| `media_control` | `play` / `pause` / `toggle` / `next` / `prev` |
| `notify` | 弹一条通知；支持图标与头像（content block 里 `annotations.role` 为 `"icon"` / `"avatar"`） |

注意这里**没有**什么：没有 `open_settings`、没有装插件、没有任意 UI 自动化。
集成面就是邻居程序有正当理由碰的那部分。

## 从 Python 调它

```python
from msp import MSPNode, Preset

me = MSPNode("my-agent", preset=Preset.FULL_PEER)
me.start()

if "notchpeninsula" not in me.neighbors():
    raise SystemExit("看不到这个节点——组件设置里的 MSP 接入打开了吗？")

print(me.call("notchpeninsula", "media_status", {}).unwrap())
me.call("notchpeninsula", "media_control", {"action": "next"})
```

带图的通知，用的是和 MCP 一样的内容块结构：

```python
me.call("notchpeninsula", "notify", {
    "kind": "info",
    "title": "下载完成",
    "body": "report.pdf 已经放在 ~/Downloads",
    "content": [{
        "type": "image",
        "data": "<base64 png>",
        "mimeType": "image/png",
        "annotations": {"role": "icon"},
    }],
})
```

## 这个案例说明了什么

1. **节点是一层薄壳。** 组件本来就有媒体会话和通知管道；MSP 那一侧只是一个 bridge 文件，
   没有人重写这个应用。
2. **推送是成立的。** 组件会广播本机事件、也订阅对端的通知——是它自己开口，而不是被轮询。
3. **状态留在它该在的地方。** `media_status` 回答的是用户此刻正在看的那个活对象，
   不是谁缓存下来的快照。

## 它做不到什么

- **只有 Windows。** 没有 macOS / Linux 构建。
- **实验性。** MSP 接入自己就标着实验性，而且**默认关闭**——对一个会开监听端口的特性，
  这是诚实的默认值。
- **除了"可达"没有别的鉴权。** 和目前所有 MSP 节点一样，它信任能连上本机端口的任何东西。
  不要把它暴露在你控制不了的网络上。
- **它不是通用自动化面。** 真要任意驱动这个组件，该用 UI 自动化工具，不是这个节点。
