"""Application settings, loaded from environment variables (prefix MPOWER_)."""

import hashlib
import logging
import os
import tempfile
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-insecure-change-me-0000000000000000"


def _normalise_db_url(url: str) -> str:
    """Accept provider URLs (postgres://, postgresql://) and pin the psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MPOWER_", env_file=".env", extra="ignore")

    env: str = "development"
    database_url: str = ""
    jwt_secret: str = Field(default=DEV_SECRET, min_length=1)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]
    seed_demo_data: bool = True
    market_sim_enabled: bool = True
    market_tick_seconds: float = 2.0
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    @property
    def serverless(self) -> bool:
        """True on Vercel / AWS Lambda: no always-on process, so no background loops."""
        return any(os.environ.get(k) for k in ("VERCEL", "VERCEL_ENV", "VERCEL_URL", "AWS_LAMBDA_FUNCTION_NAME",
                                               "LAMBDA_TASK_ROOT"))

    @property
    def market_mode(self) -> str:
        """'stream': in-process feed pushed over WebSocket. 'poll': prices advance when read (serverless)."""
        return "poll" if self.serverless else "stream"

    @model_validator(mode="after")
    def _resolve_db(self):
        # Explicit setting wins, then the variables Vercel/Neon integrations inject, then a sensible default.
        url = (self.database_url or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or "").strip()
        if not url:
            # serverless file systems are read-only except the temp dir
            url = "sqlite:////tmp/mpower.db" if self.serverless or not os.access(".", os.W_OK) else "sqlite:///./mpower.db"
        self.database_url = _normalise_db_url(url)
        if self.database_url == "sqlite:///./mpower.db" and not os.access(".", os.W_OK):
            self.database_url = f"sqlite:///{tempfile.gettempdir()}/mpower.db"
        # accept any secret a user pastes into a dashboard; short ones are stretched to a full-length key
        if len(self.jwt_secret) < 32:
            self.jwt_secret = hashlib.sha256(self.jwt_secret.encode()).hexdigest()
        return self


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.jwt_secret == DEV_SECRET:
        if s.is_production:
            raise RuntimeError("MPOWER_JWT_SECRET must be set to a strong secret in production")
        logging.getLogger("mpower").warning("Using the built-in development JWT secret - set MPOWER_JWT_SECRET")
    return s
