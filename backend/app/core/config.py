"""Application settings, read from environment variables (or a .env file)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = "dev"  # dev | test | prod
    APP_NAME: str = "InsightAI"

    # Main connection: the app's own role (can create schemas/tables).
    DATABASE_URL: str = "postgresql+psycopg2://insight:insight@localhost:5432/insight"
    # Read-only role used ONLY to run AI / widget SQL. Falls back to DATABASE_URL.
    READONLY_DATABASE_URL: str | None = None
    READONLY_DB_ROLE: str = "insight_readonly"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    DB_READONLY_POOL_SIZE: int = 5

    REDIS_URL: str = "redis://localhost:6379/0"
    # Each open SSE stream holds one pub/sub connection from this pool.
    REDIS_MAX_CONNECTIONS: int = 500

    JWT_SECRET: str = "change-me-in-production"
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 60 * 24

    FRONTEND_URL: str = "http://localhost:3000"
    # URL the PDF renderer uses to reach the frontend (e.g. http://web:3000 inside Docker).
    PRINT_BASE_URL: str | None = None
    CORS_ORIGINS: str = "http://localhost:3000"

    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str | None = None
    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    USE_OLLAMA: bool = True
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434/v1"
    OLLAMA_MODEL: str = "llama3:latest"

    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_PRO: str | None = None
    STRIPE_PRICE_ENTERPRISE: str | None = None

    # Let API connectors poll localhost / LAN addresses. Only honoured when ENV is dev or test.
    ALLOW_PRIVATE_CONNECTOR_URLS: bool = False

    MAX_UPLOAD_MB: int = 25
    MAX_WEBHOOK_KB: int = 1024
    QUERY_TIMEOUT_MS: int = 5000
    QUERY_ROW_LIMIT: int = 1000

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def stripe_enabled(self) -> bool:
        return bool(self.STRIPE_SECRET_KEY)


_WEAK_SECRETS = {"change-me", "change-me-in-production", ""}


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Anyone who knows the default secret can forge a token for any user.
    if s.ENV == "prod" and (s.JWT_SECRET in _WEAK_SECRETS or len(s.JWT_SECRET) < 32):
        raise RuntimeError("JWT_SECRET must be set to a long random value when ENV=prod")
    return s


settings = get_settings()
