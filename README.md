# msp-site

The MSP website.

- **`landing/`** — hand-written static pages (`/` English, `/zh/` Chinese). No build step.
- **`docs-site/`** — the documentation site, built with **Docusaurus 3**. Five independent docs
  instances behind one navbar: Documentation, Specification, Implementations, Design, Case studies.

Live: <https://modelsensingprotocol.github.io/msp-site/>

```
/                        landing/                    手写静态页（英文）
/zh/                     landing/zh/                 手写静态页（中文）
/docs/                   docs-site/                 文档，默认展示 2026-10-10
/docs/next/                                          未发布的下一版
/docs/spec/                                          规范
/docs/impl/  /docs/design/  /docs/case/               实现 / 设计 / 案例
/docs/zh/                                            以上全部的中文版
```

## Quick start

```bash
cd docs-site
npm install
npm run start      # → http://localhost:3000/msp-site/docs/
```

Landing page (plain files, no toolchain):

```bash
python -m http.server 8899
# → http://127.0.0.1:8899/landing/
```

Build:

```bash
cd docs-site && npm run build     # → docs-site/build
```

## What lives where

| Path | What it is | Language |
|---|---|---|
| `docs-site/docs/` | Documentation — the working guide | English (source) |
| `docs-site/spec/` | Specification chapters | English (source) |
| `docs-site/impl/` | Implementation status | English (source) |
| `docs-site/design/` | Design decisions | English (source) |
| `docs-site/case/` | Case studies of real adopters | English (source) |
| `docs-site/i18n/zh/docusaurus-plugin-content-docs-*/` | Chinese translations, one tree per instance | 中文 |
| `docs-site/versioned_docs/version-2026-10-10/` | Frozen snapshot served at `/docs/` | — |
| `landing/`, `landing/zh/` | The landing page, both languages | — |
| `tools/` | `make_favicon.py`, `localize_landing.py` | — |
| `docs-site/tools/check_examples.py` | Runs the example nodes for real | — |

Content is copied from the main repository (`docs/wiki/`, `docs/spec/`, `docs/DESIGN.md`); the
main repository stays the source of truth, this one is the published form.

## Everyday tasks

**Add a page.** Drop a `.md` in the right instance, then add it to that instance's
`sidebars-*.js`. Nothing else — the navbar tabs are already wired.

**Add a case study.** Put a page in `docs-site/case/`, add it to `sidebars-case.js`, and keep to
what is checkable: the node id, the tools and their arguments, how it is enabled, whether it is on
by default, and what it does *not* do.

**Translate a page.** Copy it to
`docs-site/i18n/zh/docusaurus-plugin-content-docs-<instance>/current/<same-path>.md` and translate.
Missing translations fall back to English.

**Change an example.** Edit `docs-site/static/examples/*.py`, then run the checks (below). Pages in
`docs/examples/` embed the same code, so keep them in step.

## Checks

```bash
# the docs build, with broken-link warnings surfaced
cd docs-site && npm run build

# the example nodes actually run: tool call, signal handoff, observer
cd docs-site && PYTHONPATH=../src python tools/check_examples.py
```

The second one is not decoration. It starts `weather.py`, calls `get_weather` and asserts the
result; starts `downloader.py` + `editor.py` and asserts the subscriber really received the
completion signal; and checks that the observer can see a peer.

## Versioning

`/docs/` serves the **2026-10-10** snapshot; unreleased work lives in `docs/` and is served at
`/docs/next/`. To freeze the current state as a new revision:

```bash
cd docs-site
# 1. temporarily drop lastVersion/versions from docusaurus.config.js
# 2. snapshot:
npm run version 2027-01-01
# 3. put those two settings back, pointing at the new revision
```

Step 1 matters: `docs:version` fails if the config names a version that does not exist yet.

Only the Documentation instance is versioned — `docs:version` applies to the default instance.
The specification carries its own revision elsewhere (`schema/<revision>/` in the main repository).

## Languages

English is the default locale; Chinese lives under `/docs/zh/` and is provided per docs instance
through `i18n/zh/`. The navbar labels are translated in
`i18n/zh/docusaurus-theme-classic/navbar.json` — the key is `item.label.<exact English label>`, and
a mismatch fails silently, so verify the tab actually changes.

## Landing page

Two hand-written pages. `landing/zh/index.html` is generated from the English one:

```bash
python tools/localize_landing.py
```

Run it after editing the English page, or the two drift apart.

## Favicon

```bash
pip install pillow
python tools/make_favicon.py
```

Generates `favicon-{16,32,48,64,180,512}.png` and `favicon.ico` into `docs-site/static/` and
`landing/assets/`. The mark is a square (no rounded corners): a centre node, three satellites, and
one **direct link** between two satellites — the node-to-node path that does not go through the
centre.

## Deploy

`.github/workflows/pages.yml`: `npm ci` → `npm run build`, then assemble `landing/` at the site root
and `docs-site/build/` under `/docs/`, and upload that. Needs **Settings → Pages → Source: GitHub
Actions** once.

## Costs, stated plainly

- A second toolchain in this repository: `node_modules` is ~218 MB and a cold build takes ~30–60 s
  (MkDocs did 48 pages in 2–8 s).
- `docs:version` only versions the default instance, so Specification / Implementations / Design /
  Case studies are unversioned by design.
- The landing page is duplicated by design; the generator keeps the two in step.

We took these on because versioned docs and a language switcher were two plugins plus two
workarounds under MkDocs Material, and both are native here.

## Don't let the diagram lie

The landing page draws four kinds of edges — observed, reported by a peer, inferred, and known but
not connected — because MSP has no gossip: a node only ever sees its own edges. Collapsing them into
one line would be the easiest lie this site could tell.

## License

MIT — see [LICENSE](LICENSE).

---

中文摘要：`landing/` 是手写静态页（英 / 中两版），`docs-site/` 是 Docusaurus 文档站，
含文档 / 规范 / 实现 / 设计 / 案例五个独立实例，英文为默认语言、中文在 `i18n/zh/`。
`/docs/` 默认展示 2026-10-10，`/docs/next/` 是开发版。
改示例后请跑 `docs-site/tools/check_examples.py`——它真的会起节点、调工具、等信号。
