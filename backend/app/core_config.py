from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "boerse-dashboard-web"
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"
    database_url: str = Field(
        default="postgresql+psycopg://boerse:boerse@postgres:5432/boerse_dashboard"
    )
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    worker_concurrency: int = 1
    worker_disable_rate_limits: bool = True
    scheduler_enabled: bool = True
    pushover_user_key: str = ""
    pushover_app_token: str = ""
    pushover_dry_run: bool = False
    cors_origins: list[AnyHttpUrl | str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
