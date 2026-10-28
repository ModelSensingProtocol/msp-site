"""把 content/ 的 Markdown 渲染成 MCP 文档站那样的分版本多页文档。

    python tools/build.py          # → docs/<REV>/

自己实现而不引 markdown 库：站点要保持零依赖零构建，而且只用到一小撮语法
（标题 / 代码块 / 表格 / 列表 / 引用 / 行内代码与链接）。生成结果可预期，
也不会有人因为装不上依赖而卡住。
"""

from __future__ import annotations

import html as H
import re
from pathlib import Path

REV = "2026-10-10"                 # 协议修订号，与 schema/2026-10-10 对齐
ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
OUT = ROOT / "docs"

# (分组, slug, 标题, 源文件)
PAGES = [
    ("Getting started", "intro", "Introduction", "01-getting-started.md"),
    ("Learn", "architecture", "Architecture & concepts", "02-concepts.md"),
    ("Develop", "provide-tools", "Provide tools and signals", "03-provide.md"),
    ("Develop", "consume", "Discover, call, subscribe", "04-consume.md"),
    ("Learn", "why-not-mcp", "Why MSP, not MCP", "07-positioning.md"),
    ("Reference", "faq", "FAQ & troubleshooting", "05-faq.md"),
    ("Reference", "glossary", "Glossary", "06-glossary.md"),
]

SPEC_URL = "https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md"
BLOB = "https://github.com/hxh230802/MSP/blob/master"
TREE = "https://github.com/hxh230802/MSP/tree/master"

# wiki 页面名 → 站点页面；其余 .md 指向 GitHub 原文
WIKI_MAP = {
    "01-getting-started.md": "intro.html",
    "02-concepts.md": "architecture.html",
    "03-provide.md": "provide-tools.html",
    "04-consume.md": "consume.html",
    "05-faq.md": "faq.html",
    "06-glossary.md": "glossary.html",
    "07-positioning.md": "why-not-mcp.html",
}


def fix_href(href: str) -> str:
    """把 wiki 里相对仓库/相对页面的链接，改写成站点内页面或 GitHub 绝对地址。"""
    if href.startswith(("http://", "https://", "#", "mailto:")):
        return href
    frag = ""
    if "#" in href:
        href, frag = href.split("#", 1)
        frag = "#" + frag
    if href in WIKI_MAP:
        return WIKI_MAP[href] + frag

    path = href
    while path.startswith("../"):
        path = path[3:]
    if path.endswith("/"):
        return TREE + "/" + (("docs/" + path) if path.startswith("spec/") else path)
    if path.startswith("spec/"):
        return BLOB + "/docs/" + path + frag
    if path.startswith("src/"):
        return BLOB + "/" + path + frag
    if path.endswith(".md"):
        return BLOB + "/docs/" + path + frag
    return href + frag


def rewrite_links(html: str) -> str:
    return re.sub(r'href="([^"]+)"', lambda m: 'href="%s"' % fix_href(m.group(1)), html)
SITE_REPO = "https://github.com/ModelSensingProtocol/msp-site"

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — MSP documentation</title>
<link rel="stylesheet" href="{css}">
</head>
<body class="docs">
<header class="nav">
  <a class="brand" href="{home}"><span>MSP</span></a>
  <span class="ver">docs · {rev}</span>
  <nav><a href="{home}">Home</a><a href="{spec}">Specification</a>
      <a href="{site}" target="_blank" rel="noreferrer">Source</a></nav>
</header>
<div class="layout">
  <aside class="sidebar">{sidebar}</aside>
  <main class="content">
    <p class="crumb"><a href="{home}">Home</a> / {crumb}</p>
{body}
    <nav class="pager">{pager}</nav>
  </main>
