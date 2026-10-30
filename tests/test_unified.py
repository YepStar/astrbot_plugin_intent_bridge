import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,Mock,patch
import pytest
from test_bridge import harness,event
from astrbot.api.provider import ProviderRequest
from astrbot.core.agent.tool import FunctionTool,ToolSet
from astrbot.core.message.message_event_result import MessageEventResult
from mcp.types import CallToolResult,TextContent
from bridge_test_pkg.routing import parse_route,EXCLUDED

def tool(name='pc_generate_photo'):
 return FunctionTool(name=name,description='角色生图',parameters={'type':'object','properties':{'prompt':{'type':'string'},'kind':{'type':'string','enum':['selfie','text2img','edit','sticker']},'send':{'type':'boolean'}},'required':['prompt']})

def response(calls,mode='auto'):
 return json.dumps({'mode':mode,'kind':'normal','calls':calls})

@pytest.mark.parametrize('calls',[
 [{'name':'not_offered','arguments':{}}],
 [{'name':'pc_generate_photo','arguments':{'prompt':'x','reference_image_path':'/invented'}}],
 [{'name':'pc_generate_photo','arguments':{'prompt':'x','kind':'shell'}}],
 [{'name':'pc_generate_photo','arguments':{}}],
])
def test_reject_unknown_or_invalid_tool_calls(calls):
 with pytest.raises(Exception):parse_route(response(calls),{'pc_generate_photo':tool()})

@pytest.mark.asyncio
async def test_photo_routes_then_dispatches_once_with_receipt_and_no_retry():
 b,c,e=harness();e.message_str='你在做什么，拍给我看看';b.speech_status=AsyncMock(return_value={'voice_reply':True,'speech_to_text':True,'reply_owner':'private_companion'})
 req=ProviderRequest(prompt=e.message_str,system_prompt='示例角色',func_tool=ToolSet(tools=[tool()]))
 c.llm_generate.return_value=NS(completion_text=response([{'name':'pc_generate_photo','arguments':{'prompt':'示例角色的日常场景肖像','kind':'selfie'}}]))
 b.execute_native=AsyncMock(return_value={'status':'failed','sent':False,'error_code':'quota'})
 await b.route_speech(e,req);await b.on_request(e,req);await b.on_request(e,req)
 b.execute_native.assert_awaited_once();c.llm_generate.assert_awaited_once()
 assert b.execute_native.call_args.args[2]['caption']==''
 assert req.prompt==e.message_str and req.system_prompt=='示例角色'
 assert req.func_tool.get_tool('pc_generate_photo') is None
 assert '"sent": false' in req.extra_user_content_parts[-1].text

@pytest.mark.asyncio
async def test_late_tool_revocation_blocks_preclassified_call():
 b,c,e=harness();e.set_extra('_intent_bridge_route',{'mode':'auto','kind':'normal','calls':[{'name':'pc_generate_photo','arguments':{'prompt':'x'}}]});e.set_extra('_intent_bridge_offered',['pc_generate_photo'])
 req=ProviderRequest(func_tool=ToolSet());b.execute_native=AsyncMock()
 await b.on_request(e,req);b.execute_native.assert_not_awaited()

@pytest.mark.asyncio
async def test_new_native_tool_discovered_without_code_change_and_delegated():
 b,c,e=harness();e.message_str='查一下最近的天气';b.speech_status=AsyncMock(return_value={'voice_reply':False,'speech_to_text':False})
 new=FunctionTool(name='weather_future_plugin',description='查询天气',parameters={'type':'object','properties':{'city':{'type':'string'}},'required':['city']})
 req=ProviderRequest(func_tool=ToolSet(tools=[new]));c.llm_generate.return_value=NS(completion_text=response([{'name':new.name,'arguments':{'city':'上海'}}]))
 b.execute_native=AsyncMock();await b.route_speech(e,req);await b.on_request(e,req)
 assert 'weather_future_plugin' in c.llm_generate.call_args.kwargs['prompt']
 assert '主Agent' in req.extra_user_content_parts[-1].text
 b.execute_native.assert_not_awaited();assert req.func_tool.get_tool(new.name)

@pytest.mark.asyncio
async def test_config_allows_new_native_tool_predispatch_without_code_change():
 b,c,e=harness();b.config['extra_auto_tools']=['weather_future_plugin'];new=FunctionTool(name='weather_future_plugin',description='天气',parameters={'type':'object','properties':{}})
 e.set_extra('_intent_bridge_route',{'mode':'auto','kind':'normal','calls':[{'name':new.name,'arguments':{}}]});e.set_extra('_intent_bridge_offered',[new.name]);b.execute_native=AsyncMock(return_value={'ok':True})
 await b.on_request(e,ProviderRequest(func_tool=ToolSet(tools=[new])))
 b.execute_native.assert_awaited_once()

@pytest.mark.asyncio
async def test_execute_native_uses_actual_core_executor_and_original_identity():
 b,c,e=harness();old=MessageEventResult().message('previous');e.set_result(old)
 async def handler(ev,prompt,kind='selfie',send=True):
  assert ev is e
  return json.dumps({'sent':False,'generated':True,'prompt':prompt})
 t=tool();t.handler=handler
 with patch('bridge_test_pkg.main.MAIN_AGENT_HOOKS.on_tool_start',new=AsyncMock()) as start,patch('bridge_test_pkg.main.MAIN_AGENT_HOOKS.on_tool_end',new=AsyncMock()) as end:
  out=await b.execute_native(e,t,{'prompt':'test'})
 assert out['generated'] and out['sent'] is False
 assert e.get_result() is old
 assert start.call_args.args[0].context.event is e
 end.assert_awaited_once()

@pytest.mark.asyncio
async def test_excluded_tools_not_offered_even_when_active_and_configured():
 b,c,e=harness();b.config['extra_auto_tools']=['pc_send_to_group'];t=FunctionTool(name='pc_send_to_group',description='转发到群',parameters={'type':'object','properties':{}})
 assert await b.route_tools(e,ProviderRequest(func_tool=ToolSet(tools=[t])))==[]

@pytest.mark.asyncio
async def test_readiness_excludes_disabled_search_without_changing_plugin_config():
 from bridge_test_pkg.readiness import tool_ready
 cfg=NS(web_search=NS(enable=False))
 p=NS(_cfg=Mock(return_value=cfg))
 assert await tool_ready(p,'grok_web_search')==(False,'feature_disabled')
 assert cfg.web_search.enable is False

@pytest.mark.asyncio
async def test_new_plugin_can_report_readiness_without_router_changes():
 from bridge_test_pkg.readiness import tool_ready
 p=NS(intent_bridge_tool_ready=AsyncMock(return_value=False))
 assert await tool_ready(p,'new_native_tool')==(False,'plugin_reports_unavailable')

@pytest.mark.asyncio
async def test_delete_confirmation_stays_in_native_agent_history():
 b,c,e=harness();t=FunctionTool(name='pc_manage_memo',description='备忘',parameters={'type':'object','properties':{'action':{'type':'string'},'selector':{'type':'string'}}})
 e.set_extra('_intent_bridge_route',{'mode':'auto','kind':'normal','calls':[{'name':t.name,'arguments':{'action':'delete','selector':'某便签'}}]});e.set_extra('_intent_bridge_offered',[t.name]);b.execute_native=AsyncMock()
 req=ProviderRequest(func_tool=ToolSet(tools=[t]));await b.on_request(e,req)
 b.execute_native.assert_not_awaited();assert req.func_tool.get_tool(t.name)
 assert '主Agent' in req.extra_user_content_parts[-1].text
