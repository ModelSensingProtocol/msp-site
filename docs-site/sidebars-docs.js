/**
 * Sidebars for the Documentation instance.
 *
 * Structured the way MCP organises its docs: a beginner path first (Getting started → Learn →
 * Guides), then operations / going further / reference, with examples as their own group.
 * The group order is the reading order.
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
      label: 'Learn',
      collapsed: false,
      items: ['architecture', 'roles', 'leases', 'signals', 'versioning'],
    },
    {
      type: 'category',
      label: 'Guides',
      collapsed: false,
      items: ['provide-tools', 'consume', 'tasks', 'debugging', 'testing'],
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
