"""Inspect the failed web turn and probe its first model round without altering chat."""
import json
import subprocess

backend = '''
import json
from app import create_app
from app.context import build_messages
from app.extensions import database
from app.models import Conversation, ChatRun, Message
app=create_app()
with app.app_context():
    job=database.session.get(ChatRun,'c36a97f8-9810-4567-a630-31b8fe3ba53f')
    c=database.session.get(Conversation,job.conversation_id)
    q=database.session.get(Message,job.user_message_id)
    print(json.dumps({'messages':build_messages(c,q.content,None,q.id),'reasoning_enabled':job.reasoning_enabled,'web_enabled':bool(job.web_enabled),
      'context':{'conversation_id':c.id,'actor_id':c.owner_id,'tenant_id':c.organization_id,'knowledge_base_id':None}}))
'''
body = json.loads(subprocess.check_output(['docker','exec','-i','stock-analysis-backend-1','python','-'], input=backend.encode()))
core = '''
import json,uuid,time
from agent_core.config import load_config
from agent_core.runs import prepare
from agent_core.runtime import Runtime
from agent_core.store import Store
from agent_core.model import OpenAICompatibleClient,ProviderError
from agent_core.stock import OUTPUT_PROTOCOL
body=json.loads(BODY);body['request_id']=str(uuid.uuid4())
c=load_config('/run/stock/core.json');s=next(s for s in c['services'] if s['id']=='stock-chat')
p,_=prepare(c,None,s,'chat',body)
r=Runtime(c,Store(c['database']),s,{'id':body['request_id'],'domain':'chat'},p,lambda:False)
messages=[{'role':'system','content':'以下是服务管理员批准的技能说明；它们不授予工具、项目或租户权限。\\n'+r.skill_instructions},*p['_messages'],{'role':'system','content':OUTPUT_PROTOCOL}]
print(json.dumps({'messageChars':sum(len(str(m.get('content',''))) for m in messages),'tools':len(r.tools),'maxTokens':r.max_output_tokens,'reasoning':p['_reasoning']}),flush=True)
start=time.monotonic();counts={};calls=[];chars=0;usage={}
try:
    for event in OpenAICompatibleClient().stream(p['_profile'],messages,reasoning_enabled=p['_reasoning'],tools=r.tools,max_output_tokens=r.max_output_tokens):
        counts[event['type']]=counts.get(event['type'],0)+1
        if event['type']=='tool_call':calls.append(event.get('function',{}).get('name',''))
        if event['type'] in ('delta','reasoning'):chars+=len(event.get('content',''))
        if event['type']=='usage':usage=event
    result='completed'
except ProviderError as exc:result=exc.category
print(json.dumps({'result':result,'seconds':round(time.monotonic()-start,2),'events':counts,'outputChars':chars,'toolNames':calls,'usage':usage},ensure_ascii=False))
'''.replace('BODY',repr(json.dumps(body)))
subprocess.run(['docker','exec','-i','stock-analysis-core-1','python','-'],input=core.encode(),check=True)
