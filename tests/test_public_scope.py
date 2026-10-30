"""Public scope authorization is explicit and independent of local memory policy."""
import pytest
from test_bridge import harness, event
from test_control import panel
from astrbot.api.event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata


def group_event(group_id):
    source = event()
    message = source.message_obj
    message.type = MessageType.GROUP_MESSAGE
    message.group_id = group_id
    message.session_id = group_id
    return AstrMessageEvent(source.message_str, message,
                           PlatformMetadata('aiocqhttp', 'test', 'qq_test'), group_id)


def test_group_requires_its_own_explicit_authorization():
    bridge, context, private = harness()
    group = group_event('group-a')
    other = group_event('group-b')
    assert group.get_group_id()
    assert not bridge.allowed(group)
    bridge.config['allowed_umos'].append(group.unified_msg_origin)
    assert bridge.allowed(group)
    assert bridge.allowed(private)
    assert not bridge.allowed(other)
    bridge.config['enabled'] = False
    assert not bridge.allowed(group)


@pytest.mark.asyncio
async def test_panel_accepts_full_group_and_private_umos():
    app, bridge, converter, key = panel()
    scopes = ['test:FriendMessage:user-a', 'test:GroupMessage:group-a']
    response = await app.test_client().post('/settings', json={'allowed_umos': scopes})
    assert response.status_code == 200
    assert bridge.config['allowed_umos'] == scopes


@pytest.mark.asyncio
@pytest.mark.parametrize('umo', ['group:123', ':GroupMessage:123', 'test:GroupMessage:',
                                 'test:Unknown:123', 'test:FriendMessage:   '])
async def test_panel_rejects_incomplete_or_unknown_umos(umo):
    app, bridge, converter, key = panel()
    response = await app.test_client().post('/settings', json={'allowed_umos': [umo]})
    assert response.status_code == 400
