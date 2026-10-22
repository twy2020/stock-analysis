import json
from unittest.mock import patch
from app.agent import stream_agent


def call(name, args, index=0):
    return {'type': 'tool_call', 'index': index, 'id': f'call-{index}',
            'function': {'name': name, 'arguments': json.dumps(args)}}


def test_greeting_does_not_retrieve():
    with patch('app.agent.OpenAICompatibleClient.stream', return_value=iter([{'type': 'delta', 'content': '你好'}])), \
         patch('app.agent.RagClient') as rag:
        events = list(stream_agent(None, None, [{'role': 'user', 'content': '你好'}], 'kb'))
    rag.assert_not_called()
    assert any(e.get('content') == '你好' for e in events)


def test_directory_scoped_recall_time_and_stable_labels():
    prompts = []
    rounds = [
        [call('list_documents', {})],
        [call('recall', {'question': '设计压力', 'documentIds': ['doc-a']})],
        [call('recall', {'question': '工作压力', 'documentIds': ['doc-a']})],
        [call('current_time', {})],
        [{'type': 'delta', 'content': '根据来源 [1][2]'}],
    ]
    def model(*args, **kwargs):
        prompts.append(args[2])
        return iter(rounds.pop(0))
    with patch('app.agent.OpenAICompatibleClient.stream', side_effect=model), patch('app.agent.RagClient') as rag:
        rag.return_value.json.return_value = {'items': [{'documentId': 'doc-a', 'title': '规范'}], 'hasMore': False}
        rag.return_value.retrieve_stream.side_effect = lambda *args: iter([('retrieval', {'queryId': 'q', 'results': [{'passage': '正文'}]})])
        events = list(stream_agent(None, None, [], 'bound-kb'))
        assert all('/bound-kb/' in args.args[0] for args in rag.return_value.retrieve_stream.call_args_list)
        assert rag.return_value.retrieve_stream.call_args.args[1]['documentIds'] == ['doc-a']
    assert [e['payload']['results'][0]['label'] for e in events if e['type'] == 'retrieval'] == [1, 2]
    time_result = json.loads([m for m in prompts[-1] if m['role'] == 'tool'][-1]['content'])
    assert time_result['timezone'] == 'Asia/Shanghai'
    assert '+08:00' in time_result['time']
    completed = [e for e in events if e.get('stage') == 'TOOL_COMPLETED']
    assert len({e['operationId'] for e in completed}) == 4


def test_invalid_tool_arguments_are_returned_to_model_without_execution():
    rounds = [[call('recall', {'question': 'x', 'knowledgeBaseId': 'other'})], [{'type': 'delta', 'content': '参数错误'}]]
    with patch('app.agent.OpenAICompatibleClient.stream', side_effect=lambda *a, **k: iter(rounds.pop(0))), patch('app.agent.RagClient') as rag:
        events = list(stream_agent(None, None, [], 'kb'))
    rag.assert_not_called()
    assert any(e.get('stage') == 'TOOL_FAILED' for e in events)


def test_tool_preamble_archived_and_tool_events_have_correlated_duration():
    rounds = [[{'type': 'delta', 'content': '先查看当前时间。'}, call('current_time', {})],
              [{'type': 'delta', 'content': '现在是下午。'}]]
    with patch('app.agent.OpenAICompatibleClient.stream', side_effect=lambda *a, **k: iter(rounds.pop(0))):
        events = list(stream_agent(None, None, [], 'kb'))
    assert any(e.get('stage') == 'MODEL_NOTE' and e['content'] == '先查看当前时间。' for e in events)
    reset = next(i for i, e in enumerate(events) if e['type'] == 'answer_reset')
    assert ''.join(e['content'] for e in events[reset+1:] if e['type'] == 'delta') == '现在是下午。'
    start = next(e for e in events if e.get('stage') == 'TIME_READING')
    end = next(e for e in events if e.get('stage') == 'TOOL_COMPLETED')
    assert start['operationId'] == end['operationId']
    assert end['status'] == 'COMPLETED' and end['elapsedMs'] >= 0
