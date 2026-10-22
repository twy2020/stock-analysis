"""Run inside the stock backend: native MCP tools, public sources, no model."""
import json
from app.web_research import execute

scope={'tenant_id':'verification','actor_id':'verification','conversation_id':'stock-web'}
report=[]
for name,args in [
    ('stock_web_search',{'queries':['上海证券交易所','证券交易所 公告'],'maxResults':3}),
    ('stock_web_fetch',{'url':'https://example.com','maxChars':1500}),
]:
    result=execute(name,args,scope,'/tmp/stock-web-verification')
    data=result['result'];size=len(json.dumps(result,ensure_ascii=False).encode())
    assert size<20000
    if name=='stock_web_search':
        assert isinstance(data.get('results'),list), list(data)
        report.append({'tool':name,'source':result['source'],'results':len(data['results']),
                       'engine':data.get('engine'),'searches':data.get('searches'),'sources':len(result['sources']),'bytes':size,'modelCalls':0})
    else:
        text=json.dumps(data,ensure_ascii=False)
        assert 'Example Domain' in text, list(data)
        report.append({'tool':name,'source':result['source'],'pageVerified':True,'bytes':size,'modelCalls':0})
print(json.dumps(report,ensure_ascii=False))
