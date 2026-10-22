from __future__ import annotations

import os


class Config:
    RAG_ENABLED = os.getenv('RAG_ENABLED', 'false').lower() == 'true'
    STOCK_ENGINE_URL = os.getenv('STOCK_ENGINE_URL', '')
    STOCK_ENGINE_TOKEN_FILE = os.getenv('STOCK_ENGINE_TOKEN_FILE', '')
    AGENT_BACKEND = os.getenv('AGENT_BACKEND', 'local')
    AGENT_CORE_URL = os.getenv('AGENT_CORE_URL', '')
    AGENT_CORE_TOKEN_FILE = os.getenv('AGENT_CORE_TOKEN_FILE', '')
    AGENT_CORE_MODEL_PROFILE = os.getenv('AGENT_CORE_MODEL_PROFILE', '')
    AGENT_CORE_CALLBACK_TOKEN_SHA256 = os.getenv('AGENT_CORE_CALLBACK_TOKEN_SHA256', '')
    TESTING = False
    DATABASE_PATH = os.getenv("DATABASE_PATH", "data/stock-chat.db")
    SECRET_KEY = os.getenv("APP_SECRET_KEY", "development-only-change-me")
    BOOTSTRAP_ADMIN_USERNAME = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    BOOTSTRAP_TENANT_ID = os.getenv('BOOTSTRAP_TENANT_ID', '')
    BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    SESSION_COOKIE_NAME = "stock_analysis_session"
    SESSION_SECURE = os.getenv("SESSION_SECURE", "false").lower() == "true"
    SESSION_TTL_SECONDS = 8 * 60 * 60
    MASTER_KEY = os.getenv("APP_MASTER_KEY", "")
    SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
    SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    SILICONFLOW_MODEL = os.getenv("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3")
    KNOWLEDGE_BASE_CACHE_TTL_SECONDS = int(os.getenv("KNOWLEDGE_BASE_CACHE_TTL_SECONDS", "30"))
