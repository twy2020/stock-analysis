from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from datetime import timedelta
from flask import current_app

from app.clients.openai_compatible import OpenAICompatibleClient, ProviderError, thinking_control
from app.clients.rag import RagClient
from app.context import build_messages, compact_conversation
from app.extensions import database
from app.features import rag_enabled
from app.models import (Conversation, Message, MessageCitation, ProviderRequest,
                        RagRequest, now)
from app.provider_pool import ProviderUnavailable, provider_pool
from app.agent import stream_agent
from app.audit import call_context


def event(name: str, payload: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


class ChatService:
    def stream(self, conversation: Conversation, user, question: str,
               reasoning_enabled: bool | None = None, prepared=None, web_enabled=False) -> Iterator[str]:
        started = time.perf_counter()
        process_events = []
        reasoning_text = ""
        def progress(payload):
            value = {**payload, "elapsedMsTotal": int((time.perf_counter() - started) * 1000),
                     "atMs": int(time.time() * 1000)}
            process_events.append(value)
            return event("progress", value)
        user_message = prepared[0] if prepared else Message(conversation_id=conversation.id, organization_id=user.organization_id,
                               owner_id=user.id, role="USER", content=question, status="COMPLETED")
        assistant = prepared[1] if prepared else Message(conversation_id=conversation.id, organization_id=user.organization_id,
                            owner_id=user.id, role="ASSISTANT", content="", status="STREAMING")
        database.session.add_all([user_message, assistant])
        database.session.commit()
        yield event("message", {"userMessageId": user_message.id, "assistantMessageId": assistant.id})

        retrieval = {"results": []}
        retrieval_info = {"processEvents": process_events, "queries": []}
        citations = []
        prompt = build_messages(conversation, question, None, user_message.id)
        from app.core_client import enabled as core_enabled
        if core_enabled():
            from app.core_chat import stream_chat
            yield from stream_chat(self, conversation, user, assistant, prompt, reasoning_enabled, web_enabled)
            return
        from app.plugins.images import prepare_ocr_prompt
        from app.plugins.security import PluginError
        def image_cancelled():
            if not conversation.active_run_id: return False
            from app.models import ChatRun
            return bool(database.session.query(ChatRun.cancel_requested).filter_by(id=conversation.active_run_id).scalar())
        try:
            with call_context(organization_id=user.organization_id,user_id=user.id,username=user.username,
                              conversation_id=conversation.id,run_id=conversation.active_run_id):
                for item in prepare_ocr_prompt(prompt,user,image_cancelled):
                    yield progress({key:value for key,value in item.items() if key!='type'})
        except PluginError as exc:
            assistant.status='FAILED'
            database.session.commit()
            yield event('error',{'code':exc.code,'retryable':True})
            return
        yield progress({"stage": "ANSWERING"})
        excluded: set[str] = set()
        previous_account = None
        rotation_reason = None
        while True:
            candidates = provider_pool.candidates(excluded)
            if any(isinstance(message.get('content'), list) for message in prompt):
                from app.plugins.images import vision_accounts
                candidates = [(account, provider) for account, provider in candidates if account.id in vision_accounts()]
            if reasoning_enabled is True:
                candidates = [(account, provider) for account, provider in candidates
                              if thinking_control(provider.provider_type, account.model)]
            if not candidates:
                assistant.status = "FAILED"
                database.session.commit()
                yield event("error", {"code": "MODEL_UNAVAILABLE", "retryable": True})
                return
            try:
                account, provider = provider_pool.select(candidates)
            except ProviderUnavailable:
                continue
            excluded.add(account.id)
            known_reasoning = bool(re.match(r"^(deepseek-reasoner|o1(?:-|$)|o3(?:-|$)|o4-mini(?:-|$))",
                                            account.model, re.IGNORECASE))
            actual_reasoning = reasoning_enabled if thinking_control(provider.provider_type, account.model) \
                else True if known_reasoning else None
            yield event("model", {"model": account.model,
                                  "reasoningEnabled": actual_reasoning})
            provider_record = ProviderRequest(account_id=account.id, user_id=user.id,
                                              conversation_id=conversation.id, status="RUNNING")
            database.session.add(provider_record)
            database.session.commit()
            answer = ""
            generated = False
            invalid_labels = []
            usage: dict = {}
            provider_started = time.perf_counter()
            try:
                with call_context(organization_id=user.organization_id, user_id=user.id, username=user.username,
                        conversation_id=conversation.id, run_id=conversation.active_run_id,
                        conversationTitle=conversation.title, attempt=len(excluded),
                        previousAccount=previous_account, rotationReason=rotation_reason), provider_pool.acquire(account):
                    options = {'reasoning_enabled': reasoning_enabled} if reasoning_enabled is not None else {}
                    for item in stream_agent(provider, account, prompt, conversation.knowledge_base_id if rag_enabled() else None, **options):
                        if item["type"] == "delta":
                            answer += item["content"]
                            yield event("delta", {"content": item["content"]})
                        elif item['type'] == 'answer_reset':
                            answer = ''
                            yield event('answer_reset', {})
                        elif item["type"] == "reasoning":
                            actual_reasoning = True
                            reasoning_text += item.get("content", "")
                            yield event("reasoning", {"enabled": True, "content": item.get("content", "")})
                        elif item['type'] == 'progress':
                            yield progress({key: value for key, value in item.items() if key != 'type'})
                        elif item['type'] == 'retrieval':
                            found = item['payload']
                            retrieval['results'].extend(found.get('results', []))
                            stages = found.get('stages', [])
                            retrieval_info.update(queryId=found.get('queryId'), mode=found.get('mode'), stages=stages,
                                durationMs=found.get('durationMs'),
                                embeddingModel=next((s.get('embeddingModel') for s in stages if s.get('embeddingModel')), None),
                                rerankModel=next((s.get('rerankModel') for s in stages if s.get('rerankModel')), None))
                            retrieval_info['queries'].append({'queryId': found.get('queryId'), 'resultCount': len(found.get('results', []))})
                            database.session.add(RagRequest(organization_id=user.organization_id, user_id=user.id,
                                conversation_id=conversation.id, knowledge_base_id=conversation.knowledge_base_id,
                                status='SUCCEEDED', query_id=found.get('queryId'), result_count=len(found.get('results', [])),
                                latency_ms=found.get('durationMs')))
                            self._save_citations(assistant, found)
                            assistant.retrieval_json = json.dumps(retrieval_info, ensure_ascii=True)
                            database.session.commit()
                            citations = self._citation_payload(assistant.id)
                            yield event('retrieval', {'citations': citations, 'retrieval': retrieval_info})
                        elif item['type'] == 'usage':
                            for key in ('prompt_tokens', 'completion_tokens'):
                                usage[key] = usage.get(key, 0) + (item.get(key) or 0)
                generated = True
                if not answer.strip():
                    raise ProviderError('EMPTY_RESPONSE', True)
                labels = {int(value) for value in re.findall(r"\[(\d+)]", answer)}
                invalid_labels = sorted(label for label in labels if label < 1 or label > len(retrieval["results"]))
                if invalid_labels:
                    raise ProviderError("INVALID_CITATION", False)
                assistant.content = answer
                yield progress({'stage': 'PROCESS_COMPLETED', 'status': 'COMPLETED'})
                retrieval_info['reasoningEnabled'] = actual_reasoning
                retrieval_info['reasoningContent'] = reasoning_text
                assistant.retrieval_json = json.dumps(retrieval_info, ensure_ascii=True)
                assistant.status = "COMPLETED"
                assistant.model = account.model
                assistant.prompt_tokens = usage.get("prompt_tokens")
                assistant.completion_tokens = usage.get("completion_tokens")
                assistant.latency_ms = int((time.perf_counter() - started) * 1000)
                provider_record.status = "SUCCEEDED"
                provider_record.latency_ms = int((time.perf_counter() - provider_started) * 1000)
                provider_record.prompt_tokens = usage.get("prompt_tokens")
                provider_record.completion_tokens = usage.get("completion_tokens")
                conversation.updated_at = now()
                database.session.flush()
                compact_conversation(conversation)
                database.session.commit()
                yield event("complete", {"messageId": assistant.id, "content": answer,
                                         "model": account.model, "citations": citations,
                                         "reasoningEnabled": actual_reasoning,
                                         "retrieval": retrieval_info})
                return
            except (ProviderError, ProviderUnavailable) as exc:
                retryable = isinstance(exc, ProviderUnavailable) or exc.retryable
                provider_record.status = "FAILED"
                provider_record.error_category = "CONCURRENCY" if isinstance(exc, ProviderUnavailable) else exc.category
                provider_record.latency_ms = int((time.perf_counter() - provider_started) * 1000)
                if isinstance(exc, ProviderError) and exc.category == "AUTHENTICATION":
                    account.status = "DISABLED"
                    retryable = True  # Disable this credential and try the next eligible account.
                elif retryable:
                    account.cooldown_until = now() + timedelta(seconds=30)
                if answer or citations:
                    assistant.content = answer
                    assistant.status = "FAILED"
                    database.session.commit()
                    yield event("error", {"code": "INVALID_CITATION" if invalid_labels else "MODEL_STREAM_INTERRUPTED", "retryable": retryable,
                        "errorCategory": provider_record.error_category, "generationCompleted": generated,
                        "sourceCount": len(retrieval['results']), "invalidLabels": invalid_labels,
                        "provider": provider.name, "account": account.name, "model": account.model})
                    return
                database.session.commit()
                if not retryable:
                    assistant.status = "FAILED"
                    database.session.commit()
                    yield event("error", {"code": "INVALID_MODEL_RESPONSE", "retryable": False,
                        "errorCategory": provider_record.error_category, "generationCompleted": generated,
                        "sourceCount": len(retrieval['results']), "provider": provider.name,
                        "account": account.name, "model": account.model})
                    return
                yield progress({'stage': 'RETRYING'})
                previous_account = account.name
                rotation_reason = provider_record.error_category
            except GeneratorExit:
                provider_record.status = "FAILED"
                provider_record.error_category = "STREAM_INTERRUPTED"
                assistant.status = "FAILED"
                assistant.content = answer
                database.session.commit()
                raise
            except Exception as exc:
                current_app.logger.exception("Answer stream failed")
                provider_record.status = "FAILED"
                assistant.status = "FAILED"
                assistant.content = answer
                database.session.commit()
                yield event("error", {"code": "MODEL_STREAM_INTERRUPTED", "retryable": True,
                    "errorCategory": "INTERNAL", "exceptionType": type(exc).__name__, "generationCompleted": generated,
                    "provider": provider.name, "account": account.name, "model": account.model})
                return

    def _save_citations(self, message: Message, retrieval: dict) -> None:
        query_id = retrieval["queryId"]
        for label, item in enumerate(retrieval["results"], 1):
            document = item["document"]
            page = item.get("page") or {}
            database.session.add(MessageCitation(
                message_id=message.id, label=item.get('label', label), query_id=query_id, citation_id=item["citationId"],
                document_id=document["id"], document_version_id=document["versionId"],
                title=document["title"], file_name=document["fileName"], media_type=document["mediaType"],
                page_start=page.get("start"), page_end=page.get("end"), passage=item["passage"],
                anchor_json=json.dumps(page.get("anchor") or {}, ensure_ascii=True),
                retrieval_score=item.get("retrievalScore"), rerank_score=item.get("rerankScore"),
                retrieval_mode=item.get("retrievalMode", retrieval.get("mode", "hybrid"))))

    def _citation_payload(self, message_id: str) -> list[dict]:
        rows = database.session.query(MessageCitation).filter_by(message_id=message_id).order_by(
            MessageCitation.label).all()
        return [{"label": row.label, "queryId": row.query_id, "citationId": row.citation_id,
                 "title": row.title, "fileName": row.file_name, "pageStart": row.page_start,
                 "pageEnd": row.page_end, "passage": row.passage,
                 "retrievalScore": row.retrieval_score, "rerankScore": row.rerank_score,
                 "retrievalMode": row.retrieval_mode} for row in rows]
