"""Application settings, loaded from environment variables (prefix MPOWER_)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MPOWER_", env_file=".env", extra="ignore")

    env: str = "development"
    database_url: str = "sqlite:///./mpower.db"
    jwt_secret: str = Field(default="dev-insecure-change-me-0000000000000000", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]
    seed_demo_data: bool = True
    market_sim_enabled: bool = True
    market_tick_seconds: float = 2.0
    # Hard compliance failures block an order; soft failures need an override reason.
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production and s.jwt_secret.startswith("dev-"):
        raise RuntimeError("MPOWER_JWT_SECRET must be set to a strong secret in production")
    return s
