import hashlib
import json
import uuid
from datetime import timedelta

import pytest
import respx
import httpx

from app.extensions import database
from app.models import now

ROOT = '/api/service/v1'
CTX = {'project_id': 'p1', 'drawing_id': 'd1', 'revision': 'r1'}
HEADERS = {'Authorization': 'Bearer integration-test-only'}


@pytest.fixture(autouse=True)
def config(app):
    app.config['PLUGIN_CONFIG'] = {'services': [{'id': 'cad', 'tenantId': 't1',
        'tokenSha256': hashlib.sha256(b'integration-test-only').hexdigest(),
        'projectIds': ['p1'], 'tools': ['cad_get_evidence'], 'maxActiveRuns': 2}],
        'httpTools': [{'name': 'cad_get_evidence', 'version': '1', 'description': 'Evidence',
            'url': 'https://cad.example/tools', 'effect': 'read',
            'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
            'outputSchema': {'type': 'object'}}]}


def space(client, context=None):
    response = client.post(ROOT+'/spaces', headers=HEADERS, json={'context': context or CTX})
    assert response.status_code == 201
    return response.json['id']


@respx.mock
def test_tool_reads_server_token_file_without_exposing_it(app, client, tmp_path):
    token = tmp_path / 'callback.token'
    token.write_text('private-callback-token', encoding='utf-8')
    app.config['PLUGIN_CONFIG']['httpTools'][0]['tokenFile'] = str(token)
    def callback(request):
        assert request.headers['Authorization'] == 'Bearer private-callback-token'
        return httpx.Response(200, json={'contractVersion':'1','status':'succeeded','data':{}})
    respx.post('https://cad.example/tools').mock(side_effect=callback)
    result = client.post(ROOT+'/tools/execute', headers=HEADERS,
        json={'context':CTX,'tool':'cad_get_evidence','arguments':{}})
    assert result.status_code == 200
    assert 'private-callback-token' not in result.text


def test_service_rejects_browser_origin_even_with_bearer(client):
    assert client.get(ROOT+'/capabilities', headers={**HEADERS,'Origin':'http://localhost'}).status_code == 403


@respx.mock
def test_direct_tool_requests_have_bounded_concurrency(app,client):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    entered=threading.Barrier(5)
    release=threading.Event()
    def callback(request):
        entered.wait(timeout=10)
        release.wait(timeout=10)
        return httpx.Response(200,json={'contractVersion':'1','status':'succeeded','data':{}})
    respx.post('https://cad.example/tools').mock(side_effect=callback)
    body={'context':CTX,'tool':'cad_get_evidence','arguments':{}}
    def send():
        return app.test_client().post(ROOT+'/tools/execute',headers=HEADERS,json=body).status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks=[pool.submit(send) for _ in range(4)]
        try:
            entered.wait(timeout=10)
            assert client.post(ROOT+'/tools/execute',headers=HEADERS,json=body).status_code==429
        finally: release.set()
        assert [task.result() for task in tasks]==[200]*4


def test_large_source_metadata_is_rejected(client):
    sid=space(client)
    response=client.put(f'{ROOT}/spaces/{sid}/documents/d1',headers=HEADERS,json={
        'title':'drawing','revision':'r1','chunks':[{'id':'c1','text':'steel','source':{'blob':'x'*20000}}]})
    assert response.status_code==413


def test_cad_images_use_authorized_ocr_without_direct_vision_account(app,client):
    import base64
    import io
    from PIL import Image
    cfg=app.config['PLUGIN_CONFIG']
    cfg['services'][0]['tools'].append('ocr_analyze')
    cfg['httpTools'].append({'name':'ocr_analyze','version':'1','effect':'analyze',
        'transport':'ocr-vision-v1','inputSchema':{'type':'object'}})
    data=io.BytesIO();Image.new('RGB',(12,12),'white').save(data,format='PNG')
    request={'context':CTX,'spaceId':space(client),'requestId':str(uuid.uuid4()),'question':'查看图纸',
        'tools':['cad_get_evidence'],'images':[{'mediaType':'image/png','data':base64.b64encode(data.getvalue()).decode()}]}
    assert client.post(ROOT+'/runs',headers=HEADERS,json=request).status_code==202
    cfg['services'][0]['tools'].remove('ocr_analyze')
    request['requestId']=str(uuid.uuid4())
    assert client.post(ROOT+'/runs',headers=HEADERS,json=request).status_code==503


