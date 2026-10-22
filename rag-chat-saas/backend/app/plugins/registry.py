"""Versioned capability boundary; no imports from tool-serving projects."""
import json
import os
import time
import uuid
import threading
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from jsonschema import Draft202012Validator, ValidationError, SchemaError
from app.audit import record
from .security import config, PluginError

_http_slots = threading.BoundedSemaphore(4)


def catalog(service, agent=False):
    allowed = set(service.get('tools', []))
    tools = {}
    for entry in config().get('httpTools', []):
        name = entry.get('name', '')
        if name not in allowed or (agent and entry.get('effect') == 'write'):
            continue
        if name in tools or not name or entry.get('version') != '1':
            raise PluginError('INVALID_PLUGIN_CONFIGURATION', 503)
        tools[name] = entry
    return tools


def validate(schema, value):
    try:
        # Remote schema resolution is deliberately not available to plugins.
        if '"$ref"' in json.dumps(schema):
            raise PluginError('SCHEMA_REFERENCES_UNSUPPORTED')
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)
    except (ValidationError, SchemaError, TypeError):
        raise PluginError('SCHEMA_VALIDATION_FAILED')


def execute(service, context, name, arguments, request_id=None, agent=False):
    if not _http_slots.acquire(blocking=False):
        raise PluginError('TOOL_CONCURRENCY_LIMIT',429)
    try:
        return _execute(service, context, name, arguments, request_id, agent)
    finally:
        _http_slots.release()


def _execute(service, context, name, arguments, request_id=None, agent=False):
    entry = catalog(service, agent).get(name)
    if entry is None:
        raise PluginError('TOOL_FORBIDDEN', 403)
    if entry.get('transport')=='ocr-vision-v1':
        raise PluginError('VISION_REQUIRES_ANALYSIS_RUN', 400)
    if not isinstance(arguments, dict):
        raise PluginError('INVALID_ARGUMENTS')
    validate(entry.get('inputSchema', {'type': 'object'}), arguments)
    url = entry.get('url', '')
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise PluginError('INVALID_PLUGIN_CONFIGURATION', 503)
    started = time.perf_counter()
    identity = {**context, 'service_id': service['id'], 'tenant_id': service['tenantId']}
    rid = str(request_id or uuid.uuid4())
    details = {'plugin': name, 'requestId': rid, **identity}
    audit_id = record('tool', name, 'RUNNING', details)
    try:
        try:
            token = (Path(entry['tokenFile']).read_text(encoding='utf-8-sig').strip()
                     if entry.get('tokenFile') else os.getenv(entry.get('tokenEnv', ''), ''))
        except OSError:
            raise PluginError('PLUGIN_CREDENTIAL_UNAVAILABLE', 503) from None
        if (entry.get('tokenEnv') or entry.get('tokenFile')) and not token:
            raise PluginError('PLUGIN_CREDENTIAL_UNAVAILABLE', 503)
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        with httpx.stream('POST', url, headers=headers, follow_redirects=False,
                timeout=min(120, max(1, entry.get('timeoutSeconds', 60))),
                json={'contractVersion': '1', 'requestId': rid, 'context': identity,
                      'tool': name, 'arguments': arguments}) as response:
            if response.status_code != 200:
                raise PluginError('TOOL_UPSTREAM_ERROR', 502)
            content = bytearray()
            for block in response.iter_bytes():
                content.extend(block)
                if len(content) > 2 * 1024 * 1024:
                    raise PluginError('TOOL_RESPONSE_TOO_LARGE', 502)
        value = json.loads(content)
        if not isinstance(value, dict) or value.get('contractVersion') != '1' or value.get('status') != 'succeeded':
            raise PluginError('TOOL_EXECUTION_FAILED', 502)
        validate(entry.get('outputSchema', {'type': 'object'}), value)
        record('tool', name, 'SUCCEEDED', details, int((time.perf_counter()-started)*1000), record_id=audit_id)
        return value
    except (httpx.HTTPError, ValueError, PluginError) as exc:
        code = exc.code if isinstance(exc, PluginError) else 'TOOL_UPSTREAM_ERROR'
        record('tool', name, 'FAILED', {**details, 'errorCategory': code},
               int((time.perf_counter()-started)*1000), record_id=audit_id)
        raise PluginError(code, exc.status if isinstance(exc, PluginError) else 502) from None
