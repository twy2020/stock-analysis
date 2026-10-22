"""Isolated management preview; never loads or modifies production configuration."""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent-core'))
from agent_core.app import create_app

directory=tempfile.TemporaryDirectory(prefix='stock-core-admin-preview-')
root=Path(directory.name)
os.environ['CORE_PREVIEW_KEY']='preview-fixture-only'
config={
    'database':str(root/'preview.db'),
    'services':[{'id':'stock-chat','name':'Stock Chat','tenantId':'stock-research','tokenSha256':hashlib.sha256(b'preview-client').hexdigest(),'domains':['chat'],'modelProfiles':['flash'],'defaultModelProfile':'flash'}],
    'providers':[{'id':'deepseek','name':'DeepSeek','baseUrl':'https://api.deepseek.com/v1','providerType':'DEEPSEEK'}, {'id':'openai','name':'OpenAI','baseUrl':'https://api.openai.com/v1','providerType':'OPENAI'}],
    'providerAccounts':[{'id':'research','name':'Research','providerId':'deepseek'},{'id':'default','name':'Default','providerId':'openai'}],
    'providerKeys':[{'id':'research-key','name':'Production','accountId':'research','apiKeyEnv':'CORE_PREVIEW_KEY'},{'id':'openai-key','name':'Default','accountId':'default','apiKeyEnv':'CORE_PREVIEW_KEY'}],
    'models':[{'id':'flash','name':'DeepSeek Flash','model':'deepseek-flash','keyId':'research-key','capabilities':{'tools':True,'reasoning':True}},
              {'id':'legacy','name':'Independent model','model':'custom-chat','baseUrl':'https://model.example/v1','apiKeyEnv':'CORE_PREVIEW_KEY'}],
    'httpTools':[{'name':'stock_query','url':'https://engine.example/query','effect':'read','version':'1','description':'Stock query'}],
}
path=root/'config.json';path.write_text(json.dumps(config),encoding='utf-8')
app=create_app(config,start_worker=False,config_path=path)
print('Isolated preview: http://127.0.0.1:18211/admin ; initial login: admin / admin123',flush=True)
app.run(host='127.0.0.1',port=18211,debug=False,use_reloader=False)
