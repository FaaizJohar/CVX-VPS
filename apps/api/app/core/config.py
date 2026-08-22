from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CVX_",
        extra="ignore",
    )

    app_name: str = "CVX"
    environment: Literal["development", "staging", "production"] = "development"
    api_v1_prefix: str = "/api/v1"

    # HTTP
    host: str = "0.0.0.0"
    port: int = 8000
    trusted_hosts: list[str] = ["*"]
    cors_origins: list[str] = []
    behind_proxy: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://cvx:cvx@localhost:5432/cvx"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: SecretStr = Field(default=SecretStr("change-me-in-production"))
    session_cookie_name: str = "cvx_session"
    session_ttl_seconds: int = 60 * 60 * 24 * 7
    session_cookie_secure: bool = True
    password_min_length: int = 10
    enrollment_token_ttl_seconds: int = 60 * 30
    password_reset_ttl_seconds: int = 60 * 60
    api_key_prefix: str = "cvx"

    # Rate limiting
    rate_limit_auth_per_minute: int = 10
    rate_limit_default_per_minute: int = 300

    # Metrics
    metrics_retention_days: int = 30
    node_offline_after_seconds: int = 90

    # Agent communication
    agent_timeout_seconds: float = 15.0
    public_base_url: str = "https://cvx.example.com"
    cvx_agent_install_url: str | None = None

    # Bootstrap
    bootstrap_owner_email: str | None = None
    bootstrap_owner_password: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
