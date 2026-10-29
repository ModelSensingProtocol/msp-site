"""生成站点 favicon（PNG 多尺寸 + ico）。

    python tools/make_favicon.py

为什么不用 SVG：16px 下细线与圆角在部分浏览器里会被裁掉或糊成一团；
Pillow 直接画像素，各尺寸都能单独渲染，浏览器表现一致。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT_DOCS = ROOT / "docs-site" / "static"
OUT_LANDING = ROOT / "landing" / "assets"

INK = (28, 25, 23, 255)        # #1c1917 深底
PAPER = (250, 250, 249, 255)   # #fafaf9 中心节点
GREEN = (62, 207, 142, 255)    # 在线邻居
GREY = (168, 162, 158, 255)    # 离线邻居
EDGE = (87, 83, 78, 255)


def dashed(d, a, b, fill, width, dash, gap):
    """在两点之间画虚线（Pillow 没有 dash 参数，自己切段）。"""
    (x1, y1), (x2, y2) = a, b
    length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    if length == 0:
        return
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    t = 0.0
    while t < length:
        t2 = min(t + dash, length)
        d.line(
            [(x1 + ux * t, y1 + uy * t), (x1 + ux * t2, y1 + uy * t2)],
            fill=fill,
            width=width,
        )
        t = t2 + gap


def draw(size: int) -> Image.Image:
    """画一个 size×size 的图标。内部按 4 倍绘制再缩小，边缘才干净。

    构图沿用原来的「中心 + 三个卫星」，另加一条**顶部↔右侧的直连**：
    那两个节点之间不必经过中心，这正是 MSP 想表达的。中心到各卫星的辐条
    保持细而浅，直连用节点本身的绿色、且更粗——主路径一眼可辨。
    """
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = s * 0.055
    # 直角方块：不要圆角
    d.rectangle([pad, pad, s - pad, s - pad], fill=INK)

    cx = cy = s / 2
    centre = (cx, cy)
    r_centre = s * 0.115
    r_sat = s * 0.088
    top = (cx, s * 0.215)
    right = (s * 0.785, s * 0.715)
    left = (s * 0.215, s * 0.715)

    # 辐条：细、浅（表示"也能这样连"，不是主路径）
    spoke_w = max(1, int(s * 0.022))
    for pt in (top, right, left):
        d.line([centre, pt], fill=EDGE, width=spoke_w)

    # 直连：两个卫星之间的实线，比辐条粗，用节点绿
    d.line([top, right], fill=GREEN, width=max(2, int(s * 0.042)))

    for pt, color in ((top, GREEN), (right, GREEN), (left, GREY)):
        d.ellipse([pt[0] - r_sat, pt[1] - r_sat, pt[0] + r_sat, pt[1] + r_sat], fill=color)

    d.ellipse(
        [cx - r_centre, cy - r_centre, cx + r_centre, cy + r_centre], fill=PAPER
    )
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    for base in (OUT_DOCS, OUT_LANDING):
        base.mkdir(parents=True, exist_ok=True)

    for size in (16, 32, 48, 64, 180, 512):
        icon = draw(size)
        icon.save(OUT_DOCS / f"favicon-{size}.png")
        if size in (32, 180):
            icon.save(OUT_LANDING / f"favicon-{size}.png")

    ico_sizes = [(16, 16), (32, 32), (48, 48)]
    draw(48).save(OUT_DOCS / "favicon.ico", sizes=ico_sizes)
    draw(48).save(OUT_LANDING / "favicon.ico", sizes=ico_sizes)
    print("已生成 favicon-{16,32,48,64,180,512}.png + favicon.ico（docs 与 landing 各一份）")


if __name__ == "__main__":
    main()
