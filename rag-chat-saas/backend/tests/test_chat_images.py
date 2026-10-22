import io
import httpx
import respx
from PIL import Image
from app.extensions import database
from app.models import User, AiProvider, AiAccount, Message, Conversation
from app.crypto import encrypt_secret


def login(client):
    token=client.post('/api/v1/auth/login',json={'username':'admin','password':'Initial-Password-42!'}).json['csrfToken']
    return {'X-CSRF-Token':client.post('/api/v1/auth/change-password',json={'password':'Admin-Password-84!'},headers={'X-CSRF-Token':token}).json['csrfToken']}


def test_admin_can_select_ocr_plugin_without_giving_users_cad_tools(app,client):
    headers=login(client)
    app.config['PLUGIN_CONFIG']={'visionPlugin':{'url':'https://vision.example/v1'}}
    response=client.put('/api/v1/admin/settings/images',headers=headers,
        json={'enabled':True,'backend':'ocr','accountIds':[]})
    assert response.status_code==200
    assert response.json['backend']=='ocr'
    assert client.get('/api/v1/images/capabilities').json['enabled'] is True
    assert client.get('/api/service/v1/capabilities').status_code==401


@respx.mock
def test_ocr_image_description_is_cached_and_owner_scoped(app,client):
    from app.plugins.models import ChatImage
    from app.plugins.images import prepare_ocr_prompt
    from app.plugins.security import PluginError
    import pytest
    headers=login(client)
    app.config['PLUGIN_CONFIG']={'visionPlugin':{'url':'https://vision.example/v1'}}
    client.put('/api/v1/admin/settings/images',headers=headers,json={'enabled':True,'backend':'ocr'})
    submit=respx.post('https://vision.example/v1/jobs').mock(return_value=httpx.Response(202,json={'job_id':'job1','state':'queued'}))
    respx.get('https://vision.example/v1/jobs/job1').mock(return_value=httpx.Response(200,json={'state':'completed'}))
    respx.get('https://vision.example/v1/jobs/job1/result').mock(return_value=httpx.Response(200,json={'result':{'schema_version':1,'summary':'BLUE PLATE'}}))
    with app.app_context():
        user=database.session.query(User).filter_by(username='admin').one()
        row=ChatImage(owner_id=user.id,name='fixture',media_type='image/png',content=b'test')
        database.session.add(row);database.session.commit()
        for _ in range(2):
            prompt=[{'role':'user','content':[{'type':'text','text':'what is it'},{'type':'image_ref','image_id':row.id}]}]
            list(prepare_ocr_prompt(prompt,user))
            assert 'BLUE PLATE' in prompt[0]['content']
        assert submit.call_count==1
        from types import SimpleNamespace
        with pytest.raises(PluginError,match='IMAGE_NOT_FOUND'):
            list(prepare_ocr_prompt([{'role':'user','content':[{'type':'image_ref','image_id':row.id}]}],
                SimpleNamespace(id='another-user')))


def test_images_disabled_by_default_admin_enable_upload_and_context(app,client):
    headers=login(client)
    assert client.post('/api/v1/images',headers=headers).status_code==403
    with app.app_context():
        provider=AiProvider(name='vision',provider_type='OPENAI_COMPATIBLE',base_url='https://example.test/v1')
        account=AiAccount(name='vision',model='vision-model',encrypted_api_key=encrypt_secret('test-only'))
        provider.accounts.append(account);database.session.add(provider);database.session.commit();aid=account.id
    assert client.put('/api/v1/admin/settings/images',headers=headers,json={'enabled':True,'accountIds':[aid]}).status_code==200
    image=io.BytesIO();Image.new('RGB',(10,10),'blue').save(image,format='PNG')
    image.seek(0)
    response=client.post('/api/v1/images',headers=headers,data={'image':(image,'drawing.png')})
    assert response.status_code==201
    iid=response.json['id']
    assert client.get(response.json['url']).mimetype=='image/jpeg'
    c=client.post('/api/v1/conversations',headers=headers,json={'title':'图纸','knowledgeBaseId':'kb'}).json
    run=client.post(f"/api/v1/conversations/{c['id']}/runs",headers=headers,json={'content':'这张图是什么','imageIds':[iid]})
    assert run.status_code==200
    history=client.get(f"/api/v1/conversations/{c['id']}/messages").json
    assert history[0]['images'][0]['id']==iid
    with app.app_context():
        from app.context import build_messages
        conversation=database.session.get(Conversation,c['id'])
        prompt=build_messages(conversation,'这张图是什么',None,run.json['userMessageId'])
        assert prompt[-1]['content'][1]['type']=='image_url'
    other=app.test_client()
    assert other.get(response.json['url']).status_code==401
