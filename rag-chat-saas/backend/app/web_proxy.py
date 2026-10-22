"""Administrator-owned routing; proxy secrets never enter agent tool schemas."""
import re
import socket
from urllib.parse import urlsplit, urlunsplit

from flask import has_app_context
from app.crypto import decrypt_json, encrypt_json
from app.extensions import database
from app.models import SystemSetting

KEY = 'stock.web_proxy'
DEFAULTS = {'enabled':False,'mode':'selected','url':'','domains':[
    'bing.com','duckduckgo.com','google.com','yandex.com','yahoo.com','reuters.com']}
ENGINE_HOSTS = {'bing':'bing.com','duckduckgo':'duckduckgo.com','google':'google.com',
                'yandex':'yandex.com','baidu':'baidu.com','sogou':'sogou.com','so360':'so.com'}


def settings():
    if not has_app_context():return {**DEFAULTS}
    row=database.session.get(SystemSetting,KEY)
    return {**DEFAULTS,**(decrypt_json(row.encrypted_value) if row else {})}


def view(value):
    parsed=urlsplit(value['url'])
    endpoint=urlunsplit((parsed.scheme,parsed.netloc.rsplit('@',1)[-1],'','','')) if parsed.hostname else ''
    return {k:value[k] for k in ('enabled','mode','domains')} | {'configured':bool(value['url']),'endpoint':endpoint}


def validate(payload, previous):
    if not isinstance(payload,dict) or set(payload)-{'enabled','mode','url','domains','clear'}:
        raise ValueError('未知代理设置')
    value={**previous}
    for key in ('enabled','clear'):
        if key in payload and type(payload[key]) is not bool:raise ValueError('代理开关格式错误')
    if 'enabled' in payload:value['enabled']=payload['enabled']
    if 'mode' in payload:
        if payload['mode'] not in ('all','selected'):raise ValueError('请选择代理范围')
        value['mode']=payload['mode']
    if 'domains' in payload:
        domains=payload['domains']
        if not isinstance(domains,list) or len(domains)>100:raise ValueError('最多配置100个域名')
        if any(not isinstance(d,str) or not re.fullmatch(r'(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)+',d) for d in domains):
            raise ValueError('请填写域名，不含协议、路径或通配符')
        value['domains']=list(dict.fromkeys(d.lower() for d in domains))
    if 'url' in payload:
        url=payload['url']
        if not isinstance(url,str) or len(url)>2048 or any(c.isspace() for c in url):raise ValueError('代理地址格式错误')
        if url:
            try:
                parsed=urlsplit(url)
                valid=parsed.scheme in ('http','https','socks5') and parsed.hostname and parsed.port is not None and parsed.path in ('','/') and not parsed.query and not parsed.fragment
                if not valid:raise ValueError()
            except ValueError:raise ValueError('请输入带端口的HTTP、HTTPS或SOCKS5代理地址') from None
            value['url']=url
    if payload.get('clear'):value.update(url='',enabled=False)
    if value['enabled'] and not value['url']:raise ValueError('启用代理前请填写地址')
    if value['enabled'] and value['mode']=='selected' and not value['domains']:raise ValueError('请填写需要代理的域名')
    return value


def save(value):
    row=database.session.get(SystemSetting,KEY)
    if row:row.encrypted_value=encrypt_json(value)
    else:database.session.add(SystemSetting(key=KEY,encrypted_value=encrypt_json(value)))
    database.session.commit()


def route(value, url='', engine=None):
    if not value.get('enabled') or not value.get('url'):return None
    host=ENGINE_HOSTS.get(engine,'') if engine else (urlsplit(url).hostname or '').lower()
    if value['mode']=='all' or any(host==d or host.endswith('.'+d) for d in value['domains']):return value['url']
    return None


def scrub(value, proxy):
    if isinstance(value,dict):return {k:scrub(v,proxy) for k,v in value.items() if k.lower() not in ('proxy','proxy_auth','proxyurl')}
    if isinstance(value,list):return [scrub(v,proxy) for v in value]
    if isinstance(value,str) and proxy:return value.replace(proxy,'[configured proxy]')
    return value


def transport_url(url):
    if not url:return url
    parsed=urlsplit(url)
    if parsed.scheme!='socks5':return url
    # Docker's host alias has IPv4/IPv6 records; local SOCKS listeners often
    # accept only the IPv4 route. TLS still uses the destination website's name.
    try:
        address=socket.getaddrinfo(parsed.hostname,parsed.port,socket.AF_INET,socket.SOCK_STREAM)[0][4][0]
    except (OSError,IndexError):return url
    credentials=parsed.netloc.rsplit('@',1)[0]+'@' if '@' in parsed.netloc else ''
    return urlunsplit((parsed.scheme,credentials+address+':'+str(parsed.port),parsed.path,'',''))
