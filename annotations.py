"""面板与分类提示词的中文注释；不修改工具标识、参数或原插件描述。"""
import re

PLUGIN_NAMES = {
    'builtin_commands':'系统内置指令','astrbot':'系统基础功能',
    'astrbot_plugin_intent_bridge':'自然意图与插件整合',
    'meme_manager':'表情包管理器','astrbot_plugin_meme_manager':'表情包管理器',
    'astrbot_plugin_private_companion':'私聊陪伴','astrbot_plugin_command_tools':'指令工具转换器',
    'astrbot_plugin_livingmemory':'私聊长期记忆','astrbot_plugin_self_learning':'群聊自学习',
    'astrbot_plugin_nomi_music':'网易云一起听','astrbot_plugin_netease_music':'网易云点歌',
    'astrbot_plugin_bilibili_ai_bot':'B站互动与浏览','astrbot_plugin_xiaoheihe_adapter':'小黑盒接入',
    'astrbot_plugin_content_companion':'内容与创作','astrbot_plugin_image_companion':'图片生成扩展',
    'astrbot_plugin_reality_companion':'现实触及扩展','astrbot_plugin_link_resolver':'链接解析',
    'astrbot_plugin_astrbot_enhance_mode':'增强模式','astrbot_plugin_bili_humanism_bridge':'B站公共记忆整合',
    'astrbot_plugin_deepseek_daily_budget':'DeepSeek每日预算',
}

# 中文名称用于展示。工具调用仍使用字典键中的原始英文标识。
TOOL_NAMES = {
    'bridge_capabilities':'发现插件能力','bridge_save_received_meme':'收藏收到的表情',
    'bridge_join_listening':'接受一起听邀请','bridge_research':'检索B站与小黑盒',
    'grok_web_search':'联网搜索公开信息','search_memes':'搜索已有表情',
    'music_now':'查看正在播放的歌曲','music_room':'查看一起听房间',
    'pc_generate_photo':'生成角色图片','pc_send_current_media':'发送本轮生成的图片',
    'pc_find_reaction_image':'查找并发送角色表情','pc_manage_memo':'管理备忘便签',
    'pc_manage_schedule':'管理今日日程','pc_view_creative_work':'查看角色作品',
    'content_companion_view_work':'查看内容资料柜','pc_get_group_id_by_name':'按名称查询群号',
    'pc_get_user_id_by_name':'按名称查找群友','pc_query_relation_person':'查询关系网人物',
    'pc_get_specified_group_members':'查询指定群成员','pc_query_wardrobe_detail':'查看衣柜与穿搭',
    'pc_set_outfit_intent':'记录角色换装意图','pc_query_interaction':'查询近期互动',
    'pc_relay_message':'转述消息','pc_send_to_group':'向指定群发消息',
    'pc_send_to_groups':'向多个群发通知','pc_send_to_private_user':'向指定用户发私聊',
    'pc_send_to_private_users':'向多个用户发私聊','pc_schedule_group_relay':'等待目标发言后转述',
    'pc_qzone_view_feed':'查看QQ空间动态','pc_qzone_publish_feed':'发布QQ空间动态',
    'pc_qzone_reply_my_comment':'回复自己空间的评论',
    'pc_reality_touch_reminder':'执行现实触及提醒','pc_reality_touch_action':'处理家居与健康请求',
    'pc_reality_touch_camera_snapshot':'读取已授权摄像头单帧',
    'recall_long_term_memory':'回忆私聊长期记忆','enhance_memory_rag_read':'检索增强记忆',
    'enhance_memory_rag_write':'写入增强记忆','enhance_use_image':'使用历史图片',
    'enhance_get_ban_list_status':'查看增强模式禁用名单','enhance_ban_user':'临时禁用群成员',
    'enhance_unban_user':'解除群成员禁用','search_bilibili':'搜索B站内容',
    'bili_parse_video':'解析B站视频','watch_video':'读取视频内容','bili_bangumi':'查询B站番剧',
    'bili_watch_videos':'浏览B站视频','bili_recall':'回顾B站浏览记忆','bili_action':'执行B站互动',
    'watch_and_share_video_private':'观看B站视频并私信分享',
    'bili_block_user':'管理B站用户屏蔽','future_task':'管理定时任务',
    'create_scheduled_task':'创建定时任务','list_scheduled_tasks':'查看定时任务',
    'delete_scheduled_task':'删除定时任务','update_scheduled_task':'修改定时任务',
    'get_current_time':'获取当前时间','astrbot_execute_shell':'执行终端命令',
    'astrbot_execute_python':'执行Python代码','astrbot_file_read_tool':'读取文件内容',
    'astrbot_shell_session':'管理终端会话','astrbot_execute_browser':'操作浏览器',
}

