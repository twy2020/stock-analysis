import hashlib
import json

import httpx
import respx

from app.chat import ChatService
from app.extensions import database
from app.models import Conversation, Message, MessageCitation, User


def configure(app, tmp_path):
    token = tmp_path / 'core.token'
    token.write_text('private-test-token')
    app.config.update(AGENT_BACKEND='core', AGENT_CORE_URL='https://core.example',
                      AGENT_CORE_TOKEN_FILE=str(token), AGENT_CORE_MODEL_PROFILE='primary',
                      AGENT_CORE_CALLBACK_TOKEN_SHA256=hashlib.sha256(b'callback-token').hexdigest())


def conversation():
    user = database.session.query(User).first()
    row = Conversation(organization_id=user.organization_id, owner_id=user.id,
                       title='Core test', knowledge_base_id='kb-1')
    database.session.add(row)
    database.session.commit()
    return row, user


def block(seq, name, payload):
    return f'id: {seq}\nevent: {name}\ndata: {json.dumps(payload)}\n\n'


@respx.mock
def test_failed_core_run_persists_terminal_timing_and_process_failure(app,tmp_path,monkeypatch):
    configure(app,tmp_path)
    clock=[100.0]
    monkeypatch.setattr('app.core_chat.time.monotonic',lambda:clock[0])
    respx.post('https://core.example/v1/chat/runs').respond(202,json={'id':'timeout-run'})
    respx.get('https://core.example/v1/runs/timeout-run/events').respond(200,text=block(1,'model',{'model':'gpt-fixture'})+block(2,'progress',{'stage':'AGENT_THINKING'})+block(3,'error',{'code':'TIMEOUT'}))
    with app.app_context():
        row,user=conversation()
        stream=ChatService().stream(row,user,'test')
        parts=[]
        for part in stream:
            parts.append(part)
            if 'AGENT_THINKING' in part:clock[0]=220.5
        assistant=database.session.query(Message).filter_by(role='ASSISTANT').one()
        assert assistant.latency_ms==120500
        assert assistant.model=='gpt-fixture'
        saved=json.loads(assistant.retrieval_json)
        assert saved['processEvents'][-1]['stage']=='PROCESS_FAILED'
        assert saved['processEvents'][-1]['elapsedMsTotal']==120500
        assert 'PROCESS_FAILED' in ''.join(parts)


@respx.mock
def test_disconnect_after_durable_completion_does_not_change_answer_to_failed(app,tmp_path):
    configure(app,tmp_path)
    respx.post('https://core.example/v1/chat/runs').respond(202,json={'id':'completed-before-disconnect'})
    respx.get('https://core.example/v1/runs/completed-before-disconnect/events').respond(200,text=block(1,'delta',{'content':'OK'})+block(2,'complete',{}))
    with app.app_context():
        row,user=conversation()
        stream=ChatService().stream(row,user,'test')
        for part in stream:
            if 'PROCESS_COMPLETED' in part:break
        stream.close()
        assistant=database.session.query(Message).filter_by(role='ASSISTANT').one()
        assert assistant.status=='COMPLETED'


@respx.mock
def test_admin_model_setting_updates_core_and_new_chat_follows_core_default(app,client,tmp_path):
    configure(app,tmp_path);app.config['AGENT_CORE_MODEL_PROFILE']=''
    from test_chat_images import login
    headers=login(client)
    settings={'models':[{'id':'native','model':'deepseek-flash'}],'defaultModelProfile':'native','revision':'v2','writable':True}
    respx.get('https://core.example/v1/settings/model').respond(200,json=settings)
    update=respx.put('https://core.example/v1/settings/model').respond(200,json=settings)
    assert client.get('/api/v1/admin/settings/model').json['defaultModelProfile']=='native'
    response=client.put('/api/v1/admin/settings/model',headers=headers,json={'revision':'v1','modelProfile':'native'})
    assert response.status_code==200,response.json
    assert json.loads(update.calls[0].request.content)=={'revision':'v1','modelProfile':'native'}
    create=respx.post('https://core.example/v1/chat/runs').respond(202,json={'id':'default-run'})
    respx.get('https://core.example/v1/runs/default-run/events').respond(200,text=block(1,'delta',{'content':'已核实'})+block(2,'complete',{}))
    with app.app_context():
        row,user=conversation()
        result=''.join(ChatService().stream(row,user,'测试'))
        assert 'event: complete' in result
    assert 'model_profile' not in json.loads(create.calls[0].request.content)


@respx.mock
def test_model_setting_conflict_is_visible_and_unauthenticated_update_is_rejected(app,client,tmp_path):
    configure(app,tmp_path)
    assert client.put('/api/v1/admin/settings/model',json={'revision':'x','modelProfile':'x'}).status_code==401
    from test_chat_images import login
    headers=login(client)
    respx.put('https://core.example/v1/settings/model').respond(409,json={'code':'ACTIVE_RUNS_CONFIGURATION_LOCKED'})
    response=client.put('/api/v1/admin/settings/model',headers=headers,json={'revision':'x','modelProfile':'primary'})
    assert response.status_code==409
    assert response.json['code']=='ACTIVE_RUNS_CONFIGURATION_LOCKED'


