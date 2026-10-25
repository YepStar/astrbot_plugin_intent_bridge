import asyncio,json,sys,types
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,Mock,patch
import pytest
import astrbot.api
from astrbot.core.star.context import Context
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage,MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.agent.tool import ToolSet,FunctionTool
from astrbot.api.provider import ProviderRequest
from astrbot.api.message_components import Plain
root=Path(__file__).resolve().parents[1]
pkg=types.ModuleType('bridge_test_pkg');pkg.__path__=[str(root)];sys.modules['bridge_test_pkg']=pkg
from bridge_test_pkg.policy import candidate,direct_music,parse_plan,safe_query
from bridge_test_pkg.main import IntentBridge
from bridge_test_pkg.providers import research
from bridge_test_pkg.catalog import plugin_for

@pytest.mark.parametrize('text',['想一起听会歌','网易云拉你了','lol更新的新版海斗好玩吗？','那他强不强呢','今天有哪些热点新闻'])
def test_positive_candidates(text):assert candidate(text)
@pytest.mark.parametrize('text',['不要一起听歌','不想一起听','不用联网查','比如我说想一起听会歌','他说网易云拉你了','/一起听','我有点难过','为什么没有触发指令',''])
def test_negative_candidates(text):assert not candidate(text)
@pytest.mark.parametrize('query',['sk-abcd-secret','qq 123456789','hello@example.com','https://localhost/a','x','a'*81])
def test_query_privacy(query):
 with pytest.raises(ValueError):safe_query(query)
def test_plan_actions_and_negation():
 assert parse_plan('{"action":"shell","command":"rm -rf /"}','你好')['action']=='none'
 assert parse_plan('{"action":"join_listening"}','不要一起听歌')['action']=='none'
 assert parse_plan('{"action":"research","query":"英雄联盟 海斗"}','不用联网查')['action']=='none'
 assert parse_plan('```json\n{"action":"research","query":"英雄联盟 海斗"}\n```','新版海斗好玩吗')['query']=='英雄联盟 海斗'

def event(text='网易云拉你了',uid='12345'):
 m=AstrBotMessage();m.type=MessageType.FRIEND_MESSAGE;m.self_id='bot';m.sender=MessageMember(user_id=uid,nickname='Tester');m.message_id='m1';m.session_id=uid;m.message=[Plain(text)];m.message_str=text;m.raw_message=None
 e=AstrMessageEvent(text,m,PlatformMetadata('aiocqhttp','test','qq_test'),uid)
 e.set_extra('_intent_bridge_available_tools',['bridge_research','bridge_join_listening','bridge_capabilities','cmd_join','search_bilibili'])
 return e

def harness():
 c=object.__new__(Context)
 c.get_config=Mock(return_value={'plugin_set':['*']})
 c.get_all_stars=Mock(return_value=[])
 c.get_current_chat_provider_id=AsyncMock(return_value='router')
 c.llm_generate=AsyncMock(return_value=NS(completion_text='{"action":"none"}'))
 c.get_llm_tool_manager=Mock(return_value=NS(func_list=[]))
 e=event();b=IntentBridge(c,{'enabled':True,'allowed_umos':[e.unified_msg_origin],'enable_preflight':True})
 return b,c,e

@pytest.mark.asyncio
async def test_scope_denies_other_user_without_lookup():
 b,c,e=harness();out=await b.join(event(uid='99999'));assert out['status']=='denied';c.get_all_stars.assert_not_called()

@pytest.mark.asyncio
async def test_join_uses_original_sdk_identity_once_and_caches_result():
 b,c,e=harness();tool=NS(active=True,name='cmd_join',call=AsyncMock(return_value=json.dumps({'status':'ok','output':'已进入测试房间'})))
 converter=NS(tools={'astrbot_plugin_nomi_music:一起听':tool})
 with patch('bridge_test_pkg.main.plugin_for',new=AsyncMock(return_value=converter)):
  a=await b.join(e);d=await b.join(e)
 assert a==d and tool.call.await_count==1
 assert tool.call.call_args.args[0].context.event is e
 assert tool.call.call_args.args[0].context.event.get_sender_id()=='12345'

