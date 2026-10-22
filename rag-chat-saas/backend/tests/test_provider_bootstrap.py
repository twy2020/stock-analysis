from cryptography.fernet import Fernet

from app import create_app
from app.extensions import database
from app.models import AiAccount, AiProvider


def test_bootstraps_siliconflow_provider_from_environment_without_plaintext_key(tmp_path):
    application = create_app({
        "TESTING": True,
        "DATABASE_PATH": str(tmp_path / "provider.db"),
        "BOOTSTRAP_ADMIN_PASSWORD": "Initial-Password-42!",
        "MASTER_KEY": Fernet.generate_key().decode("ascii"),
        "SILICONFLOW_API_KEY": "sk-bootstrap-secret",
        "SILICONFLOW_BASE_URL": "https://api.siliconflow.cn/v1",
        "SILICONFLOW_MODEL": "deepseek-ai/DeepSeek-V3",
    })

    with application.app_context():
        provider = database.session.query(AiProvider).one()
        account = database.session.query(AiAccount).one()
        assert provider.provider_type == "SILICONFLOW"
        assert provider.base_url == "https://api.siliconflow.cn/v1"
        assert account.model == "deepseek-ai/DeepSeek-V3"
        assert "sk-bootstrap-secret" not in account.encrypted_api_key

        # Re-running bootstrap against the same database is idempotent.
        create_app(application.config)
        assert database.session.query(AiProvider).count() == 1
