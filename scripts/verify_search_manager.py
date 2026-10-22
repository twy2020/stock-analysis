"""Run inside the stock backend; verify real admin routing without printing secrets."""
import json
from app import create_app
from app.extensions import database
from app.models import User,Session

app=create_app()
with app.app_context():
    user=database.session.query(User).filter_by(role='ADMIN',status='ACTIVE',password_change_required=False).first()
    assert user is not None,'No active administrator available for verification'
    session,cookie,csrf=Session.issue(user,120)
    database.session.add(session);database.session.commit()
    try:
        client=app.test_client()
        client.set_cookie(app.config['SESSION_COOKIE_NAME'],cookie)
        settings=client.get('/api/v1/admin/settings/search-engines')
        assert settings.status_code==200
        assert all('apiKey' not in p for p in settings.json['providers'])
        response=client.post('/api/v1/admin/settings/search-engines/native/test',json={},headers={'X-CSRF-Token':csrf})
        assert response.status_code==200 and response.json['ok'],response.json
        assert response.json['sources']
        print(json.dumps({'adminRoute':True,'credentialsHidden':True,'search':response.json},ensure_ascii=False))
    finally:
        database.session.delete(session);database.session.commit()
