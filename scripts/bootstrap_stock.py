"""Create isolated stock credentials/configuration; never mutate the source Core."""
import argparse
import copy
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'stock-data-engine'))
sys.path.insert(0,str(ROOT/'agent-core'))
from stock_engine.catalog import TOOLS
from agent_core.stock import SKILLS


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2) if not isinstance(value,str) else value,encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-config',type=Path,default=ROOT/'agent-core/.local/core.json')
    parser.add_argument('--refresh-tools',action='store_true')
    args=parser.parse_args(); directory=ROOT/'.stock-private';directory.mkdir(exist_ok=True)
    target=directory/'core.json'
    if target.exists():
        if args.refresh_tools:
            existing=json.loads(target.read_text('utf-8'))
            schemas={t['name']:t for t in TOOLS}
            for entry in existing.get('httpTools',[]):
                if entry.get('pluginId')=='stock-data' and entry['name'] in schemas:entry.update(copy.deepcopy(schemas[entry['name']]))
            for server in existing.get('mcpServers',[]):
                if server['id']=='stock':
                    for tool in server.get('tools',[]):
                        if tool['name'] in schemas:tool.update(copy.deepcopy(schemas[tool['name']]))
            existing['skills']=copy.deepcopy(SKILLS)
            for service in existing.get('services',[]):
                if service.get('agentType')=='stock':service['skills']=[skill['id'] for skill in SKILLS]
            write(target,existing)
            print('Stock tool schemas refreshed; credentials and model settings retained.')
        print('Existing stock configuration retained: '+str(target));return
    for name in ('engine','saas'):
        path=directory/(name+'.token')
        if not path.exists(): write(path,secrets.token_urlsafe(48))
    source=json.loads(args.source_config.read_text('utf-8-sig')) if args.source_config.exists() else {'models':[]}
    config={k:copy.deepcopy(source.get(k,[])) for k in ('models','providers','providerAccounts','providerKeys')}
    def copy_credentials(row):
        if row.get('apiKeyFile'):
            src=Path(row['apiKeyFile'])
            if not src.is_absolute():src=args.source_config.parent/src
            local_candidate=ROOT/'agent-core/.local'/src.name
            if local_candidate.exists():src=local_candidate
            secret=src.read_text('utf-8-sig').strip()
        elif row.get('apiKeyEnv'):
            secret=os.environ.get(row['apiKeyEnv'],'')
            if not secret: raise SystemExit('Configured model key environment is unavailable; set it before bootstrapping.')
        else:return
        filename='model-'+hashlib.sha256(secret.encode()).hexdigest()[:12]+'.token'
        write(directory/filename,secret);row.pop('apiKeyEnv',None);row['apiKeyFile']='/run/stock/'+filename
    for row in [*config['models'],*config['providerKeys']]:copy_credentials(row)
    for row in config['providerAccounts']:
        if row.get('billing'):copy_credentials(row['billing'])
    models=[m for m in config['models'] if m.get('enabled',True) and m.get('capabilities',{}).get('tools',True)]
    if models:
        preferred=next((m for m in models if m.get('id')=='primary'),models[0]);model_ids=[m['id'] for m in models]
    else:
        config['models']=[{'id':'primary','name':'Configure model in Core console','providerType':'OPENAI',
            'model':'configure-model','baseUrl':'https://api.openai.com/v1','apiKeyEnv':'STOCK_MODEL_API_KEY','capabilities':{'tools':True}}]
        preferred=config['models'][0];model_ids=['primary']
    if preferred['id']!='primary':
        preferred=copy.deepcopy(preferred);preferred['id']='primary';config['models'].append(preferred);model_ids.append('primary')
    entries=[{**tool,'effect':'compute' if tool['name'] in ('stock_query','stock_events','stock_backtest','stock_annotate') else 'read',
        'version':'1','domains':['chat'],'pluginId':'stock-data','url':'http://data-engine:18310/tools/execute',
        'tokenFile':'/run/stock/engine.token','timeoutSeconds':100} for tool in TOOLS]
    config.update(database='/data/stock-core.sqlite3',host='0.0.0.0',port=18210,
        httpTools=entries,plugins=[{'id':'stock-data','name':'Stock data engine','enabled':True}],skills=SKILLS,
        mcpServers=[{'id':'stock','name':'Stock data engine','transport':'http-bridge','domains':['chat'],'pluginId':'stock-data',
            'tools':[{**tool,'effect':entry['effect'],'httpTool':tool['name']} for tool,entry in zip(TOOLS,entries)]}],
        services=[{'id':'stock-chat','tenantId':'stock-research','agentType':'stock','ragEnabled':False,
            'tokenSha256':hashlib.sha256((directory/'saas.token').read_bytes()).hexdigest(),'domains':['chat'],
            'modelProfiles':model_ids,'defaultModelProfile':'primary','tools':[t['name'] for t in TOOLS],
            'mcpServers':['stock'],'mcpTools':[],'plugins':['stock-data'],'skills':[s['id'] for s in SKILLS],
            'visionPolicy':'direct' if preferred.get('capabilities',{}).get('vision') else 'ocr',
            'maxActiveRuns':4,'maxOutputTokens':4096}])
    from agent_core.config import validate_config
    from agent_core.capabilities import validate_config as validate_capabilities
    validate_capabilities(validate_config(config));write(target,config)
    env_path=directory/'stock.env'
    if not env_path.exists():
        password='Stock!'+secrets.token_urlsafe(18)
        write(env_path,'\n'.join(['BOOTSTRAP_ADMIN_USERNAME=admin','BOOTSTRAP_ADMIN_PASSWORD='+password,
            'BOOTSTRAP_TENANT_ID=stock-research','APP_SECRET_KEY='+secrets.token_urlsafe(48),
            'APP_MASTER_KEY='+__import__('base64').urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            'SESSION_SECURE=false','RAG_ENABLED=false','STOCK_APP_PORT=18110','STOCK_CORE_PORT=18210',
            'MARKET_API_URL=http://192.168.3.5:8765/api/db'])+'\n')
        write(directory/'initial-login.txt','Username: admin\nPassword: '+password+'\nChange the password after first login.\n')
    print('Stock configuration created. Model profiles: '+str(len(config['models'])))
    print('Initial credentials: '+str(directory/'initial-login.txt'))


if __name__=='__main__':main()