</div>
</body>
</html>
"""


def slugify(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "-", text.strip().lower()).strip("-") or "section"


def inline(text: str) -> str:
    codes: list[str] = []

    def stash(m):
        codes.append(m.group(1))
        return "\x00%d\x00" % (len(codes) - 1)

    text = re.sub(r"`([^`]+)`", stash, text)
    text = H.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    for i, code in enumerate(codes):
        text = text.replace("\x00%d\x00" % i, "<code>" + H.escape(code) + "</code>")
    return text


def convert(md: str) -> str:
    lines, out, i = md.splitlines(), [], 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            i += 1
            body = []
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + H.escape("\n".join(body)) + "</code></pre>")
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 1:
                out.append("<h1>%s</h1>" % inline(text))
            else:
                out.append('<h%d id="%s">%s</h%d>' % (level, slugify(text), inline(text), level))
            i += 1
            continue

        if line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|", lines[i + 1]):
            head = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            parts = ["<table><thead><tr>"] + ["<th>%s</th>" % inline(c) for c in head]
            parts.append("</tr></thead><tbody>")
            for r in rows:
                parts.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in r) + "</tr>")
            parts.append("</tbody></table>")
            out.append("".join(parts))
            continue

        if line.startswith(">"):
            body = []
            while i < len(lines) and lines[i].startswith(">"):
                body.append(lines[i].lstrip("> ").rstrip())
                i += 1
            out.append("<blockquote>" + convert("\n".join(body)) + "</blockquote>")
            continue

        if re.match(r"^\s*([-*]|\d+\.)\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.", line))
            items = []
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % inline(x) for x in items), tag))
            continue

        if re.match(r"^\s*---+\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        if not line.strip():
            i += 1
            continue

        para = []
        while i < len(lines) and lines[i].strip() and not re.match(
            r"^(#{1,4}\s|```|>|\s*([-*]|\d+\.)\s|\s*\||\s*---+\s*$)", lines[i]
        ):
            para.append(lines[i].strip())
            i += 1
        out.append("<p>%s</p>" % inline(" ".join(para)))
    return "\n".join(out)


def sidebar(current: str) -> str:
    groups, parts = [], []
    for group, slug, title, _ in PAGES:
        if group not in groups:
            groups.append(group)
            parts.append("<p class='group'>%s</p>" % group)
        cls = " class='on'" if slug == current else ""
        parts.append("<li><a%s href=\"%s.html\">%s</a></li>" % (cls, slug, title))
        if PAGES.index([p for p in PAGES if p[1] == slug][0]) == len(PAGES) - 1:
            parts.append("</ul>")
    # 简单起见：每组的 <ul> 在组切换时开合
    html_parts, open_ul, last_group = [], False, None
    for group, slug, title, _ in PAGES:
        if group != last_group:
            if open_ul:
                html_parts.append("</ul>")
            html_parts.append("<p class='group'>%s</p><ul>" % group)
            open_ul, last_group = True, group
        cls = " class='on'" if slug == current else ""
        html_parts.append("<li><a%s href=\"%s.html\">%s</a></li>" % (cls, slug, title))
    if open_ul:
        html_parts.append("</ul>")
    return "".join(html_parts)


def render(title: str, crumb: str, body: str, pager: str, css: str, home: str, sidebar_html: str) -> str:
    return HEAD.format(
        title=title, rev=REV, css=css, home=home, spec=SPEC_URL, site=SITE_REPO,
        sidebar=sidebar_html, crumb=crumb, body=body, pager=pager,
    )


def main() -> None:
    out_dir = OUT / REV
    out_dir.mkdir(parents=True, exist_ok=True)

    for idx, (_group, slug, title, src) in enumerate(PAGES):
        body = rewrite_links(convert((CONTENT / src).read_text(encoding="utf-8")))
        prev_link = '<a href="%s.html">← %s</a>' % (PAGES[idx - 1][1], PAGES[idx - 1][2]) if idx else ""
        next_link = ('<a href="%s.html">%s →</a>' % (PAGES[idx + 1][1], PAGES[idx + 1][2])
                     if idx + 1 < len(PAGES) else "")
        pager = "<div class='prev'>%s</div><div class='next'>%s</div>" % (prev_link, next_link)
        html = render(title, title, body, pager, "../../style.css", "../../index.html", sidebar(slug))
        (out_dir / (slug + ".html")).write_text(html, encoding="utf-8")
        print("  docs/%s/%s.html" % (REV, slug))

    links = "".join(
        '<li><a href="%s.html"><strong>%s</strong></a><br><span class="muted">%s</span></li>'
        % (slug, title, src)
        for _g, slug, title, src in PAGES
    )
    body = (
        "<h1>MSP documentation</h1>"
        "<p class='muted'>Protocol revision <code>%s</code> — the same revision the schema "
        "under <code>schema/%s/</code> carries.</p><ul class='doclist'>%s</ul>" % (REV, REV, links)
    )
    html = render("Documentation", "Documentation", body, "", "../../style.css", "../../index.html", sidebar(""))
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print("  docs/%s/index.html" % REV)


if __name__ == "__main__":
    main()
