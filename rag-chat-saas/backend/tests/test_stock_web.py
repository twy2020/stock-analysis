import socket
import asyncio
from unittest.mock import patch
import pytest
from app.extensions import database
from app.features import save, settings
from app.models import Conversation, ChatRun, User
from app.chat_jobs import enqueue
from app.web_research import public_url, bounded_result, resolve_search_redirect, web_error


def test_all_failed_engines_preserve_rate_limit_and_attribution(monkeypatch):
    from app.web_research import aggregate_search,WebResearchError
    async def fail(*args):raise ValueError('WEB_SEARCH_RATE_LIMITED')
    monkeypatch.setattr('app.web_research.call_mcp',fail)
    with pytest.raises(WebResearchError) as caught:
        asyncio.run(aggregate_search({'query':'robotics'},{},'/tmp'))
    assert str(caught.value)=='WEB_SEARCH_RATE_LIMITED'
    assert {s['engine'] for s in caught.value.details['searches']}=={'bing','so360','baidu'}
    assert caught.value.details['retryable'] is False


def test_configured_proxy_adds_duckduckgo_to_default_aggregate(monkeypatch):
    from app.web_research import aggregate_search
    calls=[]
    async def fake(tool,args,*extra):
        calls.append(args)
        return {'results':[{'title':'Source','url':'https://example.com'}]}
    monkeypatch.setattr('app.web_research.call_mcp',fake)
    proxy={'enabled':True,'mode':'selected','url':'socks5://proxy.example:10808','domains':['duckduckgo.com']}
    result=asyncio.run(aggregate_search({'query':'robotics'},{},'/tmp',proxy))
    assert result['engines']==['duckduckgo','bing','baidu']
    assert next(c for c in calls if c['_engine']=='duckduckgo')['_proxy']==proxy['url']
    assert '_proxy' not in next(c for c in calls if c['_engine']=='baidu')


def test_batch_search_overlaps_deduplicates_and_survives_failed_engine(monkeypatch):
    from app.web_research import aggregate_search
    active=0
    peak=0
    async def fake(tool,args,scope,base):
        nonlocal active,peak
        active+=1;peak=max(peak,active)
        await asyncio.sleep(.02)
        active-=1
        if args['_engine']=='baidu':raise ValueError('WEB_SOURCE_UNAVAILABLE')
        return {'results':[{'title':'Official','url':'https://example.com/report?utm_source='+args['_engine'],'snippet':'summary'}]}
    monkeypatch.setattr('app.web_research.call_mcp',fake)
    result=asyncio.run(aggregate_search({'queries':['one','two'],'engines':['bing','so360','baidu'],'maxResults':3},{},'/tmp'))
    assert 1<peak<=4
    assert result['partial'] and len(result['searches'])==6
    assert len(result['results'])==1
    assert result['results'][0]['engines']==['bing','so360']
    assert result['results'][0]['queries']==['one','two']


def test_batch_schema_allows_queries_and_rejects_unbounded_jobs():
    from jsonschema import validate,ValidationError
    from app.web_contract import TOOLS
    schema=TOOLS[0]['inputSchema']
    validate({'queries':['one','two'],'engines':['bing','so360']},schema)
    validate({'query':'legacy'},schema)
    for args in ({},{'queries':['a','b','c','d']},{'query':'a','engines':['shell']}):
        with pytest.raises(ValidationError):validate(args,schema)


def test_web_sources_drop_ads_and_unsafe_urls():
    from app.web_research import source_record
    for url in ('https://duckduckgo.com/y.js?ad_domain=test.com','https://www.bing.com/aclick?x=1',
                'javascript:alert(1)','http://127.0.0.1/','http://localhost/report'):
        assert source_record(url) is None
    assert source_record('https://finance.yahoo.com/quote/688836.SS/')['domain']=='finance.yahoo.com'


def test_feature_save_keeps_rag_when_only_web_is_changed(app, client):
    from test_chat import sign_in
    csrf=sign_in(client)
    result=client.put('/api/v1/admin/settings/features',json={'webEnabled':True},headers={'X-CSRF-Token':csrf})
    assert result.status_code==200 and result.json=={'ragEnabled':True,'webEnabled':True}
    assert client.put('/api/v1/admin/settings/features',json={'webEnabled':'true'},headers={'X-CSRF-Token':csrf}).status_code==400


def test_web_opt_in_is_validated_before_claiming_conversation(app):
    with app.app_context():
        user=database.session.query(User).first()
        conversation=Conversation(organization_id=user.organization_id,owner_id=user.id,title='web')
        database.session.add(conversation);database.session.commit()
        with pytest.raises(ValueError):enqueue(conversation,user,{'content':'search','webEnabled':True})
        assert conversation.active_run_id is None
        save({'ragEnabled':False,'webEnabled':True});app.config['AGENT_BACKEND']='core'
        job=enqueue(conversation,user,{'content':'search','webEnabled':True})
        assert job.web_enabled is True


