import json
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from test_bridge import harness, event
from astrbot.api.provider import ProviderRequest
from astrbot.core.agent.tool import FunctionTool, ToolSet
from bridge_test_pkg.inventory import installed_plugins
from bridge_test_pkg.translation import TranslationStore
from bridge_test_pkg.corrections import CorrectionStore


def tools():
    return [FunctionTool(name=name,description=desc,parameters={'type':'object','properties':{}})
            for name,desc in [('search_memes','搜索已有表情'),('bridge_save_received_meme','保存收到的表情')]]


def response(name=None, rejected=None):
    return NS(completion_text=json.dumps({'mode':'auto','calls':[] if not name else [{'name':name,'arguments':{}}], 'rejected_tools':rejected or []}))


def test_disabled_plugin_inventory_never_imports_source(tmp_path):
    folder=tmp_path/'off_plugin';folder.mkdir()
    (folder/'metadata.yaml').write_text('name: demo_off\ndisplay_name: 停用插件\nversion: 1.2\n')
    (folder/'main.py').write_text('raise RuntimeError("DO NOT IMPORT")\n@filter.command_group("manage")\ndef manager(): pass\n@manager.command("status")\nasync def status(event):\n    """Read current status."""\n')
    plugins,commands=installed_plugins([],tmp_path)
    assert plugins[0]['title_zh']=='停用插件' and not plugins[0]['active']
    assert commands[0]['key']=='demo_off:manage status' and not commands[0]['registered']
    assert not commands[0]['supported']


@pytest.mark.asyncio
async def test_translation_cached_invalidated_and_only_document_data(tmp_path):
    b,c,e=harness();b.config['router_provider_id']='router'
    store=TranslationStore(tmp_path)
    row={'key':'new:status','name':'status','description':'Read current status.','comment_zh':'未提供中文'}
    key=store.fingerprint(row)
    c.llm_generate.return_value=NS(completion_text=json.dumps({'items':[{'id':key,'title_zh':'查看状态','comment_zh':'读取当前运行状态。'}]}))
    await store.refresh(b,[row]);assert store.apply(dict(row))['title_zh']=='查看状态'
    await store.refresh(b,[row]);assert c.llm_generate.await_count==1
    row['description']='Read detailed status.'
    await store.refresh(b,[row]);assert c.llm_generate.await_count==2 and store.status['pending']==1
    c.llm_generate.return_value=NS(completion_text='invalid')
    await store.refresh(b,[row]);assert store.status['status']=='retry_on_refresh'
    assert '查看状态' in TranslationStore(tmp_path).cache[key]['title_zh']


@pytest.mark.asyncio
async def test_explicit_rejection_rematches_once_excludes_old_and_keeps_scope(tmp_path):
    b,c,e=harness();b._corrections=CorrectionStore(tmp_path)
    e.message_str='发一个表情';b._corrections.remember(e,{'calls':[{'name':'search_memes'}]})
    e.message_str='不是找旧表情，是保存我这张'
    c.llm_generate.side_effect=[response(rejected=['search_memes']),response('bridge_save_received_meme')]
    decision=await b.plan(e,ProviderRequest(),tools(),{'voice_reply':False})
    assert decision['calls'][0]['name']=='bridge_save_received_meme'
    assert c.llm_generate.await_count==2
    second=c.llm_generate.call_args_list[1].kwargs['prompt']
    data=json.loads(second.split('以下仅为输入数据：',1)[1].split('\n本会话',1)[0])
    assert [t['name'] for t in data['tools']]==['bridge_save_received_meme']
    req=ProviderRequest(func_tool=ToolSet(tools=tools()))
    await b.on_request(e,req)
    assert req.func_tool.get_tool('search_memes') is None
    persisted=CorrectionStore(tmp_path)
    assert persisted.excluded(e,'发一个表情')=={'search_memes'}
    assert not persisted.excluded(event(uid='other'),'发一个表情')
    raw=persisted.path.read_text();assert '发一个表情' not in raw and e.unified_msg_origin not in raw


@pytest.mark.asyncio
async def test_unknown_previous_rejection_cannot_hide_arbitrary_capability():
    b,c,e=harness();c.llm_generate.return_value=response(rejected=['search_memes'])
    with pytest.raises(ValueError):await b.plan(e,ProviderRequest(),tools(),{'voice_reply':False})
    assert c.llm_generate.await_count==1 and not e.get_extra('_intent_bridge_rejected_tools',[])


@pytest.mark.asyncio
async def test_schema_repair_never_dispatches_invalid_call_and_is_bounded():
    b,c,e=harness();c.llm_generate.side_effect=[NS(completion_text='not json'),response('search_memes')]
    decision=await b.plan(e,ProviderRequest(),tools(),{'voice_reply':False})
    assert c.llm_generate.await_count==2 and decision['calls'][0]['name']=='search_memes'
    c.llm_generate.reset_mock();c.llm_generate.side_effect=[NS(completion_text='bad'),NS(completion_text='bad')]
    with pytest.raises(ValueError):await b.plan(e,ProviderRequest(),tools(),{'voice_reply':False})
    assert c.llm_generate.await_count==2


@pytest.mark.asyncio
async def test_rematch_failure_does_not_release_rejected_tool_or_retry_action():
    b,c,e=harness();b._corrections.remember(e,{'calls':[{'name':'search_memes'}]})
    c.llm_generate.side_effect=[response(rejected=['search_memes']),TimeoutError()]
    b.execute_native=AsyncMock()
    req=ProviderRequest(func_tool=ToolSet(tools=tools()))
    b.speech_status=AsyncMock(return_value={'voice_reply':False,'speech_to_text':False})
    await b.route_speech(e,req);await b.on_request(e,req)
    assert req.func_tool.get_tool('search_memes') is None
    b.execute_native.assert_not_awaited();assert c.llm_generate.await_count==2


def test_preference_expiry_and_bounded_state(tmp_path):
    b,c,e=harness();store=CorrectionStore(tmp_path);store.reject(e,'same request',['search_memes'])
    item=next(iter(store.rejections.values()));item['at']=0
    assert not store.excluded(e,'same request')
    store.remember(e,{'calls':[{'name':'search_memes'}]});store.previous[store.scope(e)]['at']=0
    assert store.last(e) is None