@respx.mock
def test_web_sources_persist_in_events_and_allow_markdown_numeric_links(app,tmp_path):
    configure(app,tmp_path)
    source={'id':'web_fixture','url':'https://example.com/report','title':'Report','domain':'example.com','engines':['bing'],'read':True}
    respx.post('https://core.example/v1/chat/runs').respond(202,json={'id':'web-remote'})
    respx.get('https://core.example/v1/runs/web-remote/events').respond(200,text=''.join([
        block(1,'tool_result',{'tool':'stock_web_search','operationId':'op','result':{'status':'succeeded','data':{'sources':[source]}}}),
        block(2,'progress',{'stage':'TOOL_COMPLETED','operationId':'op','status':'COMPLETED'}),
        block(3,'delta',{'content':'事实[1](https://example.com/report)'}),block(4,'complete',{})]))
    with app.app_context():
        row,user=conversation()
        result=''.join(ChatService().stream(row,user,'搜索公告'))
        assert 'event: complete' in result,result
        assistant=database.session.query(Message).filter_by(role='ASSISTANT').one()
        saved=json.loads(assistant.retrieval_json)
        assert saved['webSources']==[source]
        assert saved['processEvents'][0]['sources']==[source]


@respx.mock
def test_core_chat_without_local_accounts_persists_citations_and_usage(app, tmp_path):
    configure(app, tmp_path)
    from test_chat import retrieval_payload
    found = retrieval_payload()
    found['results'][0]['label'] = 1
    create = respx.post('https://core.example/v1/chat/runs').respond(202, json={'id':'remote-1'})
    respx.get('https://core.example/v1/runs/remote-1/events').respond(200, text=''.join([
        block(1,'model',{'model':'core-model','reasoningEnabled':False}),
        block(2,'retrieval',{'payload':found}), block(3,'delta',{'content':'核对结果 [1]'}),
        block(4,'usage',{'prompt_tokens':20,'completion_tokens':8}),
        block(5,'complete',{'content':'核对结果 [1]'})]))
    with app.app_context():
        row, user = conversation()
        result = ''.join(ChatService().stream(row,user,'检查设计压力'))
        assert 'event: complete' in result, result
        assistant = database.session.query(Message).filter_by(role='ASSISTANT').one()
        assert assistant.status == 'COMPLETED'
        assert assistant.content == '核对结果 [1]'
        assert assistant.model == 'core-model' and assistant.prompt_tokens == 20
        assert json.loads(assistant.retrieval_json)['processEvents'][-1]['stage']=='PROCESS_COMPLETED'
        assert json.loads(assistant.retrieval_json)['coreRunId'] == 'remote-1'
        assert database.session.query(MessageCitation).one().citation_id == 'citation-1'
        body = json.loads(create.calls[0].request.content)
        assert body['context']['actor_id'] == user.id
        assert body['context']['tenant_id'] == user.organization_id
        assert body['model_profile'] == 'primary'


@respx.mock
def test_configured_core_failure_never_falls_back_to_local_agent(app, tmp_path, monkeypatch):
    configure(app, tmp_path)
    def forbidden(*a, **k):
        raise AssertionError('local agent must not execute')
    monkeypatch.setattr('app.chat.stream_agent', forbidden)
    respx.post('https://core.example/v1/chat/runs').respond(503,json={'error':{'code':'UNAVAILABLE'}})
    with app.app_context():
        row,user=conversation()
        result=''.join(ChatService().stream(row,user,'hello'))
        assert 'CORE_UNAVAILABLE' in result
        assert database.session.query(Message).filter_by(role='ASSISTANT').one().status=='FAILED'


@respx.mock
def test_client_reconnects_to_same_run_with_cursor_without_resubmitting(app, tmp_path):
    configure(app,tmp_path)
    from app.core_client import CoreClient
    create=respx.post('https://core.example/v1/chat/runs').respond(202,json={'id':'r'})
    first=respx.get('https://core.example/v1/runs/r/events').mock(side_effect=[
        httpx.Response(200,text=block(1,'delta',{'content':'a'})),
        httpx.Response(200,text=block(1,'delta',{'content':'a'})+block(2,'complete',{'content':'a'}))])
    with app.app_context():
        items=list(CoreClient().stream({'request_id':'request'},lambda:False))
    assert [i['type'] for i in items].count('delta')==1
    assert create.call_count==1
    assert first.calls[1].request.headers['Last-Event-ID']=='1'


