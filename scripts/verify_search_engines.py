"""Probe only fixed public search engines; never loads private configuration."""
import asyncio
import json
import time
from app.web_research import call_mcp, web_error

async def main():
    async def probe(engine):
        start=time.monotonic()
        try:
            result=await asyncio.wait_for(call_mcp('stock_web_search',{'query':'上海证券交易所','maxResults':3,'_engine':engine},{'probe':engine},'/tmp/search-probe'),25)
            return {'engine':engine,'seconds':round(time.monotonic()-start,1),'results':len(result.get('results',[]))}
        except Exception as exc:return {'engine':engine,'seconds':round(time.monotonic()-start,1),'error':web_error(exc)}
    print(json.dumps(await asyncio.gather(*(probe(e) for e in ['bing','so360','baidu'])),ensure_ascii=False))

asyncio.run(main())
