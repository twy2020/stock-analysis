"""One scoped end-to-end chat probe; prints no credentials or answer content."""
import json
from app import create_app
from app.chat import ChatService
from app.extensions import database
from app.models import Conversation, Message, User

app=create_app({'TESTING':True})
with app.app_context():
    user=database.session.query(User).filter_by(username='stock-verification').one()
    conversation=Conversation(organization_id=user.organization_id,owner_id=user.id,title='验证 · 模型连接诊断',knowledge_base_id=None)
    database.session.add(conversation);database.session.commit()
    events={}
    for block in ChatService().stream(conversation,user,'请调用 current_time 获取当前系统时间，确认日期和时区。最终请按本系统输出协议，用 <stock_answer>...</stock_answer> 包裹中文答复。无需联网或股票数据查询。',web_enabled=False):
        for line in block.splitlines():
            if line.startswith('event: '):events[line[7:]]=events.get(line[7:],0)+1
    assistant=database.session.query(Message).filter_by(conversation_id=conversation.id,role='ASSISTANT').one()
    info=json.loads(assistant.retrieval_json or '{}')
    print(json.dumps({'status':assistant.status,'model':assistant.model,'latencyMs':assistant.latency_ms,
        'errorCode':info.get('errorCode'),'coreRunId':info.get('coreRunId'),'events':events,
        'terminalStage':(info.get('processEvents') or [{}])[-1].get('stage')},ensure_ascii=True),flush=True)
