import asyncio
import copy
from unittest.mock import patch

import pytest
from app import search_manager as manager
from app.web_research import WebResearchError


@pytest.fixture(autouse=True)
def reset_health():
    manager._health.clear()
    yield
    manager._health.clear()


def test_admin_credentials_are_preserved_and_never_returned(app,client):
    from test_chat import sign_in
    csrf=sign_in(client)
    config=manager.defaults()
    config['providers'][1].update(apiKey='secret-qianfan',enabled=True)
    response=client.put('/api/v1/admin/settings/search-engines',json=config,headers={'X-CSRF-Token':csrf})
    assert response.status_code==200
    assert b'secret-qianfan' not in response.data and b'apiKey' not in response.data
    public=response.json
    assert public['providers'][1]['configured']
    public['providers']=[{k:p[k] for k in ('id','enabled','priority','timeoutSeconds','toolName')} for p in public['providers']]
    assert client.put('/api/v1/admin/settings/search-engines',json=public,headers={'X-CSRF-Token':csrf}).status_code==200
    with app.app_context():assert manager.settings()['providers'][1]['apiKey']=='secret-qianfan'
    public['providers'][1].update(clearKey=True,enabled=False)
    assert client.put('/api/v1/admin/settings/search-engines',json=public,headers={'X-CSRF-Token':csrf}).json['providers'][1]['configured'] is False


def test_reject_unsupported_provider_unknown_settings_and_missing_credentials():
    baseline=manager.defaults()
    config=copy.deepcopy(baseline);config['providers'][3]['enabled']=True
    with pytest.raises(ValueError,match='web_search'):manager.validate(config,baseline)
    config=copy.deepcopy(baseline);config['providers'][1]['enabled']=True
    with pytest.raises(ValueError,match='API Key'):manager.validate(config,baseline)
    config=copy.deepcopy(baseline);config['providers'][1]['endpoint']='http://localhost'
    with pytest.raises(ValueError):manager.validate(config,baseline)
    config=copy.deepcopy(baseline);config['engines']=['bing']*2
    with pytest.raises(ValueError):manager.validate(config,baseline)


def test_failed_provider_falls_back_and_cools_down_without_exposing_secrets(monkeypatch):
    config=manager.defaults();config['providers'][1].update(enabled=True,apiKey='secret')
    calls=[]
    async def native(*args):calls.append('native');raise ValueError('WEB_SEARCH_RATE_LIMITED')
    async def remote(provider,*args):calls.append(provider['id']);return {'results':[{'url':'https://example.com'}]}
    monkeypatch.setattr('app.web_research.aggregate_search',native)
    monkeypatch.setattr(manager,'remote_search',remote)
    result=asyncio.run(manager.search({'query':'q'},{},'/tmp',{},config))
    assert calls==['native','qianfan'] and result['provider']=='qianfan'
    assert result['providerAttempts'][0]['error']=='WEB_SEARCH_RATE_LIMITED'
    calls.clear()
    result=asyncio.run(manager.search({'query':'q'},{},'/tmp',{},config))
    assert calls==['qianfan'] and result['providerAttempts'][0]['status']=='skipped'
    assert 'secret' not in str(result) and 'secret' not in str(manager.view(config))


def test_no_sources_is_failure_and_budget_timeout_is_bounded(monkeypatch):
    config=manager.defaults();provider=config['providers'][0]
    async def empty(*args):return {'results':[]}
    monkeypatch.setattr('app.web_research.aggregate_search',empty)
    with pytest.raises(WebResearchError,match='WEB_SEARCH_NO_SOURCES'):
        asyncio.run(manager.search({'query':'q'},{},'/tmp',{},config))
    async def slow(*args):await asyncio.sleep(.1)
    monkeypatch.setattr('app.web_research.aggregate_search',slow)
    provider['timeoutSeconds']=.01
    with pytest.raises(WebResearchError,match='WEB_TIMEOUT'):
        asyncio.run(manager.provider_search(provider,{'query':'q'},{},'/tmp',{},[]))


def test_slow_native_engine_preserves_already_completed_sources(monkeypatch):
    async def fake(tool,args,*extra):
        if args['_engine']=='bing':
            return {'results':[{'url':'https://example.com','title':'Evidence'}]}
        await asyncio.sleep(2)
    monkeypatch.setattr('app.web_research.call_mcp',fake)
    provider=manager.defaults()['providers'][0];provider['timeoutSeconds']=5
    result=asyncio.run(manager.provider_search(provider,{'query':'q'},{},'/tmp',{},['bing','baidu']))
    assert result['results'][0]['url']=='https://example.com/' and result['partial']
    assert result['searches'][1]['error']=='WEB_TIMEOUT'


def test_source_normalization_bounds_deduplicates_and_excludes_private_links():
    content={'references':[{'url':'http://127.0.0.1','title':'private'},
                            {'url':'https://example.com/report?utm_source=a','title':'Report','summary':'x'*1000}],
             'answer':'[Report](https://example.com/report) [Other](https://example.org)'}
    rows=manager.normalize(content,'qianfan',3)
    assert len(rows)==2 and len(rows[0]['snippet'])==800
    assert rows[0]['engines']==['qianfan'] and rows[0]['read'] is False


def test_remote_mcp_discovers_schema_and_preserves_source_links(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    calls=[]
    @asynccontextmanager
    async def transport(endpoint,**kwargs):
        calls.append(endpoint);yield ('reader','writer',None)
    class Session:
        def __init__(self,*args):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def initialize(self):pass
        async def list_tools(self):return SimpleNamespace(tools=[SimpleNamespace(name='ai_search',inputSchema={'properties':{'query':{'type':'string'}},'required':['query']})])
        async def call_tool(self,name,args):
            calls.append((name,args));return SimpleNamespace(is_error=False,structured_content={'references':[{'url':'https://example.com','title':'Evidence'}]},content=[])
    monkeypatch.setattr('mcp.ClientSession',Session)
    monkeypatch.setattr('mcp.client.streamable_http.streamable_http_client',transport)
    provider=manager.defaults()['providers'][1];provider['apiKey']='secret'
    result=asyncio.run(manager.remote_search(provider,{'query':'robots'},{}))
    assert calls==[manager.CATALOG['qianfan']['endpoint'],('ai_search',{'query':'robots'})]
    assert result['results'][0]['title']=='Evidence' and 'secret' not in str(result)


def test_search_manager_requires_admin_auth(client):
    assert client.get('/api/v1/admin/settings/search-engines').status_code==401
    assert client.post('/api/v1/admin/settings/search-engines/native/test',json={}).status_code==401
