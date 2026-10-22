"""Bounded real-model acceptance run inside the configured SaaS container.

Creates one clearly named test conversation; never edits an existing conversation.
"""
import json
import time
from pathlib import Path

from app import create_app
from app.extensions import database
from app.models import User, Conversation, ChatRun, ChatRunEvent, Message
from app.chat_jobs import enqueue, execute_run

app=create_app({'TESTING':True})
with app.app_context():
    if app.config.get('AGENT_BACKEND')!='core':raise RuntimeError('Core is not selected')
    user=database.session.query(User).filter_by(status='ACTIVE',role='ADMIN').first()
    from app.clients.rag import RagClient
    available=RagClient().json('GET','/api/v1/consumer/knowledge-bases')
    if not available: raise RuntimeError('No published knowledge base available for acceptance')
    conversation=Conversation(organization_id=user.organization_id,owner_id=user.id,title='Agent Core 联调验收 · 工具与检索',
                              knowledge_base_id=available[0]['id'])
    database.session.add(conversation);database.session.commit()
    question='这是接入验收。请依次调用 current_time、list_documents（limit=2），再调用 recall 检索“GB T 150 压力容器 适用范围”（topK=2）。简短报告北京时间、两个文档标题，再原文引用一条实际检索片段并使用对应引用编号。不要推导工程结论；工具失败或没有结果时如实说明。'
    run=enqueue(conversation,user,{'content':question,'reasoningEnabled':False})
    run_id,cid=run.id,conversation.id
    print(json.dumps({'run_id':run_id,'conversation_id':cid,'state':'submitted'}),flush=True)
execute_run(app,run_id)
deadline=time.monotonic()+360
while time.monotonic()<deadline:
    with app.app_context():
        run=database.session.get(ChatRun,run_id)
        if run.status not in ('QUEUED','RUNNING'):
            message=database.session.get(Message,run.assistant_message_id)
            events=database.session.query(ChatRunEvent).filter_by(run_id=run_id).order_by(ChatRunEvent.id).all()
            result={'run_id':run.id,'conversation_id':cid,'status':run.status,'answer':message.content,
                    'model':message.model,'retrieval':json.loads(message.retrieval_json or '{}'),
                    'events':[{'name':e.name,'payload':e.payload} for e in events]}
            Path('/tmp/core-chat-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'run_id':run.id,'status':run.status,'model':message.model,'answer_length':len(message.content),
                              'core_run_id':result['retrieval'].get('coreRunId')},ensure_ascii=False),flush=True)
            if run.status!='COMPLETED':raise SystemExit(1)
            break
    time.sleep(1)
else:raise SystemExit('Timed out observing existing run; do not resubmit.')
