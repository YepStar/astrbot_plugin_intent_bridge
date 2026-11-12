(function (root) {
  'use strict';
  const title = plugin => String(plugin.title_zh || plugin.name || '').trim();
  const isColdmoon = plugin => title(plugin).startsWith('冷月系—');
  function comparePlugins(a, b, hasCommands = () => false) {
    return Number(isColdmoon(b)) - Number(isColdmoon(a))
      || Number(Boolean(b.active)) - Number(Boolean(a.active))
      || Number(Boolean(hasCommands(b))) - Number(Boolean(hasCommands(a)))
      || title(a).localeCompare(title(b), 'zh-CN');
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { isColdmoon, comparePlugins };
  else root.IntentBridgePluginOrder = { isColdmoon, comparePlugins };
})(typeof globalThis !== 'undefined' ? globalThis : this);
