"""Probe native search/fetch adapters through a supplied proxy, without changing settings."""
import asyncio
import json
import sys
from urllib.parse import urlsplit
from app.web_research import call_mcp,web_error

proxy=sys.argv[1]
async def main():
    async def probe(name,args):
        try:
            value=await asyncio.wait_for(call_mcp(name,{**args,'_proxy':proxy},{'probe':'proxy'},'/tmp/stock-proxy-probe'),55)
            assert proxy not in json.dumps(value)
            if name=='stock_web_search':
                return {'tool':name,'engine':value.get('engine'),'results':len(value.get('results',[]))}
            return {'tool':name,'pageVerified':'Example Domain' in json.dumps(value),'contentOk':value.get('content_ok')}
        except Exception as exc:return {'tool':name,'error':web_error(exc)}
    results=await asyncio.gather(probe('stock_web_search',{'query':'Microsoft official website','maxResults':3,'_engine':sys.argv[2] if len(sys.argv)>2 else 'bing'}),
                                 probe('stock_web_fetch',{'url':'https://example.com','maxChars':1500}))
    print(json.dumps({'protocol':urlsplit(proxy).scheme,'results':results},ensure_ascii=False))
    assert all('error' not in result for result in results), 'Native proxy probe failed'
    assert results[0]['results']>0 and results[1]['pageVerified'], 'Native proxy returned no verifiable content'

asyncio.run(main())