def test_cancel_queued_run_erases_input_and_sets_completion(app, client):
    sid = space(client)
    response = client.post(ROOT+'/runs', headers=HEADERS, json={'context':CTX,
        'requestId':str(uuid.uuid4()),'spaceId':sid,'question':'private drawing prompt'})
    rid = response.json['id']
    client.post(ROOT+f'/runs/{rid}/cancel', headers=HEADERS)
    from app.plugins.models import AnalysisRun
    with app.app_context():
        row = database.session.get(AnalysisRun, rid)
        assert row.payload == {}
        assert row.completed_at is not None


def test_service_auth_does_not_accept_cookie_or_foreign_project(client):
    assert client.get(ROOT+'/capabilities').status_code == 401
    assert client.get(ROOT+'/capabilities', headers=HEADERS).status_code == 200
    bad = {**CTX, 'project_id': 'p2'}
    assert client.post(ROOT+'/spaces', headers=HEADERS, json={'context': bad}).status_code == 403


def test_temporary_search_replacement_unload_preserves_source(client):
    sid = space(client)
    path = f'{ROOT}/spaces/{sid}'
    source = {'revision': 'r1', 'page': 3, 'coordinateSpace': 'pixels', 'bbox': [1, 2, 3, 4]}
    payload = {'title': '图纸', 'revision': 'r1', 'chunks': [{'id': 'c1', 'text': '筒体钢板厚度12毫米', 'source': source}]}
    assert client.put(path+'/documents/d1', headers=HEADERS, json=payload).status_code == 200
    result = client.post(path+'/search', headers=HEADERS, json={'question': '钢板厚度'}).json
    assert result['results'][0]['source'] == source
    assert result['results'][0]['text'] == '筒体钢板厚度12毫米'
    payload['chunks'][0]['text'] = '法兰孔距200毫米'
    client.put(path+'/documents/d1', headers=HEADERS, json=payload)
    assert not client.post(path+'/search', headers=HEADERS, json={'question': '钢板厚度'}).json['results']
    client.delete(path+'/documents/d1', headers=HEADERS)
    assert not client.post(path+'/search', headers=HEADERS, json={'question': '法兰孔距'}).json['results']


def test_promotion_survives_temporary_space_deletion_and_expiry_is_enforced(app, client):
    sid = space(client)
    path = f'{ROOT}/spaces/{sid}'
    client.put(path+'/documents/d1', headers=HEADERS, json={'title': '图纸', 'revision': 'r1',
        'chunks': [{'id': 'c1', 'text': '重量验算', 'source': {}}]})
    response = client.post(path+'/promote', headers=HEADERS, json={'name': '批准资料', 'requestId': str(uuid.uuid4())})
    assert response.status_code == 201
    persistent = response.json['id']
    client.delete(path, headers=HEADERS)
    assert client.get(f'{ROOT}/spaces/{persistent}/package', headers=HEADERS).json['documents'][0]['chunks'][0]['text'] == '重量验算'
    from app.plugins.models import KnowledgeSpace
    expired = space(client)
    with app.app_context():
        database.session.get(KnowledgeSpace, expired).expires_at = now()-timedelta(seconds=1)
        database.session.commit()
    assert client.get(f'{ROOT}/spaces/{expired}/package', headers=HEADERS).status_code == 404


@respx.mock
def test_http_tool_uses_trusted_context_rejects_unregistered_tool_and_invalid_arguments(client):
    route = respx.post('https://cad.example/tools').mock(return_value=httpx.Response(200,
        json={'contractVersion': '1', 'status': 'succeeded', 'data': {'chunks': []}}))
    body = {'contractVersion': '1', 'context': CTX, 'tool': 'cad_get_evidence', 'arguments': {}}
    response = client.post(ROOT+'/tools/execute', headers=HEADERS, json=body)
    assert response.status_code == 200
    sent = json.loads(route.calls[0].request.content)
    assert sent['context'] == {**CTX, 'service_id': 'cad', 'tenant_id': 't1'}
    body['arguments'] = {'project_id': 'p2'}
    assert client.post(ROOT+'/tools/execute', headers=HEADERS, json=body).status_code == 400
    body['tool'] = 'private_tool'
    assert client.post(ROOT+'/tools/execute', headers=HEADERS, json=body).status_code == 403


