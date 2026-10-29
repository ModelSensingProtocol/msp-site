# msp-site

The MSP website: a hand-written landing page plus a documentation site built with **Docusaurus 3**.

```
/                  landing/         静态两页（英文 / 中文），无构建
/docs/             docs-site/       文档站：默认展示 2026-10-10 版本
/docs/next/                        未发布的下一版
/docs/spec/                        规范（独立的 docs 实例）
/docs/impl/ · /docs/design/        实现 / 设计（各自独立的 docs 实例）
```

## 为什么是 Docusaurus

之前用 MkDocs Material，为了拿版本化和多语言各加了一个插件，还踩了两处坑：
`mike` 要靠 gh-pages 分支加一层 `git archive` 导出；`mkdocs-static-i18n` 与
`navigation.instant` 不兼容，只能关掉。这两件事在 Docusaurus 里都是原生能力。

代价：仓库里多了一条 Node 工具链（`node_modules` 约 218 MB，构建 30–60 秒）。
换来的是：每个分区可以有完全独立的侧栏、版本下拉、语言下拉都是内置组件。

## 本地开发

```bash
# 文档站
cd docs-site
npm install
npm run start            # http://localhost:3000/msp-site/docs/

# landing（纯静态）
python -m http.server 8899
# → http://127.0.0.1:8899/landing/
```

构建产物：

```bash
cd docs-site && npm run build      # → docs-site/build
```

## 发布

`.github/workflows/pages.yml`：`npm ci` → `npm run build` → 把 `landing/` 放根、
`docs-site/build/` 放 `/docs/` → 上传 Pages。需要 **Settings → Pages → Source: GitHub Actions**。

## 版本化

```
docs/                    ← 当前开发版（Next）
versioned_docs/version-2026-10-10/   ← 已发布快照
versions.json            ← 版本清单，驱动右上角的下拉
```

发新修订时：

```bash
cd docs-site
npm run version 2026-12-01     # 把当前 docs/ 快照成新版本
```

注意：只有**主文档**实例带版本；`spec` / `impl` / `design` 三个实例不分版本——
Docusaurus 的 `docs:version` 只作用于默认实例。规范本身用 `schema/<修订号>/` 表达版本。

## 语言

中文是默认语言（`i18n.defaultLocale: zh-CN`），英文在 `/docs/en/` 下：

```
docs/intro.md                             中文正文
i18n/en/docusaurus-plugin-content-docs/current/intro.md   英文译文
```

目前只有文档首页与快速开始有英文译文，其余页面回落中文。

## landing 的两页怎么同步

`landing/zh/index.html` 由 `tools/localize_landing.py` 从英文页生成（约 50 条对照）。
改英文页后跑一次：

```bash
python tools/localize_landing.py
```

## Favicon

`landing/assets/favicon-*.png` 与 `docs-site/static/favicon.png` 由脚本生成：

```bash
pip install pillow
python tools/make_favicon.py
```

图案是文档页头与 landing 拓扑图用的同一套语义：深色圆角方块 + 白色中心节点 +
两个绿色在线邻居 + 一个灰色离线节点。

## 图不要撒谎

landing 的拓扑示意图画了四种边（实测 / 对端自报 / 推断 / 已知未连），因为 MSP 没有
gossip——一个节点只看得见自己的边。把它们并成一条线，就是这个站最容易撒的谎。

## License

MIT — see [LICENSE](LICENSE).

---

中文摘要：`landing/` 是手写静态页（英/中两版），`docs-site/` 是 Docusaurus 文档站。
`/docs/` 默认展示 2026-10-10，`/docs/next/` 是开发版，`/docs/spec|impl|design/` 是另外三个
独立实例。发新修订用 `npm run version <修订号>`。
