"""Verify the failed indicator turn with real read-only tools, preserving chat."""
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
    job=database.session.get(ChatRun,'d9aae729-746b-49bb-b7e5-3b5d0df1e2c7')
    c=database.session.get(Conversation,job.conversation_id)
    q=database.session.get(Message,job.user_message_id)
    print(json.dumps({'messages':build_messages(c,q.content,None,q.id),'reasoning_enabled':bool(job.reasoning_enabled),
      'context':{'conversation_id':c.id,'actor_id':c.owner_id,'tenant_id':c.organization_id,'knowledge_base_id':None}}))
'''
body=json.loads(subprocess.check_output(['docker','exec','-i','stock-analysis-backend-1','python','-'],input=backend.encode()))
core='''
import json, uuid
from agent_core.config import load_config
from agent_core.runs import prepare
from agent_core.runtime import Runtime
from agent_core.agent import stream_agent
from agent_core.store import Store
from agent_core.providers import record_usage
body=json.loads(BODY)
body['request_id']=str(uuid.uuid4())
c=load_config('/run/stock/core.json');s=next(s for s in c['services'] if s['id']=='stock-chat')
prepared,_=prepare(c,None,s,'chat',body)
runtime=Runtime(c,Store(c['database']),s,{'id':body['request_id'],'domain':'chat'},prepared,lambda:False)
def usage(value,status):record_usage(runtime.store,s,prepared['_profile'],value,status,source='diagnostic',request_id=body['request_id'])
content='';calls=[];repairs=[]
for event in stream_agent(prepared['_profile'],prepared['_messages'],reasoning_enabled=prepared['_reasoning'],runtime=runtime,on_model_usage=usage):
    if event['type']=='delta':content+=event['content']
    elif event['type']=='tool_result':
        result=event.get('result',{});artifact=result.get('data',{}).get('stockArtifact',{})
        calls.append({'tool':event.get('tool'),'status':result.get('status'),'indicatorIds':[i['id'] for i in artifact.get('provenance',{}).get('query',{}).get('indicators',[])]})
    elif event.get('stage')=='ANSWER_REPAIR':repairs.append(event.get('reason'))
print(json.dumps({'question':body['messages'][-1]['content'],'content':content[:2500],'contentChars':len(content),'tools':calls,'repairs':repairs},ensure_ascii=False))
'''.replace('BODY',repr(json.dumps(body)))
subprocess.run(['docker','exec','-i','stock-analysis-core-1','python','-'],input=core.encode(),check=True)