@pytest.mark.asyncio
async def test_join_unknown_result_not_retried():
 b,c,e=harness();tool=NS(active=True,name='cmd_join',call=AsyncMock(side_effect=TimeoutError()))
 with patch('bridge_test_pkg.main.plugin_for',new=AsyncMock(return_value=NS(tools={'astrbot_plugin_nomi_music:一起听':tool}))):
  assert (await b.join(e))['status']=='unknown';await b.join(e)
 tool.call.assert_awaited_once()

@pytest.mark.asyncio
async def test_disabled_persona_command_is_not_executed():
 b,c,e=harness();e.set_extra('_intent_bridge_available_tools',['bridge_join_listening']);tool=NS(active=True,name='cmd_join',call=AsyncMock())
 with patch('bridge_test_pkg.main.plugin_for',new=AsyncMock(return_value=NS(tools={'astrbot_plugin_nomi_music:一起听':tool}))):assert (await b.join(e))['status']=='denied'
 tool.call.assert_not_awaited()

@pytest.mark.asyncio
async def test_hook_keeps_persona_and_user_text_and_isolates_toolset():
 b,c,e=harness();tools=ToolSet(tools=[FunctionTool(name=x,description=x,parameters={'type':'object','properties':{}}) for x in ['bridge_join_listening','cmd_join']]);req=ProviderRequest(prompt=e.message_str,system_prompt='original persona',func_tool=tools)
 converter=NS(tools={'astrbot_plugin_nomi_music:一起听':NS(name='cmd_join')})
 e.set_extra('_intent_bridge_route',{'mode':'auto','kind':'normal','calls':[{'name':'bridge_join_listening','arguments':{}}]})
 e.set_extra('_intent_bridge_offered',['bridge_join_listening','cmd_join'])
 with patch.object(b,'join',new=AsyncMock(return_value={'status':'ok','output':'已进入房间'})),patch('bridge_test_pkg.main.plugin_for',new=AsyncMock(return_value=converter)):
  await b.on_request(e,req);await b.on_request(e,req)
 assert req.system_prompt=='original persona' and req.prompt==e.message_str
 assert len(req.extra_user_content_parts)==2  # One directory and one execution receipt.
 assert len(tools.tools)==2 and len(req.func_tool.tools)==0
 c.llm_generate.assert_not_awaited()

@pytest.mark.asyncio
async def test_casual_chat_has_no_classifier_cost():
 b,c,e=harness();e.message_str='今天有点累';req=ProviderRequest(prompt=e.message_str,func_tool=ToolSet(tools=[FunctionTool(name='bridge_research',description='x',parameters={'type':'object','properties':{}})]));await b.on_request(e,req);c.llm_generate.assert_not_awaited()

@pytest.mark.asyncio
async def test_research_partial_failure_preserves_other_platform_and_no_error_secrets():
 with patch('bridge_test_pkg.providers.bili_search',new=AsyncMock(side_effect=RuntimeError('cookie=private-secret'))),patch('bridge_test_pkg.providers.xhh_search',new=AsyncMock(return_value={'platform':'xiaoheihe','status':'ok','items':[{'title':'真实帖子','url':'https://www.xiaoheihe.cn/app/bbs/link/123'}]})):
  out=await research(None,None,'英雄联盟 海斗')
 assert out['sources'][1]['items'] and out['sources'][0]['status']=='error'
 assert 'private-secret' not in json.dumps(out)

@pytest.mark.asyncio
async def test_plugin_activation_and_session_policy():
 b,c,e=harness();star=NS(name='sample',root_dir_name='sample',activated=True,reserved=False,star_cls='instance');c.get_all_stars.return_value=[star]
 with patch('bridge_test_pkg.catalog.SessionPluginManager.is_plugin_enabled_for_session',new=AsyncMock(return_value=False)):
  assert await plugin_for(c,e,'sample') is None
 star.activated=False
 assert await plugin_for(c,e,'sample') is None

@pytest.mark.asyncio
async def test_lookup_cache_is_scoped_per_session():
 b,c,e=harness();result={'sources':[{'items':[{'title':'real'}]}]}
 with patch('bridge_test_pkg.main.research',new=AsyncMock(return_value=result)) as fn:
  await b.lookup(e,'英雄联盟 海斗');await b.lookup(e,'英雄联盟 海斗');assert fn.await_count==1
  out=await b.lookup(event(uid='99999'),'英雄联盟 海斗');assert out['status']=='denied'

