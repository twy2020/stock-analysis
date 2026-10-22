from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app import create_app


@pytest.fixture()
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "RAG_ENABLED": True,
        "DATABASE_PATH": str(tmp_path / "test.db"),
        "BOOTSTRAP_ADMIN_USERNAME": "admin",
        "BOOTSTRAP_ADMIN_PASSWORD": "Initial-Password-42!",
        "SESSION_SECURE": False,
        "MASTER_KEY": Fernet.generate_key().decode("ascii"),
    })
    return application


@pytest.fixture()
def client(app):
    return app.test_client()
