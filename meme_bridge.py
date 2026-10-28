"""Explicit attachment collection; never accepts a model-authored URL or path."""
import asyncio
import copy
import hashlib
import importlib
import re
import time
from collections import OrderedDict
from pathlib import Path

from astrbot.api.message_components import Image, Reply

SAVE = re.compile(r'保存|收藏|收录|收下|存下|存起来|收起来|加.{0,5}(图库|表情库)')
DENY = re.compile(r'(不要|别|不用|不必|取消|先不).{0,15}(保存|收藏|收录|存|收)|(?:例如|比如|假如|假设|他说|她说|测试用例)')


def explicit_save(text):
    return bool(SAVE.search(str(text or '')) and not DENY.search(str(text or '')))


class ImageInbox:
    def __init__(self):
        self.items = OrderedDict()

    @staticmethod
    def key(event):
        return (event.unified_msg_origin, str(event.get_sender_id()))

    @staticmethod
    def current(event):
        return [c for c in event.message_obj.message if isinstance(c, Image)][:4]

    @staticmethod
    def quoted(event):
        return [c for part in event.message_obj.message if isinstance(part, Reply)
                for c in (part.chain or []) if isinstance(c, Image)][:4]

    def remember(self, event):
        now = time.monotonic()
        for key in list(self.items):
            if now - self.items[key]['at'] > 300:
                del self.items[key]
        images = self.current(event)
        if images:
            self.items[self.key(event)] = {'at': now, 'images': copy.deepcopy(images)}
            self.items.move_to_end(self.key(event))
        while len(self.items) > 128:
            self.items.popitem(last=False)

    def select(self, event, source='auto'):
        current, quoted = self.current(event), self.quoted(event)
        recent = self.items.get(self.key(event), {})
        images = recent.get('images', []) if time.monotonic()-recent.get('at', 0) <= 300 else []
        if source == 'current':return current
        if source == 'reply':return quoted
        if source == 'recent':return images
        if source != 'auto':raise ValueError('Invalid attachment source')
        return current or quoted or images

    def summary(self, event):
        return {s: len(self.select(event, s)) for s in ('current','reply','recent')}


async def save_images(bridge, event, plugin, category='', source='auto', image_index=1):
    if not explicit_save(event.message_str):
        return {'status':'denied','saved':False,'reason':'需要当前用户明确要求保存；否定、引用示例不执行'}
    admin = getattr(event, 'role', '') == 'admin'
    is_admin = getattr(event, 'is_admin', None)
    if callable(is_admin):admin = admin or bool(is_admin())
    if not admin:
        return {'status':'denied','saved':False,'reason':'沿用表情管理器的管理员保存权限'}
    images = bridge._image_inbox.select(event, source)
    if not images:
        return {'status':'needs_image','saved':False,'reason':'请重新发送或引用要保存的图片；最近图片引用仅保留5分钟'}
    if type(image_index) is not int or image_index < 0 or image_index > len(images):
        return {'status':'needs_selection','saved':False,'image_count':len(images)}
    images = images if image_index == 0 else [images[image_index-1]]
    package = plugin.__class__.__module__.rsplit('.', 1)[0]
    auto = importlib.import_module(package + '.backend.auto_collect')
    semantic = importlib.import_module(package + '.backend.semantic.storage')
    category = str(category or bridge.config.get('meme_default_category','用户收藏')).strip()
    if len(category) > 48 or not auto.is_safe_category_name(category):
        return {'status':'invalid_category','saved':False}
    pack = plugin._resolve_runtime_pack_context(event=event)
    pack_id = str(pack.get('pack_id') or '')
    if not pack_id:return {'status':'unavailable','saved':False,'reason':'未选择可用表情包'}
    contents = []
    for image in images:
        path = Path(await asyncio.wait_for(image.convert_to_file_path(), timeout=25))
        if path.stat().st_size > 20*1024*1024:
            return {'status':'too_large','saved':False}
        content = await asyncio.to_thread(path.read_bytes)
        extension = await asyncio.to_thread(auto.AutoCollectManager._validate_image, content)
        contents.append((content, hashlib.sha256(content).hexdigest(), extension))
    saved, duplicates = [], 0
    async with bridge._meme_save_lock:
        plugin.semantic_task_manager.begin_external_pack_operation(pack_id, '用户明确收藏表情')
        try:
            for content, digest, extension in contents:
                path = await asyncio.to_thread(auto.AutoCollectManager._write_pack_image,
                                               pack_id, category, content, digest, extension)
                if path is None:duplicates += 1
                else:saved.append(path.name)
            semantic.invalidate_semantic_metadata(Path(pack['memes_dir']).parent)
        finally:
            plugin.semantic_task_manager.end_external_pack_operation(pack_id)
    await plugin.reload_emotions()
    return {'status':'saved' if saved else 'already_saved','saved':bool(saved),
            'saved_count':len(saved),'duplicate_count':duplicates,'pack_id':pack_id,
            'category':category,'files':saved,'semantic_index':'not_confirmed',
            'note':'图片已入库；不据此声称语义索引已完成。无需重复保存。'}
