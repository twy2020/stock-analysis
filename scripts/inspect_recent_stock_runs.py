"""Read recent stock failures and public model routing, without credentials or replay."""
import json
import subprocess
import sys
sys.stdout.reconfigure(encoding='utf-8')
script='''
import json
from app import create_app
from app.extensions import database
from app.models import ChatRun,Message
from flask import current_app
app=create_app()
with app.app_context():
    rows=database.session.query(ChatRun).filter(ChatRun.id=='b8794ce0-6eed-43a7-a611-091b040150ef').all()
    report=[]
    for row in rows:
        question=database.session.get(Message,row.user_message_id)
        answer=database.session.get(Message,row.assistant_message_id)
        info=json.loads(answer.retrieval_json or '{}') if answer else {}
        report.append({'id':row.id,'coreRunId':info.get('coreRunId'),'status':row.status,'question':question.content[:200] if question else '',
                       'model':answer.model if answer else None,'error':info.get('errorCode'),'elapsedMs':answer.latency_ms if answer else None,
                       'events':[{k:e.get(k) for k in ('stage','tool','status','elapsedMs','elapsedMsTotal','code')} for e in info.get('processEvents',[])]})
    print(json.dumps({'forcedModelProfile':current_app.config.get('AGENT_CORE_MODEL_PROFILE'),'runs':report},ensure_ascii=False))
'''
report=json.loads(subprocess.check_output(['docker','exec','-i','stock-analysis-backend-1','python','-'],input=script.encode()))
print(json.dumps(report,ensure_ascii=False),flush=True)
ids=[r['coreRunId'] for r in report['runs'] if r['coreRunId']][:4]
script='''
import json,sqlite3
from agent_core.config import load_config
c=load_config('/run/stock/core.json')
s=next(s for s in c['services'] if s['id']=='stock-chat')
print(json.dumps({'models':[{k:m.get(k) for k in ('id','model','enabled','providerType','supportsTools','supportsReasoning')} for m in c['models']],
 'service':{k:s.get(k) for k in ('modelProfiles','defaultModelProfile','maxOutputTokens','skills','maxActiveRuns')}},ensure_ascii=False))
db=sqlite3.connect(c['database'])
for rid in IDS:
    events=[]
    for name,raw in db.execute('SELECT name,payload FROM events WHERE run_id=? ORDER BY seq',(rid,)):
        p=json.loads(raw)
        if name in ('tool_call','tool_result','error','usage','model','progress'):
            if name=='progress' and p.get('stage') not in ('MODEL_NOTE','ANSWER_REPAIR'):continue
            if name=='tool_result':
                value=p.get('result',{})
                p={'tool':p.get('tool'),'operationId':p.get('operationId'),'status':value.get('status'),'error':value.get('error'),
                   'summary':json.dumps(value,ensure_ascii=False)[:500]}
            events.append({'type':name,**p})
    print(json.dumps({'coreRunId':rid,'events':events},ensure_ascii=False))
'''.replace('IDS',repr(ids))
subprocess.run(['docker','exec','-i','stock-analysis-core-1','python','-'],input=script.encode(),check=True)
