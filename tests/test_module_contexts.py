import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from test_bridge import harness
from astrbot.api.provider import ProviderRequest
from astrbot.core.star.star import star_map
from bridge_test_pkg.readiness import module_contexts
import bridge_test_pkg.catalog as catalog

@pytest.mark.asyncio
async def test_state_hook_is_session_filtered_and_read_once(monkeypatch):
    b,c,e=harness()
    getter=lambda event: {'pending_offer':{'offer_id':'scoped-offer','song':{'name':'Test'}}}
    monkeypatch.setitem(star_map,'ncm.fixture',NS(name='music_fixture'))
    resolver=AsyncMock(return_value=NS(intent_bridge_context=getter))
    monkeypatch.setattr(catalog,'plugin_for',resolver)
    tools=[NS(handler_module_path='ncm.fixture'),NS(handler_module_path='ncm.fixture')]
    states=await module_contexts(c,e,tools)
    assert states['music_fixture']['pending_offer']['offer_id']=='scoped-offer'
    assert resolver.await_count==1
    resolver.return_value=None
    assert await module_contexts(c,e,tools)=={}

@pytest.mark.asyncio
async def test_pending_context_reaches_classifier_without_executing(monkeypatch):
    b,c,e=harness()
    monkeypatch.setitem(star_map,'ncm.fixture',NS(name='music_fixture'))
    monkeypatch.setattr(catalog,'plugin_for',AsyncMock(return_value=NS(intent_bridge_context=lambda event:{'pending_offer':{'offer_id':'pending-123'}})))
    tool=NS(name='ncm_reply_together',active=True,description='Accept the current offer',handler_module_path='ncm.fixture',parameters={'type':'object','properties':{'offer_id':{'type':'string'},'accept':{'type':'boolean'}},'required':['offer_id','accept']})
    c.llm_generate=AsyncMock(return_value=NS(completion_text=json.dumps({'mode':'auto','calls':[{'name':'ncm_reply_together','arguments':{'offer_id':'pending-123','accept':True}}]})))
    e.message_str='好呀，来吧'
    plan=await b.plan(e,ProviderRequest(),[tool],{'voice_reply':False})
    assert plan['calls'][0]['arguments']=={'offer_id':'pending-123','accept':True}
    assert 'pending-123' in c.llm_generate.call_args.kwargs['prompt']
