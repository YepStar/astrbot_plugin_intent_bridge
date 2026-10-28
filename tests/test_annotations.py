from types import SimpleNamespace as NS
import test_bridge  # 复用现有测试包初始化，不加载真实运行中的插件实例。
from bridge_test_pkg.annotations import tool_annotation,command_annotation
from bridge_test_pkg.routing import descriptors,parse_route
import json


def test_chinese_annotations_preserve_call_identity_and_schema():
    schema={'type':'object','properties':{'category':{'type':'string'}}}
    tool=NS(name='bridge_save_received_meme',description='Original description',parameters=schema,active=True)
    record=descriptors([tool])[0]
    assert record['name']=='bridge_save_received_meme'
    assert record['parameters'] is schema
    assert record['description']=='Original description'
    assert '收藏' in record['title_zh'] and '真实' in record['comment_zh']
    plan=parse_route(json.dumps({'mode':'auto','calls':[{'name':tool.name,'arguments':{'category':'开心'}}]}),{tool.name:tool})
    assert plan['calls'][0]['name']==tool.name


def test_unknown_capability_does_not_invent_chinese_functionality():
    record=tool_annotation('unknown_future_tool','Unspecified future behavior')
    assert '原插件未提供中文用途说明' in record['comment_zh']
    known=command_annotation('meme_manager','表情管理 添加表情')
    assert '随后发送图片' in known['comment_zh']
    cmd=tool_annotation('cmd_dynamic_123','Run command','meme_manager:表情管理 查看图库')
    assert cmd['title_zh']=='表情管理 查看图库'
