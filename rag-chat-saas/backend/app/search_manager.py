"""Administrator-owned search providers behind the existing bounded web tool."""
import asyncio
import json
import re
import threading
import time

from flask import has_app_context
from app.crypto import decrypt_json, encrypt_json
from app.extensions import database
from app.models import SystemSetting

KEY = 'stock.search_manager'
CATALOG = {
    'native': {'name':'多引擎搜索', 'transport':'stdio', 'endpoint':'', 'supported':True,
               'docs':'https://www.npmjs.com/package/ai-search-mcp'},
    'qianfan': {'name':'百度千帆 AI 搜索', 'transport':'streamable-http', 'supported':True,
                'endpoint':'https://qianfan.baidubce.com/v2/ai_search/mcp',
                'docs':'https://cloud.baidu.com/product/ai_search'},
    'zhihu': {'name':'知乎站内搜索', 'transport':'sse', 'supported':True,
              'endpoint':'https://developer.zhihu.com/api/mcp/zhihu_search/v1/sse',
              'docs':'https://developer.zhihu.com/'},
    'deepseek': {'name':'DeepSeek 官方 web_search', 'transport':'responses', 'supported':False,
                 'endpoint':'https://api.deepseek.com/v1/responses',
                 'docs':'https://api-docs.deepseek.com/guides/responses_api',
                 'reason':'当前官方 Responses 文档明确标注 web_search 被忽略，不能作为搜索来源。'},
}
ENGINES = {'duckduckgo','bing','baidu','so360','sogou','google','yandex'}
_lock = threading.Lock()
_health = {}
_slots = threading.BoundedSemaphore(4)


def defaults():
    return {'providers':[{'id':key,'enabled':key=='native','priority':i+1,'timeoutSeconds':25 if key=='native' else 18,
                           'apiKey':'','toolName':''} for i,key in enumerate(CATALOG)], 'engines':[]}


def settings():
    if not has_app_context():return defaults()
    row=database.session.get(SystemSetting,KEY)
    return decrypt_json(row.encrypted_value) if row else defaults()


def view(value):
    with _lock:health={k:dict(v) for k,v in _health.items()}
    return {'engines':value['engines'], 'providers':[
        {**CATALOG[p['id']], **{k:v for k,v in p.items() if k!='apiKey'},
         'configured':p['id']=='native' or bool(p['apiKey']),
         'health':health.get(p['id'],{'status':'untested'})} for p in value['providers']]}


def validate(payload,previous):
    if not isinstance(payload,dict) or set(payload)!={'providers','engines'}:raise ValueError('搜索设置格式错误')
    engines=payload['engines']
    if not isinstance(engines,list) or len(engines)>3 or any(not isinstance(e,str) or e not in ENGINES for e in engines) or len(set(engines))!=len(engines):
        raise ValueError('请选择最多三个不同的本地搜索引擎')
    rows=payload['providers']
    if not isinstance(rows,list) or len(rows)!=len(CATALOG):raise ValueError('供应商列表不完整')
    seen=set(); result=[]; old={p['id']:p for p in previous['providers']}
    for row in rows:
        if not isinstance(row,dict) or set(row)-{'id','enabled','priority','timeoutSeconds','apiKey','toolName','clearKey'}:
            raise ValueError('未知搜索供应商设置')
        key=row.get('id')
        if not isinstance(key,str) or key not in CATALOG or key in seen:raise ValueError('搜索供应商无效')
        seen.add(key)
        if type(row.get('enabled')) is not bool or type(row.get('priority')) is not int or not 1<=row['priority']<=4:
            raise ValueError('启用状态或优先级错误')
        if type(row.get('timeoutSeconds')) is not int or not 5<=row['timeoutSeconds']<=25:raise ValueError('超时需为5至25秒')
        if not isinstance(row.get('apiKey',''),str) or len(row.get('apiKey',''))>4096 or any(c.isspace() for c in row.get('apiKey','')):
            raise ValueError('API Key 格式错误')
        if type(row.get('clearKey',False)) is not bool:raise ValueError('清除凭据格式错误')
        name=row.get('toolName','')
        if not isinstance(name,str) or (name and not re.fullmatch(r'[\w.-]{1,100}',name)):raise ValueError('MCP 工具名称格式错误')
        token='' if row.get('clearKey') else row.get('apiKey') or old[key]['apiKey']
        if row['enabled'] and not CATALOG[key]['supported']:raise ValueError(CATALOG[key]['reason'])
        if row['enabled'] and key!='native' and not token:raise ValueError('启用前请配置 API Key')
        result.append({'id':key,'enabled':row['enabled'],'priority':row['priority'],
                       'timeoutSeconds':row['timeoutSeconds'],'apiKey':token,'toolName':name})
    if len({p['priority'] for p in result})!=len(result):raise ValueError('供应商优先级不能重复')
    return {'providers':result,'engines':engines}


