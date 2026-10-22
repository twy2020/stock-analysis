from __future__ import annotations

import json

from cryptography.fernet import Fernet
from flask import current_app


def cipher() -> Fernet:
    key = current_app.config.get("MASTER_KEY", "")
    if not key:
        raise RuntimeError("APP_MASTER_KEY is required")
    return Fernet(key.encode("ascii") if isinstance(key, str) else key)


def encrypt_json(value: dict) -> str:
    payload = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return cipher().encrypt(payload).decode("ascii")


def decrypt_json(value: str) -> dict:
    return json.loads(cipher().decrypt(value.encode("ascii")).decode("utf-8"))


def encrypt_secret(value: str) -> str:
    return cipher().encrypt(value.encode("utf-8")).decode("ascii")
