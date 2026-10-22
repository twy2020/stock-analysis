"""Map Core execution events into the existing SaaS conversation contract."""
import base64
import json
import re
import time

from flask import current_app
from app.core_client import CoreClient, CoreError
from app.context import compact_conversation
from app.extensions import database
from app.features import rag_enabled
from app.models import ChatRun, RagRequest, now


def _owned_images(prompt, user):
    from app.plugins.models import ChatImage
    for message in prompt:
        if not isinstance(message.get('content'), list): continue
        for index, part in enumerate(message['content']):
            if part.get('type') != 'image_ref': continue
            row = database.session.query(ChatImage).filter_by(id=part.get('image_id'), owner_id=user.id).first()
            if not row:
                raise CoreError('IMAGE_NOT_FOUND')
            message['content'][index] = {'type': 'image_url', 'image_url': {
                'url': f'data:{row.media_type};base64,' + base64.b64encode(row.content).decode()}}


def stream_chat(service, conversation, user, assistant, prompt, reasoning_enabled, web_enabled=False):
    from app.chat import event
    started = time.monotonic()
    answer, reasoning, citations, allowed_labels, usage = '', '', [], set(), {}
    selected_model = assistant.model
    info = {'backend': 'core', 'queries': [], 'processEvents': [], 'stockArtifacts': []}
    data_references = set()
    operation_sources = {}
    stream = None
    def cancelled():
        if not conversation.active_run_id: return False
        return bool(database.session.query(ChatRun.cancel_requested).filter_by(id=conversation.active_run_id).scalar())
    try:
        _owned_images(prompt, user)
        body = {'request_id': conversation.active_run_id or assistant.id, 'messages': prompt,
                'reasoning_enabled': reasoning_enabled,
                'context': {'conversation_id': conversation.id, 'actor_id': user.id,
                            'tenant_id': user.organization_id, 'knowledge_base_id': conversation.knowledge_base_id if rag_enabled() else None}}
        from app.features import web_enabled as web_allowed
        body['web_enabled'] = bool(web_enabled and web_allowed())
        profile = current_app.config.get('AGENT_CORE_MODEL_PROFILE')
        if profile: body['model_profile'] = profile
        stream = CoreClient().stream(body, cancelled)
        complete = False
        for item in stream:
            name = item['type']
            payload = {k: v for k, v in item.items() if k != 'type'}
            if name == 'core_run':
                info['coreRunId'] = item['id']
                assistant.retrieval_json = json.dumps(info, ensure_ascii=False)
                database.session.commit()
                yield event(name, payload)
            elif name == 'delta':
                answer += item.get('content', '')
                yield event(name, payload)
            elif name == 'answer_reset':
                answer = ''
                yield event(name, {})
            elif name == 'model':
                selected_model = item.get('model')
                assistant.model = selected_model
                info['reasoningEnabled'] = item.get('reasoningEnabled')
                yield event(name, payload)
            elif name == 'reasoning':
                reasoning += item.get('content', '')
                info['reasoningEnabled'] = True
                yield event(name, {'enabled': True, 'content': item.get('content', '')})
            elif name == 'progress':
                if payload.get('operationId') in operation_sources:
                    payload['sources']=operation_sources[payload['operationId']]
                payload.update(elapsedMsTotal=int((time.monotonic()-started)*1000), atMs=int(time.time()*1000))
                info['processEvents'].append(payload)
                yield event(name, payload)
            elif name == 'tool_result':
                from app.stock import artifact_from_result, REFERENCE
                artifact = artifact_from_result(item)
                if artifact:
                    data_references.add(artifact['datasetRef'])
                    if not any(a['datasetRef']==artifact['datasetRef'] for a in info['stockArtifacts']):
                        info['stockArtifacts'].append(artifact)
                    assistant.retrieval_json = json.dumps(info,ensure_ascii=False)
                    database.session.commit()
                    yield event('stock_artifact',{'artifact':artifact})
                result = item.get('result',{})
                if 'stock_web_' in str(item.get('tool','')) and result.get('status')=='succeeded':
                    data=result.get('data',{})
                    if data.get('status')=='succeeded':data=data.get('data',{})
                    sources=data.get('sources',[])
                    if sources:
                        operation_sources[item.get('operationId')]=sources
                        known={s['id']:s for s in info.get('webSources',[])}
                        for source in sources:
                            previous=known.get(source['id'],{})
                            known[source['id']]={**source,'read':bool(source.get('read') or previous.get('read'))}
                        info['webSources']=list(known.values())
                if str(item.get('tool','')).startswith(('stock_','mcp__stock__')) and result.get('status')=='succeeded':
                    ref = result.get('data',{}).get('datasetRef')
                    if isinstance(ref,str) and REFERENCE.fullmatch(ref):
                        data_references.add(ref)
                        if not any(a['datasetRef']==ref for a in info['stockArtifacts']):
                            previous = database.session.query(type(assistant)).filter_by(conversation_id=conversation.id,owner_id=user.id,role='ASSISTANT').all()
                            known = next((a for message in previous for a in json.loads(message.retrieval_json or '{}').get('stockArtifacts',[]) if a['datasetRef']==ref),None)
                            if known:
                                info['stockArtifacts'].append(known)
                                yield event('stock_artifact',{'artifact':known})
            elif name == 'retrieval':
                found = item['payload']
                allowed_labels.update(x['label'] for x in found.get('results', []))
                info.update({k: found.get(k) for k in ('queryId','mode','stages','durationMs')})
                info['queries'].append({'queryId': found.get('queryId'), 'resultCount': len(found.get('results', []))})
                service._save_citations(assistant, found)
                database.session.add(RagRequest(organization_id=user.organization_id, user_id=user.id,
                    conversation_id=conversation.id, knowledge_base_id=conversation.knowledge_base_id,
                    status='SUCCEEDED', query_id=found.get('queryId'), result_count=len(found.get('results', [])),
                    latency_ms=found.get('durationMs')))
                database.session.commit()
                citations = service._citation_payload(assistant.id)
                yield event(name, {'citations': citations, 'retrieval': info})
            elif name == 'usage':
                for key in ('prompt_tokens','completion_tokens'):
                    usage[key] = usage.get(key, 0) + (item.get(key) or 0)
            elif name == 'error':
                raise CoreError(item.get('code', 'CORE_EXECUTION_FAILED'))
            elif name == 'complete':
                complete = True
        if not complete: raise CoreError('CORE_STREAM_INTERRUPTED')
        if not answer.strip(): raise CoreError('EMPTY_RESPONSE')
        if any(ref not in data_references for ref in re.findall(r'\[data:([^\]]+)]',answer)):
            raise CoreError('INVALID_DATA_REFERENCE')
        if any(int(x) not in allowed_labels for x in re.findall(r'\[(\d+)](?!\()', answer)):
            raise CoreError('INVALID_CITATION')
        assistant.status, assistant.content = 'COMPLETED', answer
        info['reasoningContent'] = reasoning
        assistant.retrieval_json = json.dumps(info, ensure_ascii=False)
        assistant.prompt_tokens, assistant.completion_tokens = usage.get('prompt_tokens'), usage.get('completion_tokens')
        assistant.latency_ms = int((time.monotonic()-started)*1000)
        terminal={'stage':'PROCESS_COMPLETED','status':'COMPLETED','elapsedMsTotal':assistant.latency_ms,'atMs':int(time.time()*1000)}
        info['processEvents'].append(terminal)
        assistant.retrieval_json = json.dumps(info, ensure_ascii=False)
        conversation.updated_at = now()
        database.session.flush()
        compact_conversation(conversation)
        database.session.commit()
        yield event('progress',terminal)
        yield event('complete', {'messageId': assistant.id, 'content': answer, 'model': assistant.model,
                                'citations': citations, 'stockArtifacts':info['stockArtifacts'], 'reasoningEnabled': info.get('reasoningEnabled'), 'retrieval': info})
    except GeneratorExit:
        if assistant.status == 'COMPLETED': raise
        assistant.status, assistant.content = 'FAILED', answer
        assistant.latency_ms = int((time.monotonic()-started)*1000)
        info['errorCode'] = 'CORE_STREAM_INTERRUPTED'
        info['processEvents'].append({'stage':'PROCESS_FAILED','status':'FAILED','code':info['errorCode'],
                                     'elapsedMsTotal':assistant.latency_ms,'atMs':int(time.time()*1000)})
        info['reasoningContent'] = reasoning
        assistant.retrieval_json = json.dumps(info, ensure_ascii=False)
        database.session.commit()
        raise
    except Exception as exc:
        database.session.rollback()
        assistant.status, assistant.content = 'FAILED', answer
        assistant.model = selected_model
        assistant.prompt_tokens, assistant.completion_tokens = usage.get('prompt_tokens'), usage.get('completion_tokens')
        info['errorCode'] = exc.code if isinstance(exc, CoreError) else 'CORE_INVALID_RESPONSE'
        assistant.latency_ms = int((time.monotonic()-started)*1000)
        terminal={'stage':'PROCESS_FAILED','status':'FAILED','code':info['errorCode'],
                  'elapsedMsTotal':assistant.latency_ms,'atMs':int(time.time()*1000)}
        info['processEvents'].append(terminal)
        info['reasoningContent'] = reasoning
        assistant.retrieval_json = json.dumps(info, ensure_ascii=False)
        database.session.commit()
        yield event('progress',terminal)
        yield event('error', {'code': exc.code if isinstance(exc, CoreError) else 'CORE_INVALID_RESPONSE',
                              'retryable': False, 'backend': 'core'})
    finally:
        if stream: stream.close()
