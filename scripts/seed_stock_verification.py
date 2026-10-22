"""Create temporary, scoped UI verification records using real engine calculations.

Executed in the STOCK backend container only. Does not request a paid model.
Prints the temporary session only to its local Playwright parent, never to logs.
"""
import json
import secrets
import uuid
import os
from app import create_app
from app.extensions import database
from app.models import User, Conversation, Message, Session
from app.stock import engine_request

app=create_app({'TESTING':True})
with app.app_context():
    user=database.session.query(User).filter_by(username='stock-verification').one_or_none()
    if user is None:
        user=User.create('stock-verification',secrets.token_urlsafe(32),role='USER',
                         password_change_required=False,organization_id='stock-research')
        database.session.add(user);database.session.flush()
    user.status='ACTIVE'
    if os.environ.get('STOCK_VERIFY_SAVED') == 'true':
        saved = database.session.query(Conversation).filter_by(owner_id=user.id, title='验证 · 平安银行研究').order_by(Conversation.created_at.desc()).all()
        for item in saved:
            message = database.session.query(Message).filter_by(conversation_id=item.id, role='ASSISTANT').first()
            artifacts = json.loads(message.retrieval_json or '{}').get('stockArtifacts', []) if message else []
            if len(artifacts) != 3:
                continue
            scope = {'tenant_id':user.organization_id,'actor_id':user.id,'conversation_id':item.id}
            engine_request('/artifacts/read', {'datasetRef':artifacts[0]['datasetRef'],'context':scope})
            session,cookie,csrf=Session.issue(user,1800);database.session.add(session);database.session.commit()
            print(json.dumps({'cookie':cookie,'csrf':csrf,'conversationId':item.id,'userId':user.id,
                'artifacts':[{'datasetRef':a['datasetRef'],'rowCount':a['rowCount'],'title':a['title']} for a in artifacts]}))
            raise SystemExit(0)
        raise RuntimeError('No saved verification datasets available')
    conversation=Conversation(id=str(uuid.uuid4()),organization_id=user.organization_id,owner_id=user.id,title='验证 · 平安银行研究')
    database.session.add(conversation);database.session.flush()
    scope={'tenant_id':user.organization_id,'actor_id':user.id,'conversation_id':conversation.id}
    artifacts=[]
    common={'universe':{'codes':['000001']},'window':{'bars':300,'warmup':260},'output':{'previewRows':0}}
    queries=[{**common,'task':'analyze','indicators':[{'id':'MA5','expression':'MA(CLOSE,5)'},{'id':'MA20','expression':'MA(CLOSE,20)'},{'id':'RSI14','expression':'RSI(CLOSE,14)','panel':'separate'}]},
             {**common,'task':'events','condition':'CROSS(CLOSE,MA(CLOSE,20))','periods':[1,3,5,10],'cooldown':10},
             {**common,'task':'backtest','buy':'CROSS(MA(CLOSE,5),MA(CLOSE,20))','sell':'CROSSDOWN(MA(CLOSE,5),MA(CLOSE,20))'}]
    for query in queries:
        result=engine_request('/tools/execute',{'contractVersion':'1','tool':'stock_query','arguments':query,'context':scope})
        if result.get('status')!='succeeded':raise RuntimeError(str(result))
        artifact=result['data']['stockArtifact'];artifacts.append(artifact)
        assert artifact['preview']==[]
        assert all('rows' not in c for c in artifact['charts'])
    summary=artifacts[0]['summary']['000001']
    database.session.add(Message(conversation_id=conversation.id,organization_id=user.organization_id,owner_id=user.id,
        role='USER',status='COMPLETED',content='查看平安银行行情、事件统计与均线策略回测。'))
    answer=f"最新入库交易日为 {summary['lastDate']}，收盘 {summary['lastClose']} 元。 [data:{artifacts[0]['datasetRef']}]\n\n事件统计与回测使用数据引擎计算；请结合样本数、同期基准及未复权限制进行研究。"
    database.session.add(Message(conversation_id=conversation.id,organization_id=user.organization_id,owner_id=user.id,
        role='ASSISTANT',status='COMPLETED',content=answer,retrieval_json=json.dumps({'stockArtifacts':artifacts},ensure_ascii=False)))
    session,cookie,csrf=Session.issue(user,1800);database.session.add(session);database.session.commit()
    print(json.dumps({'cookie':cookie,'csrf':csrf,'conversationId':conversation.id,'userId':user.id,
                      'artifacts':[{'datasetRef':a['datasetRef'],'rowCount':a['rowCount'],'title':a['title']} for a in artifacts]}))
