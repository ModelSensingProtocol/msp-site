"""生成站点 favicon（PNG 多尺寸 + ico）。

    python tools/make_favicon.py

为什么不用 SVG：16px 下细线与圆角在部分浏览器里会被裁掉或糊成一团；
Pillow 直接画像素，各尺寸都能单独渲染，浏览器表现一致。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT_DOCS = ROOT / "docs" / "assets"
OUT_LANDING = ROOT / "landing" / "assets"

INK = (28, 25, 23, 255)        # #1c1917 深底
PAPER = (250, 250, 249, 255)   # #fafaf9 中心节点
GREEN = (62, 207, 142, 255)    # 在线邻居
GREY = (168, 162, 158, 255)    # 离线邻居
EDGE = (87, 83, 78, 255)


def draw(size: int) -> Image.Image:
    """画一个 size×size 的图标。内部按 4 倍绘制再缩小，边缘才干净。"""
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = s * 0.055
    d.rounded_rectangle([pad, pad, s - pad, s - pad], radius=s * 0.22, fill=INK)

    cx = cy = s / 2
    r_main = s * 0.135
    r_sat = s * 0.10
    nodes = [
        ((s / 2, s * 0.26), r_sat, GREEN),
        ((s * 0.74, s * 0.70), r_sat, GREEN),
        ((s * 0.26, s * 0.70), r_sat, GREY),
    ]

    width = max(1, int(s * 0.05))
    for (x, y), _r, _c in nodes:
        d.line([(x, y), (cx, cy)], fill=EDGE, width=width)

    for (x, y), r, color in nodes:
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)

    d.ellipse([cx - r_main, cy - r_main, cx + r_main, cy + r_main], fill=PAPER)
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