@pytest.mark.asyncio
async def test_xhh_reads_only_search_and_post_bodies():
 from bridge_test_pkg.providers import xhh_search
 client=NS(credentials=NS(),_request=AsyncMock(return_value=NS(payload={'result':{'items':[{'info':{'linkid':'abc123','title':'新版本体验','create_at':1700000000}}]}})),fetch_thread_context=AsyncMock(return_value=NS(body='来自真实帖子的正文',comments=[{'text':'一位网友的意见'}])))
 module=NS(ENDPOINTS={},Endpoint=lambda *a:tuple(a));plugin=NS(runtime=NS(config=NS(snapshot=lambda:{'profiles':[{'enabled':True,'profile_id':'default'}]}),get_client=AsyncMock(return_value=client)))
 with patch('bridge_test_pkg.providers.plugin_for',new=AsyncMock(return_value=plugin)),patch('bridge_test_pkg.providers.importlib.import_module',return_value=module):
  out=await xhh_search(None,None,'英雄联盟 海斗',2,'default')
 assert out['items'][0]['evidence']=='post_body_excerpt'
 assert out['items'][0]['body_excerpt']=='来自真实帖子的正文'
 assert module.ENDPOINTS['intent_bridge_readonly_search_v1'][0]=='GET'
 assert client._request.call_args.kwargs['params']['q']=='英雄联盟 海斗'

@pytest.mark.asyncio
async def test_bili_labels_excerpt_and_dates():
 from bridge_test_pkg.providers import bili_search
 b,c,e=harness();plugin=NS(config={'ENABLE_LLM_TOOLS':True},search_bilibili_videos=AsyncMock(return_value=[{'bvid':'BV1234567890','title':'<em>标题</em>','pubdate':1700000000}]),_get_video_oid=AsyncMock(return_value=1),_get_video_info=AsyncMock(return_value={'cid':2,'desc':'简介'}),_get_video_subtitles=AsyncMock(return_value='实际字幕摘录'),_get_hot_comments=AsyncMock(return_value=['一位网友的观点']))
 with patch('bridge_test_pkg.providers.plugin_for',new=AsyncMock(return_value=plugin)):
  out=await bili_search(c,e,'海斗',2)
 assert out['items'][0]['evidence']=='subtitle_excerpt'
 assert out['items'][0]['subtitle_excerpt']=='实际字幕摘录'
 assert out['items'][0]['title']=='标题'
 assert out['items'][0]['published_at'].endswith('+00:00')

@pytest.mark.asyncio
async def test_classifier_failure_does_not_fabricate_completed_research():
 b,c,e=harness();e.message_str='lol更新的新版海斗好玩吗';c.llm_generate.return_value=NS(completion_text='not json')
 req=ProviderRequest(prompt=e.message_str,func_tool=ToolSet(tools=[FunctionTool(name='bridge_research',description='x',parameters={'type':'object','properties':{}})]))
 with patch.object(b,'lookup',new=AsyncMock()) as lookup:
  await b.route_speech(e,req);await b.on_request(e,req);lookup.assert_not_awaited()
 assert not e.get_extra('_intent_bridge_route')
 assert '不谎称已完成' in req.extra_user_content_parts[-1].text

@pytest.mark.asyncio
async def test_quoted_or_negated_tool_call_still_denied():
 b,c,e=harness();e.message_str='不要一起听歌';assert (await b.join(e))['status']=='denied'
 e.message_str='不用联网查';assert (await b.lookup(e,'英雄联盟 海斗'))['status']=='denied'


