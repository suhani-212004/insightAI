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

    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str = "change-me-in-production"
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 60 * 24

    FRONTEND_URL: str = "http://localhost:3000"
    # URL the PDF renderer uses to reach the frontend (e.g. http://web:3000 inside Docker).
    PRINT_BASE_URL: str | None = None
    CORS_ORIGINS: str = "http://localhost:3000"

    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_PRO: str | None = None
    STRIPE_PRICE_ENTERPRISE: str | None = None

    MAX_UPLOAD_MB: int = 25
    QUERY_TIMEOUT_MS: int = 5000
    QUERY_ROW_LIMIT: int = 1000

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def stripe_enabled(self) -> bool:
        return bool(self.STRIPE_SECRET_KEY)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
