// @ts-check
const { themes } = require("prism-react-renderer");

/**
 * MSP 文档站（Docusaurus 3）。
 *
 * 站点在 Pages 上装在 /msp-site/docs/ 下，所以 baseUrl 带上这一段；
 * 四个分区各是一个独立的 docs 实例，因此顶栏可以像 MCP 那样分 tab，
 * 每个 tab 有自己的侧栏树：
 *
 *   /docs/            文档（wiki 八页，带版本）
 *   /docs/spec/…      规范
 *   /docs/impl/…      实现
 *   /docs/design/…    设计
 */
module.exports = {
  title: "MSP",
  tagline: "Local software is a neighbour, not a socket",
  url: "https://modelsensingprotocol.github.io",
  baseUrl: "/msp-site/docs/",
  trailingSlash: true,
  onBrokenLinks: "warn",
  onBrokenAnchors: "warn",
  favicon: "favicon.png",

  i18n: {
    defaultLocale: "en",
    locales: ["en", "zh"],
    localeConfigs: {
      en: { label: "English", htmlLang: "en" },
      zh: { label: "中文", htmlLang: "zh-CN" },
    },
  },

  presets: [
    [
      "classic",
      {
        docs: {
          path: "docs",
          routeBasePath: "/",
          sidebarPath: "./sidebars-docs.js",
          // 有版本快照后，当前 docs/ 是「下一版」；默认展示最新已发布版本
          lastVersion: "2026-10-10",
          versions: {
            current: { label: "Next", path: "next" },
            "2026-10-10": { label: "2026-10-10", banner: "none" },
          },
        },
        blog: false,
        theme: { customCss: "./src/css/custom.css" },
      },
    ],
  ],

  plugins: [
    [
      "@docusaurus/plugin-content-docs",
      { id: "spec", path: "spec", routeBasePath: "spec", sidebarPath: "./sidebars-spec.js" },
    ],
    [
      "@docusaurus/plugin-content-docs",
      { id: "impl", path: "impl", routeBasePath: "impl", sidebarPath: "./sidebars-impl.js" },
    ],
    [
      "@docusaurus/plugin-content-docs",
      { id: "design", path: "design", routeBasePath: "design", sidebarPath: "./sidebars-design.js" },
    ],
    [
      "@docusaurus/plugin-content-docs",
      { id: "case", path: "case", routeBasePath: "case", sidebarPath: "./sidebars-case.js" },
    ],
  ],

  themeConfig: {
    image: "favicon.png",
    colorMode: { defaultMode: "light", disableSwitch: false, respectPrefersColorScheme: false },
    navbar: {
      title: "MSP",
      // 点 logo 回 landing。必须用绝对地址：Docusaurus 会给 "/…" 自动加 baseUrl，
      // 写成 "/msp-site/" 会被拼成 /msp-site/docs/msp-site/。
      logo: { alt: "MSP", src: "favicon.png", href: "https://modelsensingprotocol.github.io/msp-site/" },
      items: [
        { type: "docSidebar", sidebarId: "main", label: "Docs", position: "left" },
        { type: "docSidebar", docsPluginId: "spec", sidebarId: "main", label: "Specification", position: "left" },
        { type: "docSidebar", docsPluginId: "impl", sidebarId: "main", label: "Implementations", position: "left" },
        { type: "docSidebar", docsPluginId: "design", sidebarId: "main", label: "Design", position: "left" },
        { type: "docSidebar", docsPluginId: "case", sidebarId: "main", label: "Case studies", position: "left" },
        { type: "docsVersionDropdown", position: "right" },
        { type: "localeDropdown", position: "right" },
        { href: "https://modelsensingprotocol.github.io/msp-site/", label: "Homepage", position: "right" },
        { href: "https://github.com/ModelSensingProtocol/msp-site", label: "GitHub", position: "right" },
      ],
    },
    footer: {
      style: "light",
      links: [
        {
          title: "MSP",
          items: [
            // 绝对地址：本地 npm start 时 landing 不在同源下，相对地址会 404
            { label: "Homepage", href: "https://modelsensingprotocol.github.io/msp-site/" },
          ],
        },
      ],
      copyright: `Copyright © MSP — Model Sensing Protocol. MIT licensed. This site is documentation, not the specification; the normative text lives in the repository.`,
    },
    prism: {
      theme: themes.github,
      darkTheme: themes.dracula,
      additionalLanguages: ["python", "bash", "json", "yaml", "toml"],
    },
    docs: { sidebar: { hideable: false, autoCollapseCategories: true } },
    tableOfContents: { minHeadingLevel: 2, maxHeadingLevel: 4 },
  },
};
