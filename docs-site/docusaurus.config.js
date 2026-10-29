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
  tagline: "本地软件是邻居，不是插座",
  url: "https://modelsensingprotocol.github.io",
  baseUrl: "/msp-site/docs/",
  trailingSlash: true,
  onBrokenLinks: "warn",
  onBrokenAnchors: "warn",
  favicon: "favicon.png",

  i18n: {
    defaultLocale: "zh-CN",
    locales: ["zh-CN", "en"],
    localeConfigs: {
      "zh-CN": { label: "中文", htmlLang: "zh-CN" },
      en: { label: "English", htmlLang: "en" },
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
            current: { label: "下一版", path: "next" },
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
  ],

  themeConfig: {
    image: "favicon.png",
    colorMode: { defaultMode: "light", disableSwitch: false, respectPrefersColorScheme: false },
    navbar: {
      title: "MSP",
      logo: { alt: "MSP", src: "favicon.png" },
      items: [
        { type: "docSidebar", sidebarId: "main", label: "文档", position: "left" },
        { type: "docSidebar", docsPluginId: "spec", sidebarId: "main", label: "规范", position: "left" },
        { type: "docSidebar", docsPluginId: "impl", sidebarId: "main", label: "实现", position: "left" },
        { type: "docSidebar", docsPluginId: "design", sidebarId: "main", label: "设计", position: "left" },
        { type: "docsVersionDropdown", position: "right" },
        { type: "localeDropdown", position: "right" },
        { href: "https://github.com/ModelSensingProtocol/msp-site", label: "GitHub", position: "right" },
      ],
    },
    footer: {
      style: "light",
      links: [],
      copyright: `Copyright © MSP — Model Sensing Protocol，MIT 许可 · 本站是文档，不是规范；规范性文本在仓库里。`,
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
