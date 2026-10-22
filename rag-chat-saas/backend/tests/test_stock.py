import json
import respx
from app.chat import ChatService
from app.extensions import database
from app.models import Message
from test_core_bridge import configure, conversation, block


def artifact():
    return {'version':'stock-artifact/1','datasetRef':'ds_'+'a'*32,'title':'行情',
            'summary':{'lastClose':12.3},'preview':[],'rowCount':300,'charts':[{'kind':'candlestick','title':'K线'}],
            'provenance':{'dataAsOf':'2026-09-30'},'warnings':[]}


@respx.mock
def test_core_stock_artifact_survives_message_persistence(app,tmp_path):
    configure(app,tmp_path); app.config['RAG_ENABLED']=False
    submit=respx.post('https://core.example/v1/chat/runs').respond(202,json={'id':'r'})
    item=artifact(); answer='收盘12.3元 [data:'+item['datasetRef']+']'
    respx.get('https://core.example/v1/runs/r/events').respond(200,text=''.join([
        block(1,'tool_result',{'tool':'stock_query','operationId':'op','result':{'status':'succeeded','data':{'stockArtifact':item}}}),
        block(2,'delta',{'content':answer}),block(3,'complete',{'content':answer})]))
    with app.app_context():
        row,user=conversation()
        result=''.join(ChatService().stream(row,user,'分析平安银行'))
        assert 'event: stock_artifact' in result
        assistant=database.session.query(Message).filter_by(role='ASSISTANT').one()
        assert assistant.status=='COMPLETED',result
        assert json.loads(assistant.retrieval_json)['stockArtifacts'][0]['datasetRef']==item['datasetRef']
    assert json.loads(submit.calls[0].request.content)['context']['knowledge_base_id'] is None


@respx.mock
def test_fabricated_stock_reference_rejected(app,tmp_path):
    configure(app,tmp_path)
    respx.post('https://core.example/v1/chat/runs').respond(202,json={'id':'r'})
    respx.get('https://core.example/v1/runs/r/events').respond(200,text=
        block(1,'delta',{'content':'结果 [data:ds_'+'b'*32+']'})+block(2,'complete',{}))
    with app.app_context():
        row,user=conversation(); result=''.join(ChatService().stream(row,user,'分析'))
        assert 'INVALID_DATA_REFERENCE' in result


def test_stock_prompt_requires_engine_computation(app):
    from app.context import build_messages
    with app.app_context():
        row,_=conversation(); content=build_messages(row,'分析',None)[0]['content']
        assert '数据引擎' in content and 'schema' in content


def test_admin_feature_policy_persists_and_blocks_retrieval(app, client):
    from test_chat import sign_in
    from app.features import rag_enabled
    csrf = sign_in(client)
    endpoint = '/api/v1/admin/settings/features'
    headers = {'X-CSRF-Token':csrf}
    assert client.get(endpoint).json == {'ragEnabled':True,'webEnabled':False}
    assert client.put(endpoint,json={'ragEnabled':'false'},headers=headers).status_code == 400
    assert client.put(endpoint,json={'ragEnabled':False},headers=headers).json == {'ragEnabled':False,'webEnabled':False}
    with app.app_context():
        assert rag_enabled() is False
    assert client.get('/api/v1/knowledge-bases').json == []
    assert client.get('/api/v1/conversations/capabilities').json['ragAvailable'] is False
    assert client.post('/api/internal/agent-core/rag',json={}).status_code == 403
    assert client.get(endpoint).json == {'ragEnabled':False,'webEnabled':False}
    client.put(endpoint,json={'ragEnabled':True},headers=headers)
    with app.app_context():
        assert rag_enabled() is True


def test_feature_settings_require_admin(app, client):
    assert client.get('/api/v1/admin/settings/features').status_code == 401


def test_disabled_rag_allows_run_without_knowledge_base(app, client):
    from test_chat import sign_in
    app.config['RAG_ENABLED'] = False
    csrf = sign_in(client)
    headers = {'X-CSRF-Token':csrf}
    row = client.post('/api/v1/conversations', json={'title':'研究'}, headers=headers).json
    assert row['knowledgeBaseId'] is None
    response = client.post(f"/api/v1/conversations/{row['id']}/runs",
        json={'content':'筛选最近放量的股票'}, headers=headers)
    assert response.status_code == 200
    assert response.json['status'] == 'QUEUED'


def test_browser_artifact_requires_owned_message_and_saved_reference(app, client, monkeypatch):
    from test_chat import sign_in
    from app.models import User
    sign_in(client)
    calls = []
    def read(path, body):
        calls.append((path, body))
        return {'table':[{'close':12.3}]}
    monkeypatch.setattr('app.stock.engine_request', read)
    with app.app_context():
        row, user = conversation()
        message = Message(conversation_id=row.id, organization_id=user.organization_id,
            owner_id=user.id, role='ASSISTANT', content='结果', status='COMPLETED',
            retrieval_json=json.dumps({'stockArtifacts':[artifact()]}))
        database.session.add(message); database.session.commit()
        url = f"/api/v1/stock/messages/{message.id}/artifacts/{artifact()['datasetRef']}"
        scope = {'tenant_id':user.organization_id,'actor_id':user.id,'conversation_id':row.id}
    assert client.get(url).json['table'][0]['close'] == 12.3
    assert calls[-1][1]['context'] == scope
    assert client.get(url+'?view=table').status_code == 200
    assert calls[-1][1]['view'] == 'table'
    assert calls[-1][1]['context'] == scope
    assert client.get(url.replace('a'*32, 'b'*32)).status_code == 404
    with app.app_context():
        other = User(organization_id=scope['tenant_id'], username='other-owner',
            password_hash='unused', role='USER', status='ACTIVE')
        database.session.add(other); database.session.flush()
        message = database.session.query(Message).filter_by(role='ASSISTANT').one()
        message.owner_id = other.id; database.session.commit()
    assert client.get(url).status_code == 404
    assert client.get(url+'?view=table').status_code == 404
    assert len(calls) == 2
