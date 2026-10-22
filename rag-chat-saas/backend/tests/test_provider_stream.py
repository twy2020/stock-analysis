import json
import httpx
import pytest
import respx
from app.models import AiProvider, AiAccount
from app.crypto import encrypt_secret
from app.extensions import database
from app.clients.openai_compatible import OpenAICompatibleClient, ProviderError


@respx.mock
def test_cumulative_usage_is_reported_once_and_reasoning_is_separate(app):
    frames=[{'choices':[{'delta':{'reasoning_content':'internal'}}], 'usage':{'completion_tokens':1}},
            {'choices':[{'delta':{'content':'final'}}], 'usage':{'completion_tokens':2}},
            {'choices':[{'delta':{},'finish_reason':'stop'}], 'usage':{'completion_tokens':2,'prompt_tokens':10}}]
    respx.post('https://model.example/v1/chat/completions').mock(return_value=httpx.Response(200,
        text=''.join('data: '+json.dumps(f)+'\n\n' for f in frames)+'data: [DONE]\n\n'))
    with app.app_context():
        provider=AiProvider(name='test',provider_type='SILICONFLOW',base_url='https://model.example/v1')
        account=AiAccount(name='test',model='deepseek-ai/DeepSeek-V4-Flash',encrypted_api_key=encrypt_secret('test'))
        provider.accounts.append(account);database.session.add(provider);database.session.commit()
        items=list(OpenAICompatibleClient().stream(provider,account,[{'role':'user','content':'hi'}],reasoning_enabled=False))
    assert [i['content'] for i in items if i['type']=='delta']==['final']
    assert [i['content'] for i in items if i['type']=='reasoning']==['internal']
    assert [i for i in items if i['type']=='usage']==[{'type':'usage','completion_tokens':2,'prompt_tokens':10}]


@respx.mock
def test_truncated_model_output_is_not_reported_as_success(app):
    respx.post('https://model.example/v1/chat/completions').mock(return_value=httpx.Response(200,
        text='data: {"choices":[{"delta":{"content":"partial"},"finish_reason":"length"}]}\n\n'))
    with app.app_context():
        provider=AiProvider(name='test',provider_type='OPENAI_COMPATIBLE',base_url='https://model.example/v1')
        account=AiAccount(name='test',model='test',encrypted_api_key=encrypt_secret('test'))
        provider.accounts.append(account);database.session.add(provider);database.session.commit()
        with pytest.raises(ProviderError,match='OUTPUT_LIMIT'):
            list(OpenAICompatibleClient().stream(provider,account,[{'role':'user','content':'hi'}]))