def test_callback_checks_admin_run_and_conversation_ownership(app, client, tmp_path, monkeypatch):
    token=tmp_path/'engine.token';token.write_text('private-web-test')
    app.config['STOCK_ENGINE_TOKEN_FILE']=str(token)
    with app.app_context():
        save({'ragEnabled':False,'webEnabled':True})
        user=database.session.query(User).first()
        c=Conversation(organization_id=user.organization_id,owner_id=user.id,title='web')
        database.session.add(c);database.session.flush()
        job=ChatRun(id='web-test',conversation_id=c.id,owner_id=user.id,user_message_id='q',assistant_message_id='a',status='RUNNING',web_enabled=True)
        database.session.add(job);c.active_run_id=job.id;database.session.commit()
        body={'tool':'stock_web_fetch','arguments':{'url':'https://example.com'},
              'context':{'actor_id':user.id,'tenant_id':user.organization_id,'conversation_id':c.id}}
    monkeypatch.setattr('app.api.web_research.execute',lambda *args:{'source':'Dhole','result':{'content':'verified fixture'}})
    headers={'Authorization':'Bearer private-web-test'}
    assert client.post('/api/internal/stock-web/execute',json=body).status_code==401
    assert client.post('/api/internal/stock-web/execute',json=body,headers=headers).json['status']=='succeeded'
    assert client.post('/api/internal/stock-web/execute',json={**body,'arguments':{'url':'https://example.com','method':'POST'}},headers=headers).status_code==400
    with app.app_context():
        database.session.get(ChatRun,'web-test').web_enabled=False;database.session.commit()
    assert client.post('/api/internal/stock-web/execute',json=body,headers=headers).status_code==403
    with app.app_context():save({'ragEnabled':False,'webEnabled':False})
    assert client.post('/api/internal/stock-web/execute',json=body,headers=headers).json['code']=='WEB_DISABLED'


def test_public_url_rejects_credentials_private_and_mixed_dns():
    for url in ('file:///data/stock.db','https://user:secret@example.com','http://example.com:8000'):
        with pytest.raises(ValueError):public_url(url)
    public=(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))
    private=(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))
    with patch('app.web_research.socket.getaddrinfo',return_value=[public,private]):
        with pytest.raises(ValueError):public_url('https://example.com')
    with patch('app.web_research.socket.getaddrinfo',return_value=[public]):
        assert public_url('https://example.com')=='https://example.com'


def test_web_content_is_bounded_and_marks_adapter_truncation():
    result=bounded_result({'content':'中文'*40000,'other':'中文'*40000,'url':'https://example.com','next_offset':4000})
    assert result['adapterTruncated'] is True and result['next_offset']==4000
    import json
    assert len(json.dumps(result,ensure_ascii=False).encode())<18000


def test_search_redirect_reads_refresh_without_running_javascript():
    from unittest.mock import MagicMock
    response=MagicMock(status_code=200)
    response.iter_bytes.return_value=[b'<script>doNotRun()</script><meta http-equiv="refresh" content="0;URL=\'https://quotes.sina.cn/stock\'">']
    client=MagicMock();client.stream.return_value.__enter__.return_value=response
    with patch('httpx.Client') as factory,patch('app.web_research.public_url',side_effect=lambda url:url) as validate:
        factory.return_value.__enter__.return_value=client
        assert resolve_search_redirect('https://www.so.com/link?m=encoded')=='https://quotes.sina.cn/stock'
        validate.assert_any_call('https://quotes.sina.cn/stock')
    assert resolve_search_redirect('https://example.com')=='https://example.com'


def test_search_redirect_does_not_follow_private_destinations():
    from unittest.mock import MagicMock
    response=MagicMock(status_code=302,headers={'location':'http://127.0.0.1/internal'})
    client=MagicMock();client.stream.return_value.__enter__.return_value=response
    with patch('httpx.Client') as factory,patch('app.web_research.public_url',side_effect=['https://www.so.com/link?m=x',ValueError('PRIVATE_WEB_URL_FORBIDDEN')]):
        factory.return_value.__enter__.return_value=client
        with pytest.raises(ValueError,match='PRIVATE_WEB_URL_FORBIDDEN'):
            resolve_search_redirect('https://www.so.com/link?m=x')
        assert client.stream.call_count==1


def test_mcp_exception_groups_preserve_safe_failure_codes():
    assert web_error(ExceptionGroup('stdio',[ExceptionGroup('session',[ValueError('WEB_SOURCE_UNAVAILABLE')])]))=='WEB_SOURCE_UNAVAILABLE'
    assert web_error(ExceptionGroup('timeout',[TimeoutError()]))=='WEB_TIMEOUT'
    assert web_error(ExceptionGroup('secret',[ValueError('private upstream content')]))=='WEB_RESEARCH_UNAVAILABLE'