TOOL_COMMENTS = {
    'bridge_save_received_meme':'把用户明确要求收藏的真实图片保存到当前图库；支持本条、引用或同一私聊最近5分钟的图片，保留管理员权限，按真实入库回执确认成功。',
    'bridge_capabilities':'查看本会话真实可用的插件、工具和指令，不会仅因发现功能就自动执行或授权。',
    'bridge_join_listening':'接受已经收到的网易云一起听邀请；没有邀请、用户否定或仅在举例时不加入。',
    'bridge_research':'只读检索B站与小黑盒的公开内容，返回真实正文、字幕或评论摘录，不发布评论。',
    'grok_web_search':'通过已配置的搜索服务查询当前公开网页信息，返回文字结果；不把私聊或凭据作为搜索词。',
    'search_memes':'在已安装图库中寻找适合表达当前语气的已有表情；这不是收藏新图片的功能。',
    'enhance_memory_rag_read':'读取增强模式记忆库中与请求相关的记录；受原插件开关和权限限制。',
    'enhance_memory_rag_write':'将明确需要保存的信息写入增强模式记忆库，不用于保存表情图片。',
    'enhance_use_image':'从运行时历史中选择一张真实图片，用于多模态输入或历史补充；不会凭空生成图片路径。',
    'enhance_get_ban_list_status':'只读查看增强模式维护的禁用名单状态。',
    'enhance_ban_user':'临时禁用当前群中的指定用户；仍由原插件检查管理员权限。',
    'enhance_unban_user':'解除当前群指定用户的禁用状态；仍由原插件检查管理员权限。',
    'content_companion_view_work':'读取角色资料柜中实际存在的作品，不把临时生成的文章说成库存。',
    'future_task':'创建、查看或调整定时任务；具体支持的动作和确认流程以原工具参数为准。',
    'recall_long_term_memory':'检索此前真实保存的私聊记忆，帮助回忆聊过的事；没有记录时不编造。',
    'astrbot_execute_shell':'在原工具许可的环境中执行终端命令，执行权限仍由原工具控制。',
    'astrbot_execute_python':'在原工具许可的环境中运行Python代码，执行权限仍由原工具控制。',
    'astrbot_file_read_tool':'按原工具提供的路径和权限读取文件，不因接入意图路由获得额外访问权限。',
    'watch_and_share_video_private':'按用户明确要求观看指定B站视频、保存视频记忆，再向原插件配置的主人B站账号发送分享卡片；只有原插件已启用该功能且接收账号有效时可用。',
}

COMMAND_COMMENTS = {
    'help':'查看可用指令与帮助说明。','sid':'查看当前会话的完整UMO标识，可用于填写私聊授权范围。',
    'new':'创建新的对话；会影响当前上下文，是否允许由原指令决定。',
    'reset':'重置当前对话上下文；这类生命周期指令可能不支持工具转换。',
    'stop':'停止当前进行中的响应或任务；以原指令实际支持范围为准。',
    'plugin':'管理已安装插件及其启用状态；具体子指令和权限沿用原插件。',
    'provider':'查看或切换模型提供商；具体子指令与参数以原指令为准。',
    'model':'查看或切换当前模型；具体参数以原指令为准。',
    'persona':'查看或切换人格；具体参数以原指令为准。',
    'cmdtools':'查看和管理指令转换器的授权列表。','deepseek预算':'查看DeepSeek今日预算、已用与预留费用。',
    'name':'设置当前会话UMO的显示名称，需要管理员权限。',
    'stats':'查看当前对话的Token用量统计。',
    'dashboard_update':'更新AstrBot管理面板，需要管理员权限；程序更新类指令可能不支持工具转换。',
    'set':'设置当前会话中的指定变量，需提供变量名和值。',
    'unset':'移除当前会话中的指定变量，需提供变量名。',
    'enhance':'增强模式的管理指令入口，具体功能由其子指令提供。',
    'enhance rag-webui':'打开增强记忆检索的管理页面。',
    'biliUMO':'查看当前B站会话的UMO标识。',
    '表情管理 添加表情':'进入指定分类的手动收图流程，需要随后发送图片；自然语言直接收藏应使用“收藏收到的表情”专用适配器。',
    '表情管理 查看图库':'列出当前图库中可以使用的表情分类。',
    '表情管理 添加分类':'在当前图库中添加分类及其说明。',
    '表情管理 清空全部':'清空图库中的全部表情图片；属于删除操作，必须沿用原模块权限和确认规则。',
    '表情管理 清空指定类型':'删除指定分类中的图片；属于删除操作。',
    '表情管理 删除类型本身':'删除指定分类及其说明；属于删除操作。',
    '一起听':'接受当前收到的网易云一起听邀请。','听歌状态':'查看当前一起听房间状态。',
}


def has_chinese(text):
    return bool(re.search(r'[\u3400-\u9fff]',str(text or '')))


def plugin_title(name):
    return PLUGIN_NAMES.get(name,name)


def command_annotation(plugin, command, description=''):
    raw=str(description or '').strip()
    title=command if has_chinese(command) else COMMAND_COMMENTS.get(command,'插件指令').split('；')[0].split('。')[0]
    if title=='插件指令' and has_chinese(raw):
        title=raw.split('\n',1)[0].split('。',1)[0][:40]
    comment=COMMAND_COMMENTS.get(command)
    if not comment and has_chinese(raw):comment=raw.split('\n\n',1)[0][:500]
    if not comment:
        comment=f'来自「{plugin_title(plugin)}」的指令；原插件未提供中文用途说明，请结合原始说明和参数判断。'
    return {'title_zh':title,'comment_zh':comment}


def tool_annotation(name, description='', command_key=None):
    if command_key and ':' in command_key:
        plugin,command=command_key.split(':',1)
        return command_annotation(plugin,command,description)
    raw=str(description or '').strip()
    title=TOOL_NAMES.get(name)
    comment=TOOL_COMMENTS.get(name)
    if not title:title='插件工具：'+name
    if not comment and has_chinese(raw):comment=raw.split('\n\n',1)[0][:500]
    if not comment:comment='原插件未提供中文用途说明；请展开原始说明查看具体功能，调用参数与权限沿用原工具。'
    return {'title_zh':title,'comment_zh':comment}