def save(value):
    row=database.session.get(SystemSetting,KEY)
    if row:row.encrypted_value=encrypt_json(value)
    else:database.session.add(SystemSetting(key=KEY,encrypted_value=encrypt_json(value)))
    database.session.commit()
    with _lock:_health.clear()


def normalize(value,engine,limit):
    from app.web_research import source_record
    found={}
    def add(url,title='',snippet=''):
        source=source_record(url,title,[engine])
        if source and source['id'] not in found:
            found[source['id']]={**source,'snippet':str(snippet)[:800]}
    def walk(item,depth=0):
        if depth>12 or len(found)>=limit:return
        if isinstance(item,dict):
            url=next((item[k] for k in ('url','link','web_url','source_url') if isinstance(item.get(k),str)),None)
            if url:add(url,item.get('title') or item.get('name',''),item.get('snippet') or item.get('summary',''))
            for child in list(item.values())[:60]:walk(child,depth+1)
        elif isinstance(item,list):
            for child in item[:40]:walk(child,depth+1)
        elif isinstance(item,str):
            text=item[:18000]
            try:
                decoded=json.loads(text)
                if isinstance(decoded,(dict,list)):walk(decoded,depth+1);return
            except ValueError:pass
            for title,url in re.findall(r'\[([^\]\n]{1,250})\]\((https?://[^\s)]+)\)',text):add(url,title)
    walk(value)
    return list(found.values())[:limit]


async def remote_search(provider,arguments,proxy_settings):
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.streamable_http import streamable_http_client
    from app.web_proxy import route,transport_url
    import httpx2 as httpx
    endpoint=CATALOG[provider['id']]['endpoint']
    def factory(headers=None,timeout=None,auth=None):
        return httpx.AsyncClient(headers=headers,timeout=timeout or 15,auth=auth,
                                 proxy=transport_url(route(proxy_settings,endpoint)),trust_env=False,follow_redirects=False)
    headers={'Authorization':'Bearer '+provider['apiKey']}
    async with factory(headers=headers) as client:
      context=(sse_client(endpoint,headers=headers,httpx_client_factory=factory) if provider['id']=='zhihu'
               else streamable_http_client(endpoint,http_client=client))
      async with context as streams:
        async with ClientSession(streams[0],streams[1]) as session:
            await session.initialize()
            tools=(await session.list_tools()).tools
            candidates=[t for t in tools if (t.name==provider['toolName'] if provider['toolName'] else 'search' in t.name.lower())]
            if len(candidates)!=1:raise ValueError('WEB_MCP_TOOL_SELECTION_REQUIRED')
            tool=candidates[0];schema=tool.inputSchema
            properties=schema.get('properties',{})
            query_field=next((k for k in ('query','search_query','q','keyword','keywords') if k in properties and properties[k].get('type')=='string'),None)
            if not query_field:raise ValueError('WEB_MCP_SCHEMA_UNSUPPORTED')
            required=set(schema.get('required',[]))-{query_field}
            if required:raise ValueError('WEB_MCP_SCHEMA_UNSUPPORTED')
            rows={}
            for query in (arguments.get('queries') or [arguments['query']])[:3]:
                # Keep batches bounded; preserve the read-only tool's exact schema.
                result=await session.call_tool(tool.name,{query_field:query})
                if result.is_error:raise ValueError('WEB_MCP_TOOL_FAILED')
                content=result.structured_content or [p.text for p in result.content if p.type=='text']
                for row in normalize(content,provider['id'],arguments.get('maxResults',5)):rows.setdefault(row['id'],row)
            return {'engine':provider['id'],'toolName':tool.name,'results':list(rows.values())[:arguments.get('maxResults',5)],
                    'filterNotice':'此供应商未接收 site/freshness 过滤条件' if arguments.get('site') or arguments.get('freshness') else None}


