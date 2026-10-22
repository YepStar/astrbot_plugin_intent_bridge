"""Inspect live registry metadata; never read plugin configuration or credentials."""
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import star_handlers_registry, EventType
from astrbot.core.star.session_plugin_manager import SessionPluginManager


async def plugin_for(context, event, name):
    cfg = context.get_config(umo=event.unified_msg_origin)
    for star in context.get_all_stars():
        if name not in {star.name, star.root_dir_name} or not star.activated:
            continue
        for allowed in [cfg.get('plugin_set', ['*']), event.plugins_name]:
            if allowed is not None and allowed != ['*'] and star.name not in allowed and not star.reserved:
                return None
        if not await SessionPluginManager.is_plugin_enabled_for_session(event.unified_msg_origin, star.name):
            return None
        return star.star_cls
    return None


def live_catalog(context, event, query=''):
    available = set(event.get_extra('_intent_bridge_available_tools', []))
    tools = [{'type':'tool','name':t.name,'description':str(t.description or '')[:180], 'available':t.name in available}
             for t in context.get_llm_tool_manager().func_list if t.active]
    commands = []
    for h in star_handlers_registry.get_handlers_by_event_type(EventType.AdapterMessageEvent, plugins_name=event.plugins_name):
        star = star_map.get(h.handler_module_path)
        if not star:
            continue
        for f in h.event_filters:
            if isinstance(f, CommandFilter):
                for cmd in f.get_complete_command_names():
                    commands.append({'type':'command','plugin':star.name,'name':cmd,'description':h.desc[:180]})
    entries = commands + tools
    if query:
        words = query.casefold().split()
        entries = [x for x in entries if any(w in str(x).casefold() for w in words)]
    return entries[:100]
