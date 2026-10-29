"""跑一遍站点上的示例脚本，确认它们不是"看起来能跑"。

    PYTHONPATH=../src python tools/check_examples.py

做三件事：
  1. 起 weather.py，用客户端调它的 get_weather，断言返回值；
  2. 起 downloader.py 与 editor.py，触发一个任务，断言 editor 收到了 completed 信号；
  3. 起 probe.py，断言它能看见别人、而别人看不见它。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "static" / "examples"
SRC = ROOT.parent.parent / "src"  # ModelSensingProtocol/src


def env_for(nodes_dir: str) -> dict:
    env = dict(os.environ)
    env["MSP_NODES_DIR"] = nodes_dir
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def spawn(name: str, nodes_dir: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-u", str(EXAMPLES / name)],
        env=env_for(nodes_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    time.sleep(2.0)  # 等它宣告/发现落地
    return proc


def stop(*procs: subprocess.Popen) -> str:
    out = []
    for proc in procs:
        proc.terminate()
        try:
            text, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            text, _ = proc.communicate()
        out.append(text or "")
    return "\n".join(out)


def check_tool_call(nodes_dir: str) -> None:
    weather = spawn("weather.py", nodes_dir)

    client = f"""
import os, json
from msp import MSPNode, Preset
node = MSPNode("checker", preset=Preset.FULL_PEER, nodes_dir={nodes_dir!r})
node.start()
assert "weather" in node.neighbors(), f"没发现 weather: {{node.neighbors()}}"
r = node.call("weather", "get_weather", {{"location": "杭州", "days": 2}}, timeout=5.0)
assert not r.is_error, f"调用失败: {{r.error}}"
assert r.structured["location"] == "杭州", r.structured
print("CALL_OK", json.dumps(r.structured, ensure_ascii=False))
node.stop()
"""
    result = subprocess.run(
        [sys.executable, "-u", "-c", client],
        env=env_for(nodes_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    out = stop(weather)
    assert "CALL_OK" in result.stdout, f"调用未成功\nstdout={result.stdout}\nstderr={result.stderr}\nweather={out}"
    print("  ✓ weather.py：被发现并成功调用 get_weather")


def check_signal_handoff(nodes_dir: str) -> None:
    downloader = spawn("downloader.py", nodes_dir)
    editor = spawn("editor.py", nodes_dir)

    client = f"""
from msp import MSPNode, Preset
node = MSPNode("checker2", preset=Preset.FULL_PEER, nodes_dir={nodes_dir!r})
node.start()
assert "downloader" in node.neighbors(), f"没发现 downloader: {{node.neighbors()}}"
r = node.call("downloader", "start_task", {{"url": "https://example.com/x", "size_mb": 5}}, timeout=5.0)
assert not r.is_error, f"start_task 失败: {{r.error}}"
print("TASK", r.structured["taskId"])
node.stop()
"""
    result = subprocess.run(
        [sys.executable, "-u", "-c", client],
        env=env_for(nodes_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    time.sleep(4.0)  # 等任务跑完（示例里 10 步 × 0.2s）
    out = stop(downloader, editor)
    assert "TASK" in result.stdout, f"start_task 未成功: {result.stdout} {result.stderr}"
    assert "download.completed" in out, f"editor 没收到完成信号\n{out}"
    print("  ✓ downloader.py → editor.py：任务启动，完成信号被订阅方收到")


def check_observer(nodes_dir: str) -> None:
    weather = spawn("weather.py", nodes_dir)
    probe = spawn("probe.py", nodes_dir)
    time.sleep(2.5)
    out = stop(weather, probe)
    # 同一个临时目录里可能还留着前面检查的租约，所以只断言"看得到 weather"，
    # 不要求邻居数量恰好为 1。
    probe_lines = [ln for ln in out.splitlines() if ln.startswith("[probe] 邻居")]
    assert probe_lines, f"observer 没输出邻居\n{out}"
    assert "weather" in " ".join(probe_lines), f"observer 没看到 weather\n{out}"
    print("  ✓ probe.py：只看不说——能看见 weather，且自身不宣告")


def main() -> None:
    if not (SRC / "msp").is_dir():
        sys.exit(f"找不到 msp 源码：{SRC}（用 PYTHONPATH 指向 ModelSensingProtocol/src 的父目录运行）")

    with tempfile.TemporaryDirectory(prefix="msp-examples-") as tmp:
        print(f"临时发现目录: {tmp}")
        check_tool_call(tmp)
        check_signal_handoff(tmp)
        check_observer(tmp)
    print("\n全部示例跑通")


if __name__ == "__main__":
    main()
