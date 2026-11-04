import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from quart import Quart
from astrbot.api.provider import ProviderRequest
from astrbot.core.agent.tool import FunctionTool,ToolSet
from mcp.types import CallToolResult,TextContent
from test_bridge import harness,event
from bridge_test_pkg.records import RouteRecords,describe


def tool(name='ncm_search'):
    return FunctionTool(name=name,description='搜索真实歌曲',parameters={'type':'object','properties':{'query':{'type':'string'}},'required':['query']})

async def classified(text='推荐你先听安和桥',calls=None):
    b,c,e=harness();e.message_str=text
    offered=[tool()]
    b.speech_status=AsyncMock(return_value={'voice_reply':False,'speech_to_text':False})
    b.route_tools=AsyncMock(return_value=offered)
    c.llm_generate.return_value=NS(completion_text=json.dumps({'mode':'auto','kind':'normal','music_actions':['listen'],'calls':calls if calls is not None else [{'name':'ncm_search','arguments':{'query':'安和桥'}}]}))
    req=ProviderRequest(prompt=text,func_tool=ToolSet(tools=offered))
    await b.route_speech(e,req)
    return b,c,e,req

@pytest.mark.asyncio
async def test_user_text_and_validated_calls_are_correlated_and_durable():
    b,c,e,req=await classified()
    identity=e.get_extra('_intent_bridge_record_id')
    row=b.records_store.find(identity)
    assert row['user_text']=='推荐你先听安和桥' and row['status']=='matched'
    assert row['planned'][0]['name']=='ncm_search'
    assert row['planned'][0]['arguments']=={'query':'安和桥'}
    assert row['executions']==[]
    await b.route_speech(e,req)
    assert len(b.records_store.rows)==1
    recovered=RouteRecords(b.records_store.path.parent)
    assert recovered.find(identity)['planned']==row['planned']
    assert b.records_store.path.stat().st_mode & 0o777==0o600

@pytest.mark.asyncio
async def test_preflight_and_main_agent_continuation_have_separate_receipts():
    b,c,e,req=await classified()
    b.config['extra_auto_tools']=['ncm_search']
    b.execute_native=AsyncMock(return_value={'status':'ok','songs':[]})
    await b.on_request(e,req)
    identity=e.get_extra('_intent_bridge_record_id')
    row=b.records_store.find(identity)
    assert row['dispatch']['ncm_search']=='preflight'
    assert len(row['executions'])==1 and row['executions'][0]['via']=='preflight'
    follow=tool('ncm_listen');args={'song_id':'101'}
    await b.record_agent_tool_start(e,follow,args)
    await b.record_agent_tool_end(e,follow,args,CallToolResult(content=[TextContent(type='text',text='{"status":"started"}')]))
    await b.finish_route_record(e)
    assert [r['name'] for r in row['planned']]==['ncm_search']
    assert [r['name'] for r in row['executions']]==['ncm_search','ncm_listen']
    assert row['executions'][1]['status']=='started' and row['finished_at']

@pytest.mark.asyncio
async def test_preflight_native_hooks_do_not_double_count():
    b,c,e,req=await classified()
    b.config['extra_auto_tools']=['ncm_search']
    async def execute(ev,t,args):
        await b.record_agent_tool_start(ev,t,args)
        await b.record_agent_tool_end(ev,t,args,CallToolResult(content=[]))
        return {'status':'ok'}
    b.execute_native=execute
    await b.on_request(e,req)
    row=b.records_store.find(e.get_extra('_intent_bridge_record_id'))
    assert len(row['executions'])==1
    assert not e.get_extra('_intent_bridge_record_preflight')

@pytest.mark.asyncio
async def test_deferred_plan_does_not_claim_execution():
    b,c,e,req=await classified();b.config['enable_preflight']=False
    await b.on_request(e,req)
    row=b.records_store.find(e.get_extra('_intent_bridge_record_id'))
    assert row['dispatch']['ncm_search']=='deferred_to_agent'
    assert row['executions']==[]

