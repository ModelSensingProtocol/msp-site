"""
MSP 主动式事件推送 —— 最小可跑 Demo
=====================================

要证明的一件事：**本机的事件推送，不需要 webhook、不需要 TTL 续期、不需要
谁去订阅谁。**

三个角色，全在一个进程里，但它们之间只通过 MSP 的信号总线说话：

    file-watcher   一台"本机软件"（截图工具 / 文件监控 / 剪贴板…随便是什么）
                   它有变化就 publish 一个信号，不关心谁在听。
    ai             主动式 Agent。它只做一件事：订阅 `file.**`。
    （没有第三个）   没有注册中心、没有回调 URL、没有心跳续期。

跑法：

    python demo/pubsub_demo.py

大约 6 秒，你会看到 AI 端逐个收到信号，而 file-watcher 从头到尾不知道
是谁收到了它。
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import time

# Windows 控制台默认 GBK：不改成 UTF-8，中文和箭头全是乱码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from msp import MSPNode
from msp.core.preset import Preset

import os

# 想隔离演示环境就设 MSP_NODES_DIR（默认 ~/.msp/nodes）
NODES_DIR = os.environ.get("MSP_NODES_DIR", "~/.msp/nodes")

# 一个临时目录，冒充"用户的工作目录"
WORK = pathlib.Path(tempfile.mkdtemp(prefix="msp-demo-")) / "inbox"
WORK.mkdir(parents=True)

RECEIVED: list[dict] = []


def banner(text: str) -> None:
    print(f"\n\033[36m{text}\033[0m")


# ---------------------------------------------------------------------------
# 节点 1：一台普通的本机软件
#
# 它不知道 AI 的存在，也不需要知道。它只声明"我会发这类信号"，
# 然后有变化就扔进总线。
# ---------------------------------------------------------------------------
watcher = MSPNode("file-watcher", preset=Preset.LOCAL_TOOL, nodes_dir=NODES_DIR)


@watcher.signal_source("file.modified")
def watch_inbox():
    """生成器：目录里有新文件就 yield 一个 payload。

    注意这里没有 socket、没有 HTTP、没有 URL —— 这就是"神经末梢"。
    """
    seen: set[str] = set()
    deadline = time.time() + 8.0
    while time.time() < deadline:
        for path in sorted(WORK.iterdir()):
            if path.name in seen:
                continue
            seen.add(path.name)
            print(f"  \033[33m[watcher]\033[0m 检测到 {path.name} → publish('file.modified')")
            yield {"name": path.name, "path": str(path), "size": path.stat().st_size}
        time.sleep(0.1)


# ---------------------------------------------------------------------------
# 节点 2：主动式 Agent
#
# 它只写了一行订阅。没有 events/subscribe、没有 webhook 地址、没有 TTL。
# ---------------------------------------------------------------------------
ai = MSPNode("ai", preset=Preset.LOCAL_AI, nodes_dir=NODES_DIR)


@ai.on("file.**")
def on_any_file(signal):
    """`file.**` 匹配 file 之下任意层：file.modified、file.created.remote…"""
    RECEIVED.append(signal.payload or {})
    print(f"  \033[32m[ai]\033[0m 收到 {signal.path}：{signal.payload}")


def main() -> None:
    banner("1. 两个节点各自启动（谁也没连谁）")
    watcher.start(settle=False)
    ai.start(settle=False)
    print(f"   watcher → {watcher.listen_addresses}")
    print(f"   ai      → {ai.listen_addresses}")

    banner("2. 等发现层把邻居连上（共享目录宣告，零配置）")
    time.sleep(1.2)
    print(f"   ai 看到的邻居：{ai.connections()}")
    print(f"   watcher 看到的邻居：{watcher.connections()}")
    print("   ↑ watcher 是被连的那一方：它不需要知道谁在连它")

    banner("3. 往目录里丢三个文件（就这一步在'制造事件'）")
    for i, name in enumerate(["screenshot-1.png", "screenshot-2.png", "note.md"], 1):
        (WORK / name).write_text(f"demo {i}", encoding="utf-8")
        time.sleep(1.0)

    banner("4. 结果")
    print(f"   AI 收到 {len(RECEIVED)} 条信号：")
    for item in RECEIVED:
        print(f"     · {item.get('name')}")

    banner("5. 对照 MCP Events")
    print("   · 没有 events/subscribe —— 订阅就是一行 @ai.on(\"file.**\")")
    print("   · 没有 webhook URL —— watcher 不知道谁在听，也不需要知道")
    print("   · 没有 TTL 续期 —— 连接在，订阅就在；断了自动重连")
    print("   · 没有轮询 —— 信号由 watcher 推出来，不是 AI 去问")

    watcher.stop()
    ai.stop()


if __name__ == "__main__":
    try:
        main()
    finally:
        time.sleep(0.2)
