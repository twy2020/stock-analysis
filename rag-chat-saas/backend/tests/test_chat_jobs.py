import json
import threading
import uuid
from app.chat import ChatService, event
from app.chat_jobs import execute_run
from app.extensions import database
from app.models import ChatRun, Message, User
from test_chat import sign_in


def setup_conversation(client):
    csrf=sign_in(client)
    conversation=client.post('/api/v1/conversations',json={'title':'任务测试','knowledgeBaseId':'kb'},headers={'X-CSRF-Token':csrf}).json
    return conversation['id'],{'X-CSRF-Token':csrf}


def fake_stream(self,conversation,user,question,reasoning_enabled=None,prepared=None):
    yield event('message',{'userMessageId':prepared[0].id,'assistantMessageId':prepared[1].id})
    yield event('delta',{'content':'回答：'+question})
    yield event('complete',{'content':'回答：'+question,'citations':[]})


def test_background_job_survives_observer_disconnect_and_replays(app,client,monkeypatch):
    cid,headers=setup_conversation(client)
    ready=threading.Event(); release=threading.Event()
    def blocked(*args,**kwargs):
        yield from list(fake_stream(*args,**kwargs))[:2]
        ready.set(); release.wait(5)
        yield event('complete',{'content':'最终回答','citations':[]})
    monkeypatch.setattr(ChatService,'stream',blocked)
    run=client.post(f'/api/v1/conversations/{cid}/runs',json={'content':'问题'},headers=headers).json
    worker=threading.Thread(target=execute_run,args=(app,run['id'])); worker.start()
    assert ready.wait(5)
    assert client.get('/api/v1/conversations').json[0]['activeRunId']==run['id']
    assert client.post(f'/api/v1/conversations/{cid}/runs',json={'content':'冲突问题'},headers=headers).status_code==409
    observer=client.get(f'/api/v1/conversations/{cid}/runs/{run["id"]}/events',buffered=False)
    first=next(iter(observer.response)).decode(); observer.close()
    assert 'event: message' in first
    release.set(); worker.join(5); assert not worker.is_alive()
    c=client.get('/api/v1/conversations').json[0]
    assert c['activeRunId'] is None and c['unread']
    for _ in range(2):
        replay=client.get(f'/api/v1/conversations/{cid}/runs/{run["id"]}/events').text
        assert 'event: complete' in replay and '最终回答' in replay
    assert client.get(f'/api/v1/conversations/{cid}/messages').json[-1]['content']=='最终回答'
    client.post(f'/api/v1/conversations/{cid}/read',json={'runId':'old'},headers=headers)
    assert client.get('/api/v1/conversations').json[0]['unread']
    client.post(f'/api/v1/conversations/{cid}/read',json={'runId':run['id']},headers=headers)
    assert not client.get('/api/v1/conversations').json[0]['unread']


def test_edit_latest_replaces_answer_edit_old_appends_and_regenerate_keeps_question(app,client,monkeypatch):
    monkeypatch.setattr(ChatService,'stream',fake_stream)
    cid,headers=setup_conversation(client)
    def send(payload):
        response=client.post(f'/api/v1/conversations/{cid}/runs',json=payload,headers=headers)
        assert response.status_code==200,response.json
        execute_run(app,response.json['id'])
        return client.get(f'/api/v1/conversations/{cid}/messages').json
    rows=send({'content':'原问题'})
    user_id,answer_id=rows[0]['id'],rows[1]['id']
    rows=send({'content':'最新修改','editMessageId':user_id})
    assert len(rows)==2 and rows[0]['id']==user_id and rows[1]['id']==answer_id
    assert rows[1]['content']=='回答：最新修改'
    vote=client.post(f'/api/v1/conversations/{cid}/messages/{answer_id}/vote',json={'vote':1},headers=headers)
    assert vote.json=={'vote':1}
    rows=send({'regenerateMessageId':answer_id})
    assert len(rows)==2 and rows[1]['vote']==0
    rows=send({'content':'第二个问题'})
    rows=send({'content':'旧问题追加','editMessageId':user_id})
    assert len(rows)==6 and rows[0]['content']=='最新修改' and rows[4]['content']=='旧问题追加'


def test_job_idempotency_and_user_isolation(app,client,monkeypatch):
    cid,headers=setup_conversation(client)
    payload={'content':'问题','requestId':str(uuid.uuid4())}
    first=client.post(f'/api/v1/conversations/{cid}/runs',json=payload,headers=headers).json
    again=client.post(f'/api/v1/conversations/{cid}/runs',json=payload,headers=headers).json
    assert first['id']==again['id']
    with app.app_context():
        assert database.session.query(ChatRun).count()==1
        database.session.add(User.create('other','Other-Password-42!',password_change_required=False)); database.session.commit()
    other=app.test_client(); sign_in(other,'other','Other-Password-42!',change=False)
    assert other.get(f'/api/v1/conversations/{cid}/runs/{first["id"]}/events').status_code==404


def test_queued_cancel_retains_question_and_unlocks_conversation(app,client,monkeypatch):
    monkeypatch.setattr(ChatService,'stream',fake_stream)
    cid,headers=setup_conversation(client)
    run=client.post(f'/api/v1/conversations/{cid}/runs',json={'content':'取消测试'},headers=headers).json
    client.post(f'/api/v1/conversations/{cid}/runs/{run["id"]}/cancel',headers=headers)
    execute_run(app,run['id'])
    assert client.get(f'/api/v1/conversations/{cid}/runs/{run["id"]}').json['status']=='CANCELLED'
    assert client.get('/api/v1/conversations').json[0]['activeRunId'] is None


def test_tool_commentary_is_retained_in_process_not_final_answer(app,client,monkeypatch):
    def stream(*args, **kwargs):
        yield event('delta', {'content':'先检查目录。'})
        yield event('progress', {'stage':'MODEL_NOTE','content':'先检查目录。','elapsedMsTotal':120})
        yield event('answer_reset', {})
        yield event('delta', {'content':'最终回答'})
        yield event('complete', {'content':'最终回答','citations':[]})
    monkeypatch.setattr(ChatService,'stream',stream)
    cid,headers=setup_conversation(client)
    run=client.post(f'/api/v1/conversations/{cid}/runs',json={'content':'问题'},headers=headers).json
    execute_run(app,run['id'])
    answer=client.get(f'/api/v1/conversations/{cid}/messages').json[-1]
    assert answer['content']=='最终回答'
    assert answer['processEvents'][0]['content']=='先检查目录。'
    replay=client.get(f'/api/v1/conversations/{cid}/runs/{run["id"]}/events').text
    assert 'event: answer_reset' in replay


def test_stream_does_not_hold_writer_lock_while_waiting_for_model_audit(app,client,monkeypatch):
    from app.audit import record
    finished=threading.Event()
    def stream(*args,**kwargs):
        yield event('delta',{'content':'第一段'})
        yield event('delta',{'content':'第二段'})
        def model_audit():
            with app.app_context():
                if record('model','chat.completions','SUCCEEDED',{}): finished.set()
        writer=threading.Thread(target=model_audit);writer.start()
        writer.join(2)
        assert finished.is_set(), 'Worker kept a write transaction open across the next model event'
        yield event('complete',{'content':'第一段第二段','citations':[]})
    monkeypatch.setattr(ChatService,'stream',stream)
    cid,headers=setup_conversation(client)
    run=client.post(f'/api/v1/conversations/{cid}/runs',json={'content':'并发写入'},headers=headers).json
    execute_run(app,run['id'])
    assert finished.is_set()
    assert client.get(f'/api/v1/conversations/{cid}/messages').json[-1]['status']=='COMPLETED'
