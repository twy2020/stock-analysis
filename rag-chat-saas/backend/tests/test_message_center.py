import pytest
from app.extensions import database
from app.models import User, Organization


@pytest.fixture()
def actors(app):
    with app.app_context():
        admin = database.session.query(User).filter_by(username='admin').one()
        admin.password_change_required = False
        database.session.add_all([User.create(name, 'Member-password-42!', password_change_required=False) for name in ('alice', 'bob')])
        other = Organization(name='Other')
        database.session.add(other); database.session.flush()
        database.session.add(User.create('outside', 'Member-password-42!', role='ADMIN', password_change_required=False, organization_id=other.id))
        database.session.commit()
    result = {}
    for name in ('admin', 'alice', 'bob', 'outside'):
        client = app.test_client()
        response = client.post('/api/v1/auth/login', json={'username':name,'password':'Initial-Password-42!' if name == 'admin' else 'Member-password-42!'})
        result[name] = (client, {'X-CSRF-Token':response.json['csrfToken']})
    return result


def test_ticket_replies_read_cursor_and_closure(actors):
    user, uh = actors['alice']; admin, ah = actors['admin']
    created = user.post('/api/v1/feedback', data={'comment':'显示错误','snapshot':'{}'}, headers=uh)
    ticket = created.json['id']; path = '/api/v1/feedback/' + ticket
    assert user.get('/api/v1/feedback').status_code == 200
    assert admin.get('/api/v1/admin/feedback').json['items'][0]['unread'] is True
    assert user.get('/api/v1/message-center/unread').json['feedback'] == 0
    admin_detail = admin.get('/api/v1/admin/feedback/'+ticket).json
    assert admin.post('/api/v1/admin/feedback/'+ticket+'/read', json={'through':admin_detail['latestReplyId']}, headers=ah).status_code == 204
    assert admin.get('/api/v1/admin/feedback/stats').json['unread'] == 0
    assert admin.post('/api/v1/admin/feedback/'+ticket+'/replies', json={'body':'请补充现象'},headers=ah).status_code == 201
    detail = user.get(path).json
    assert detail['replies'][0]['body'] == '请补充现象'
    assert user.get('/api/v1/message-center/unread').json['feedback'] == 1
    admin.post('/api/v1/admin/feedback/'+ticket+'/replies', json={'body':'还有一个检查项'},headers=ah)
    user.post(path+'/read',json={'through':detail['latestReplyId']},headers=uh)
    assert user.get('/api/v1/message-center/unread').json['feedback'] == 1
    detail = user.get(path).json
    user.post(path+'/read',json={'through':detail['latestReplyId']},headers=uh)
    assert user.get('/api/v1/message-center/unread').json['feedback'] == 0
    assert user.post(path+'/replies',json={'body':'补充细节'},headers=uh).status_code == 201
    assert admin.get('/api/v1/admin/feedback/stats').json['unread'] == 1
    compact = user.get(path+'?summary=true').json
    assert 'snapshot' not in compact and 'replies' not in compact
    assert admin.patch('/api/v1/admin/feedback/'+ticket,json={'status':'RESOLVED'},headers=ah).status_code == 200
    assert user.post(path+'/replies',json={'body':'关闭后不能发送'},headers=uh).status_code == 409
    assert user.get(path).json['status'] == 'RESOLVED'
    assert user.get('/api/v1/message-center/unread').json['feedback'] == 1
    assert admin.patch('/api/v1/admin/feedback/'+ticket,json={'status':'NEW'},headers=ah).status_code == 200
    assert user.post(path+'/replies',json={'body':'重新开启后继续沟通'},headers=uh).status_code == 201


def test_ticket_access_isolation_validation_and_pagination(actors):
    user, uh = actors['alice']; bob, bh = actors['bob']; outside, oh = actors['outside']
    ticket = user.post('/api/v1/feedback',data={'comment':'个人问题'},headers=uh).json['id']
    path = '/api/v1/feedback/' + ticket
    assert bob.get(path).status_code == 404
    assert bob.post(path+'/replies',json={'body':'冒用'},headers=bh).status_code == 404
    assert outside.get('/api/v1/admin/feedback/'+ticket).status_code == 404
    assert bob.get('/api/v1/feedback').json['total'] == 0
    assert user.post(path+'/replies',json={'body':' '},headers=uh).status_code == 400
    assert user.post(path+'/replies',json={'body':'未授权'}).status_code == 403
    assert user.patch('/api/v1/admin/feedback/'+ticket,json={'status':'RESOLVED'},headers=uh).status_code == 403
    assert user.get('/api/v1/feedback?q=不匹配').json['total'] == 0
    assert user.get('/api/v1/feedback?page=2').json['items'] == []
    assert user.post(path+'/read',json={'through':9999999},headers=uh).status_code == 400


def test_announcements_read_state_is_per_user_and_org(actors):
    admin, ah = actors['admin']; alice, uh = actors['alice']; bob, bh = actors['bob']; outside, oh = actors['outside']
    response = admin.post('/api/v1/admin/announcements',json={'title':'系统维护','content':'今晚进行维护'},headers=ah)
    assert response.status_code == 201
    message = response.json['id']
    assert alice.get('/api/v1/message-center/unread').json['system'] == 1
    assert outside.get('/api/v1/announcements').json['total'] == 0
    assert alice.post('/api/v1/announcements/'+message+'/read',headers=uh).status_code == 204
    assert alice.get('/api/v1/message-center/unread').json['system'] == 0
    assert bob.get('/api/v1/message-center/unread').json['system'] == 1
    assert alice.post('/api/v1/admin/announcements',json={'title':'冒用','content':'消息'},headers=uh).status_code == 403
    assert outside.post('/api/v1/announcements/'+message+'/read',headers=oh).status_code == 404
    assert admin.patch('/api/v1/admin/announcements/'+message,json={'active':False},headers=ah).status_code == 200
    assert bob.get('/api/v1/message-center/unread').json['system'] == 0
