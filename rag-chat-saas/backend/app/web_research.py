"""Fixed MCP subprocesses; no commands, credentials or browser actions from AI."""
import asyncio
import hashlib
import ipaddress
import json
import os
import socket
import threading
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin, urlunsplit, parse_qsl, urlencode

SEARCH_SLOTS = threading.BoundedSemaphore(4)

WEB_ERRORS={'PUBLIC_HTTP_URL_REQUIRED','PRIVATE_WEB_URL_FORBIDDEN','WEB_DNS_UNAVAILABLE',
            'WEB_SOURCE_UNAVAILABLE','WEB_MCP_TOOL_FAILED','WEB_TIMEOUT','WEB_SEARCH_RATE_LIMITED','WEB_PROXY_UNAVAILABLE','WEB_SEARCH_UNAVAILABLE',
            'WEB_MCP_TOOL_SELECTION_REQUIRED','WEB_MCP_SCHEMA_UNSUPPORTED','WEB_SEARCH_NO_SOURCES','WEB_PROVIDER_COOLDOWN','WEB_PROVIDER_AUTH_FAILED'}


class WebResearchError(ValueError):
    def __init__(self,code,details):
        super().__init__(code)
        self.details=details


class RefreshTarget(HTMLParser):
    target = None

    def handle_starttag(self, tag, attrs):
        values=dict(attrs)
        if tag == 'meta' and (values.get('http-equiv') or '').lower() == 'refresh':
            _, separator, target=(values.get('content') or '').partition(';')
            name, equals, value=target.partition('=')
            if separator and equals and name.strip().lower() == 'url':
                self.target=value.strip().strip('\"\'')


def resolve_search_redirect(url, proxy_settings=None):
    parsed=urlsplit(url)
    if parsed.hostname not in ('so.com','www.so.com') or parsed.path != '/link':
        return url
    import httpx
    from app.web_proxy import route,transport_url
    with httpx.Client(timeout=4,follow_redirects=False,trust_env=False,proxy=transport_url(route(proxy_settings or {},url))) as client:
        for _ in range(2):
            public_url(url)
            with client.stream('GET',url,headers={'User-Agent':'Mozilla/5.0'}) as response:
                if response.status_code in (301,302,303,307,308):
                    target=response.headers.get('location')
                elif response.status_code == 200:
                    body=bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk[:16384-len(body)])
                        if len(body)>=16384:break
                    parser=RefreshTarget();parser.feed(body.decode('utf-8',errors='replace'))
                    target=parser.target
                else:target=None
            if not target:raise ValueError('WEB_SOURCE_UNAVAILABLE')
            url=urljoin(url,target)
            public_url(url)
            if urlsplit(url).hostname not in ('so.com','www.so.com'):
                return url
    raise ValueError('WEB_SOURCE_UNAVAILABLE')


def web_error(exception):
    if isinstance(exception,BaseExceptionGroup):
        codes={web_error(child) for child in exception.exceptions}
        return next(iter(codes)) if len(codes)==1 else 'WEB_RESEARCH_UNAVAILABLE'
    if isinstance(exception,TimeoutError):return 'WEB_TIMEOUT'
    if isinstance(exception,ValueError) and str(exception) in WEB_ERRORS:return str(exception)
    return 'WEB_RESEARCH_UNAVAILABLE'


def public_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,80,443):
        raise ValueError('PUBLIC_HTTP_URL_REQUIRED')
    try:
        addresses=socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=='https' else 80),type=socket.SOCK_STREAM)
    except OSError: raise ValueError('WEB_DNS_UNAVAILABLE') from None
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('PRIVATE_WEB_URL_FORBIDDEN')
    return url


