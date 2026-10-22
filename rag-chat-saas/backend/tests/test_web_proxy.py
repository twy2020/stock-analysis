import asyncio
import json
from unittest.mock import patch,MagicMock
import pytest
from app.web_proxy import DEFAULTS,validate,route,view,scrub


def test_validation_routing_and_redaction():
    proxy='socks5://user:secret@host.docker.internal:10808'
    value=validate({'url':proxy,'enabled':True,'domains':['Yahoo.COM']},DEFAULTS)
    assert route(value,'https://finance.yahoo.com/quote/')==proxy
    assert route(value,'https://fake-yahoo.com') is None
    assert route(value,engine='baidu') is None
    value['domains']=['bing.com']
    assert route(value,engine='bing')==proxy
    assert route({**value,'enabled':False},engine='bing') is None
    assert 'secret' not in json.dumps(view(value))
    assert scrub({'proxy':proxy,'content':proxy},proxy)=={'content':'[configured proxy]'}
    assert validate({'url':''},value)['url']==proxy
    assert validate({'clear':True},value)['enabled'] is False
    for payload in ({'url':'file:///tmp/x'},{'url':'http://host:99999'}, {'url':'http://host:7890/path'},
                    {'enabled':True},{'domains':['*.bing.com']},{'domains':['https://bing.com']}):
        with pytest.raises(ValueError):validate(payload,DEFAULTS)


def test_socks_transport_uses_ipv4_without_changing_saved_policy():
    from app.web_proxy import transport_url
    url='socks5://user:secret@host.docker.internal:10808'
    with patch('app.web_proxy.socket.getaddrinfo',return_value=[(2,1,6,'',('192.168.65.254',10808))]):
        assert transport_url(url)=='socks5://user:secret@192.168.65.254:10808'
        assert transport_url('https://proxy.example.com:7890')=='https://proxy.example.com:7890'


def test_admin_proxy_is_encrypted_and_not_returned_to_client(app,client):
    from test_chat import sign_in
    from app.models import SystemSetting
    from app.extensions import database
    from app.web_proxy import KEY,settings
    assert client.get('/api/v1/admin/settings/web-proxy').status_code==401
    csrf=sign_in(client)
    headers={'X-CSRF-Token':csrf}
    result=client.put('/api/v1/admin/settings/web-proxy',json={'enabled':True,'url':'http://user:secret@host.docker.internal:7890'},headers=headers)
    assert result.status_code==200 and result.json['configured']
    assert 'secret' not in result.get_data(as_text=True)
    with app.app_context():
        assert 'secret' not in database.session.get(SystemSetting,KEY).encrypted_value
        assert settings()['url'].startswith('http://user:secret@')
    client.put('/api/v1/admin/settings/web-proxy',json={'enabled':False},headers=headers)
    assert client.get('/api/v1/admin/settings/features').json['webEnabled'] is False
    response=MagicMock(status_code=200)
    with patch('app.api.admin.httpx.Client') as factory:
        factory.return_value.__enter__.return_value.stream.return_value.__enter__.return_value=response
        assert client.post('/api/v1/admin/settings/web-proxy/test',json={},headers=headers).json['ok']
        assert factory.call_args.kwargs['trust_env'] is False


def test_concurrent_search_routes_only_selected_engines(monkeypatch):
    from app.web_research import aggregate_search
    calls=[]
    async def fake(tool,args,*rest):
        calls.append(args)
        return {'results':[]}
    monkeypatch.setattr('app.web_research.call_mcp',fake)
    value={**DEFAULTS,'enabled':True,'url':'http://host.docker.internal:7890','domains':['bing.com']}
    asyncio.run(aggregate_search({'query':'test','engines':['bing','baidu']},{},'/tmp',value))
    assert calls[0]['_proxy']==value['url']
    assert '_proxy' not in calls[1]
