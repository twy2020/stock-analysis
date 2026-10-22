from dataclasses import dataclass
from functools import wraps
import hashlib
import hmac
import re
from flask import current_app, request, g
from pydantic import BaseModel, ConfigDict, Field


class PluginError(ValueError):
    def __init__(self, code, status=400, message=None):
        self.code, self.status, self.message = code, status, message or code
        super().__init__(self.message)


class DrawingContext(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    project_id: str = Field(min_length=1, max_length=160)
    drawing_id: str = Field(min_length=1, max_length=160)
    revision: str = Field(min_length=1, max_length=160)


def config():
    return current_app.config.get('PLUGIN_CONFIG', {})


def authorize_context(service, value):
    try:
        context = DrawingContext.model_validate(value).model_dump()
    except ValueError:
        raise PluginError('INVALID_CONTEXT')
    if context['project_id'] not in service.get('projectIds', []):
        raise PluginError('PROJECT_FORBIDDEN', 403)
    return context


def require_service(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.headers.get('Origin'):
            raise PluginError('SERVICE_BROWSER_ACCESS_FORBIDDEN', 403)
        auth = request.headers.get('Authorization', '')
        token = auth[7:] if auth.startswith('Bearer ') else ''
        digest = hashlib.sha256(token.encode()).hexdigest()
        service = next((s for s in config().get('services', []) if token and
            s.get('enabled', True) and hmac.compare_digest(digest, s.get('tokenSha256', ''))), None)
        if not service:
            raise PluginError('SERVICE_AUTHENTICATION_REQUIRED', 401)
        g.plugin_service = service
        request.max_content_length = 30 * 1024 * 1024
        return view(*args, **kwargs)
    return wrapped