@respx.mock
def test_callback_rejects_forged_scope_and_only_queries_bound_knowledge(app, client, tmp_path):
    configure(app,tmp_path)
    from app.crypto import encrypt_json
    from app.models import SystemSetting
    with app.app_context():
        row,user=conversation()
        body={'operation':'list_documents','arguments':{'offset':0,'limit':10},'request_id':'tool-1',
              'context':{'conversation_id':row.id,'actor_id':user.id,'tenant_id':user.organization_id,'knowledge_base_id':'kb-1'}}
        database.session.add(SystemSetting(key='rag.connection',encrypted_value=encrypt_json({'baseUrl':'https://rag.example','apiKey':'test'})))
        database.session.commit()
    headers={'Authorization':'Bearer callback-token'}
    url='/api/internal/agent-core/rag'
    assert client.post(url,json=body).status_code==401
    forged={**body,'context':{**body['context'],'knowledge_base_id':'other'}}
    assert client.post(url,json=forged,headers=headers).status_code==403
    upstream=respx.post('https://rag.example/api/v1/consumer/knowledge-bases/kb-1/tools/execute').respond(200,json={'items':[]})
    result=client.post(url,json=body,headers=headers)
    assert result.status_code==200,result.json
    assert upstream.call_count==1
    assert json.loads(upstream.calls[0].request.content)=={'operation':'list_documents','arguments':{'offset':0,'limit':10}}


@respx.mock
def test_closing_client_stream_cancels_remote_run(app, tmp_path):
    configure(app,tmp_path)
    from app.core_client import CoreClient
    respx.post('https://core.example/v1/chat/runs').respond(202,json={'id':'r'})
    cancel=respx.post('https://core.example/v1/runs/r/cancel').respond(200,json={'status':'CANCELLED'})
    with app.app_context():
        stream=CoreClient().stream({'request_id':'request'},lambda:False)
        assert next(stream)=={'type':'core_run','id':'r'}
        stream.close()
    assert cancel.call_count==1


@respx.mock
def test_owned_ocr_image_refs_are_forwarded_to_core_without_local_vision(app,tmp_path):
    configure(app,tmp_path)
    import base64
    from app.crypto import encrypt_json
    from app.models import SystemSetting
    from app.plugins.models import ChatImage
    create=respx.post('https://core.example/v1/chat/runs').respond(202,json={'id':'image-run'})
    respx.get('https://core.example/v1/runs/image-run/events').respond(200,text=
        block(1,'delta',{'content':'图片分析结果'})+block(2,'complete',{'content':'图片分析结果'}))
    with app.app_context():
        row,user=conversation()
        question=Message(conversation_id=row.id,organization_id=user.organization_id,owner_id=user.id,
                         role='USER',content='看图',status='COMPLETED')
        assistant=Message(conversation_id=row.id,organization_id=user.organization_id,owner_id=user.id,
                         role='ASSISTANT',content='',status='STREAMING')
        database.session.add_all([question,assistant])
        database.session.flush()
        database.session.add(SystemSetting(key='chat.images',encrypted_value=encrypt_json({'enabled':True,'backend':'ocr'})))
        database.session.add(ChatImage(owner_id=user.id,message_id=question.id,name='drawing.png',media_type='image/png',content=b'image-bytes'))
        database.session.commit()
        result=''.join(ChatService().stream(row,user,'看图',prepared=(question,assistant)))
        assert 'event: complete' in result
    messages=json.loads(create.calls[0].request.content)['messages']
    assert messages[-1]['content'][1]['image_url']['url']=='data:image/png;base64,'+base64.b64encode(b'image-bytes').decode()


@respx.mock
def test_core_manages_image_availability_without_local_visual_accounts(app,client,tmp_path):
    configure(app,tmp_path)
    from test_chat_images import login
    headers=login(client)
    respx.get('https://core.example/v1/capabilities').respond(200,json={'tools':[{'name':'ocr_analyze'}]})
    response=client.put('/api/v1/admin/settings/images',headers=headers,json={'enabled':True,'backend':'ocr','accountIds':[]})
    assert response.status_code==200,response.json
    assert client.get('/api/v1/images/capabilities').json['enabled'] is True
    assert client.get('/api/v1/admin/settings/images').json['managedByCore'] is True


@respx.mock
def test_restart_cancels_durable_core_run_even_after_backend_setting_changes(app,tmp_path):
    configure(app,tmp_path)
    app.config['AGENT_BACKEND']='local'
    from app.models import ChatRun, ChatRunEvent
    from app.core_client import recover_interrupted_runs
    cancel=respx.post('https://core.example/v1/runs/interrupted-core/cancel').respond(200,json={'status':'CANCELLED'})
    with app.app_context():
        row,user=conversation()
        run=ChatRun(id='interrupted',conversation_id=row.id,owner_id=user.id,user_message_id='q',assistant_message_id='a',status='RUNNING')
        database.session.add(run);database.session.flush()
        database.session.add(ChatRunEvent(run_id=run.id,name='core_run',payload={'id':'interrupted-core'}))
        database.session.commit()
        recover_interrupted_runs()
    assert cancel.call_count==1
