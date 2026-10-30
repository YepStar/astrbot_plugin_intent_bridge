import importlib,sys,types
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,Mock,patch
import json
import pytest
from PIL import Image as PIL
from astrbot.api.message_components import Image,Reply
from astrbot.api.provider import ProviderRequest
from astrbot.core.agent.tool import FunctionTool,ToolSet
from test_bridge import harness,event
from bridge_test_pkg.meme_bridge import ImageInbox,explicit_save,save_images

@pytest.mark.parametrize('text',['保存这个表情','把上一张收藏起来','收录到开心分类','把这两张都存起来'])
def test_save_intent(text):assert explicit_save(text)
@pytest.mark.parametrize('text',['不要保存这张','比如我说保存表情','假设我要收藏这个','看看表情','取消收藏'])
def test_negative_intent(text):assert not explicit_save(text)

def test_cache_scope_expiration_and_reply(tmp_path):
 p=tmp_path/'a.png';PIL.new('RGB',(16,16)).save(p)
 e=event('图');e.message_obj.message=[Image.fromFileSystem(p)]
 inbox=ImageInbox();inbox.remember(e)
 assert len(inbox.select(event('保存这个')))==1
 assert not inbox.select(event('保存这个',uid='other'))
 inbox.items[inbox.key(e)]['at']-=301
 assert not inbox.select(event('保存这个'))
 e.message_obj.message=[Reply(id='quoted',chain=[Image.fromFileSystem(p)])]
 assert len(inbox.select(e,'reply'))==1

@pytest.fixture
def manager_modules(tmp_path,monkeypatch):
 import astrbot.core.utils.astrbot_path as paths
 monkeypatch.setattr(paths,'get_astrbot_plugin_data_path',lambda:str(tmp_path/'data'))
 package=types.ModuleType('meme_fixture');package.__path__=[__import__('os').environ.get('MEME_MANAGER_SOURCE','/AstrBot/data/plugins/meme_manager')]
 monkeypatch.setitem(sys.modules,'meme_fixture',package)
 for name in list(sys.modules):
  if name.startswith('meme_fixture.'):monkeypatch.delitem(sys.modules,name)
 auto=importlib.import_module('meme_fixture.backend.auto_collect')
 sem=importlib.import_module('meme_fixture.backend.semantic.storage')
 packs=tmp_path/'packs';(packs/'test-pack/memes').mkdir(parents=True)
 monkeypatch.setattr(auto,'PACKS_DIR',packs)
 monkeypatch.setattr(auto,'get_pack_paths',lambda p:{'memes_dir':packs/p/'memes'})
 monkeypatch.setattr(sem,'invalidate_semantic_metadata',Mock())
 class Plugin:pass
 Plugin.__module__='meme_fixture.main';plugin=Plugin()
 plugin._resolve_runtime_pack_context=lambda **kw:{'pack_id':'test-pack','memes_dir':str(packs/'test-pack/memes')}
 plugin.semantic_task_manager=NS(begin_external_pack_operation=Mock(),end_external_pack_operation=Mock())
 plugin.reload_emotions=AsyncMock()
 return plugin,packs

@pytest.mark.asyncio
async def test_actual_gif_saved_followup_and_deduplicated(tmp_path,manager_modules):
 plugin,packs=manager_modules;gif=tmp_path/'a.gif'
 frames=[PIL.new('RGB',(24,24),c) for c in ('red','blue')]
 frames[0].save(gif,save_all=True,append_images=frames[1:],format='GIF',duration=80,loop=0)
 b,c,e=harness();e.role='admin';e.message_obj.message=[Image.fromFileSystem(gif)]
 b._image_inbox.remember(e);e.message_str='把上一张表情保存起来';e.message_obj.message=[]
 out=await save_images(b,e,plugin)
 assert out['saved_count']==1 and out['category']=='用户收藏'
 file=next((packs/'test-pack/memes/用户收藏').iterdir())
 assert file.read_bytes()==gif.read_bytes()
 with PIL.open(file) as image:assert image.n_frames==2
 again=await save_images(b,e,plugin)
 assert again['status']=='already_saved' and again['duplicate_count']==1
 assert plugin.semantic_task_manager.end_external_pack_operation.call_count==2