async def call_mcp(tool, arguments, scope, base):
    from app.web_proxy import transport_url
    if arguments.get('_proxy'):arguments={**arguments,'_proxy':transport_url(arguments['_proxy'])}
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    identity=hashlib.sha256((json.dumps(scope,sort_keys=True)+(arguments.get('_proxy') or 'direct')).encode()).hexdigest()
    home=Path(base)/identity;home.mkdir(parents=True,exist_ok=True)
    env={'HOME':str(home), 'PATH':os.environ.get('PATH',''), 'LANG':'C.UTF-8',
         'PLAYWRIGHT_BROWSERS_PATH':os.environ.get('PLAYWRIGHT_BROWSERS_PATH','/opt/stock-browsers')}
    if tool=='stock_web_search':
        command='/opt/stock-node/lib/ld-musl-x86_64.so.1'
        args=['--library-path','/opt/stock-node/lib','/opt/stock-node/node','--require','/app/app/search_strict.cjs','/opt/stock-search/node_modules/ai-search-mcp/bin/cli.js']; name='search'
        env.update(SEARCH_REGION='cn-zh', SEARCH_TIMEOUT_MS='10000', SEARCH_LOG_LEVEL='off')
        env.update(SEARCH_ENGINE=arguments.get('_engine','auto'), SEARCH_STRICT_ENGINE='1',
                   SEARCH_CACHE_FILE=str(home/(arguments.get('_engine','auto')+'-'+hashlib.sha256(arguments['query'].encode()).hexdigest()[:16]+'.json')))
        payload={k:v for k,v in arguments.items() if k not in ('_engine','_proxy')}
        if arguments.get('_proxy'):env['SEARCH_HTTP_PROXY']=arguments['_proxy']
    else:
        command='dhole';args=[];name='smart_fetch'
        env.update(DHOLE_HOME=str(home/'dhole'), DHOLE_TOOLS='smart_fetch', DHOLE_DEFAULT_CONTENT_CHARS='4000')
        payload={'url':arguments['url'],'offset':arguments.get('offset',0),
                 'max_content_chars':arguments.get('maxChars',4000),'timeout':30000,
                 'include_links':False, 'include_media':False, 'solve_cloudflare':False}
        if arguments.get('focus'):payload['focus']=arguments['focus']
        if arguments.get('_proxy'):payload['options']={'proxy':arguments['_proxy']}
    with open(os.devnull,'w') as stderr:
        async with stdio_client(StdioServerParameters(command=command,args=args,env=env),errlog=stderr) as (reader,writer):
            async with ClientSession(reader,writer) as session:
                await session.initialize()
                result=await session.call_tool(name,payload)
                if result.is_error:
                    text='\n'.join(part.text for part in result.content if part.type=='text')
                    raise ValueError('WEB_SEARCH_RATE_LIMITED' if 'RATE_LIMITED' in text else 'WEB_MCP_TOOL_FAILED')
                value=result.structured_content
                if not value:
                    text='\n'.join(part.text for part in result.content if part.type=='text')
                    try:value=json.loads(text)
                    except ValueError:value={'content':text}
                if not isinstance(value,dict):value={'content':value}
                if value.get('error')=='proxy_unreachable':raise ValueError('WEB_PROXY_UNAVAILABLE')
                if value.get('error') or value.get('content_ok') is False:raise ValueError('WEB_SOURCE_UNAVAILABLE')
                from app.web_proxy import scrub
                return scrub(value,arguments.get('_proxy'))


def bounded_result(value):
    truncated=False
    def trim(item):
        nonlocal truncated
        if isinstance(item,str):
            truncated |= len(item)>9000
            return item[:9000]
        if isinstance(item,list):
            truncated |= len(item)>20
            return [trim(v) for v in item[:20]]
        if isinstance(item,dict):
            truncated |= len(item)>40
            return {k:trim(v) for k,v in list(item.items())[:40]}
        return item
    result=trim(value)
    if truncated:result['adapterTruncated']=True
    if len(json.dumps(result,ensure_ascii=False).encode())>18000:
        return {'content':json.dumps(result,ensure_ascii=False)[:4000], 'adapterTruncated':True,
                'next_offset':value.get('next_offset'), 'url':value.get('url')}
    return result


def source_record(url, title='', engines=None, read=False):
    try:
        parsed=urlsplit(url)
        if len(url)>2048:return None
        if (parsed.hostname in ('duckduckgo.com','www.duckduckgo.com') and parsed.path=='/y.js'
            or parsed.hostname in ('bing.com','www.bing.com') and parsed.path=='/aclick'
            or parsed.hostname and parsed.hostname.endswith('googleadservices.com')):return None
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
            return None
        if parsed.port not in (None,80,443):return None
        try:
            if not ipaddress.ip_address(parsed.hostname).is_global:return None
        except ValueError:
            if '.' not in parsed.hostname or parsed.hostname.endswith(('.local','.internal')):return None
        query=urlencode(sorted((k,v) for k,v in parse_qsl(parsed.query,keep_blank_values=True)
                               if not k.lower().startswith('utm_') and k.lower() not in ('fbclid','gclid')))
        canonical=urlunsplit((parsed.scheme,parsed.netloc.lower(),parsed.path or '/',query,''))
        return {'id':'web_'+hashlib.sha256(canonical.encode()).hexdigest()[:16],
                'url':canonical,'title':str(title or parsed.hostname)[:250],
                'domain':parsed.hostname.lower(),'engines':engines or [],'read':read}
    except (ValueError,TypeError):return None


