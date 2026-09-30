"""Validated deployment configuration. No settings are loaded at import time."""

from functools import lru_cache
from decimal import Decimal
from uuid import UUID

# Display/documentation only; monetary arithmetic uses integer 4/1000.
GMF_TAX_RATE = Decimal("0.004")
DEFAULT_SYSTEM_TAX_GMF_ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000004")

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "HabiCapital P2P API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    DATABASE_URL: PostgresDsn
    DB_POOL_SIZE: int = Field(default=5, ge=1)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0)
    JWT_SECRET_KEY: str = Field(min_length=64)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, gt=0)
    ADMIN_EMAIL: str = "admin@habicapital.co"
    ADMIN_PASSWORD: str = Field(min_length=12)
    ADMIN_ALIAS: str = "admin_system"
    SYSTEM_TAX_GMF_ACCOUNT_ID: UUID = DEFAULT_SYSTEM_TAX_GMF_ACCOUNT_ID
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("ENVIRONMENT")
    @classmethod
    def check_environment(cls, value: str) -> str:
        if value not in {"development", "test", "staging", "production"}:
            raise ValueError("Invalid environment")
        return value

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def check_algorithm(cls, value: str) -> str:
        if value != "HS256":
            raise ValueError("Only HS256 is supported")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