@pytest.mark.asyncio
async def test_permission_and_missing_image(manager_modules):
 plugin,packs=manager_modules;b,c,e=harness();e.message_str='保存这个表情'
 assert (await save_images(b,e,plugin))['status']=='denied'
 e.role='admin';assert (await save_images(b,e,plugin))['status']=='needs_image'
 e.message_str='不要保存';assert (await save_images(b,e,plugin))['status']=='denied'
 plugin.semantic_task_manager.begin_external_pack_operation.assert_not_called()

@pytest.mark.asyncio
async def test_path_traversal_and_semantic_flow(tmp_path,manager_modules):
 plugin,packs=manager_modules;b,c,e=harness();e.role='admin';e.message_str='保存这个表情'
 p=tmp_path/'a.png';PIL.new('RGB',(8,8),color='green').save(p)
 e.message_obj.message=[Image.fromFileSystem(p)]
 assert (await save_images(b,e,plugin,category='../escape'))['status']=='invalid_category'
 t=FunctionTool(name='bridge_save_received_meme',description='保存真实附件',parameters={'type':'object','properties':{'source':{'type':'string'}}})
 req=ProviderRequest(prompt=e.message_str,func_tool=ToolSet(tools=[t]))
 b.speech_status=AsyncMock(return_value={'voice_reply':False,'speech_to_text':False})
 c.llm_generate.return_value=NS(completion_text=json.dumps({'mode':'auto','kind':'normal','calls':[{'name':t.name,'arguments':{'source':'current'}}]}))
 with patch('bridge_test_pkg.main.plugin_for',new=AsyncMock(return_value=plugin)):
  await b.route_speech(e,req);await b.on_request(e,req);await b.on_request(e,req)
 assert len(list((packs/'test-pack/memes/用户收藏').iterdir()))==1
 assert req.func_tool.get_tool(t.name) is None
 assert '"saved_count": 1' in req.extra_user_content_parts[-1].text

@pytest.mark.asyncio
async def test_correct_search_to_save_dispatches_real_meme_storage(tmp_path,manager_modules):
 from types import SimpleNamespace as NS
 plugin,packs=manager_modules
 picture=tmp_path/'correction.png';PIL.new('RGB',(24,24),'green').save(picture)
 b,c,e=harness();e.role='admin';e.message_str='找个表情'
 b._corrections.remember(e,{'calls':[{'name':'search_memes'}]})
 e.message_str='不对，不是找旧表情，是保存我发的这张'
 e.message_obj.message=[Image.fromFileSystem(picture)]
 b.speech_status=AsyncMock(return_value={'voice_reply':False,'speech_to_text':False})
 candidates=ToolSet(tools=[FunctionTool(name=n,description=n,parameters={'type':'object','properties':{}}) for n in ['search_memes','bridge_save_received_meme']])
 req=ProviderRequest(func_tool=candidates)
 c.llm_generate.side_effect=[NS(completion_text=json.dumps({'mode':'auto','calls':[],'rejected_tools':['search_memes']})),NS(completion_text=json.dumps({'mode':'auto','calls':[{'name':'bridge_save_received_meme','arguments':{}}]}))]
 with patch('bridge_test_pkg.main.plugin_for',new=AsyncMock(return_value=plugin)):
  await b.route_speech(e,req);await b.on_request(e,req)
 files=list((packs/'test-pack/memes/用户收藏').iterdir())
 assert len(files)==1 and files[0].read_bytes()==picture.read_bytes()
 assert req.func_tool.get_tool('search_memes') is None
 assert '"saved_count": 1' in req.extra_user_content_parts[-1].text
 assert c.llm_generate.await_count==2
