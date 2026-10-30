"""生成文档站用的架构图（中英两份 PNG）。

    python tools/make_architecture.py

构图沿用 MCP 那张公开架构图的视觉语言——白底、圆角描边方框、细灰箭头、
中间一个强调色的协议框、两侧是「AI 应用」与「软件与设备」。差别在于中间框里
画的是一个**小网**：三个节点、三条边，其中一条用绿色加粗，表示两个节点之间
可以直连、不经过模型。

为什么用生成而不是手绘：两种语言各要一份，标签跟着文案走；像 favicon 与
banner 一样用 Pillow 画，改文案只动 LABELS。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs-site" / "static" / "img"

SCALE = 2
W, H = 1180, 420

INK = (28, 25, 23)
MUTED = (120, 113, 108)
BORDER = (231, 229, 228)
ARROW = (168, 162, 158)
ACCENT = (37, 99, 235)
ACCENT_BG = (245, 249, 255)
GREEN = (47, 158, 107)
BG = (255, 255, 255)

# 西文用 Segoe UI，中文必须换带 CJK 字形的字体——否则渲染出来是一排方块。
LATIN = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"]
CJK = [
    "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/Deng.ttf",       # 等线
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
]


def font(size: int, bold: bool = False, cjk: bool = False) -> ImageFont.FreeTypeFont:
    if cjk:
        # 先找粗体再找常规，找不到粗体时用常规代替（不做合成加粗）
        order = CJK[1::2] + CJK[0::2] if bold else CJK[0::2] + CJK[1::2]
        candidates = order + LATIN
    else:
        candidates = LATIN[1::2] + LATIN[0::2] if bold else LATIN
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


LABELS = {
    "en": {
        "left": [
            ("Chat interfaces", "agent UIs, assistants"),
            ("IDEs and editors", "code assistants"),
            ("Your own scripts", "anything on a socket"),
        ],
        "right": [
            ("Media widget", "NotchPeninsula"),
            ("Downloader", "long tasks"),
            ("Editor", "files, projects"),
        ],
        "title": "MSP",
        "sub": "peers, not a hub",
        "left_group": "AI applications",
        "right_group": "Software and devices",
        "both": "bidirectional",
        "direct": "node to node, no model in between",
    },
    "zh": {
        "left": [
            ("对话与 agent", "助手界面"),
            ("IDE 与编辑器", "代码助手"),
            ("自己的脚本", "任何有 socket 的东西"),
        ],
        "right": [
            ("媒体组件", "NotchPeninsula"),
            ("下载器", "长任务"),
            ("编辑器", "文件与项目"),
        ],
        "title": "MSP",
        "sub": "对等节点，不是总线",
        "left_group": "AI 应用",
        "right_group": "软件与设备",
        "both": "双向",
        "direct": "节点之间直连，不经过模型",
    },
}


def S(*vals):
    return [v * SCALE for v in vals]


def text_center(d, xy, s, f, fill):
    w = d.textlength(s, font=f)
    d.text((xy[0] - w / 2, xy[1]), s, font=f, fill=fill)


def box(d, box_xy, title, sub, f_title, f_sub, outline=BORDER, width=2):
    d.rounded_rectangle(box_xy, radius=10 * SCALE, fill=BG, outline=outline, width=width * SCALE)
    cx = (box_xy[0] + box_xy[2]) / 2
    cy = (box_xy[1] + box_xy[3]) / 2
    text_center(d, (cx, cy - f_title.size * 1.05), title, f_title, INK)
    text_center(d, (cx, cy + f_sub.size * 0.45), sub, f_sub, MUTED)


def arrowhead(d, tip, direction, color=ARROW, size=6):
    dx, dy = direction
    length = (dx * dx + dy * dy) ** 0.5 or 1
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    p1 = (tip[0] - ux * size * SCALE + px * size * SCALE * 0.55,
          tip[1] - uy * size * SCALE + py * size * SCALE * 0.55)
    p2 = (tip[0] - ux * size * SCALE - px * size * SCALE * 0.55,
          tip[1] - uy * size * SCALE - py * size * SCALE * 0.55)
    d.polygon([tip, p1, p2], fill=color)


def two_way(d, a, b):
    """一条线、两端各一个箭头——比画两条平行线干净。"""
    d.line([a, b], fill=ARROW, width=2 * SCALE)
    arrowhead(d, a, (a[0] - b[0], a[1] - b[1]))
    arrowhead(d, b, (b[0] - a[0], b[1] - a[1]))


def draw(lang: str) -> Image.Image:
    L = LABELS[lang]
    img = Image.new("RGB", (W * SCALE, H * SCALE), BG)
    d = ImageDraw.Draw(img)

    cjk = lang == "zh"
    f_title = font(16 * SCALE, bold=True, cjk=cjk)
    f_sub = font(13 * SCALE, cjk=cjk)
    f_small = font(12 * SCALE, cjk=cjk)
    f_mid_title = font(24 * SCALE, bold=True, cjk=cjk)
    f_mid_sub = font(13 * SCALE, cjk=cjk)

    box_w, box_h, gap = 232, 58, 46
    col_top = 40
    left_x = 30
    right_x = W - 30 - box_w
    rows = [col_top + i * (box_h + gap) for i in range(3)]

    for (title, sub), y in zip(L["left"], rows):
        box(d, S(left_x, y, left_x + box_w, y + box_h), title, sub, f_title, f_sub)
    for (title, sub), y in zip(L["right"], rows):
        box(d, S(right_x, y, right_x + box_w, y + box_h), title, sub, f_title, f_sub)

    # 中间的协议框
    cx1, cx2 = 355, 825
    cy1, cy2 = 65, 300
    d.rounded_rectangle(S(cx1, cy1, cx2, cy2), radius=12 * SCALE,
                        fill=ACCENT_BG, outline=ACCENT, width=2 * SCALE)
    mid_cx = (cx1 + cx2) / 2

    text_center(d, S(mid_cx, cy1 + 26), L["title"], f_mid_title, INK)
    text_center(d, S(mid_cx, cy1 + 62), L["sub"], f_mid_sub, MUTED)

    # 框内的小网：三个节点、三条边，右侧那条绿色加粗
    n_top = (mid_cx + 34, cy1 + 104)
    n_bl = (mid_cx - 40, cy1 + 176)
    n_br = (mid_cx + 40, cy1 + 176)
    for a, b in ((n_top, n_bl), (n_top, n_br)):
        d.line(S(*a, *b), fill=ARROW, width=2 * SCALE)
    d.line(S(*n_bl, *n_br), fill=GREEN, width=4 * SCALE)
    for pt, color in ((n_top, ARROW), (n_bl, ARROW), (n_br, GREEN)):
        d.ellipse(S(pt[0] - 6, pt[1] - 6, pt[0] + 6, pt[1] + 6), fill=color, outline=BG, width=2 * SCALE)
    text_center(d, S(mid_cx, cy1 + 198), L["direct"], f_small, GREEN)

    # 两侧箭头：每行一条，双向
    for y in rows:
        mid_y = y + box_h / 2
        two_way(d, S(left_x + box_w + 6, mid_y), S(cx1 - 6, mid_y))
        two_way(d, S(cx2 + 6, mid_y), S(right_x - 6, mid_y))

    # 分组标签紧贴各自列的底部
    col_bottom = rows[-1] + box_h
    text_center(d, S(left_x + box_w / 2, col_bottom + 18), L["left_group"], f_small, MUTED)
    text_center(d, S(right_x + box_w / 2, col_bottom + 18), L["right_group"], f_small, MUTED)
    mid_row_y = rows[1] + box_h / 2 + 18
    text_center(d, S((left_x + box_w + cx1) / 2, mid_row_y), L["both"], f_small, ARROW)
    text_center(d, S((cx2 + right_x) / 2, mid_row_y), L["both"], f_small, ARROW)

    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for lang, suffix in (("en", ""), ("zh", "-zh")):
        img = draw(lang)
        path = OUT / f"architecture{suffix}.png"
        img.save(path, optimize=True)
        print(f"  {path.name}  {img.size[0]}x{img.size[1]}")


if __name__ == "__main__":
    main()
