"""Non-mutating feature checks beyond the registry's active flag.

Plugins may implement intent_bridge_tool_ready(name) -> bool to supply their own
runtime readiness. No credentials, network probes or configuration writes here.
"""
import inspect

async def tool_ready(plugin,name):
    probe=getattr(plugin,'intent_bridge_tool_ready',None)
    if callable(probe):
        result=probe(name)
        if inspect.isawaitable(result):result=await result
        if not isinstance(result,bool):return False,'invalid_readiness_contract'
        if not result:return False,'plugin_reports_unavailable'
    if name in {'grok_web_search','enhance_memory_rag_read','enhance_memory_rag_write'}:
        getter=getattr(plugin,'_cfg',None)
        if callable(getter):
            cfg=getter();section=getattr(cfg,'web_search' if name=='grok_web_search' else 'memory_rag',None)
            if section is not None and not getattr(section,'enable',False):
                return False,'feature_disabled'
    if name.startswith('pc_reality_'):
        if not getattr(plugin,'enable_experimental_bluetooth_wakeup',False):
            return False,'hardware_module_disabled'
    if name=='pc_generate_photo':
        if not getattr(plugin,'enabled',True) or not getattr(plugin,'enable_photo_text_action',False):
            return False,'image_feature_disabled'
        available=getattr(plugin,'_photo_generation_runtime_available',None)
        if callable(available) and not available():return False,'image_extension_unavailable'
    return True,''

async def module_contexts(context, event, tools):
    """Read optional session-scoped module state without executing module actions."""
    import inspect
    import json
    from astrbot.core.star.star import star_map
    from .catalog import plugin_for
    result = {}
    seen = set()
    for tool in tools:
        star = star_map.get(getattr(tool, 'handler_module_path', None))
        if not star or star.name in seen:
            continue
        seen.add(star.name)
        plugin = await plugin_for(context, event, star.name)
        getter = getattr(plugin, 'intent_bridge_context', None)
        if not callable(getter):
            continue
        try:
            value = getter(event)
            if inspect.isawaitable(value):
                value = await value
            if isinstance(value, dict) and len(json.dumps(value, ensure_ascii=False)) <= 8000:
                result[star.name] = value
        except Exception:
            continue
    return result
