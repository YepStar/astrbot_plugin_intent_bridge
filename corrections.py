"""显式纠错后排除旧能力；按用户及会话隔离，不因执行失败自动重试。"""

import hashlib
import time
from collections import OrderedDict
from pathlib import Path

from .translation import atomic_json, read_json, state_directory


def digest(text):
    return hashlib.sha256(str(text).encode()).hexdigest()


class CorrectionStore:
    def __init__(self, directory=None):
        self.path = Path(directory or state_directory()) / "route_rejections.json"
        self.rejections = read_json(self.path)
        self.previous = OrderedDict()

    def scope(self, event):
        return digest(event.unified_msg_origin + "\n" + str(event.get_sender_id()))

    def query_key(self, event, query):
        normalized = " ".join(str(query).casefold().split())
        return self.scope(event) + ":" + digest(normalized)

    def excluded(self, event, query):
        item = self.rejections.get(self.query_key(event, query), {})
        if not isinstance(item, dict) or time.time() - item.get("at", 0) > 30 * 86400:
            return set()
        return set(item.get("tools", []))

    def last(self, event):
        item = self.previous.get(self.scope(event))
        if item and time.time() - item["at"] < 600:
            return item
        return None

    def remember(self, event, decision):
        # 普通聊天使上一轮纠错候选失效，避免误拒绝很久以前的动作。
        key = self.scope(event)
        if not decision["calls"]:
            self.previous.pop(key, None)
            return
        self.previous[key] = {
            "at": time.time(),
            "query": str(event.message_str)[:1600],
            "tools": [call["name"] for call in decision["calls"]],
        }
        self.previous.move_to_end(key)
        while len(self.previous) > 128:
            self.previous.popitem(last=False)

    def reject(self, event, query, names):
        rejected = self.excluded(event, query) | set(names)
        updated = {
            k: v
            for k, v in self.rejections.items()
            if isinstance(v, dict) and time.time() - v.get("at", 0) < 30 * 86400
        }
        updated[self.query_key(event, query)] = {
            "at": time.time(),
            "tools": sorted(rejected)[:100],
        }
        updated = dict(
            sorted(updated.items(), key=lambda item: item[1].get("at", 0))[-500:]
        )
        # 即使磁盘失败，本轮内存排除也必须生效；由调用端报告持久化失败。
        self.rejections = updated
        atomic_json(self.path, updated)
