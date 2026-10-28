# msp-site

The landing page for **[Model Sensing Protocol](https://github.com/hxh230802/MSP)** — a small,
dependency-free static site.

Two files do all the work: `index.html` and `style.css`. No build step, no CDN, no framework;
it follows the system light/dark preference and opens correctly from `file://`.

## Documentation

`/docs/<revision>/` is versioned by **protocol revision** — the same identifier the schema carries
(`2026-10-10` today), mirroring how `modelcontextprotocol.io` prefixes its docs with the spec date.

```
content/*.md          ← mirror of docs/wiki/ in the main repository (the source of truth)
tools/build.py        ← Markdown subset → HTML, one page per topic
tools/sync-content.sh ← copy content/ from the main repository, then rebuild
docs/2026-10-10/*.html← generated, committed (the site stays build-free)
```

Rebuild after editing `content/`:

```bash
python tools/build.py
```

## Layout

```
landing/            the hand-written landing page (served at /)
docs/               Markdown sources for the docs section
mkdocs.yml          MkDocs Material config (search, TOC, code copy, dark mode)
_docs/              build output (git-ignored)
```

The docs are built with **MkDocs Material** rather than a hand-rolled generator, because search,
on-page TOC and a version switcher are the parts a reader notices and a static generator does not
give you for free. `mike` is the next step — it publishes `/docs/<protocol-revision>/…`, matching
how `modelcontextprotocol.io` versions its docs.

## Preview

```bash
pip install mkdocs-material
mkdocs serve                 # docs at http://127.0.0.1:8000/
python -m http.server 8899   # landing at http://127.0.0.1:8899/landing/
```

## Deploy

The repository publishes itself: `.github/workflows/pages.yml` uploads the repository root as the
Pages artifact. It needs **Settings → Pages → Source: GitHub Actions** once.

## What it says, and where that comes from

| Section | Source of truth |
|---|---|
| Why MSP / capabilities | `docs/POSITIONING.md` in the main repository |
| Start building | the quickstart in `docs/wiki/`, whose code is executed as a test |
| Implementations | the real state of each repository |
| MSP is not MCP | the comparison table in `docs/POSITIONING.zh-CN.md` |

> Some links point at the main repository, which is **private at the time of writing**. They work for
> people with access and will work for everyone once it is published.

## Editing

Keep the diagram honest: it draws four kinds of edges (observed / reported / inferred / known but
not connected) because MSP has no gossip — a node only ever sees its own edges. Collapsing them
into one line would be the easiest way to lie about the network.

## License

MIT — see [LICENSE](LICENSE).

---

中文：这是 MSP 的门面页，纯静态两文件，零构建。预览 `python -m http.server 8899`；
发布靠仓库自带的 Pages 工作流。图里的连线分四种（实测 / 自报 / 推断 / 已知未连），
因为 MSP 没有 gossip——一个节点只看得到自己的边。
