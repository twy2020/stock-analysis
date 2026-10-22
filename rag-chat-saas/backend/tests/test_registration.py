import json

from app.extensions import database
from app.models import AuditRecord, SystemSetting

PASSWORD = 'Registration-password-42!'


def signup(app, username='new-user', **extra):
    return app.test_client().post('/api/v1/auth/register', json=dict(username=username, password=PASSWORD, **extra))


def administrator(client):
    login = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'Initial-Password-42!'})
    changed = client.post('/api/v1/auth/change-password', json={'password': PASSWORD}, headers={'X-CSRF-Token': login.json['csrfToken']})
    return {'X-CSRF-Token': changed.json['csrfToken']}


def test_registration_session_role_and_validation(app, client):
    assert client.get('/api/v1/auth/registration').json == {'inviteRequired': False}
    response = client.post('/api/v1/auth/register', json={'username': ' New-User ', 'password': PASSWORD, 'role': 'ADMIN'})
    assert response.status_code == 201
    assert response.json['user'] == {'username': 'new-user', 'role': 'USER', 'passwordChangeRequired': False}
    assert client.get('/api/v1/auth/session').status_code == 200
    assert client.get('/api/v1/conversations').status_code == 200
    assert signup(app, 'NEW-USER').status_code == 409
    assert signup(app, 'has spaces').status_code == 400
    assert app.test_client().post('/api/v1/auth/register', json={'username':'valid', 'password':'short'}).status_code == 400
    assert client.get('/api/v1/admin/settings/registration').status_code == 403


def test_invite_changes_only_affect_new_registrations_and_are_audited(app, client):
    assert signup(app, 'before').status_code == 201
    headers = administrator(client)
    url = '/api/v1/admin/settings/registration'
    assert client.put(url, json={'inviteRequired': True}, headers=headers).status_code == 400
    assert client.put(url, json={'inviteRequired': False}).status_code == 403
    code = 'invitation-test-secret'
    response = client.put(url, json={'inviteRequired': True, 'inviteCode': code}, headers=headers)
    assert response.json == {'inviteRequired': True, 'inviteCodeConfigured': True}
    assert app.test_client().get('/api/v1/auth/registration').json == {'inviteRequired': True}
    assert signup(app, 'missing').status_code == 400
    assert signup(app, 'wrong', inviteCode='incorrect').status_code == 400
    assert signup(app, 'after', inviteCode=code).status_code == 201
    assert client.put(url, json={'inviteRequired': True, 'inviteCode': ''}, headers=headers).status_code == 200
    assert signup(app, 'retained', inviteCode=code).status_code == 201
    assert client.put(url, json={'inviteRequired': True, 'inviteCode': 'replacement-code'}, headers=headers).status_code == 200
    assert signup(app, 'expired', inviteCode=code).status_code == 400
    assert signup(app, 'updated', inviteCode='replacement-code').status_code == 201
    for username in ('before', 'after'):
        assert app.test_client().post('/api/v1/auth/login', json={'username':username, 'password':PASSWORD}).status_code == 200
    assert client.put(url, json={'inviteRequired': False}, headers=headers).status_code == 200
    assert signup(app, 'free-again').status_code == 201
    with app.app_context():
        row = database.session.get(SystemSetting, 'auth.registration')
        assert 'replacement-code' not in row.encrypted_value
        records = database.session.query(AuditRecord).all()
        details = json.dumps([r.details for r in records])
        assert code not in details and PASSWORD not in details and 'replacement-code' not in details
        registered = [r for r in records if r.action == 'auth.register' and r.status == 'SUCCEEDED']
        assert registered and all(r.organization_id and r.user_id for r in registered)
        assert any(r.action == 'admin.put_registration_settings' and r.details.get('inviteCodeChanged') for r in records)
