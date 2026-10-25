"""Exercise actual patched companion methods without importing hardware modules."""
import ast,time,os
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
source_path=Path(os.environ.get('COMPANION_TTS_SOURCE', '/AstrBot/data/plugins/astrbot_plugin_private_companion/tts_enhancement.py'))
if not source_path.exists():
 pytest.skip('set COMPANION_TTS_SOURCE to the patched companion source', allow_module_level=True)
source=source_path.read_text()
tree=ast.parse(source)
names={'_event_tts_request_signal','_tts_session_interval_remaining','_tts_hard_block_reason','_maybe_convert_plain_reply_to_tts','apply_tts_enhancement_request'}
methods=[node for node in ast.walk(tree) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names]
cls=ast.ClassDef(name='ActualPolicy',bases=[],keywords=[],body=methods,decorator_list=[])
module=ast.Module(body=[cls],type_ignores=[]);ast.fix_missing_locations(module)
ns={'Any':object,'_single_line':lambda x,n:str(x or '')[:n],'time':time}
exec(compile(module,'actual_tts_policy','exec'),ns);Policy=ns['ActualPolicy']

def policy(strong=False):
 p=Policy();p._tts_strong_constraint_enabled=lambda:strong
 p._tts_setting=lambda k,d=None:{'tts_session_min_interval_seconds':90}.get(k,d)
 p._tts_session_key=lambda e:'private';p._tts_effective_min_interval_seconds=lambda e:90
 p._tts_session_last_at={'private':time.time()}
 return p

@pytest.mark.parametrize('text',['想听你说话','亲口说喜欢我','能哼两句吗'])
def test_semantic_voice_recognized_and_bypasses_automatic_cooldown(text):
 p=policy();e=NS(message_str=text,_intent_bridge_voice_decision='voice')
 assert p._event_tts_request_signal(e)[0]=='positive'
 assert p._tts_session_interval_remaining(e)==0

def test_strong_policy_and_auto_cooldown_preserved():
 e=NS(_intent_bridge_voice_decision='voice');assert policy(True)._tts_session_interval_remaining(e)>0
 assert policy()._tts_session_interval_remaining(NS())>0

@pytest.mark.asyncio
async def test_text_blocks_prompt_plain_conversion_and_tagged_synthesis():
 p=policy();e=NS(message_str='开会中',_intent_bridge_voice_decision='text')
 assert p._event_tts_request_signal(e)[0]=='negative'
 assert p._tts_hard_block_reason(e)=='semantic_text_preference'
 assert await p._maybe_convert_plain_reply_to_tts('好',e)==[]
 assert await p.apply_tts_enhancement_request(e,NS()) is None
