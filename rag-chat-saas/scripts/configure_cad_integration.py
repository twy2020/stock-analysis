"""Generate ignored local service configuration; never print credential values."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--project', required=True, action='append')
    parser.add_argument('--cad-token', default='F:/tmp/cad-agent-tool.token')
    parser.add_argument('--cad-port', default=8767, type=int)
    parser.add_argument('--ocr-token', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = root / '.local' / 'integrations'
    target.mkdir(parents=True, exist_ok=True)
    token_path = target / 'cad-service.token'
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(48), encoding='utf-8')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    tools = []
    for item in manifest.get('tools', manifest.get('capabilities', [])):
        if item['name'] not in ('cad_get_evidence','cad_propose_parts','cad_calculate_weight'):
            continue
        entry = {k:item[k] for k in ('name','description','inputSchema','outputSchema') if k in item}
        entry.update(version='1', effect=item.get('effect',item.get('effects')))
        if entry['name'] == 'cad_calculate_weight':
            entry['inputSchema'] = {'type':'object','properties':{},'additionalProperties':False}
            entry['description'] = '读取当前绑定项目已审核参数并确定性计算重量，不接受自定义项目参数。'
        tools.append(entry)
    tools.insert(0, {'name':'cad_get_drawing_evidence','version':'1','effect':'read',
        'description':'读取当前绑定图纸的证据目录及可装载的 document，无参数。',
        'inputSchema':{'type':'object','properties':{},'additionalProperties':False},
        'outputSchema':{'type':'object'}})
    for entry in tools:
        entry.update(url=f'http://host.docker.internal:{args.cad_port}/api/cad/analysis/tools',
                     tokenFile='/run/cad/callback.token', timeoutSeconds=60)
    if args.ocr_token:
        tools.append({'name':'ocr_analyze','version':'1','effect':'analyze','transport':'ocr-vision-v1',
            'description':'查看本次请求所附图片，输出未审核视觉描述、区域和提案。图片索引从0开始。',
            'url':'http://host.docker.internal:5011/api/plugins/vision/v1','tokenFile':'/run/ocr/service.token',
            'inputSchema':{'type':'object','properties':{
                'imageIndices':{'type':'array','minItems':1,'maxItems':4,'uniqueItems':True,'items':{'type':'integer','minimum':0,'maximum':3}},
                'question':{'type':'string','minLength':1,'maxLength':8192}},'required':['imageIndices','question'],'additionalProperties':False},
            'outputSchema':{'type':'object'}})
    config = {'services':[{'id':'cad-workbench','tenantId':'company','projectIds':args.project,
        'tokenSha256':hashlib.sha256(token_path.read_bytes()).hexdigest(),
        'tools':[t['name'] for t in tools], 'maxActiveRuns':2}], 'httpTools':tools,
        'visionAccountIds':[]}
    if args.ocr_token:
        config['visionPlugin']={'url':'http://host.docker.internal:5011/api/plugins/vision/v1','tokenFile':'/run/ocr/service.token'}
    config_path = target / 'service-plugins.local.json'
    config_path.write_text(json.dumps(config,ensure_ascii=False,indent=2), encoding='utf-8')
    override = {'services':{'backend':{'environment':{'SERVICE_PLUGINS_CONFIG':'/run/integrations/service-plugins.local.json'},
        'volumes':[f'{target.as_posix()}:/run/integrations:ro',
                   f'{Path(args.cad_token).as_posix()}:/run/cad/callback.token:ro']}}}
    if args.ocr_token:
        override['services']['backend']['volumes'].append(f'{args.ocr_token.as_posix()}:/run/ocr/service.token:ro')
    override_path = target / 'compose.local.json'
    override_path.write_text(json.dumps(override,indent=2),encoding='utf-8')
    print(json.dumps({'base_url':'http://127.0.0.1:18100/api/service/v1',
        'token_file':str(token_path),'config':str(config_path),'compose_override':str(override_path)}))


if __name__ == '__main__':
    main()
