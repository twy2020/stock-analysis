"""Select an existing Core model for stock-chat without exposing credentials."""
import json
import sys
import urllib.request
from pathlib import Path

root=Path(__file__).resolve().parents[1]
token=(root/'.stock-private/admin.token').read_text('utf-8-sig').strip()
headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
base='http://127.0.0.1:18210'
with urllib.request.urlopen(urllib.request.Request(base+'/admin/api/registry',headers=headers),timeout=15) as response:
    registry=json.load(response)
identifier=sys.argv[1]
assert any(m['id']==identifier and m.get('enabled',True) for m in registry['models']), 'Model unavailable'
model=next(m for m in registry['models'] if m['id']==identifier)
if model.get('baseUrl','').rstrip('/')=='https://api.deepseek.com/v1' and model.get('providerType')!='DEEPSEEK':
    body={'revision':registry['revision'],'kind':'models','id':identifier,'changes':{'providerType':'DEEPSEEK'}}
    request=urllib.request.Request(base+'/admin/api/registry',headers=headers,method='PATCH',data=json.dumps(body).encode())
    with urllib.request.urlopen(request,timeout=15) as response:registry=json.load(response)
service=next(s for s in registry['services'] if s['id']=='stock-chat')
body={'revision':registry['revision'],'kind':'services','id':'stock-chat',
      'changes':{'modelProfiles':list(dict.fromkeys([*service['modelProfiles'],identifier])),'defaultModelProfile':identifier}}
request=urllib.request.Request(base+'/admin/api/registry',headers=headers,method='PATCH',data=json.dumps(body).encode())
with urllib.request.urlopen(request,timeout=15) as response:
    updated=json.load(response)
service=next(s for s in updated['services'] if s['id']=='stock-chat')
print(json.dumps({'service':service['id'],'defaultModelProfile':service['defaultModelProfile'],'modelProfiles':service['modelProfiles']}))
