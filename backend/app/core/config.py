"""
Application settings (Pydantic Settings v2).
Loads from environment / .env — never commit secrets.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Environment ---
    ENV: str = Field(default="development", description="development | production | staging")
    APP_NAME: str = Field(default="K.U.A. Backend")
    LOG_LEVEL: str = Field(default="INFO")

    # --- HTTP ---
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000)
    # Comma-separated (Railway/Render: add your public hostname, e.g. api.example.com)
    TRUSTED_HOSTS: str = Field(
        default="localhost,127.0.0.1,testserver,backend,*.localhost",
    )

    # --- CORS ---
    FRONTEND_ORIGINS: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        description="Comma-separated allowed browser origins",
    )

    # --- Database ---
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://kua:kua@postgres:5432/kua",
        description="Async SQLAlchemy URL, e.g. postgresql+asyncpg://user:pass@host:5432/db",
    )
    DB_POOL_SIZE: int = Field(default=10)
    DB_MAX_OVERFLOW: int = Field(default=20)
    DB_POOL_PRE_PING: bool = Field(default=True)

    # --- Redis (cache + ARQ) ---
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis for cache + background job broker",
    )

    # --- JWT / Auth ---
    JWT_SECRET: str = Field(
        default="CHANGE_ME_IN_PRODUCTION_MIN_32_CHARS______",
        min_length=32,
        description="Symmetric secret for JWT",
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_EXPIRE_MINUTES: int = Field(default=30)
    JWT_REFRESH_EXPIRE_DAYS: int = Field(default=14)
    JWT_ISSUER: str = Field(default="kua.api")
    JWT_AUDIENCE: str = Field(default="kua.operators")

    COOKIE_ACCESS_NAME: str = Field(default="kua_access_token")
    COOKIE_REFRESH_NAME: str = Field(default="kua_refresh_token")
    COOKIE_DOMAIN: Optional[str] = Field(default=None)
    COOKIE_SECURE: bool = Field(default=False)
    COOKIE_SAMESITE: str = Field(
        default="lax",
        description="lax | strict | none (none requires Secure cookies)",
    )

    # Operator bootstrap (optional; creates user if missing at startup)
    OPERATOR_USERNAME: str = Field(default="operator")
    OPERATOR_PASSWORD_HASH: Optional[str] = Field(
        default=None,
        description="bcrypt hash; if empty, password login disabled until seeded",
    )
    OPERATOR_DISPLAY_NAME: str = Field(default="Acquisitions Operator")
    OPERATOR_CLEARANCE: str = Field(default="tier-1")

    # --- Security headers ---
    CSP: str = Field(
        default="default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        description="API responses — minimal CSP (browsers hitting JSON only)",
    )

    # --- Rate limits (slowapi) ---
    RATE_LIMIT_DEFAULT: str = Field(default="200/minute")
    RATE_LIMIT_AUTH: str = Field(default="10/minute")

    # --- OpenAPI docs ---
    @property
    def docs_enabled(self) -> bool:
        return self.ENV.lower() in ("development", "dev", "local", "test")

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.FRONTEND_ORIGINS.split(",") if o.strip()]

    @property
    def trusted_hosts_list(self) -> List[str]:
        hosts = [h.strip() for h in self.TRUSTED_HOSTS.split(",") if h.strip()]
        if self.ENV.lower() in ("development", "dev", "local", "test"):
            # Local dev with arbitrary hosts (docker internal names, etc.)
            if "*" not in hosts:
                hosts.append("*")
        return hosts

    @property
    def sync_database_url(self) -> str:
        """Alembic / sync drivers use postgresql:// not asyncpg."""
        url = self.DATABASE_URL
        if "+asyncpg" in url:
            return url.replace("+asyncpg", "+psycopg", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
