from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Make Money Easy"
    env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./data/app.db"
    default_lot_size: int = 1000
    default_fee_rate: float = Field(default=0.001425, ge=0)
    default_tax_rate: float = Field(default=0.003, ge=0)
    scheduler_timezone: str = "Asia/Taipei"
    scheduler_enabled: bool = True
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MME_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
