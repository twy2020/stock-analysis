"""Exercise real SaaS/Core/MCP web research with an isolated verification account."""
import json
import subprocess
import urllib.request
import uuid
import sys
import time
import argparse

sys.stdout.reconfigure(encoding='utf-8')
parser=argparse.ArgumentParser()
parser.add_argument('--question',default='帮我查一下宇树科技股票当前价')
parser.add_argument('--company-discovery',action='store_true')
options=parser.parse_args()

setup = '''
import json,secrets
from app import create_app
from app.extensions import database
from app.models import User,Session
app=create_app()
with app.app_context():
    user=database.session.query(User).filter_by(username='stock-web-verification').one_or_none()
    if user is None:
        user=User.create('stock-web-verification',secrets.token_urlsafe(32),role='USER',password_change_required=False,organization_id='stock-research')
        database.session.add(user);database.session.flush()
    user.status='ACTIVE'
    session,cookie,csrf=Session.issue(user,600);database.session.add(session);database.session.commit()
    print(json.dumps({'cookie':cookie,'csrf':csrf,'userId':user.id}))
'''
auth = json.loads(subprocess.check_output(['docker','exec','-i','stock-analysis-backend-1','python','-'],input=setup.encode()))
base = 'http://127.0.0.1:18110'
headers = {'Cookie': 'stock_analysis_session='+auth['cookie'], 'X-CSRF-Token':auth['csrf'], 'Content-Type':'application/json'}

def request(path, body):
    req = urllib.request.Request(base+path,data=json.dumps(body).encode(),headers=headers,method='POST')
    with urllib.request.urlopen(req,timeout=45) as response:
        return json.load(response)

try:
    conversation = request('/api/v1/conversations', {'title':'验证 · 联网股价查询','knowledgeBaseId':None})
    started=time.monotonic()
    run = request('/api/v1/conversations/'+conversation['id']+'/runs', {'content':options.question,'webEnabled':True,'reasoningEnabled':False,'requestId':str(uuid.uuid4())})
    print(json.dumps({'runId':run['id'],'conversationId':conversation['id']},ensure_ascii=False),flush=True)
    req = urllib.request.Request(base+'/api/v1/conversations/'+conversation['id']+'/runs/'+run['id']+'/events',headers=headers)
    events=[];terminal=None;model=None
    with urllib.request.urlopen(req,timeout=240) as response:
        name=''
        for line in response:
            line=line.decode().strip()
            if line.startswith('event:'):name=line[6:].strip()
            if line.startswith('data:'):
                value=json.loads(line[5:])
                if name=='model':model=value
                if name=='progress':
                    event={k:value[k] for k in ('stage','tool','status','code','elapsedMs','sources') if k in value}
                    events.append(event);print(json.dumps(event,ensure_ascii=False),flush=True)
                if name in ('complete','error'):
                    terminal={'type':name,'code':value.get('code'),'answer':value.get('content','')[:2200]}
                    break
    print(json.dumps({'elapsedSeconds':round(time.monotonic()-started,1),'model':model,'terminal':terminal,'webTools':[e for e in events if 'stock_web_' in e.get('tool','')]},ensure_ascii=False),flush=True)
    assert terminal and terminal['type']=='complete', 'Real web chat did not complete'
    assert any(e.get('stage')=='TOOL_COMPLETED' and e.get('tool','').endswith('stock_web_search') for e in events), 'Search was not executed successfully'
    if not options.company_discovery:
        assert any(e.get('stage')=='TOOL_COMPLETED' and e.get('tool','').endswith('stock_web_fetch') for e in events), 'Source reading was not executed successfully'
    else:
        assert not any(e.get('tool') in ('stock_health','stock_backtest','stock_events','stock_sql') for e in events), 'Company research called market-only tools'
        assert not any(e.get('stage')=='ANSWER_REPAIR' for e in events), 'Final answer required another repair'
    assert any(e.get('sources') for e in events), 'Web sources were missing from SSE events'
    assert '](' in terminal['answer'], 'Answer did not contain Markdown source links'
finally:
    cleanup = '''
from app import create_app
from app.extensions import database
from app.models import User,Session
app=create_app()
with app.app_context():
    user=database.session.query(User).filter_by(username='stock-web-verification').one()
    user.status='DISABLED'
    database.session.query(Session).filter_by(user_id=user.id).delete()
    database.session.commit()
'''
    subprocess.run(['docker','exec','-i','stock-analysis-backend-1','python','-'],input=cleanup.encode(),check=True)
