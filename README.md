# msp-site

The landing page for **[Model Sensing Protocol](https://github.com/hxh230802/MSP)** — a small,
dependency-free static site.

Two files do all the work: `index.html` and `style.css`. No build step, no CDN, no framework;
it follows the system light/dark preference and opens correctly from `file://`.

## Preview

```bash
python -m http.server 8899
# → http://127.0.0.1:8899/
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
