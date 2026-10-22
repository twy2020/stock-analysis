"""Bounded LangGraph tool loop. RAG remains a model-independent business service."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import TypedDict
from pydantic import BaseModel, ConfigDict, Field
from langgraph.graph import StateGraph, START, END
from langgraph.config import get_stream_writer
from app.clients.openai_compatible import OpenAICompatibleClient, ProviderError
from app.clients.rag import RagClient, RagClientError
from app.audit import record


class DirectoryArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    offset: int = Field(default=0, ge=0, le=1000000)
    limit: int = Field(default=100, ge=1, le=100)


class RecallArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question: str = Field(min_length=1, max_length=8192)
    documentIds: list[str] = Field(default_factory=list, max_length=50)
    topK: int = Field(default=8, ge=1, le=20)


class TimeArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


ARGUMENTS = {'list_documents': DirectoryArgs, 'recall': RecallArgs, 'current_time': TimeArgs}
DESCRIPTIONS = {
    'list_documents': '分页获取当前知识库已发布文档目录。指定文件检索前先确认 documentId；hasMore=true 时可继续分页。',
    'recall': '检索当前知识库。专业知识、标准和文件相关问题必须调用。documentIds 为空表示全库，否则只检索指定文档。可改写问题再次召回。',
    'current_time': '获取当前真实日期、星期和时间，时区 Asia/Shanghai。',
}
TOOLS = [{'type': 'function', 'function': {'name': name, 'description': DESCRIPTIONS[name],
          'parameters': args.model_json_schema()}} for name, args in ARGUMENTS.items()]


class State(TypedDict):
    messages: list[dict]
    calls: list[dict]
    rounds: int
    used: int


def stream_agent(provider, account, messages, knowledge_base_id, reasoning_enabled=None, runtime=None):
    """Custom streaming preserves native token/SSE timing and existing provider routing."""
    next_label = 1
    def model(state):
        write = get_stream_writer()
        calls = {}
        content, reasoning = '', ''
        speaking = False
        thinking = False
        write({'type': 'progress', 'stage': 'AGENT_THINKING'})
        limits={'max_output_tokens':runtime.max_output_tokens} if runtime is not None else {}
        for item in OpenAICompatibleClient().stream(provider, account, state['messages'],
                reasoning_enabled=reasoning_enabled, tools=runtime.tools if runtime else [t for t in TOOLS if knowledge_base_id or t['function']['name']=='current_time'],
                tool_choice='none' if state['rounds'] >= 6 or state['used'] >= 12 else 'auto', **limits):
            if item['type'] == 'tool_call':
                if not calls:
                    write({'type': 'progress', 'stage': 'TOOL_PREPARING'})
                index = item.get('index', 0)
                call = calls.setdefault(index, {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                if item.get('id'): call['id'] = item['id']
                for key in ('name', 'arguments'):
                    call['function'][key] += (item.get('function') or {}).get(key, '')
                if len(calls) > 12 or len(call['function']['arguments']) > 32768:
                    raise ProviderError('TOOL_LIMIT', False)
            else:
                if item['type'] == 'delta':
                    content += item['content']
                    if not calls and not speaking:
                        speaking = True
                        write({'type': 'progress', 'stage': 'RESPONSE_STREAMING'})
                if item['type'] == 'reasoning':
                    reasoning += item['content']
                    if not thinking:
                        thinking = True
                        write({'type': 'progress', 'stage': 'MODEL_REASONING'})
                if item['type'] != 'delta' or not calls:
                    write(item)
        assistant = {'role': 'assistant', 'content': content or None}
        if reasoning: assistant['reasoning_content'] = reasoning
        if calls:
            if state['rounds'] >= 6 or state['used'] >= 12:
                raise ProviderError('TOOL_LIMIT', False)
            if any(not call['id'] for call in calls.values()): raise ProviderError('INVALID_TOOL_CALL', False)
            assistant['tool_calls'] = list(calls.values())
            if content:
                write({'type': 'progress', 'stage': 'MODEL_NOTE', 'content': content})
            write({'type': 'answer_reset'})
        return {'messages': [*state['messages'], assistant], 'calls': list(calls.values())}

    def execute(state):
        nonlocal next_label
        write = get_stream_writer()
        messages = list(state['messages'])
        used = state['used']
        for call in state['calls']:
            name = call['function']['name']
            started = time.perf_counter()
            operation = {'tool': name, 'operationId': f"{state['rounds']}:{call['id']}"}
            audit_id=record('tool',name,'RUNNING',{'operationId':operation['operationId']})
            used += 1
            try:
                if used > 12: raise ValueError('Tool call limit reached; answer with available information')
                if runtime is not None:
                    write({'type':'progress','stage':'TOOL_EXECUTING',**operation,'status':'RUNNING'})
                    result = runtime.execute(name, call['function']['arguments'], operation)
                    elapsed = int((time.perf_counter()-started)*1000)
                    write({'type':'tool_result', **operation, 'result':result})
                    write({'type':'progress','stage':'TOOL_COMPLETED',**operation,'status':'COMPLETED','elapsedMs':elapsed})
                    record('tool',name,'SUCCEEDED',{'operationId':operation['operationId']},elapsed,record_id=audit_id)
                    encoded = json.dumps(result,ensure_ascii=False)
                    if len(encoded)>64000:
                        encoded=json.dumps({'truncated':True,'preview':encoded[:63000]},ensure_ascii=False)
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':encoded})
                    continue
                if name not in ARGUMENTS: raise ValueError('Unknown tool')
                if name in ('recall','list_documents') and not knowledge_base_id: raise ValueError('RAG_DISABLED')
                args = ARGUMENTS[name].model_validate_json(call['function']['arguments']).model_dump()
                write({'type': 'progress', **operation, 'status': 'RUNNING',
                       'stage': {'list_documents': 'DOCUMENTS_LISTING', 'recall': 'SEARCHING', 'current_time': 'TIME_READING'}[name]})
                if name == 'current_time':
                    now = datetime.now(timezone(timedelta(hours=8)))
                    result = {'time': now.isoformat(), 'timezone': 'Asia/Shanghai', 'weekday': now.isoweekday()}
                elif name == 'list_documents':
                    result = RagClient().json('POST', f'/api/v1/consumer/knowledge-bases/{knowledge_base_id}/tools/execute',
                                              {'operation': name, 'arguments': args})
                else:
                    result = None
                    for event, payload in RagClient().retrieve_stream(
                            f'/api/v1/consumer/knowledge-bases/{knowledge_base_id}/retrieve', {**args, 'mode': 'hybrid'}):
                        if event == 'progress': write({'type': 'progress', **payload, 'parentOperationId': operation['operationId']})
                        elif event == 'retrieval': result = payload
                    if result is None: raise RagClientError()
                    for item in result.get('results', []):
                        item['label'] = next_label
                        next_label += 1
                    write({'type': 'retrieval', 'payload': result})
                write({'type': 'progress', 'stage': 'TOOL_COMPLETED', **operation, 'status': 'COMPLETED',
                       'elapsedMs': int((time.perf_counter() - started) * 1000),
                       'resultCount': len(result.get('results', result.get('items', [])))})
                record('tool',name,'SUCCEEDED',{'resultCount':len(result.get('results',result.get('items',[])))},
                       int((time.perf_counter()-started)*1000),record_id=audit_id)
            except (ValueError, RagClientError) as exc:
                record('tool',name,'FAILED',{'errorCategory':'RAG_UNAVAILABLE' if isinstance(exc,RagClientError) else 'INVALID_ARGUMENTS'},
                       int((time.perf_counter()-started)*1000),record_id=audit_id)
                result = {'error': '工具执行失败，请调整参数或告知用户暂时无法核实。', 'retryable': isinstance(exc, RagClientError)}
                write({'type': 'progress', 'stage': 'TOOL_FAILED', **operation, 'status': 'FAILED',
                       'elapsedMs': int((time.perf_counter() - started) * 1000)})
            # Bound the prompt without changing persisted source text or citation anchors.
            model_result = json.loads(json.dumps(result, ensure_ascii=False))
            for item in model_result.get('results', []):
                if len(item.get('passage', '')) > 6000:
                    item['passage'] = item['passage'][:6000]
                    item['passageTruncated'] = True
            messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(model_result, ensure_ascii=False)})
        if state['rounds'] >= 5 or used >= 12:
            messages.append({'role': 'system', 'content': '工具调用次数已达上限。请根据已有结果回答，信息不足时如实说明，禁止再请求工具。'})
        return {'messages': messages, 'rounds': state['rounds'] + 1, 'used': used, 'calls': []}

    graph = StateGraph(State)
    graph.add_node('model', model)
    graph.add_node('tools', execute)
    graph.add_edge(START, 'model')
    graph.add_conditional_edges('model', lambda s: 'tools' if s['calls'] else END)
    graph.add_edge('tools', 'model')
    yield from graph.compile().stream({'messages': messages, 'calls': [], 'rounds': 0, 'used': 0},
                                     {'recursion_limit': 16}, stream_mode='custom')