@pytest.mark.asyncio
async def test_speech_guide_uses_active_providers_without_extra_classifier_or_send():
 b,c,e=harness();e.message_str='冷月，想听你的声音'
 c.get_config.return_value={'plugin_set':['*'],'provider_stt_settings':{'enable':True},'provider_tts_settings':{'enable':False}}
 c.get_using_stt_provider_async=AsyncMock(return_value=object())
 c.get_using_tts_provider_async=AsyncMock(return_value=object())
 companion=NS(enabled=True,_tts_setting=lambda k,d:True if k=='enable_tts_enhancement' else d)
 req=ProviderRequest(prompt=e.message_str,system_prompt='original persona')
 with patch('bridge_test_pkg.main.plugin_for',new=AsyncMock(return_value=companion)):
  await b.on_request(e,req);await b.on_request(e,req)
 assert len(req.extra_user_content_parts)==1
 assert '本轮可用能力目录' in req.extra_user_content_parts[0].text
 assert req.system_prompt=='original persona' and req.prompt==e.message_str
 c.llm_generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_providers_never_claim_speech_is_available():
 b,c,e=harness()
 c.get_config.return_value={'provider_stt_settings':{'enable':True},'provider_tts_settings':{'enable':True}}
 c.get_using_stt_provider_async=AsyncMock(return_value=None)
 c.get_using_tts_provider_async=AsyncMock(return_value=None)
 assert await b.speech_status(e)=={'speech_to_text':False,'voice_reply':False,'reply_owner':'none'}


@pytest.mark.asyncio
async def test_companion_language_provider_works_with_native_tts_disabled():
 b,c,e=harness();c.get_using_tts_provider_async=AsyncMock(return_value=None)
 companion=NS(enabled=True,_tts_setting=lambda k,d:True,_resolve_tts_synthesis_provider=Mock(return_value=object()))
 with patch('bridge_test_pkg.main.plugin_for',new=AsyncMock(return_value=companion)):
  assert (await b.speech_status(e))['reply_owner']=='private_companion'
 companion._resolve_tts_synthesis_provider.assert_called_once_with(e,None)


@pytest.mark.asyncio
async def test_disabled_companion_does_not_enable_tts_when_native_tts_is_off():
 b,c,e=harness();c.get_using_tts_provider_async=AsyncMock(return_value=object())
 with patch('bridge_test_pkg.main.plugin_for',new=AsyncMock(return_value=None)):
  assert not (await b.speech_status(e))['voice_reply']


@pytest.mark.asyncio
async def test_native_tts_guide_does_not_request_companion_tags():
 b,c,e=harness();e.message_str='你好'
 c.get_config.return_value={'provider_tts_settings':{'enable':True}}
 c.get_using_tts_provider_async=AsyncMock(return_value=object())
 with patch('bridge_test_pkg.main.plugin_for',new=AsyncMock(return_value=None)):
  req=ProviderRequest(prompt=e.message_str);await b.on_request(e,req)
 assert '不手写语音标签' in req.extra_user_content_parts[0].text


@pytest.mark.asyncio
async def test_speech_metadata_obeys_session_scope():
 b,c,e=harness();c.get_using_tts_provider_async=AsyncMock(return_value=object())
 other=event('发条语音',uid='99999');req=ProviderRequest(prompt=other.message_str)
 await b.on_request(other,req)
 assert not req.extra_user_content_parts
 c.get_using_tts_provider_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_transcribed_music_request_reuses_existing_router():
 b,c,e=harness()
 # AstrBot preprocessing replaces Record with Plain and appends the transcript.
 e.message_str='想一起听会歌';e.message_obj.message_str=e.message_str
 e.message_obj.message=[Plain(e.message_str)]
 e.set_extra('_intent_bridge_route',{'mode':'auto','kind':'normal','calls':[{'name':'bridge_join_listening','arguments':{}}]})
 e.set_extra('_intent_bridge_offered',['bridge_join_listening'])
 req=ProviderRequest(prompt=e.message_str,func_tool=ToolSet(tools=[FunctionTool(name='bridge_join_listening',description='x',parameters={'type':'object','properties':{}})]))
 with patch.object(b,'join',new=AsyncMock(return_value={'status':'ok'})) as join,patch('bridge_test_pkg.main.plugin_for',new=AsyncMock(return_value=None)):
  await b.on_request(e,req)
 join.assert_awaited_once_with(e)
 assert req.prompt=='想一起听会歌'


