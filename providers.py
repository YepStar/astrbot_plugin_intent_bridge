"""Read-only adapters to already enabled/logged-in plugin instances."""
from __future__ import annotations
import asyncio
import importlib
import re
from datetime import datetime, timezone
from .catalog import plugin_for
from .policy import safe_query

SEARCH_KEY = 'intent_bridge_readonly_search_v1'


def plain(value, limit=2200):
    value = re.sub(r'<[^>]*>', '', str(value or ''))
    return re.sub(r'\s+', ' ', value).strip()[:limit]


def stamp(value):
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ''


async def bili_search(context, event, query, limit):
    plugin = await plugin_for(context, event, 'astrbot_plugin_bilibili_ai_bot')
    if plugin is None or not plugin.config.get('ENABLE_LLM_TOOLS', True) or 'search_bilibili' not in event.get_extra('_intent_bridge_available_tools',[]):
        return {'platform':'bilibili','status':'unavailable','items':[]}
    videos = await plugin.search_bilibili_videos(query, ps=min(8,limit*3))
    videos = sorted(videos, key=lambda x: float(x.get('pubdate') or 0), reverse=True)
    items = []
    for v in videos[:limit]:
        bvid = str(v.get('bvid', ''))
        if not re.fullmatch(r'BV[0-9A-Za-z]{10}', bvid):
            continue
        item = {'title':plain(v.get('title'),180), 'author':plain(v.get('author'),80),
                'url':f'https://www.bilibili.com/video/{bvid}', 'published_at':stamp(v.get('pubdate')),
                'description':plain(v.get('desc'),500), 'evidence':'search_metadata'}
        oid = await plugin._get_video_oid(bvid)
        if oid:
            info = await plugin._get_video_info(oid) or {}
            item['description'] = plain(info.get('desc') or item['description'], 900)
            subtitle = await plugin._get_video_subtitles(bvid, info.get('cid',0))
            comments = await plugin._get_hot_comments(oid, limit=3)
            if subtitle:
                item['subtitle_excerpt'] = plain(subtitle)
                item['evidence'] = 'subtitle_excerpt'
            if comments:
                item['sample_comments'] = [plain(x,160) for x in comments[:3]]
        items.append(item)
    return {'platform':'bilibili','status':'ok' if items else 'no_results','items':items}


async def xhh_search(context, event, query, limit, profile_id):
    plugin = await plugin_for(context, event, 'astrbot_plugin_xiaoheihe_adapter')
    if plugin is None:
        return {'platform':'xiaoheihe','status':'unavailable','items':[]}
    runtime = plugin.runtime
    cfg = runtime.config.snapshot()
    if not any(p.get('enabled') and p.get('profile_id') == profile_id for p in cfg['profiles']):
        return {'platform':'xiaoheihe','status':'unavailable','items':[]}
    client = await runtime.get_client(profile_id)
    if client.credentials is None:
        return {'platform':'xiaoheihe','status':'not_logged_in','items':[]}
    module = importlib.import_module(type(client).__module__.rsplit('.',1)[0] + '.endpoints')
    contract = module.Endpoint('GET','/bbs/app/api/general/search/v1',True,True)
    if SEARCH_KEY in module.ENDPOINTS and module.ENDPOINTS[SEARCH_KEY] != contract:
        raise RuntimeError('Search contract key collision')
    module.ENDPOINTS[SEARCH_KEY] = contract
    response = await client._request(SEARCH_KEY, params={
        'q':query,'search_type':'link','offset':0,'limit':max(10,limit*3),'is_pull_down':0,'dw':628})
    result = response.payload.get('result', {})
    raw = result.get('items', []) if isinstance(result,dict) else []
    items, seen = [], set()
    for wrapper in raw:
        post = wrapper.get('info', wrapper) if isinstance(wrapper,dict) else {}
        pid = str(post.get('linkid', post.get('link_id', '')))
        if not re.fullmatch(r'[0-9A-Za-z]{1,32}', pid) or pid in seen:
            continue
        seen.add(pid)
        item = {'title':plain(post.get('title'),180), 'url':f'https://www.xiaoheihe.cn/app/bbs/link/{pid}',
                'published_at':stamp(post.get('create_at')), 'evidence':'search_metadata',
                'description':plain(post.get('description'),500)}
        try:
            full = await client.fetch_thread_context(pid)
            item['body_excerpt'] = plain(full.body)
            item['evidence'] = 'post_body_excerpt' if item['body_excerpt'] else 'search_metadata'
            item['sample_comments'] = [plain(x.get('text',x.get('content','')),160) for x in full.comments[:3] if isinstance(x,dict)]
        except asyncio.CancelledError:
            raise
        except Exception:
            item['detail_status'] = 'unavailable'
        items.append(item)
        if len(items) >= limit:
            break
    return {'platform':'xiaoheihe','status':'ok' if items else 'no_results','items':items}


async def research(context, event, query, sources='both', *, limit=2, timeout=25, profile_id='default'):
    query = safe_query(query)
    if sources not in {'both','bilibili','xiaoheihe'}:
        raise ValueError('Unsupported source')
    limit = max(1,min(3,int(limit)))
    async def bounded(name, factory):
        try:
            return await asyncio.wait_for(factory(), timeout=timeout)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return {'platform':name,'status':'error','error_type':type(exc).__name__,'items':[]}
    jobs=[]
    if sources in {'both','bilibili'}:
        jobs.append(bounded('bilibili',lambda:bili_search(context,event,query,limit)))
    if sources in {'both','xiaoheihe'}:
        jobs.append(bounded('xiaoheihe',lambda:xhh_search(context,event,query,limit,profile_id)))
    return {'query':query,'retrieved_at':datetime.now(timezone.utc).isoformat(),
            'trust':'external_untrusted_data','sources':await asyncio.gather(*jobs),
            'interpretation':'仅依据返回摘录回答；标题不是完整内容，评论不代表共识。核对资料日期和主题是否匹配；未知名称不要擅自纠正，不宣称亲自游玩或完整看过视频。保留一两个支持结论的来源链接。'}
