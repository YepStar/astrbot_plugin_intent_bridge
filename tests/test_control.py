import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,Mock
import pytest
from quart import Quart
from test_bridge import harness
from bridge_test_pkg.control import ControlPanel

class Config(dict):
 def save_config(self):
  if self.get('fail_save'):raise OSError('test')

def panel():
 b,c,e=harness();b.config=Config(b.config);b.config['api_key']='must-not-leak'
 key='test_plugin:查看状态';handler=NS(handler_module_path='fixture.main',desc='只读状态')
 converter=NS(catalog=Mock(return_value={key:[(handler,NS())]}),refresh=AsyncMock(),tools={},unsupported={},allowed=set(),config=Config(allowed_commands=[]),_allowlist_lock=asyncio.Lock())
 converter.is_allowed=lambda k:k in converter.allowed
 c.get_all_stars.return_value=[NS(name='astrbot_plugin_command_tools',activated=True,version='1',star_cls=converter)]
 c.get_llm_tool_manager.return_value=NS(func_list=[NS(name='weather',description='天气',active=True,handler_module_path=None)])
 control=ControlPanel(b);app=Quart(__name__)
 for path in ['status','refresh','commands','settings','tools']:
  handler={'status':control.status,'refresh':control.refresh,'commands':control.command,'settings':control.settings,'tools':control.tool}[path]
  app.add_url_rule('/'+path,view_func=handler,methods=['GET'] if path=='status' else ['POST'])
 return app,b,converter,key

@pytest.mark.asyncio
async def test_refresh_does_not_authorize_or_execute():
 app,b,c,key=panel();r=await app.test_client().post('/refresh');d=await r.get_json()
 assert d['commands'][0]['key']==key and not d['commands'][0]['enabled']
 assert c.config['allowed_commands']==[] and 'must-not-leak' not in str(d)
 c.refresh.assert_awaited_once()

@pytest.mark.asyncio
async def test_command_toggle_persists_exact_selector():
 app,b,c,key=panel();client=app.test_client()
 assert (await client.post('/commands',json={'key':key,'enabled':True})).status_code==200
 assert c.allowed=={key} and c.config['allowed_commands']==[key]
 assert (await client.post('/commands',json={'key':key,'enabled':False})).status_code==200
 assert not c.allowed
 assert (await client.post('/commands',json={'key':'unknown:删除','enabled':True})).status_code==409

@pytest.mark.asyncio
async def test_validation_rollback_and_tool_mask():
 app,b,c,key=panel();client=app.test_client()
 assert (await client.post('/settings',json={'allowed_umos':['group:123']})).status_code==400
 assert (await client.post('/settings',json={'meme_default_category':'../escape'})).status_code==400
 assert (await client.post('/settings',json={'enabled':False,'meme_default_category':'收藏'})).status_code==200
 assert b.config['enabled'] is False
 b.config['fail_save']=True
 assert (await client.post('/settings',json={'enabled':True})).status_code==500
 assert b.config['enabled'] is False
 b.config.pop('fail_save')
 assert (await client.post('/tools',json={'name':'weather','enabled':False})).status_code==200
 assert b.config['disabled_tools']==['weather']
 assert (await client.post('/tools',json={'name':'pc_send_to_group','enabled':True})).status_code==400

@pytest.mark.asyncio
async def test_disabled_parent_cannot_be_toggled_even_with_forged_api_request():
 from bridge_test_pkg.control import star_map
 app,b,c,key=panel();star_map['fixture.main'].activated=False
 client=app.test_client()
 assert (await client.post('/commands',json={'key':key,'enabled':True})).status_code==409
 c.allowed.add(key);c.config['allowed_commands']=[key]
 assert (await client.post('/commands',json={'key':key,'enabled':False})).status_code==409
 assert c.config['allowed_commands']==[key]

@pytest.mark.asyncio
async def test_revoke_one_from_package_retains_other_exact_commands():
 app,b,c,key=panel();other='test_plugin:其他状态'
 catalog=c.catalog.return_value;catalog[other]=catalog[key]
 c.allowed={'test_plugin'};c.config['allowed_commands']=['test_plugin']
 c.is_allowed=lambda k:k in c.allowed or k.split(':')[0] in c.allowed
 r=await app.test_client().post('/commands',json={'key':key,'enabled':False})
 assert r.status_code==200 and c.allowed=={other}

@pytest.mark.asyncio
async def test_command_refresh_failure_rolls_back_authorization():
 app,b,c,key=panel();c.refresh.side_effect=[RuntimeError('refresh failed'),None]
 r=await app.test_client().post('/commands',json={'key':key,'enabled':True})
 assert r.status_code==500 and not c.allowed and c.config['allowed_commands']==[]