def record(key,status,started,code=None):
    with _lock:
        _health[key]={'status':status,'elapsedMs':int((time.monotonic()-started)*1000),
                      'checkedAt':int(time.time()),'code':code,'cooldownUntil':time.time()+60 if status=='failed' else 0}


def provider_error(exc):
    from app.web_research import web_error
    if isinstance(exc,BaseExceptionGroup):
        codes={provider_error(child) for child in exc.exceptions}
        return next(iter(codes)) if len(codes)==1 else 'WEB_RESEARCH_UNAVAILABLE'
    response=getattr(exc,'response',None)
    if response is not None:
        if response.status_code in (401,403):return 'WEB_PROVIDER_AUTH_FAILED'
        if response.status_code==429:return 'WEB_SEARCH_RATE_LIMITED'
    if isinstance(exc,ValueError) and str(exc).startswith('WEB_'):return str(exc)
    if 'timeout' in type(exc).__name__.lower():return 'WEB_TIMEOUT'
    return web_error(exc)


async def provider_search(provider,arguments,scope,base,proxy_settings,engines):
    from app.web_research import aggregate_search,WebResearchError
    started=time.monotonic();acquired=False
    try:
        async with asyncio.timeout(provider['timeoutSeconds']):
            while not _slots.acquire(blocking=False):await asyncio.sleep(.05)
            acquired=True
            if provider['id']=='native':
                args={**arguments}
                if engines:args['engines']=engines
                # Reserve time for MCP subprocess teardown and source normalization;
                # a slow engine must not discard another engine's completed results.
                result=await aggregate_search(args,scope,base,proxy_settings,min(18,max(1,provider['timeoutSeconds']-5)))
            else:result=await remote_search(provider,arguments,proxy_settings)
            if not result.get('results'):raise ValueError('WEB_SEARCH_NO_SOURCES')
            record(provider['id'],'succeeded',started)
            return result
    except Exception as exc:
        code=provider_error(exc)
        record(provider['id'],'failed',started,code)
        raise WebResearchError(code,getattr(exc,'details',{})) from None
    finally:
        if acquired:_slots.release()


async def search(arguments,scope,base,proxy_settings,config):
    from app.web_research import WebResearchError
    attempts=[]
    try:
        async with asyncio.timeout(40):
            for p in sorted(config['providers'],key=lambda p:p['priority']):
                if not p['enabled'] or not CATALOG[p['id']]['supported'] or (p['id']!='native' and not p['apiKey']):continue
                with _lock:cooldown=_health.get(p['id'],{}).get('cooldownUntil',0)>time.time()
                if cooldown:
                    attempts.append({'provider':p['id'],'status':'skipped','error':'WEB_PROVIDER_COOLDOWN'});continue
                try:
                    result=await provider_search(p,arguments,scope,base,proxy_settings,config['engines'])
                    attempts.append({'provider':p['id'],'status':'succeeded'})
                    return {**result,'provider':p['id'],'providerAttempts':attempts}
                except WebResearchError as exc:
                    attempts.append({'provider':p['id'],'status':'failed','error':str(exc),**exc.details})
    except TimeoutError:attempts.append({'status':'failed','error':'WEB_TIMEOUT'})
    codes={a['error'] for a in attempts if a.get('error')}
    code=next(iter(codes)) if len(codes)==1 else 'WEB_SEARCH_UNAVAILABLE'
    raise WebResearchError(code,{'providerAttempts':attempts,'retryable':False})


def test_provider(key,config,proxy_settings,base):
    from app.web_research import WebResearchError
    if key not in CATALOG:raise ValueError('未知搜索供应商')
    if not CATALOG[key]['supported']:return {'ok':False,'code':'WEB_SEARCH_UNSUPPORTED','message':CATALOG[key]['reason']}
    p=next(p for p in config['providers'] if p['id']==key)
    if key!='native' and not p['apiKey']:return {'ok':False,'code':'WEB_PROVIDER_NOT_CONFIGURED'}
    try:
        result=asyncio.run(provider_search(p,{'query':'上海证券交易所','maxResults':3},{'verification':'search-manager'},base,proxy_settings,config['engines']))
        return {'ok':True,'provider':key,'sources':result['results'],'toolName':result.get('toolName'),
                'searches':result.get('searches',[])}
    except WebResearchError as exc:return {'ok':False,'code':str(exc),'details':exc.details}
