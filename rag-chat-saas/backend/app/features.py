"""Persisted administrator controls for optional application features."""
from flask import current_app
from app.crypto import decrypt_json, encrypt_json
from app.extensions import database
from app.models import SystemSetting

KEY = 'system.features'


def private_settings():
    row = database.session.get(SystemSetting, KEY)
    value = decrypt_json(row.encrypted_value) if row else {}
    return {'ragEnabled':current_app.config.get('RAG_ENABLED', False), 'webEnabled':False, **value}


def settings():
    value = private_settings()
    return {k:value[k] for k in ('ragEnabled','webEnabled')}


def web_enabled():
    return settings()['webEnabled'] is True


def rag_enabled():
    return settings()['ragEnabled'] is True


def save(value):
    row = database.session.get(SystemSetting, KEY)
    if row:
        row.encrypted_value = encrypt_json(value)
    else:
        database.session.add(SystemSetting(key=KEY, encrypted_value=encrypt_json(value)))
    database.session.commit()
