from __future__ import annotations

from app.extensions import database
from app.models import Session, User


def login(client, username="admin", password="Initial-Password-42!"):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_bootstrap_admin_must_change_password_and_session_token_is_hashed(app, client):
    response = login(client)

    assert response.status_code == 200
    assert response.json["user"] == {"username": "admin", "role": "ADMIN", "passwordChangeRequired": True}
    assert response.json["csrfToken"]
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie

    with app.app_context():
        user = database.session.query(User).filter_by(username="admin").one()
        session = database.session.query(Session).filter_by(user_id=user.id).one()
        assert user.password_hash != "Initial-Password-42!"
        assert session.token_hash not in cookie

    blocked = client.get("/api/v1/conversations")
    assert blocked.status_code == 428
    assert blocked.json["code"] == "PASSWORD_CHANGE_REQUIRED"


def test_password_change_requires_csrf_and_rotates_session(client):
    signed_in = login(client)
    csrf = signed_in.json["csrfToken"]

    rejected = client.post("/api/v1/auth/change-password", json={"password": "New-Password-84!"})
    assert rejected.status_code == 403
    changed = client.post(
        "/api/v1/auth/change-password",
        json={"password": "New-Password-84!"},
        headers={"X-CSRF-Token": csrf},
    )
    assert changed.status_code == 200
    assert changed.json["user"]["passwordChangeRequired"] is False
    assert changed.json["csrfToken"] != csrf

    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": changed.json["csrfToken"]})
    assert login(client, password="New-Password-84!").status_code == 200
    assert login(client, password="Initial-Password-42!").status_code == 401


def test_session_endpoint_logout_and_invalid_credentials(client):
    assert login(client, password="wrong").status_code == 401
    signed_in = login(client)
    session = client.get("/api/v1/auth/session")
    assert session.status_code == 200
    assert session.json["user"]["username"] == "admin"
    assert session.json["csrfToken"]

    assert client.post("/api/v1/auth/logout").status_code == 403
    assert client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": session.json["csrfToken"]}
    ).status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401


def test_conversation_queries_are_always_owner_scoped(app, client):
    signed_in = login(client)
    changed = client.post(
        "/api/v1/auth/change-password",
        json={"password": "New-Password-84!"},
        headers={"X-CSRF-Token": signed_in.json["csrfToken"]},
    )
    csrf = changed.json["csrfToken"]
    created = client.post("/api/v1/conversations", json={"title": "Mine"}, headers={"X-CSRF-Token": csrf})
    assert created.status_code == 201

    with app.app_context():
        other = User.create("other", "Other-Password-42!", role="USER", password_change_required=False)
        database.session.add(other)
        database.session.commit()

    other_client = app.test_client()
    assert login(other_client, "other", "Other-Password-42!").status_code == 200
    assert other_client.get("/api/v1/conversations").json == []
    assert other_client.get(f"/api/v1/conversations/{created.json['id']}").status_code == 404
    assert other_client.get(f"/api/v1/conversations/{created.json['id']}/messages").status_code == 404
    other_session = other_client.get("/api/v1/auth/session").json
    assert other_client.patch(f"/api/v1/conversations/{created.json['id']}", json={"title": "Stolen"},
                              headers={"X-CSRF-Token": other_session["csrfToken"]}).status_code == 404
    assert other_client.delete(f"/api/v1/conversations/{created.json['id']}",
                               headers={"X-CSRF-Token": other_session["csrfToken"]}).status_code == 404

    renamed = client.patch(f"/api/v1/conversations/{created.json['id']}", json={"title": "Renamed"},
                           headers={"X-CSRF-Token": csrf})
    assert renamed.status_code == 200
    assert renamed.json["title"] == "Renamed"
    deleted = client.delete(f"/api/v1/conversations/{created.json['id']}", headers={"X-CSRF-Token": csrf})
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/conversations/{created.json['id']}").status_code == 404
