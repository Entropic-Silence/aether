import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Aether API"
    api_prefix: str = "/api/v1"
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://aether:aether_dev_pw@127.0.0.1:5432/aether",
    )
    secret_key: str = os.environ.get("SECRET_KEY", "dev-insecure-secret-key-change-me")
    access_token_minutes: int = int(os.environ.get("ACCESS_TOKEN_MINUTES", "1440"))
    allow_registration: bool = os.environ.get("ALLOW_REGISTRATION", "false") == "true"
    cors_origins: str = os.environ.get("CORS_ORIGINS", "*")
    default_product_name: str = os.environ.get("PRODUCT_NAME", "Aether")
    default_accent: str = os.environ.get("ACCENT_COLOR", "#10a37f")

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
