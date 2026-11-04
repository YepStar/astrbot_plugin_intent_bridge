import json
import pytest
from bridge_test_pkg.routing import parse_route, build_prompt, PRESETS
from bridge_test_pkg.main import GUIDE

def test_music_route_preserves_semantic_direction():
    result=parse_route(json.dumps({'mode':'auto','calls':[],'music_actions':['listen']}),{})
    assert result['music_actions']==['listen']

@pytest.mark.parametrize('actions',['listen',['shell'],[{}],None])
def test_route_rejects_invalid_music_actions(actions):
    with pytest.raises(ValueError):parse_route(json.dumps({'mode':'auto','calls':[],'music_actions':actions}),{})

def test_workflows_distinguish_recommend_to_bot_and_share_to_user():
    prompt=build_prompt('这种天很适合听民谣呢，推荐你先听《安和桥》',[],[],False)
    assert 'music_actions' in prompt
    for guide in [GUIDE,PRESETS['music']]:
        assert 'ncm_listen' in guide and '推荐你先听' in guide
        assert '推荐我听' in guide and 'ncm_share' in guide
