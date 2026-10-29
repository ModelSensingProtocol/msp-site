module.exports = {
  main: [
    'index',
    'base-protocol',
    'architecture',
    'capabilities',
    'discovery',
    'transports',
    'patterns',
    { type: 'category', label: 'Pattern details', items: ['patterns/request-reply', 'patterns/publish-subscribe', 'patterns/multi-round', 'patterns/task'] },
    'schema',
    'security',
    'interop',
  ],
};
