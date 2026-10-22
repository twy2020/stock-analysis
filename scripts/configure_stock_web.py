"""Register fixed stock web adapters without changing other Core installations."""
import json
import runpy
from pathlib import Path

root=Path(__file__).resolve().parents[1]
path=root/'.stock-private/core.json'
config=json.loads(path.read_text('utf-8'))
tools=runpy.run_path(str(root/'rag-chat-saas/backend/app/web_contract.py'))['TOOLS']
if all(any(e.get('name')==tool['name'] for e in config.get('httpTools',[])) for tool in tools):
    for tool in tools:
        for entry in config['httpTools']:
            if entry.get('name')==tool['name']:
                entry.update(inputSchema=tool['inputSchema'],description=tool['description'])
        for server in config.get('mcpServers',[]):
            if server.get('id')=='stock-web':
                for entry in server.get('tools',[]):
                    if entry.get('name')==tool['name']:
                        entry.update(inputSchema=tool['inputSchema'],description=tool['description'])
    path.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Updated stock web schemas; existing permissions retained.')
    raise SystemExit(0)
entries=[{**tool,'version':'1','effect':'read','domains':['chat'],'pluginId':'stock-web',
          'url':'http://backend:8000/api/internal/stock-web/execute','tokenFile':'/run/stock/engine.token',
          'timeoutSeconds':65} for tool in tools]
config['httpTools']=[e for e in config.get('httpTools',[]) if e.get('name') not in {t['name'] for t in tools}]+entries
config['plugins']=[p for p in config.get('plugins',[]) if p['id']!='stock-web']+[
    {'id':'stock-web','name':'ai-search-mcp + Dhole','enabled':True}]
config['mcpServers']=[s for s in config.get('mcpServers',[]) if s['id']!='stock-web']+[
    {'id':'stock-web','name':'Stock web MCP adapter','transport':'http-bridge','domains':['chat'],
     'pluginId':'stock-web','tools':[{**tool,'effect':'read','httpTool':tool['name']} for tool in tools]}]
for service in config['services']:
    if service.get('agentType')=='stock':
        for key,values in [('tools',[t['name'] for t in tools]),('plugins',['stock-web']),('mcpServers',['stock-web'])]:
            service[key]=list(dict.fromkeys([*service.get(key,[]),*values]))
path.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
print('Registered stock web HTTP adapters and MCP bridge; SaaS administrator opt-in is required.')
