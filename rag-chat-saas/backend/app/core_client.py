"""Server-side Agent Core transport. Never falls back or re-submits a run."""
import json
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from flask import current_app


class CoreError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def enabled():
    return current_app.config.get('AGENT_BACKEND', 'local') == 'core'


class CoreClient:
    def __init__(self):
        self.base = str(current_app.config.get('AGENT_CORE_URL', '')).rstrip('/')
        url = urlsplit(self.base)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise CoreError('CORE_NOT_CONFIGURED')
        try:
            token = Path(current_app.config['AGENT_CORE_TOKEN_FILE']).read_text('utf-8-sig').strip()
        except (KeyError, OSError, TypeError):
            raise CoreError('CORE_NOT_CONFIGURED') from None
        if not token:
            raise CoreError('CORE_NOT_CONFIGURED')
        self.headers = {'Authorization': 'Bearer ' + token}

    def request(self, method, path, body=None):
        try:
            response = httpx.request(method, self.base + path, json=body, headers=self.headers,
                                     timeout=15, follow_redirects=False)
            if response.status_code >= 300:
                if path=='/v1/settings/model':
                    code=response.json().get('code')
                    if code in ('ACTIVE_RUNS_CONFIGURATION_LOCKED','ACTIVE_GATEWAY_CONFIGURATION_LOCKED','CONFIGURATION_CONFLICT','CONFIGURATION_READ_ONLY','CONFIGURATION_FILE_CHANGED','MODEL_FORBIDDEN','MODEL_TOOLS_REQUIRED','MODEL_UNAVAILABLE'):
                        raise CoreError(code)
                raise CoreError('CORE_UNAVAILABLE')
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (httpx.HTTPError, ValueError):
            raise CoreError('CORE_UNAVAILABLE') from None

    def cancel(self, rid):
        return self.request('POST', '/v1/runs/' + quote(rid, safe='') + '/cancel', {})

    def stream(self, body, cancelled):
        if cancelled():
            raise CoreError('CANCELLED')
        result = self.request('POST', '/v1/chat/runs', body)
        rid = result.get('id')
        if not isinstance(rid, str) or not rid:
            raise CoreError('CORE_INVALID_RESPONSE')
        terminal, cursor, retries = False, 0, 0
        started = time.monotonic()
        try:
            yield {'type': 'core_run', 'id': rid}
            while time.monotonic() - started < 600:
                if cancelled():
                    raise CoreError('CANCELLED')
                received = False
                try:
                    headers = {**self.headers, 'Accept': 'text/event-stream', 'Last-Event-ID': str(cursor)}
                    with httpx.stream('GET', self.base + '/v1/runs/' + quote(rid, safe='') + '/events',
                                      headers=headers, timeout=65, follow_redirects=False) as response:
                        if response.status_code != 200:
                            raise CoreError('CORE_UNAVAILABLE')
                        name, seq, data = '', 0, []
                        for line in response.iter_lines():
                            if cancelled():
                                raise CoreError('CANCELLED')
                            if len(line) > 4 * 1024 * 1024:
                                raise CoreError('CORE_EVENT_TOO_LARGE')
                            if line.startswith('event:'): name = line[6:].strip()
                            elif line.startswith('id:'): seq = int(line[3:].strip())
                            elif line.startswith('data:'): data.append(line[5:].strip())
                            elif not line:
                                if data and seq > cursor:
                                    payload = json.loads('\n'.join(data))
                                    if not isinstance(payload, dict): raise ValueError()
                                    cursor, received = seq, True
                                    terminal = name in ('complete', 'error')
                                    yield {**payload, 'type': name}
                                    if terminal: return
                                name, seq, data = '', 0, []
                except httpx.HTTPError:
                    pass  # Only reattach to the same run. POST is never repeated.
                retries = 0 if received else retries + 1
                if retries >= 3:
                    raise CoreError('CORE_STREAM_INTERRUPTED')
                time.sleep(.15)
            raise CoreError('CORE_TIMEOUT')
        except (ValueError, TypeError):
            raise CoreError('CORE_INVALID_RESPONSE') from None
        finally:
            if not terminal:
                try: self.cancel(rid)
                except CoreError: pass


def cancel_chat_run(job):
    """Use the recorded backend ownership, even after deployment settings change."""
    from app.extensions import database
    from app.models import ChatRunEvent
    row = database.session.query(ChatRunEvent).filter_by(run_id=job.id, name='core_run').first()
    if row:
        CoreClient().cancel(row.payload['id'])


def recover_interrupted_runs():
    """Stop remote work before the SaaS dispatcher marks interrupted jobs failed."""
    from app.extensions import database
    from app.models import ChatRun
    for job in database.session.query(ChatRun).filter_by(status='RUNNING').all():
        try:
            cancel_chat_run(job)
        except CoreError as exc:
            # Do not replay a paid request. A user may retry cancellation later.
            current_app.logger.warning('Core cancellation unconfirmed for SaaS run %s: %s', job.id, exc.code)
