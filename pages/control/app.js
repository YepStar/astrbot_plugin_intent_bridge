(() => {
  'use strict';
  let state = null, tab = 'commands', selected = '', busy = false, pendingKey = '';
  const $ = id => document.getElementById(id);
  const message = (text, error = false) => { $('message').textContent = text; $('message').className = error ? 'error' : ''; };
  const node = (tag, text = '', cls = '') => { const el = document.createElement(tag); el.textContent = text; if (cls) el.className = cls; return el; };
  const api = async (method, path, body) => {
    const sdk = window.AstrBotPluginPage;
    if (!sdk) throw Error('请从 AstrBot 插件页面打开控制台');
    const out = method === 'GET' ? await sdk.apiGet(path) : await sdk.apiPost(path, body || {});
    if (out?.error || out?.status === 'error') throw Error(out.error || out.message || '请求失败');
    return out;
  };
  let confirmResolve = null, confirmFocus = null;
  function finishConfirm(accepted) {
    if (!confirmResolve) return;
    const resolve = confirmResolve; confirmResolve = null;
    $('confirm-backdrop').hidden = true; document.querySelector('.shell').inert = false;
    if (confirmFocus?.isConnected) confirmFocus.focus(); resolve(accepted);
  }
  function confirmCommand(command) {
    if (confirmResolve) return Promise.resolve(false);
    return new Promise(resolve => {
      confirmResolve = resolve; confirmFocus = document.activeElement;
      $('confirm-title').textContent = '确认接入指令';
      $('confirm-description').textContent = '将「' + command.plugin_title + '」的 /' + command.name + ' 接入自然语言判断？\n模型将可按你的请求调用，执行时仍检查原指令权限。接入不会立即执行指令。';
      document.querySelector('.shell').inert = true; $('confirm-backdrop').hidden = false; $('confirm-cancel').focus();
    });
  }
  $('confirm-cancel').onclick = () => finishConfirm(false);
  $('confirm-accept').onclick = () => finishConfirm(true);
  $('confirm-backdrop').onclick = e => { if (e.target === $('confirm-backdrop')) finishConfirm(false); };
  document.addEventListener('keydown', e => {
    if (!confirmResolve) return;
    if (e.key === 'Escape') { e.preventDefault(); finishConfirm(false); }
    else if (e.key === 'Tab') {
      if (e.shiftKey && document.activeElement === $('confirm-cancel')) { e.preventDefault(); $('confirm-accept').focus(); }
      else if (!e.shiftKey && document.activeElement === $('confirm-accept')) { e.preventDefault(); $('confirm-cancel').focus(); }
    }
  });
  function fillSettings() {
    const s = state.settings;
    $('enabled').checked = s.enabled; $('preflight').checked = s.enable_preflight; $('meme-save').checked = s.enable_meme_save;
    $('meme-category').value = s.meme_default_category; $('umos').value = s.allowed_umos.join('\n');
    $('provider').value = s.router_provider_id; $('timeout').value = s.router_timeout_seconds;
  }
  const matches = (r, q) => !q || [r.name, r.title_zh, r.plugin, r.description, r.comment_zh, r.key].join(' ').toLowerCase().includes(q);
  const commandRank = command => command.enabled ? 0 : command.supported ? 1 : 2;
  const commandRows = name => state.commands.filter(c => c.plugin === name).sort((a, b) => commandRank(a) - commandRank(b) || (a.title_zh || a.name).localeCompare(b.title_zh || b.name, 'zh-CN'));
  const visiblePlugins = () => state.plugins.filter(p => p.name !== 'astrbot_plugin_intent_bridge');
  // 已转换的命令统一放在“指令”，避免工具页出现重复开关和不一致状态。
  const nativeRows = name => state.tools.filter(t => t.plugin === name && !t.command_key);
  function renderParents(q) {
    const hasCommands = plugin => commandRows(plugin.name).some(command => command.supported);
    const parents = visiblePlugins().sort((a, b) => Number(b.active) - Number(a.active) || Number(hasCommands(b)) - Number(hasCommands(a)) || (a.title_zh || a.name).localeCompare(b.title_zh || b.name, 'zh-CN'));
    const visible = parents.filter(p => matches(p, q) || [...commandRows(p.name), ...nativeRows(p.name)].some(r => matches(r, q)));
    if (!visible.some(p => p.name === selected)) selected = visible[0]?.name || '';
    $('installed-count').textContent = parents.length;
    const list = $('plugin-list'); list.replaceChildren();
    for (const p of visible) {
      const commands = commandRows(p.name), tools = nativeRows(p.name);
      const button = node('button', '', 'plugin-item' + (p.active ? ' is-enabled' : ' is-disabled') + (selected === p.name ? ' is-selected' : ''));
      button.type = 'button'; button.dataset.plugin = p.name; button.setAttribute('aria-pressed', String(selected === p.name));
      const top = node('span', '', 'plugin-item-top'); top.append(node('span', p.active ? '●' : '○', 'plugin-dot'), node('span', p.title_zh || p.name, 'plugin-name'), node('span', '›', 'plugin-chevron'));
      button.append(top, node('span', p.name, 'plugin-id'), node('span', (p.active ? '已启用' : p.loaded ? '已停用' : '未载入') + ' · ' + commands.length + ' 指令 · ' + tools.length + ' 工具', 'plugin-meta'));
      button.onclick = () => { selected = p.name; render(); }; list.append(button);
    }
    if (!visible.length) list.append(node('p', '没有匹配的插件', 'empty'));
    return state.plugins.find(p => p.name === selected);
  }
  function render() {
    if (!state) return;
    $('plugins-count').textContent = state.plugins.filter(p => p.active && p.name !== '__core__').length;
    $('tools-count').textContent = state.tools.filter(t => t.routed).length;
    $('commands-count').textContent = state.commands.filter(c => c.available).length;
    $('updated').textContent = state.refreshed_at ? new Date(state.refreshed_at * 1000).toLocaleString('zh-CN', { hour12: false }) : '等待刷新';
    const q = $('search').value.trim().toLowerCase(), p = renderParents(q);
    const heading = $('plugin-heading'); heading.replaceChildren();
    if (p) {
      const title = node('div', '', 'plugin-heading-title'); title.append(node('h3', p.title_zh || p.name), node('span', p.active ? '已启用' : p.loaded ? '已停用 · 只读' : '未载入 · 只读', 'tag' + (p.active ? ' on' : '')));
      heading.append(title, node('code', p.name + (p.version ? ' · v' + p.version : ''), 'identifier'));
      if (!p.active) heading.append(node('p', '请到 AstrBot「系统 → 插件」启用并成功载入，再刷新这里。', 'inactive-hint'));
    } else heading.append(node('h3', '选择一个插件'));
    $('filter').disabled = tab === 'recent';
    const notes = { commands: '只改变指令的自然语言接入状态；原插件的启停、权限和交互要求仍然有效。', tools: '原生工具按会话和人格再次筛选；暂停只影响意图路由。已转换指令请在“指令”页管理。', recent: '全部插件最近的判断与执行状态；不保存聊天正文。纠错重匹配只由你的明确反馈触发。' };
    $('list-note').textContent = notes[tab];
    const filter = $('filter').value;
    let rows = tab === 'recent' ? [...state.recent].reverse() : p ? tab === 'commands' ? commandRows(p.name) : nativeRows(p.name) : [];
    rows = rows.filter(r => (tab === 'recent' || matches(p || {}, q) || matches(r, q)) && (tab === 'recent' || filter === 'all' || (filter === 'on' ? r.available || r.routed : !(r.available || r.routed))));
    const list = $('list'); list.replaceChildren();
    if (!rows.length) {
      list.append(node('div', tab === 'recent' ? '尚无执行记录，发送请求后刷新查看。' : tab === 'commands' ? '该插件没有符合条件的指令。部分插件仅提供原生工具，可切换上方标签查看。' : '该插件没有符合条件的原生工具。', 'empty')); return;
    }
    for (const r of rows) {
      const row = node('article', '', 'row'), body = node('div', '', 'row-main');
      let title = r.title_zh || r.name, identifier = r.name, desc = r.comment_zh || r.description || '原插件未提供说明', status = '', on = false;
      if (tab === 'commands') {
        identifier = '/' + r.name; on = r.available;
        status = !p.active ? '插件未启用 · 只读' : on ? '已接入' : r.enabled ? '已授权 · 当前不可用' : !r.supported ? '暂不支持接入' : '未接入';
      } else if (tab === 'tools') {
        on = r.routed; status = r.blocked ? '遵循主 Agent 原有规则' : !r.active ? '工具已停用' : on ? '已纳入路由' : '路由已暂停';
      } else {
        title = (r.tools || []).map(n => state.tools.find(t => t.name === n)?.title_zh || n).join('、') || '普通对话';
        identifier = (r.tools || []).join(', '); desc = new Date(r.at * 1000).toLocaleString('zh-CN', { hour12: false });
        status = ({ executed: '执行', rematched: '纠错重匹配', repaired: '格式修复', classified: '意图判断' }[r.phase] || r.phase) + ' · ' + (r.status || r.mode || '完成');
      }
      body.append(node('div', title, 'row-title'), node('code', identifier, 'identifier'), node('div', desc, 'row-description'), node('span', status, 'tag' + (on ? ' on' : '')));
      if (r.reason && tab === 'commands') body.append(node('p', r.reason, 'reason'));
      if (r.translation_source === 'model_cache') body.append(node('span', '自动中文说明', 'translation-label'));
      if (r.description && r.description !== desc) {
        const detail = node('details', '', 'original-description'); detail.append(node('summary', '原始说明'), node('p', r.description)); body.append(detail);
      }
      row.append(body);
      if (tab === 'commands' && p.active) {
        const button = node('button', busy && pendingKey === r.key ? '保存中…' : r.enabled ? '撤销接入' : '接入', 'action' + (r.enabled ? ' revoke' : ''));
        button.type = 'button'; button.disabled = busy || !state.converter_available || !r.plugin_active || (!r.enabled && !r.supported);
        button.onclick = async () => { if (busy) return; if (!r.enabled && !(await confirmCommand(r))) { message('已取消，接入状态未修改。'); return; } await mutate('commands', { key: r.key, enabled: !r.enabled }); }; row.append(button);
      }
      if (tab === 'tools' && p.active && !r.blocked) {
        const button = node('button', on ? '暂停路由' : '接入路由', 'action'); button.type = 'button'; button.disabled = busy || !r.active;
        button.onclick = () => mutate('tools', { name: r.name, enabled: !on }); row.append(button);
      }
      list.append(row);
    }
  }
  async function load(refresh = false, fill = false) { state = await api(refresh ? 'POST' : 'GET', refresh ? 'refresh' : 'status'); if (fill) fillSettings(); render(); }
  async function mutate(path, body) {
    if (busy) return; busy = true; pendingKey = body.key || body.name || ''; message('正在保存接入设置…'); render();
    try { await api('POST', path, body); await load(); message('已保存，后续消息会使用新设置。'); }
    catch (e) { message(e.message || '操作失败', true); }
    finally { busy = false; pendingKey = ''; render(); }
  }
  $('refresh').onclick = async () => {
    if (busy) return; busy = true; $('refresh').disabled = true; message('正在重新扫描本机插件、同步指令并翻译新增外文说明…'); render();
    try {
      await load(true); const t = state.translation || {};
      message('刷新完成：' + state.plugins.filter(p => p.name !== '__core__').length + ' 个插件。' + (t.translated ? '新增 ' + t.translated + ' 条中文说明。' : '') + (t.pending ? '还有 ' + t.pending + ' 条待翻译，请检查分类模型后再次刷新。' : ''));
    } catch (e) { message(e.message || '刷新失败', true); }
    finally { busy = false; $('refresh').disabled = false; render(); }
  };
  for (const button of document.querySelectorAll('[data-tab]')) button.onclick = () => {
    tab = button.dataset.tab; for (const other of document.querySelectorAll('[data-tab]')) other.setAttribute('aria-pressed', String(other === button)); render();
  };
  $('search').oninput = render; $('filter').onchange = render;
  $('settings').onsubmit = async e => {
    e.preventDefault(); if (busy) return; busy = true;
    const body = { enabled: $('enabled').checked, enable_preflight: $('preflight').checked, enable_meme_save: $('meme-save').checked, meme_default_category: $('meme-category').value.trim(), allowed_umos: $('umos').value.split('\n').map(v => v.trim()).filter(Boolean), router_provider_id: $('provider').value.trim(), router_timeout_seconds: Number($('timeout').value) };
    const button = e.target.querySelector('button[type=submit]'); button.disabled = true; render();
    try { await api('POST', 'settings', body); await load(false, true); message('路由设置已保存。'); }
    catch (err) { message(err.message || '保存失败', true); }
    finally { busy = false; button.disabled = false; render(); }
  };
  (async () => {
    try { if (!window.AstrBotPluginPage) throw Error('请从 AstrBot → 插件 → 自然意图与插件整合 → 控制台打开'); await window.AstrBotPluginPage.ready(); await load(false, true); message('选择左侧插件查看指令；右上刷新会重新扫描并自动补充中文说明。'); }
    catch (e) { message(e.message || '读取失败', true); $('list').append(node('div', '无法读取能力，请重新登录 AstrBot 后打开本页。', 'empty')); }
  })();
})();
