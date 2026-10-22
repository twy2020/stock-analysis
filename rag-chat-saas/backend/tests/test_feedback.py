import io
import json

from PIL import Image

from app.extensions import database
from app.models import User


def sign_in(client, username, password):
    result = client.post('/api/v1/auth/login', json={'username': username, 'password': password})
    return {'X-CSRF-Token': result.json['csrfToken']}


def test_feedback_snapshot_images_admin_access_and_owner_isolation(app, client):
    with app.app_context():
        admin = database.session.query(User).filter_by(username='admin').one()
        admin.password_change_required = False
        database.session.add(User.create('member', 'Member-password-42!', password_change_required=False))
        database.session.commit()
    headers = sign_in(client, 'member', 'Member-password-42!')
    convo = client.post('/api/v1/conversations', json={'title': '压力问题'}, headers=headers).json
    image = io.BytesIO()
    Image.new('RGB', (20, 20), 'white').save(image, format='PNG')
    image.seek(0)
    snapshot = {'messages': [{'role': 'USER', 'content': '当前问题', 'status': 'COMPLETED'}], 'draft': '补充问题'}
    result = client.post('/api/v1/feedback', data={
        'comment': '回答显示异常', 'conversationId': convo['id'], 'snapshot': json.dumps(snapshot),
        'images': (image, 'screen.png'),
    }, headers=headers)
    assert result.status_code == 201
    feedback_id = result.json['id']
    assert client.get('/api/v1/admin/feedback').status_code == 403
    admin_client = app.test_client()
    admin_headers = sign_in(admin_client, 'admin', 'Initial-Password-42!')
    listing = admin_client.get('/api/v1/admin/feedback').json
    assert listing['total'] == 1
    assert listing['items'][0]['username'] == 'member'
    detail = admin_client.get(f'/api/v1/admin/feedback/{feedback_id}').json
    assert detail['snapshot']['messages'][0]['content'] == '当前问题'
    url = detail['images'][0]['url']
    assert admin_client.get(url).mimetype == 'image/png'
    assert client.get(url).status_code == 403
    assert app.test_client().get(url).status_code == 401
    assert admin_client.patch(f'/api/v1/admin/feedback/{feedback_id}', json={'status': 'RESOLVED'}, headers=admin_headers).status_code == 200
    assert admin_client.get('/api/v1/admin/feedback?status=NEW').json['total'] == 0
    # An administrator cannot attach another user's conversation as their own feedback.
    assert admin_client.post('/api/v1/feedback', data={'comment': '冒用', 'conversationId': convo['id'], 'snapshot': '{}'}, headers=admin_headers).status_code == 404


def test_feedback_rejects_invalid_uploads_and_empty_comments(app, client):
    with app.app_context():
        user = database.session.query(User).first()
        user.password_change_required = False
        database.session.commit()
    headers = sign_in(client, 'admin', 'Initial-Password-42!')
    assert client.post('/api/v1/feedback', data={'comment': '  '}, headers=headers).status_code == 400
    assert client.post('/api/v1/feedback', data={'comment': '错误', 'snapshot': '[]'}, headers=headers).status_code == 400
    assert client.post('/api/v1/feedback', data={'comment': '错误', 'snapshot': '{}', 'images': (io.BytesIO(b'<svg onload="alert(1)"/>'), 'bad.png')}, headers=headers).status_code == 400
    assert client.post('/api/v1/feedback', data={'comment': '错误', 'snapshot': '{}'}).status_code == 403
    assert client.get('/api/v1/admin/feedback').json['total'] == 0
    snapshot = {'messages': [{'role': 'USER', 'content': 'x' * 95000} for _ in range(7)]}
    assert client.post('/api/v1/feedback', data={'comment': '长对话', 'snapshot': json.dumps(snapshot)}, headers=headers).status_code == 201
