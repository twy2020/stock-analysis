from __future__ import annotations

import json
import time
from collections.abc import Iterator

import httpx

from app.crypto import cipher
from app.models import AiAccount, AiProvider


class ProviderError(RuntimeError):
    def __init__(self, category: str, retryable: bool, http_status: int | None = None):
        super().__init__(category)
        self.category = category
        self.retryable = retryable
        self.http_status = http_status


def thinking_control(provider_type: str, model: str) -> str | None:
    """Only advertise toggles whose provider wire format is known."""
    name = model.lower()
    if provider_type == 'DEEPSEEK' and name in {'deepseek-flash', 'deepseek-pro'}:
        return 'thinking'
    if provider_type == 'SILICONFLOW' and name.removeprefix('pro/').startswith((
            'deepseek-ai/deepseek-v4', 'deepseek-ai/deepseek-v3.1', 'deepseek-ai/deepseek-v3.2')):
        return 'enable_thinking'
    return None


class OpenAICompatibleClient:
    def stream(self, provider: AiProvider, account: AiAccount, messages: list[dict],
               reasoning_enabled: bool | None = None, tools: list[dict] | None = None,
               tool_choice: str = "auto", max_output_tokens: int | None = None) -> Iterator[dict]:
        from app.audit import context, record
        started=time.perf_counter()
        ctx=context.get()
        details={'provider':provider.name,'account':account.name,'model':account.model,
                 'accountId':account.id,'attempt':ctx.get('attempt',1),'rotated':bool(ctx.get('previousAccount')),
                 'previousAccount':ctx.get('previousAccount'),'rotationReason':ctx.get('rotationReason'),
                 'conversationTitle':ctx.get('conversationTitle'),'reasoningEnabled':reasoning_enabled,
                 'messageCount':len(messages),'firstTokenMs':None,'promptTokens':None,'completionTokens':None}
        rid=record('model','chat.completions','RUNNING',details)
        status='FAILED'
        try:
            for item in self._stream(provider,account,messages,reasoning_enabled,tools,tool_choice,max_output_tokens):
                if details['firstTokenMs'] is None and item['type'] in {'delta','reasoning','tool_call'}:
                    details['firstTokenMs']=int((time.perf_counter()-started)*1000)
                if item['type']=='usage':
                    details.update(promptTokens=item.get('prompt_tokens'),completionTokens=item.get('completion_tokens'))
                yield item
            if details['firstTokenMs'] is None:
                raise ProviderError('EMPTY_RESPONSE', True, 200)
            status='SUCCEEDED'
            details['httpStatus']=200
        except ProviderError as exc:
            details.update(errorCategory=exc.category,retryable=exc.retryable,httpStatus=exc.http_status)
            raise
        except GeneratorExit:
            status='CANCELLED'; details['errorCategory']='CANCELLED'
            raise
        except Exception:
            details['errorCategory']='INTERNAL'
            raise
        finally:
            record('model','chat.completions',status,details,int((time.perf_counter()-started)*1000),record_id=rid)

    def _stream(self, provider: AiProvider, account: AiAccount, messages: list[dict],
                reasoning_enabled=None, tools=None, tool_choice='auto',max_output_tokens=None):
        api_key = cipher().decrypt(account.encrypted_api_key.encode("ascii")).decode("utf-8")
        base_url = (account.base_url or provider.base_url).rstrip("/")
        payload = {"model": account.model, "messages": messages, "stream": True,
                   "stream_options": {"include_usage": True}}
        if max_output_tokens is not None:
            payload['max_tokens']=max(256,min(8192,int(max_output_tokens)))
        if tools:
            payload.update(tools=tools, tool_choice=tool_choice, parallel_tool_calls=False)
        control = thinking_control(provider.provider_type, account.model)
        if reasoning_enabled is not None and control:
            payload[control] = {"type": "enabled" if reasoning_enabled else "disabled"} \
                if control == 'thinking' else reasoning_enabled
        elif reasoning_enabled is True:
            raise ProviderError('THINKING_UNSUPPORTED', False)
        try:
            with httpx.stream("POST", f"{base_url}/chat/completions",
                              headers={"Authorization": f"Bearer {api_key}", "Accept": "text/event-stream"},
                              json=payload, timeout=120) as response:
                if response.status_code >= 400:
                    category = "AUTHENTICATION" if response.status_code in {401, 403} else \
                        "RATE_LIMIT" if response.status_code == 429 else "UPSTREAM"
                    raise ProviderError(category, response.status_code == 429 or response.status_code >= 500, response.status_code)
                usage={}
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    value = json.loads(data)
                    choice = (value.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    for call in delta.get("tool_calls") or []:
                        yield {**call, "type": "tool_call"}
                    if isinstance(delta.get("reasoning_content"), str) and delta["reasoning_content"]:
                        yield {"type": "reasoning", "content": delta["reasoning_content"]}
                    content = delta.get("content")
                    if content:
                        yield {"type": "delta", "content": content}
                    if value.get("usage"):
                        usage.update({k:v for k,v in value['usage'].items() if v is not None})
                    if choice.get('finish_reason')=='length':
                        raise ProviderError('OUTPUT_LIMIT',False,200)
                if usage:
                    yield {'type':'usage',**usage}
        except ProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderError('TIMEOUT', True) from exc
        except httpx.ConnectError as exc:
            raise ProviderError('CONNECTION', True) from exc
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise ProviderError("UPSTREAM", True) from exc
