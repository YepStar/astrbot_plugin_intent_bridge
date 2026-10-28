"""Dashboard-authenticated discovery and explicit command integration controls."""
import asyncio
import time
import sys

from quart import jsonify, request
from astrbot.core.star.star import star_map

from .inventory import installed_plugins, registered_commands
from .translation import TranslationStore
from .routing import EXCLUDED
from .annotations import tool_annotation, command_annotation, plugin_title


class ControlPanel:
    def __init__(self, bridge):
        self.bridge = bridge
        self.refreshed_at = None
        self.lock = asyncio.Lock()
        self.translations = TranslationStore()
        self.inventory_root = None

    def converter(self):
        for s in self.bridge.context.get_all_stars():
            if s.activated and s.name == 'astrbot_plugin_command_tools':
                return s.star_cls
        return None

    async def snapshot(self, refresh=False):
        b = self.bridge
        converter = self.converter()
        if refresh and converter:
            await converter.refresh()
        plugins, static_commands = installed_plugins(b.context.get_all_stars(), self.inventory_root)
        plugin_map = {p['name']: p for p in plugins}
        commands = {row['key']: row for row in static_commands}
        catalog = registered_commands()
        if converter:
            catalog.update(converter.catalog())
        if catalog:
            factory = getattr(sys.modules.get(type(converter).__module__), 'CommandTool', None)
            for key, entries in catalog.items():
                handler, filt = entries[0]
                star = star_map.get(handler.handler_module_path)
                tool = converter.tools.get(key) if converter else None
                reason = converter.unsupported.get(key, '') if converter else '指令工具转换器未启用，暂时只能查看。'
                supported = len(entries) == 1 and not reason
                if len(entries) != 1:
                    reason = '同名指令存在冲突，不能接入。'
                if key.startswith('astrbot_plugin_command_tools:'):
                    supported, reason = False, '指令转换器自身的管理指令仅展示，请使用原始管理入口。'
                if (getattr(handler, 'handler_module_path', '') == 'astrbot.builtin_stars.builtin_commands.main'
                        and getattr(handler, 'handler_name', '') in {'reset', 'stop', 'new_conv', 'update_dashboard'}):
                    supported, reason = False, '会话或程序生命周期指令暂不支持转换。'
                if supported and factory:
                    try:
                        factory(converter, key, handler, filt)
                    except (ValueError, TypeError, NotImplementedError):
                        supported, reason = False, '参数或交互形式暂不支持转换；请使用原插件指令。'
                parent, name = key.split(':', 1)
                active = bool(star and star.activated)
                commands[key] = {'key': key, 'plugin': parent, 'name': name,
                    'description': str(handler.desc or '')[:700],
                    'enabled': converter.is_allowed(key) if converter else False, 'available': bool(tool and tool.active and active),
                    'plugin_active': active, 'supported': supported, 'registered': True,
                    'reason': reason}
        for row in commands.values():
            row.update(command_annotation(row['plugin'], row['name'], row['description']))
            row['plugin_title'] = plugin_map.get(row['plugin'], {}).get('title_zh', plugin_title(row['plugin']))
            row['available'] = row['available'] and row['plugin_active']
        disabled = set(b.config.get('disabled_tools', []))
        tools = []
        for t in b.context.get_llm_tool_manager().func_list:
            owner = star_map.get(getattr(t, 'handler_module_path', None))
            command_key = getattr(t, 'key', None)
            parent = command_key.split(':', 1)[0] if isinstance(command_key, str) and ':' in command_key else owner.name if owner else '__core__'
            active = bool(t.active and (not owner or owner.activated))
            tools.append({'name': t.name, 'description': str(t.description or '')[:700],
                          **tool_annotation(t.name, t.description, command_key),
                          'plugin_title': plugin_map.get(parent, {}).get('title_zh', plugin_title(parent)),
                          'plugin': parent, 'active': active, 'command_key': command_key,
                          'routed': active and t.name not in EXCLUDED and t.name not in disabled,
                          'blocked': t.name in EXCLUDED})
        # 没有插件元数据的核心工具独立分组；已安装但无指令的插件仍然保留。
        if any(t['plugin'] == '__core__' for t in tools):
            plugins.append({'name': '__core__', 'title_zh': 'AstrBot 核心工具', 'active': True,
                            'version': '', 'loaded': True, 'description': '系统提供的原生工具'})
        if refresh:
            await self.translations.refresh(b, list(commands.values()) + tools)
            self.refreshed_at = int(time.time())
        for row in list(commands.values()) + tools:
            self.translations.apply(row)
        return {'refreshed_at': self.refreshed_at, 'plugins': plugins,
            'commands': sorted(commands.values(), key=lambda r: r['key']), 'tools': tools,
            'translation': self.translations.status,
            'settings': {k:b.config.get(k,d) for k,d in {
                'enabled': True, 'enable_preflight': True, 'enable_meme_save': True,
                'meme_default_category': '用户收藏', 'allowed_umos': [],
                'router_provider_id': '', 'router_timeout_seconds': 12}.items()},
            'recent': list(b._route_history)[-30:], 'converter_available': converter is not None}

    async def status(self):
        return jsonify(await self.snapshot())

    async def refresh(self):
        async with self.lock:return jsonify(await self.snapshot(True))

    async def settings(self):
        body=await request.get_json()
        if not isinstance(body,dict):return jsonify({'error':'配置必须为对象'}),400
        allowed={'enabled','enable_preflight','enable_meme_save','meme_default_category',
                 'allowed_umos','router_provider_id','router_timeout_seconds'}
        if set(body)-allowed:return jsonify({'error':'未知配置项'}),400
        for k,v in body.items():
            if k in {'enabled','enable_preflight','enable_meme_save'} and type(v) is not bool:
                return jsonify({'error':'开关值必须为布尔值'}),400
            if k=='allowed_umos' and (not isinstance(v,list) or len(v)>100 or any(
                    not isinstance(x,str) or ':FriendMessage:' not in x or len(x)>200 for x in v)):
                return jsonify({'error':'请填写完整私聊UMO，每行一个'}),400
            if k=='router_timeout_seconds' and (type(v) is not int or not 3<=v<=60):
                return jsonify({'error':'分类超时应为3—60秒'}),400
            if k in {'meme_default_category','router_provider_id'} and (not isinstance(v,str) or len(v)>100):
                return jsonify({'error':'文本配置无效'}),400
            if k=='meme_default_category' and (not v.strip() or len(v)>48 or any(x in v for x in ('/','\\')) or v in {'.','..'}):
                return jsonify({'error':'收藏分类必须为单个安全目录名'}),400
        async with self.lock:
            old=dict(self.bridge.config)
            try:
                self.bridge.config.update(body);self.bridge.config.save_config()
            except Exception:
                self.bridge.config.clear();self.bridge.config.update(old)
                return jsonify({'error':'保存失败，配置已回滚'}),500
        return jsonify({'ok':True})

    async def command(self):
        body=await request.get_json()
        if not isinstance(body,dict) or set(body)!={'key','enabled'} or type(body['enabled']) is not bool:
            return jsonify({'error':'参数无效'}),400
        converter=self.converter()
        if converter is None:return jsonify({'error':'指令转换器未启用'}),409
        key=body['key']
        if not isinstance(key,str) or key not in converter.catalog():
            return jsonify({'error':'指令已变化，请刷新'}),409
        if ':' not in key:return jsonify({'error':'只能逐条授权完整指令'}),400
        async with self.lock:
            async with converter._allowlist_lock:
                catalog = converter.catalog()
                entries = catalog.get(key, [])
                if not entries:
                    return jsonify({'error': '指令已变化，请刷新'}), 409
                star = star_map.get(entries[0][0].handler_module_path)
                if not star or not star.activated:
                    return jsonify({'error': '插件未启用；请到 AstrBot 系统 → 插件中修改。'}), 409
                if body['enabled']:
                    snapshot = await self.snapshot()
                    row = next((r for r in snapshot['commands'] if r['key'] == key), None)
                    if not row or not row['supported']:
                        return jsonify({'error': row['reason'] if row else '指令不可接入'}), 409
                parent = key.split(':', 1)[0]
                old = list(converter.config.get('allowed_commands', []))
                new = [k for k in old if k != key]
                if not body['enabled'] and parent in new:
                    # 整包授权展开为当前其他指令，才能准确撤销单条，且不授权未来未知指令。
                    new.remove(parent)
                    new.extend(k for k in catalog if k.startswith(parent + ':') and k != key)
                if body['enabled']:
                    new.append(key)
                new = list(dict.fromkeys(new))
                try:
                    converter.config['allowed_commands'] = new
                    converter.config.save_config()
                    converter.allowed = set(new)
                    await converter.refresh()
                except Exception:
                    converter.config['allowed_commands'] = old
                    converter.allowed = set(old)
                    try:
                        converter.config.save_config()
                        await converter.refresh()
                    except Exception:
                        return jsonify({'error': '更新失败且回滚刷新未完成，请检查 AstrBot 日志。'}), 500
                    return jsonify({'error': '保存或刷新失败，已回滚授权。'}), 500
        return jsonify({'ok': True, 'note': '已更新；实际执行仍检查会话、人格及管理员权限。'})

    async def tool(self):
        body=await request.get_json()
        if not isinstance(body,dict) or set(body)!={'name','enabled'} or type(body['enabled']) is not bool:
            return jsonify({'error':'参数无效'}),400
        name=body['name']
        known={t.name:t for t in self.bridge.context.get_llm_tool_manager().func_list}
        if not isinstance(name,str) or name not in known or name in EXCLUDED:
            return jsonify({'error':'该工具不可接入预执行路由'}),400
        if body['enabled'] and not known[name].active:
            return jsonify({'error':'工具本身已停用，请先在原插件启用'}),409
        async with self.lock:
            old=list(self.bridge.config.get('disabled_tools',[]))
            new=set(old)
            if body['enabled']:new.discard(name)
            else:new.add(name)
            try:
                self.bridge.config['disabled_tools']=sorted(new);self.bridge.config.save_config()
            except Exception:
                self.bridge.config['disabled_tools']=old
                return jsonify({'error':'保存失败'}),500
        return jsonify({'ok':True})

    def register(self):
        for path,handler,methods in [('status',self.status,['GET']),('refresh',self.refresh,['POST']),
                                     ('settings',self.settings,['POST']),('commands',self.command,['POST']),
                                     ('tools',self.tool,['POST'])]:
            self.bridge.context.register_web_api('/astrbot_plugin_intent_bridge/'+path,
                                                 handler,methods,'自然意图控制面板')
