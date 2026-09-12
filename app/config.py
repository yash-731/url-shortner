from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "URL Shortener"
    base_url: str = "http://localhost:8000"

    database_url: str = "sqlite+aiosqlite:///./shortener.db"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 24

    shortcode_length: int = 7
    shortcode_max_attempts: int = 5
    cache_ttl_seconds: int = 3600

    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60
    redirect_rate_limit_requests: int = 600

    @field_validator("database_url")
    @classmethod
    def _use_async_driver(cls, value: str) -> str:
        """Managed hosts hand out sync DSNs; SQLAlchemy's async engine needs the async driver."""
        if value.startswith("postgres://"):
            value = value.replace("postgres://", "postgresql://", 1)
        if value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("sqlite://") and "+aiosqlite" not in value:
            value = value.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