def test_runs_idempotency_context_binding_cancellation_and_replay(client):
    sid = space(client)
    body = {'contractVersion': '1', 'requestId': str(uuid.uuid4()), 'context': CTX,
            'spaceId': sid, 'question': '分析图纸', 'tools': []}
    created = client.post(ROOT+'/runs', headers=HEADERS, json=body)
    assert created.status_code == 202
    rid = created.json['id']
    assert client.post(ROOT+'/runs', headers=HEADERS, json=body).json['id'] == rid
    assert client.post(ROOT+'/runs', headers=HEADERS, json={**body, 'question': 'changed'}).status_code == 409
    bad = {**body, 'requestId': str(uuid.uuid4()), 'context': {**CTX, 'revision': 'r2'}}
    assert client.post(ROOT+'/runs', headers=HEADERS, json=bad).status_code == 409
    assert client.post(f'{ROOT}/runs/{rid}/cancel', headers=HEADERS).json['status'] == 'CANCELLED'
    events = client.get(f'{ROOT}/runs/{rid}/events', headers=HEADERS).text
    assert 'event: error' in events and 'CANCELLED' in events


@respx.mock
def test_background_agent_uses_real_tool_loop_and_persists_sse(app,client):
    from app.models import AiProvider,AiAccount
    from app.crypto import encrypt_secret
    from app.plugins.runs import execute_run
    with app.app_context():
        provider=AiProvider(name='test',provider_type='OPENAI_COMPATIBLE',base_url='https://model.example/v1')
        provider.accounts.append(AiAccount(name='a',model='test-model',encrypted_api_key=encrypt_secret('test-only')))
        database.session.add(provider);database.session.commit()
    sid=space(client)
    client.put(f'{ROOT}/spaces/{sid}/documents/d1',headers=HEADERS,json={'title':'图纸','revision':'r1',
        'chunks':[{'id':'c1','text':'钢板厚度12毫米','source':{'page':1}}]})
    def respond(request):
        value=json.loads(request.content)
        assert value['max_tokens']==4096
        names=[t['function']['name'] for t in value['tools']]
        assert 'session_recall' in names and 'recall' not in names
        if not any(m['role']=='tool' for m in value['messages']):
            delta={'tool_calls':[{'index':0,'id':'call-1','function':{'name':'session_recall','arguments':json.dumps({'question':'钢板厚度'})}}]}
        else:
            found=json.loads(next(m['content'] for m in value['messages'] if m['role']=='tool'))
            assert found['results'][0]['source']=={'page':1}
            delta={'content':'钢板厚度为12毫米，待审核。'}
        return httpx.Response(200,text='data: '+json.dumps({'choices':[{'delta':delta}]})+'\n\ndata: [DONE]\n\n')
    respx.post('https://model.example/v1/chat/completions').mock(side_effect=respond)
    run=client.post(ROOT+'/runs',headers=HEADERS,json={'requestId':str(uuid.uuid4()),'context':CTX,'spaceId':sid,'question':'厚度是多少','tools':[]}).json
    execute_run(app,run['id'])
    state=client.get(f"{ROOT}/runs/{run['id']}",headers=HEADERS).json
    assert state['status']=='COMPLETED', state
    assert '12毫米' in state['content']
    stream=client.get(run['eventsUrl'],headers=HEADERS).text
    assert 'event: tool_result' in stream and 'event: delta' in stream and 'event: complete' in stream


def test_service_revocation_and_cross_service_isolation(app,client):
    sid=space(client)
    app.config['PLUGIN_CONFIG']['services'].append({'id':'other','tenantId':'t1','projectIds':['p1'],
        'tokenSha256':hashlib.sha256(b'other').hexdigest(),'tools':[]})
    assert client.get(f'{ROOT}/spaces/{sid}',headers={'Authorization':'Bearer other'}).status_code==404
    app.config['PLUGIN_CONFIG']['services'][0]['projectIds']=[]
    assert client.get(f'{ROOT}/spaces/{sid}',headers=HEADERS).status_code==403
