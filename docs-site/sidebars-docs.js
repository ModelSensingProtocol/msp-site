/**
 * Sidebars for the Documentation instance.
 *
 * Two passes over the same material, in reading order:
 *
 *   Getting started  — 跑起来（index, intro）
 *   The library      — 库自己的概念，严格按依赖链排：报文 → 节点与 preset → peer 视图
 *   Learn / Guides   — 机制与任务
 *   Operations / Going further / Reference / Examples
 *
 * 每页只引入一个新概念，并且只用前面已经解释过的概念——所以顺序不能随意调换。
 */
module.exports = {
  main: [
    {
      type: 'category',
      label: 'Getting started',
      collapsed: false,
      items: ['index', 'intro'],
    },
    {
      type: 'category',
      label: 'The library',
      collapsed: false,
      items: ['library/signal-and-path', 'library/node-and-preset', 'library/peer-view'],
    },
    {
      type: 'category',
      label: 'Learn',
      collapsed: false,
      items: ['architecture', 'roles', 'leases', 'signals', 'versioning'],
    },
    {
      type: 'category',
      label: 'Guides',
      collapsed: false,
      items: ['provide-tools', 'consume', 'proactive-events', 'tasks', 'debugging', 'testing'],
    },
    {
      type: 'category',
      label: 'Operations',
      items: ['lan', 'security'],
    },
    {
      type: 'category',
      label: 'Going further',
      items: ['multi-round', 'topology', 'performance'],
    },
    {
      type: 'category',
      label: 'Reference',
      items: ['faq', 'glossary', 'why-not-mcp'],
    },
    {
      type: 'category',
      label: 'Examples',
      items: [
        'examples/index',
        'examples/weather',
        'examples/downloader',
        'examples/editor',
        'examples/probe',
      ],
    },
  ],
};
