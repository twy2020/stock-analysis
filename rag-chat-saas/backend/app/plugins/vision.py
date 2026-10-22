"""OCR vision v1 consumer. Only HTTP; provider configuration stays in OCR."""
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from app.audit import record
from .security import PluginError


def analyze(config, images, text, context, request_id, capability='cad.analysis', cancelled=lambda: False):
    base = config.get('url', '').rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise PluginError('VISION_CONFIGURATION_INVALID', 503)
    try:
        token = (Path(config['tokenFile']).read_text('utf-8-sig').strip()
                 if config.get('tokenFile') else os.getenv(config.get('tokenEnv', ''), ''))
    except OSError:
        raise PluginError('VISION_CREDENTIAL_UNAVAILABLE', 503) from None
    if (config.get('tokenFile') or config.get('tokenEnv')) and not token:
        raise PluginError('VISION_CREDENTIAL_UNAVAILABLE', 503)
    headers = {'Authorization': f'Bearer {token}', 'Idempotency-Key': request_id}
    started = time.monotonic()
    audit = record('tool', 'ocr.vision', 'RUNNING', {'context': context, 'requestId': request_id})
    with httpx.Client(headers=headers, timeout=20, follow_redirects=False) as client:
        def call(method, path, payload=None):
            with client.stream(method, base+path, json=payload) as response:
                if response.status_code not in (200, 202):
                    raise PluginError('VISION_UPSTREAM_ERROR', 502)
                data = bytearray()
                for block in response.iter_bytes():
                    data.extend(block)
                    if len(data)>2*1024*1024: raise PluginError('VISION_RESPONSE_TOO_LARGE', 502)
            value = json.loads(data)
            if not isinstance(value, dict): raise PluginError('VISION_INVALID_RESPONSE', 502)
            return value
        job = None
        try:
            submitted = call('POST', '/jobs', {'schema_version':1, 'capability':capability,
                'images':images, 'text':text[:20000], 'design_data':{}, 'context':context})
            job = submitted.get('job_id')
            if not isinstance(job,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}',job):
                raise PluginError('VISION_INVALID_RESPONSE',502)
            # Construct paths locally; never follow URLs returned by an upstream.
            yield {'type':'progress','stage':'IMAGE_ANALYZING','jobId':job,'status':'RUNNING','elapsedMs':0}
            previous = None
            while True:
                if cancelled() or time.monotonic()-started>240:
                    call('POST', f'/jobs/{job}/cancel', {})
                    raise PluginError('CANCELLED' if cancelled() else 'VISION_TIMEOUT', 408)
                status = call('GET', f'/jobs/{job}')
                state = status.get('state')
                if state == 'completed':
                    result = call('GET', f'/jobs/{job}/result').get('result')
                    if not isinstance(result,dict) or result.get('schema_version')!=1:
                        raise PluginError('VISION_INVALID_RESPONSE',502)
                    record('tool','ocr.vision','SUCCEEDED',{'jobId':job,'context':context},
                        int((time.monotonic()-started)*1000),record_id=audit)
                    yield {'type':'result','jobId':job,'result':result}
                    return
                if state in ('failed','cancelled'):
                    raise PluginError('VISION_FAILED' if state=='failed' else 'CANCELLED',502)
                if state not in ('queued','running','cancel_requested'):
                    raise PluginError('VISION_INVALID_RESPONSE',502)
                if state!=previous:
                    yield {'type':'progress','stage':'IMAGE_ANALYZING','jobId':job,'state':state,
                           'status':'RUNNING','elapsedMs':int((time.monotonic()-started)*1000)}
                    previous=state
                time.sleep(.5)
        except GeneratorExit:
            if job:
                try: call('POST', f'/jobs/{job}/cancel', {})
                except (httpx.HTTPError, ValueError, PluginError): pass
            record('tool','ocr.vision','CANCELLED',{'jobId':job,'context':context},
                int((time.monotonic()-started)*1000),record_id=audit)
            raise
        except (httpx.HTTPError, ValueError, PluginError) as exc:
            code = exc.code if isinstance(exc,PluginError) else 'VISION_UPSTREAM_ERROR'
            record('tool','ocr.vision','FAILED',{'jobId':job,'code':code,'context':context},
                int((time.monotonic()-started)*1000),record_id=audit)
            raise PluginError(code, exc.status if isinstance(exc,PluginError) else 502) from None
