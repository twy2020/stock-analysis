from app.crypto import decrypt_json, encrypt_json
from app.extensions import database
from app.models import SystemSetting

KEY = 'auth.registration'


def settings():
    row = database.session.get(SystemSetting, KEY)
    return decrypt_json(row.encrypted_value) if row else {'inviteRequired': False}


def view(value):
    return {'inviteRequired': value.get('inviteRequired', False), 'inviteCodeConfigured': bool(value.get('inviteCode'))}


def save(value):
    row = database.session.get(SystemSetting, KEY)
    if row:
        row.encrypted_value = encrypt_json(value)
    else:
        database.session.add(SystemSetting(key=KEY, encrypted_value=encrypt_json(value)))
    database.session.commit()
