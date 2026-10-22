from collections import Counter
from types import SimpleNamespace
import pytest
from app.provider_pool import ProviderPool, ProviderUnavailable
from app.extensions import database
from app.models import AiAccount, AiProvider
from app.crypto import encrypt_secret
from test_admin import authenticated_admin


def pairs(weights):
    return [(SimpleNamespace(id=str(i), weight=w, concurrency_limit=2), None) for i, w in enumerate(weights)]


def test_equal_weights_rotate_sequential_answers():
    pool = ProviderPool()
    accounts = pairs([1, 1])
    assert [pool.select(accounts)[0].id for _ in range(6)] == ['0', '1'] * 3


def test_weight_ratio_and_live_weight_changes():
    pool = ProviderPool()
    accounts = pairs([2, 1])
    assert Counter(pool.select(accounts)[0].id for _ in range(30)) == {'0': 20, '1': 10}
    accounts[0][0].weight = 1
    accounts[1][0].weight = 3
    assert Counter(pool.select(accounts)[0].id for _ in range(40)) == {'0': 10, '1': 30}


def test_capacity_and_capability_filtered_candidates_are_respected():
    pool = ProviderPool()
    accounts = pairs([100, 1])
    accounts[0][0].concurrency_limit = 1
    with pool.acquire(accounts[0][0]):
        assert pool.select(accounts)[0].id == '1'
    assert pool.select(accounts[:1])[0].id == '0'
    with pytest.raises(ProviderUnavailable):
        pool.select([])


def test_weight_patch_persists_and_rejects_invalid_values(app, client):
    csrf = authenticated_admin(client)
    with app.app_context():
        provider = AiProvider(name='test', provider_type='OPENAI_COMPATIBLE', base_url='https://example.com/v1')
        account = AiAccount(name='test', encrypted_api_key=encrypt_secret('fake-key'), model='chat', weight=1)
        provider.accounts.append(account)
        database.session.add(provider)
        database.session.commit()
        account_id = account.id
    response = client.patch(f'/api/v1/admin/accounts/{account_id}', json={'weight': 73}, headers={'X-CSRF-Token': csrf})
    assert response.status_code == 200
    assert response.json['accounts'][0]['weight'] == 73
    assert client.get('/api/v1/admin/providers').json[0]['accounts'][0]['weight'] == 73
    for value in [0, 101, 1.5, '2']:
        assert client.patch(f'/api/v1/admin/accounts/{account_id}', json={'weight': value}, headers={'X-CSRF-Token': csrf}).status_code == 400
    assert client.get('/api/v1/admin/providers').json[0]['accounts'][0]['weight'] == 73
