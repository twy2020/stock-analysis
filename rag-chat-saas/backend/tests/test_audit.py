import json
import respx
from httpx import Response
from app.chat_jobs import execute_run
from app.extensions import database
from app.models import AuditRecord, Message, User, Organization
from test_chat import sign_in, configure_dependencies


@respx.mock
def test_invalid_citation_is_audited_after_successful_model_output(app, client):
    csrf=sign_in(client); headers={'X-CSRF-Token':csrf}
    configure_dependencies(app)
    respx.post('https://model.example/v1/chat/completions').mock(return_value=Response(200,text='data: '+json.dumps({'choices':[{'delta':{'content':'回答已经写完，但错误沿用历史来源[3]。'}}]})+'\n\ndata: [DONE]\n\n'))
    cid=client.post('/api/v1/conversations',json={'title':'异常审计','knowledgeBaseId':'kb'},headers=headers).json['id']
    run=client.post(f'/api/v1/conversations/{cid}/runs',json={'content':'继续解释'},headers=headers).json
    execute_run(app,run['id'])
    response=client.get('/api/v1/admin/audit?kind=exception')
    assert response.status_code==200
    assert response.json['total']==1
    row=response.json['items'][0]
    assert row['runId']==run['id'] and row['conversationId']==cid
    assert row['details']['errorCategory']=='INVALID_CITATION'
    assert row['details']['generationCompleted'] is True
    assert row['details']['invalidLabels']==[3] and row['details']['sourceCount']==0
    assert row['details']['answer'].endswith('[3]。')
    assert row['details']['question']=='继续解释'
    assert row['details']['recentEvents']
    client.delete(f'/api/v1/conversations/{cid}',headers=headers)
    assert client.get('/api/v1/admin/audit?kind=exception').json['total']==1


@respx.mock
def test_real_call_failure_rotation_and_vote_history(app,client):
    csrf=sign_in(client); headers={'X-CSRF-Token':csrf}
    configure_dependencies(app,two_accounts=True)
    route=respx.post('https://model.example/v1/chat/completions')
    route.side_effect=[Response(401,json={'error':'SECRET-UPSTREAM-RESPONSE'}),Response(200,text='data: '+json.dumps({'choices':[{'delta':{'content':'回答正文'}}],'usage':{'prompt_tokens':12,'completion_tokens':8}})+'\n\ndata: [DONE]\n\n')]
    cid=client.post('/api/v1/conversations',json={'title':'审计测试','knowledgeBaseId':'kb'},headers=headers).json['id']
    run=client.post(f'/api/v1/conversations/{cid}/runs',json={'content':'你好'},headers=headers).json
    execute_run(app,run['id'])
    result=client.get('/api/v1/admin/audit?kind=model').json
    assert result['total']==2
    assert result['summary']['counts']=={'FAILED':1,'SUCCEEDED':1}
    failed=next(r for r in result['items'] if r['status']=='FAILED')
    success=next(r for r in result['items'] if r['status']=='SUCCEEDED')
    assert failed['details']['httpStatus']==401
    assert success['details']['rotated'] and success['details']['previousAccount']=='primary'
    assert success['runId']==run['id'] and success['details']['completionTokens']==8
    assert 'SECRET-UPSTREAM' not in json.dumps(result) and 'model-key' not in json.dumps(result)
    assert client.get('/api/v1/admin/audit?kind=model&rotated=true').json['total']==1
    answer=client.get(f'/api/v1/conversations/{cid}/messages').json[-1]
    for vote in (1,-1,0):
        response=client.post(f'/api/v1/conversations/{cid}/messages/{answer["id"]}/vote',json={'vote':vote},headers=headers)
        assert response.status_code==200
    votes=client.get('/api/v1/admin/audit?kind=activity&action=chat.vote_message').json
    assert votes['total']==3
    assert {row['details']['vote'] for row in votes['items']}=={-1,0,1}
    assert all(row['details']['answer']=='回答正文' and row['details']['question']=='你好' for row in votes['items'])
    assert client.delete(f'/api/v1/conversations/{cid}',headers=headers).status_code==204
    assert client.get('/api/v1/admin/audit?kind=model').json['total']==2
    assert client.get('/api/v1/admin/audit?kind=activity&action=chat.vote_message').json['total']==3


def test_audit_permissions_scope_filters_and_password_redaction(app,client):
    csrf=sign_in(client)
    with app.app_context():
        admin=database.session.query(User).filter_by(username='admin').one()
        for i in range(34):
            database.session.add(AuditRecord(organization_id=admin.organization_id,kind='model',action='chat.completions',status='SUCCEEDED',username='tester',details={'model':'test'}))
        other=Organization(name='other');database.session.add(other);database.session.flush()
        database.session.add(AuditRecord(organization_id=other.id,kind='model',action='chat.completions',status='FAILED',username='other',details={}))
        database.session.add(User.create('ordinary','Ordinary-Password-42!',password_change_required=False,organization_id=admin.organization_id))
        database.session.commit()
    result=client.get('/api/v1/admin/audit?kind=model&page=2&q=tester').json
    assert result['total']==34 and len(result['items'])==4
    assert client.get('/api/v1/admin/audit?from=invalid').status_code==400
    assert 'Initial-Password' not in client.get('/api/v1/admin/audit?kind=activity').text
    other_client=app.test_client();sign_in(other_client,'ordinary','Ordinary-Password-42!',change=False)
    assert other_client.get('/api/v1/admin/audit').status_code==403


def test_audit_completion_shares_stream_transaction_without_second_writer_lock(app):
    from app.audit import record
    with app.app_context():
        rid=record('model','chat.completions','RUNNING',{'model':'test'})
        # Pending token/event flushes hold the connection's write lock before a model ends.
        database.session.add(AuditRecord(kind='activity',action='stream-partial',status='SUCCEEDED',details={}))
        database.session.flush()
        assert record('model','chat.completions','SUCCEEDED',{'firstTokenMs':12},24,record_id=rid)==rid
        database.session.expire_all()
        assert database.session.get(AuditRecord,rid).status=='SUCCEEDED'
