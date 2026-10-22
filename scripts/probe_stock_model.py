"""Minimal, credential-free diagnostics run inside the stock Core container."""
import json
import os
import time
from agent_core.config import load_config, model_profile
from agent_core.model import OpenAICompatibleClient, ProviderError
from agent_core.security import CoreError

config=load_config('/run/stock/core.json')
service=next(s for s in config['services'] if s['id']=='stock-chat')
profile=model_profile(config,service)
if os.environ.get('STOCK_PROBE_PROXY'):profile['proxyUrl']=os.environ['STOCK_PROBE_PROXY']
for mode in (('text','tools') if not os.environ.get('STOCK_PROBE_MODE') else (os.environ['STOCK_PROBE_MODE'],)):
    started=time.monotonic()
    result={'profile':profile['id'],'model':profile['model'],'mode':mode}
    kwargs={'max_output_tokens':256,'timeout_seconds':15}
    prompt='Reply only OK.'
    if mode=='tools':
        prompt='Call connection_probe with value OK.'
        kwargs.update(tools=[{'type':'function','function':{'name':'connection_probe','description':'Connection verification only.',
            'parameters':{'type':'object','properties':{'value':{'type':'string','enum':['OK']}},'required':['value'],'additionalProperties':False}}}],
            tool_choice={'type':'function','function':{'name':'connection_probe'}})
    try:
        events=list(OpenAICompatibleClient().stream(profile,[{'role':'user','content':prompt}],**kwargs))
        result.update(status='succeeded',textCharacters=sum(len(e.get('content','')) for e in events if e['type']=='delta'),
                      toolCallFrames=sum(e['type']=='tool_call' for e in events))
        if mode=='tools':
            calls={}
            for event in events:
                if event['type']!='tool_call':continue
                call=calls.setdefault(event.get('index',0),{'name':'','arguments':''})
                for field in call:call[field]+=event.get('function',{}).get(field,'') or ''
            try: valid=len(calls)==1 and all(c['name']=='connection_probe' and json.loads(c['arguments'])=={'value':'OK'} for c in calls.values())
            except ValueError:valid=False
            result['validToolCall']=valid
            if not valid:result.update(status='failed',code='MODEL_TOOL_TEST_FAILED')
    except (ProviderError,CoreError) as exc:
        result.update(status='failed',code=getattr(exc,'category',getattr(exc,'code','UNKNOWN')))
    result['elapsedMs']=int((time.monotonic()-started)*1000)
    print(json.dumps(result),flush=True)