@pytest.mark.asyncio
async def test_failed_stt_record_does_not_trigger_an_action():
 from astrbot.api.message_components import Record
 b,c,e=harness();e.message_str='';e.message_obj.message_str='';e.message_obj.message=[Record(file='/missing.wav')]
 req=ProviderRequest(prompt='',func_tool=ToolSet(tools=[FunctionTool(name='bridge_join_listening',description='x',parameters={'type':'object','properties':{}})]))
 with patch.object(b,'join',new=AsyncMock()) as join:
  await b.on_request(e,req)
 join.assert_not_awaited();c.llm_generate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('transcript',['想一起听会歌','不要一起听歌','用语音回复我'])
async def test_real_astrbot_stt_preprocess_feeds_original_intent_event(transcript):
 from astrbot.api.message_components import Record
 from astrbot.core.pipeline.preprocess_stage.stage import PreProcessStage
 b,c,e=harness();e.message_str='';e.message_obj.message_str=''
 e.message_obj.message=[Record(file='/tmp/intent-test.wav')]
 stt=NS(get_text=AsyncMock(return_value=transcript))
 c.get_using_stt_provider_async=AsyncMock(return_value=stt)
 stage=PreProcessStage();stage.config={};stage.platform_settings={}
 stage.stt_settings={'enable':True};stage.plugin_manager=NS(context=c)
 with patch.object(Record,'convert_to_file_path',new=AsyncMock(return_value='/tmp/intent-test.wav')),patch('astrbot.core.pipeline.preprocess_stage.stage.ensure_wav',new=AsyncMock(return_value='/tmp/intent-test.wav')):
  await stage.process(e)
 assert e.message_str==transcript and isinstance(e.get_messages()[0],Plain)
 stt.get_text.assert_awaited_once()
 e.set_extra('_intent_bridge_route',{'mode':'auto','kind':'normal','calls':[{'name':'bridge_join_listening','arguments':{}}] if transcript=='想一起听会歌' else []})
 e.set_extra('_intent_bridge_offered',['bridge_join_listening'])
 req=ProviderRequest(prompt=e.message_str,func_tool=ToolSet(tools=[FunctionTool(name='bridge_join_listening',description='x',parameters={'type':'object','properties':{}})]))
 with patch.object(b,'join',new=AsyncMock(return_value={'status':'ok'})) as join,patch('bridge_test_pkg.main.plugin_for',new=AsyncMock(return_value=None)):
  await b.on_request(e,req)
 assert join.await_count==(1 if transcript=='想一起听会歌' else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('text,mode,kind',[
 ('想听你说话','voice','speak'),('你能哼两句吗','voice','sing'),
 ('亲口说喜欢我','voice','speak'),('现在开会不方便听','text','normal'),
 ('你说呢','auto','normal')])
async def test_semantic_voice_once_and_keeps_user_words(text,mode,kind):
 b,c,e=harness();e.message_str=text
 b.speech_status=AsyncMock(return_value={'voice_reply':True})
 c.llm_generate.return_value=NS(completion_text=json.dumps({'mode':mode,'kind':kind}))
 req=ProviderRequest(prompt=text,system_prompt='persona',contexts=[{'role':'user','content':'前文'}])
 await b.route_speech(e,req);await b.route_speech(e,req)
 c.llm_generate.assert_awaited_once()
 assert getattr(e,'_intent_bridge_voice_decision')==mode
 assert req.prompt==text and req.system_prompt=='persona'
 assert '前文' in c.llm_generate.call_args.kwargs['prompt']
 if kind=='sing':assert '不能保证旋律' in req.extra_user_content_parts[0].text

@pytest.mark.asyncio
async def test_semantic_voice_no_provider_or_other_session_no_call():
 b,c,e=harness();b.speech_status=AsyncMock(return_value={'voice_reply':False})
 await b.route_speech(e,ProviderRequest());await b.route_speech(event(uid='99999'),ProviderRequest())
 c.llm_generate.assert_not_awaited()

@pytest.mark.asyncio
@pytest.mark.parametrize('raw',['not json','{"mode":"shell"}','[]'])
async def test_semantic_classifier_failure_preserves_legacy_policy(raw):
 b,c,e=harness();b.speech_status=AsyncMock(return_value={'voice_reply':True})
 c.llm_generate.return_value=NS(completion_text=raw)
 await b.route_speech(e,ProviderRequest())
 assert not hasattr(e,'_intent_bridge_voice_decision')
