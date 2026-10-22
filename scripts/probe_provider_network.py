"""No-key network trace: distinguish TCP/TLS failures from model generation."""
import json
import time
import ssl
import certifi
import httpx
from agent_core.config import load_config, model_profile

config=load_config('/run/stock/core.json')
service=next(s for s in config['services'] if s['id']=='stock-chat')
profile=model_profile(config,service)
for attempt,protocol in enumerate(('default','TLSv1_2','default','TLSv1_2')):
    started=time.monotonic();events=[]
    def trace(name,info):
        if name.startswith(('connection.connect_tcp.','connection.start_tls.','http11.receive_response_headers.')):
            events.append({'stage':name,'elapsedMs':int((time.monotonic()-started)*1000)})
    result={'attempt':attempt+1,'tls':protocol}
    try:
        context=ssl.create_default_context(cafile=certifi.where())
        if protocol=='TLSv1_2':context.maximum_version=ssl.TLSVersion.TLSv1_2
        with httpx.Client(timeout=httpx.Timeout(10,connect=5),trust_env=False,follow_redirects=False,verify=context) as client:
            response=client.get(profile['baseUrl'].rstrip('/')+'/models',extensions={'trace':trace})
        result['httpStatus']=response.status_code
    except httpx.HTTPError as exc:result['errorType']=type(exc).__name__
    result['events']=events
    print(json.dumps(result),flush=True)
