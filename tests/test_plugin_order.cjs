const test = require('node:test');
const assert = require('node:assert/strict');
const {comparePlugins, isColdmoon} = require('../pages/control/plugin-order.js');
test('series plugins sort before ordinary plugins even when disabled', () => {
  const rows=[{name:'other',title_zh:'普通插件',active:true},{name:'series',title_zh:'冷月系—新插件',active:false}];
  assert.deepEqual([...rows].sort(comparePlugins).map(p=>p.name),['series','other']);
});
test('new names need no allowlist and similarly named prose is not a series prefix', () => {
  assert.equal(isColdmoon({title_zh:' 冷月系—未来插件 '}),true);
  assert.equal(isColdmoon({title_zh:'兼容冷月系插件'}),false);
});
test('existing status and command ordering remains inside each group', () => {
  const rows=[{name:'off',title_zh:'冷月系—甲',active:false},{name:'no_commands',title_zh:'冷月系—乙',active:true},{name:'commands',title_zh:'冷月系—丙',active:true}];
  assert.deepEqual(rows.sort((a,b)=>comparePlugins(a,b,p=>p.name==='commands')).map(p=>p.name),['commands','no_commands','off']);
});