@pytest.mark.asyncio
async def test_classification_error_and_regular_chat_remain_visible():
    b,c,e,req=await classified(calls=[])
    assert b.records_store.rows[0]['status']=='chat'
    c.llm_generate.side_effect=TimeoutError()
    e2=event('再去听借我');req2=ProviderRequest(prompt=e2.message_str,func_tool=req.func_tool)
    await b.route_speech(e2,req2)
    assert b.records_store.rows[-1]['status']=='analysis_failed'
    assert b.records_store.rows[-1]['error_type']=='TimeoutError'

@pytest.mark.asyncio
async def test_recording_io_failure_does_not_block_routing():
    b,c,e=harness();b.records_store.save=lambda:(_ for _ in ()).throw(OSError('disk unavailable'))
    b.speech_status=AsyncMock(return_value={'voice_reply':False,'speech_to_text':False})
    b.route_tools=AsyncMock(return_value=[tool()]);c.llm_generate.return_value=NS(completion_text='{"mode":"auto","calls":[]}')
    await b.route_speech(e,ProviderRequest(prompt=e.message_str,func_tool=ToolSet(tools=[tool()])))
    assert e.get_extra('_intent_bridge_route')['calls']==[]
    assert b._record_error=='OSError'


def test_redaction_search_pagination_and_retention(tmp_path):
    records=RouteRecords(tmp_path,limit=3)
    for i in range(5):
        e=event('第'+str(i)+'条 sk-abcdefghijklmnop MUSIC_U=privatecookie')
        identity=records.begin(e)
        records.patch(identity,status='matched',planned=[describe(NS(name='cmd_x',description='',key='plugin:播放'),{'password':'secret','query':'安和桥','token':'private'})])
    assert len(records.rows)==3
    encoded=records.path.read_text()
    assert 'abcdefghijklmnop' not in encoded and 'privatecookie' not in encoded and 'secret' not in encoded
    assert records.query(query='安和桥')['total']==3
    assert records.query(query='/播放')['total']==3
    assert len(records.query(offset=1,limit=1)['items'])==1
    assert records.rows[-1]['planned'][0]['command']=='/播放'


def test_restart_marks_incomplete_calls_as_unconfirmed(tmp_path):
    records=RouteRecords(tmp_path);identity=records.begin(event())
    records.start_call(identity,tool(),{'query':'test'},'main_agent')
    recovered=RouteRecords(tmp_path)
    assert recovered.find(identity)['status']=='interrupted'
    assert recovered.find(identity)['executions'][0]['status']=='unknown'


def test_corrupt_history_is_not_overwritten(tmp_path):
    path=tmp_path/'route_records.json';path.write_text('broken')
    records=RouteRecords(tmp_path)
    assert records.storage_error
    with pytest.raises(OSError):records.begin(event())
    assert path.read_text()=='broken'

@pytest.mark.asyncio
async def test_records_api_searches_without_model_calls():
    b,c,e,req=await classified()
    app=Quart(__name__);app.add_url_rule('/records',view_func=b.control.records,methods=['GET'])
    c.llm_generate.reset_mock()
    response=await app.test_client().get('/records',query_string={'query':'安和桥'})
    assert response.status_code==200
    data=await response.get_json();assert data['total']==1 and data['items'][0]['user_text']=='推荐你先听安和桥'
    c.llm_generate.assert_not_awaited()
    assert (await app.test_client().get('/records?offset=-1')).status_code==400

@pytest.mark.asyncio
async def test_unauthorized_session_is_not_recorded():
    b,c,e=harness();other=event('请帮我听歌',uid='999')
    await b.route_speech(other,ProviderRequest(prompt=other.message_str,func_tool=ToolSet(tools=[tool()])))
    assert b.records_store.rows==[]
    c.llm_generate.assert_not_awaited()

@pytest.mark.asyncio
async def test_failed_dispatch_records_unknown_once_without_retry():
    b,c,e,req=await classified();b.config['extra_auto_tools']=['ncm_search']
    b.execute_native=AsyncMock(side_effect=TimeoutError())
    await b.on_request(e,req);await b.on_request(e,req)
    row=b.records_store.find(e.get_extra('_intent_bridge_record_id'))
    assert len(row['executions'])==1 and row['executions'][0]['status']=='unknown'
    assert row['executions'][0]['result']['error_type']=='TimeoutError'
    b.execute_native.assert_awaited_once()
