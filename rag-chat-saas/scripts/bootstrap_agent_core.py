"""One-time local migration. Secrets are captured in memory and written to private files.

Does not restart services, change CAD routing, or print credential material.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import secrets
import subprocess


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def token_file(path):
    if not path.exists(): path.write_text(secrets.token_urlsafe(48), encoding='utf-8')
    return hashlib.sha256(path.read_text('utf-8-sig').strip().encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core-root', required=True, type=Path)
    parser.add_argument('--cad-token', required=True, type=Path)
    parser.add_argument('--ocr-token', required=True, type=Path)
    parser.add_argument('--container',default='rag-chat-saas-backend-1')
    parser.add_argument('--port',type=int,default=18700)
    args=parser.parse_args()
    saas=Path(__file__).resolve().parents[1]
    local=saas/'.local'/'integrations'
    target=args.core_root.resolve()/'.local'
    target.mkdir(parents=True,exist_ok=True)
    config_path=target/'core.json'
    if config_path.exists():
        raise SystemExit('Core config already exists; review it in place instead of replacing it.')
    source=json.loads((local/'service-plugins.local.json').read_text('utf-8-sig'))
    # Read-only SQLite access avoids booting another application or dispatcher.
    export_script='''import os,sqlite3,json
from cryptography.fernet import Fernet
db=sqlite3.connect('file:'+os.environ.get('DATABASE_PATH','/data/rag-chat.db')+'?mode=ro',uri=True)
db.row_factory=sqlite3.Row
rows=db.execute("SELECT a.id,a.name,a.model,a.encrypted_api_key,COALESCE(a.base_url,p.base_url) AS base_url,p.provider_type FROM ai_accounts a JOIN ai_providers p ON p.id=a.provider_id WHERE a.status='ACTIVE' AND p.status='ACTIVE'").fetchall()
selected=next((r for r in rows if 'deepseek' in r['model'].lower()),None)
if selected is None: raise RuntimeError('No configured text model available')
row=dict(selected)
row['api_key']=Fernet(os.environ['APP_MASTER_KEY'].encode()).decrypt(row.pop('encrypted_api_key').encode()).decode()
row['tenant_id']=db.execute('SELECT id FROM organizations ORDER BY rowid LIMIT 1').fetchone()[0]
print(json.dumps(row))
'''
    result=subprocess.run(['docker','exec',args.container,'python','-c',export_script],capture_output=True,check=False)
    if result.returncode:
        raise SystemExit('Could not export configured model; no service has been changed.')
    exported=json.loads(result.stdout)
    key_path=target/'model-primary.token'
    key_path.write_text(exported.pop('api_key'),encoding='utf-8')
    saas_token=local/'agent-core-service.token'
    saas_digest=token_file(saas_token)
    callback=local/'core-callback.token'
    callback_digest=token_file(callback)
    admin=target/'admin.token'
    admin_digest=token_file(admin)
    tools=copy.deepcopy(source.get('httpTools',[]))
    for item in tools:
        if item.get('transport')=='ocr-vision-v1':
            item.update(url='http://127.0.0.1:5011/api/plugins/vision/v1',tokenFile=str(args.ocr_token.resolve()))
            item['inputSchema']['properties']['imageIndices'].update(maxItems=6)
            item['inputSchema']['properties']['imageIndices']['items'].pop('maximum',None)
        else:
            item.update(url='http://127.0.0.1:8765/api/cad/analysis/tools',tokenFile=str(args.cad_token.resolve()))
    tools.append({'name':'cad_get_candidate_evidence','version':'1','effect':'read',
        'description':'按候选读取原文、设计参数、约束和局部图片；可按region_id读取整图或分区。图片由OCR工具识读，不按像素量测。',
        'url':'http://127.0.0.1:8765/api/cad/analysis/tools','tokenFile':str(args.cad_token.resolve()),
        'timeoutSeconds':60,'inputSchema':{'type':'object','properties':{
            'candidate_id':{'type':'string','maxLength':240},'region_id':{'type':'string','maxLength':128}},
            'required':['candidate_id'],'additionalProperties':False},'outputSchema':{'type':'object'}})
    services=copy.deepcopy(source['services'])
    for service in services:
        service.update(domains=['cad'],modelProfiles=['primary'],defaultModelProfile='primary')
        service['tools']=list(dict.fromkeys(service.get('tools',[])+['cad_get_candidate_evidence']))
    services.append({'id':'chat-saas','tenantId':exported['tenant_id'],'tokenSha256':saas_digest,
        'domains':['chat'],'modelProfiles':['primary'],'defaultModelProfile':'primary','tools':['ocr_analyze'],
        'maxActiveRuns':4,'ragCallback':{'url':'http://127.0.0.1:18100/api/internal/agent-core/rag','tokenFile':str(callback)}})
    config={'database':str(target/'core.sqlite3'),'adminTokenSha256':admin_digest,
        'models':[{'id':'primary','name':exported['name'],'model':exported['model'],'baseUrl':exported['base_url'],
                   'providerType':exported['provider_type'],'apiKeyFile':str(key_path)}],
        'services':services,'httpTools':tools}
    write_json(config_path,config)
    override=json.loads((local/'compose.local.json').read_text('utf-8-sig'))
    override['services']['backend']['environment'].update(AGENT_BACKEND='core',
        AGENT_CORE_URL=f'http://host.docker.internal:{args.port}',
        AGENT_CORE_TOKEN_FILE='/run/integrations/agent-core-service.token',AGENT_CORE_MODEL_PROFILE='primary',
        AGENT_CORE_CALLBACK_TOKEN_SHA256=callback_digest)
    write_json(local/'compose.core.local.json',override)
    print(json.dumps({'coreConfig':str(config_path),'composeOverride':str(local/'compose.core.local.json'),
                      'model':exported['model'],'callers':[s['id'] for s in services]},ensure_ascii=False))


if __name__=='__main__':main()