async def aggregate_search(arguments, scope, base, proxy_settings=None, timeout_seconds=18):
    from app.web_proxy import route
    queries=list(dict.fromkeys(arguments.get('queries') or [arguments['query']]))[:3]
    engines=arguments.get('engines') or (['duckduckgo','bing','baidu'] if route(proxy_settings or {},engine='duckduckgo') else ['bing','so360','baidu'])
    limit=arguments.get('maxResults',5)
    async def search(query, engine):
        acquired=False
        try:
            # A process-wide bound also applies to simultaneous chat requests.
            async with asyncio.timeout(timeout_seconds):
                while not SEARCH_SLOTS.acquire(blocking=False):await asyncio.sleep(.05)
                acquired=True
                payload={k:v for k,v in arguments.items() if k in ('site','freshness')}
                proxy=route(proxy_settings or {},engine=engine)
                if proxy:payload['_proxy']=proxy
                result=await call_mcp('stock_web_search',{**payload,'query':query,'maxResults':limit,'_engine':engine},scope,base)
                return {'query':query,'engine':engine,'status':'succeeded','freshnessApplied':bool(result.get('freshnessApplied'))},result.get('results',[])
        except Exception as exc:
            return {'query':query,'engine':engine,'status':'failed','error':web_error(exc)},[]
        finally:
            if acquired:SEARCH_SLOTS.release()
    batches=await asyncio.gather(*(search(q,e) for q in queries for e in engines))
    statuses=[status for status,_ in batches]
    if all(s['status']=='failed' for s in statuses):
        errors={s['error'] for s in statuses}
        code=next(iter(errors)) if len(errors)==1 else 'WEB_SEARCH_UNAVAILABLE'
        raise WebResearchError(code,{'searches':statuses,'retryable':False,
                                   'message':'搜索引擎均不可用，不重复相同搜索；根据已有证据回答并说明未核实信息。'})
    merged={}
    # Interleave ranks so a successful first engine cannot fill the whole budget.
    for rank in range(limit):
        for status,rows in batches:
            if rank>=len(rows):continue
            row=rows[rank]
            source=source_record(row.get('url'),row.get('title'),[status['engine']])
            if not source:continue
            key=source['id']
            if key not in merged:
                merged[key]={**source,'snippet':str(row.get('snippet',''))[:800],'queries':[]}
            entry=merged[key]
            if status['engine'] not in entry['engines']:entry['engines'].append(status['engine'])
            if status['query'] not in entry['queries']:entry['queries'].append(status['query'])
    rows=list(merged.values())[:limit]
    async def resolve(row):
        if urlsplit(row['url']).hostname not in ('so.com','www.so.com'):return row
        try:
            url=await asyncio.to_thread(resolve_search_redirect,row['url'],proxy_settings)
            source=source_record(url,row['title'],row['engines'])
            if source:return {**row,**source}
        except Exception:pass
        return row
    resolved=await asyncio.gather(*(resolve(row) for row in rows))
    final={}
    for row in resolved:
        if row['id'] in final:
            for engine in row['engines']:
                if engine not in final[row['id']]['engines']:final[row['id']]['engines'].append(engine)
        else:final[row['id']]=row
    rows=list(final.values())
    return {'engine':'aggregate','queries':queries,'engines':engines,'searches':statuses,
            'partial':any(s['status']=='failed' for s in statuses),'total':len(rows),'results':rows}


def execute(tool, arguments, scope, base):
    from app.web_proxy import settings,route
    from app.search_manager import search,settings as search_settings
    proxy_settings=settings()
    original=arguments.get('url')
    try:
        if tool=='stock_web_fetch':
            public_url(original)
            arguments={**arguments,'url':resolve_search_redirect(original,proxy_settings)}
            proxy=route(proxy_settings,arguments['url'])
            if proxy:arguments['_proxy']=proxy
        operation=search(arguments,scope,base,proxy_settings,search_settings()) if tool=='stock_web_search' else call_mcp(tool,arguments,scope,base)
        result=asyncio.run(asyncio.wait_for(operation,timeout=55))
    except WebResearchError:raise
    except Exception as exc:
        raise ValueError(web_error(exc)) from None
    if original and original!=arguments['url']:result['searchRedirectUrl']=original
    sources=([ {k:v for k,v in row.items() if k not in ('snippet','queries')} for row in result.get('results',[])]
             if tool=='stock_web_search' else [source_record(arguments['url'],result.get('title'),read=True)])
    return {'source':result.get('provider','ai-search-mcp') if tool=='stock_web_search' else 'Dhole','sources':[s for s in sources if s],
            'accessedAt':datetime.now(timezone.utc).isoformat(),
            'untrustedExternalContent':True, 'result':bounded_result(result)}
