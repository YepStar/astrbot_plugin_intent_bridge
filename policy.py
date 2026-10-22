"""Small deterministic gates; models may select only a bounded action vocabulary."""
from __future__ import annotations
import json
import re

MUSIC = re.compile(r'(一起听.{0,6}(歌|音乐)|想.{0,5}一起听|网易云.{0,8}(拉|邀|进|房间)|[拉邀].{0,5}你.{0,5}(听歌|网易云))', re.I)
RESEARCH = re.compile(r'(最新|新版|更新|版本|补丁|新闻|热点|时事|刚出|好玩吗|强不强|强吗|值得.{0,4}(玩|买)|攻略|评测|测评|搜一下|查一下|搜索|查查|怎么评价)', re.I)
META = re.compile(r'(例如|比如|假设|如果.{0,8}(说|问)|他说|她说|指令|触发词|测试|为什么.{0,8}(执行|触发)|[“「『"].{0,60}(一起听|网易云).{0,60}[”」』"])')
NO_MUSIC = re.compile(r'(不想|不要|别|不用|不必|取消|先不).{0,10}(听|接受|加入|进|邀|网易云)|退出.{0,6}(听|房间)|停止.{0,6}(听|音乐)')
NO_SEARCH = re.compile(r'(不要|别|不用|不必|无需).{0,10}(搜|查|联网)|不联网')
PRIVATE = re.compile(r'(?:\b\d{6,}\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|https?://|sk-[\w-]+|Bearer\s+|(?:cookie|token|password|api[_ -]?key)\s*[:=])', re.I)


def candidate(text):
    text = str(text or '').strip()
    if not text or text.startswith(('/', '!')) or META.search(text):
        return False
    return bool((MUSIC.search(text) and not NO_MUSIC.search(text)) or (RESEARCH.search(text) and not NO_SEARCH.search(text)))


def direct_music(text):
    return bool(MUSIC.search(text or '') and not META.search(text or '') and not NO_MUSIC.search(text or ''))


def safe_query(value):
    value = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not 2 <= len(value) <= 80 or PRIVATE.search(value) or any(ord(c) < 32 for c in value):
        raise ValueError('Query must be a short public-topic phrase without identifiers or credentials')
    return value


def parse_plan(raw, user_text):
    raw = str(raw or '').strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw)
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {'action': 'none'}
    action = data.get('action')
    if action == 'join_listening' and not NO_MUSIC.search(user_text) and not META.search(user_text):
        return {'action': action}
    if action == 'research' and not NO_SEARCH.search(user_text):
        return {'action': action, 'query': safe_query(data.get('query')), 'sources': 'both'}
    return {'action': 'none'}
