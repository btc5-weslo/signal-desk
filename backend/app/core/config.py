from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.data_dir import default_dev_data_dir

DEV_JWT_SECRET = "dev-only-change-me"
MIN_PROD_JWT_SECRET_BYTES = 32

# Loopback only. Production / Vercel proxy IPs belong in SIGNAL_TRUSTED_PROXIES.
DEFAULT_TRUSTED_PROXIES = ["127.0.0.0/8", "::1", "localhost"]


def _parse_str_list(v):
    if v is None or v == "":
        return []
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("["):
            import json

            return json.loads(s)
        return [p.strip() for p in s.split(",") if p.strip()]
    return v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SIGNAL_", extra="ignore")

    env: str = "dev"
    database_url: str = "sqlite:///./dev.db"  # prod: postgresql+psycopg://...
    redis_url: str | None = None  # prod: redis://... (enables cross-worker WS fan-out)
    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60
    use_mock_data: bool = False  # mock rows are never served when this is false
    # Required in staging/prod. No hard-coded default path.
    data_dir: str | None = None  # SIGNAL_DATA_DIR
    # Explicit origin list. JSON array or comma-separated via SIGNAL_CORS_ORIGINS.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    # IPs/CIDRs (and "localhost") allowed to set X-Forwarded-Host for branding only.
    trusted_proxies: Annotated[list[str], NoDecode] = list(DEFAULT_TRUSTED_PROXIES)
    # Dev-only: serve live signals that lack a QA-approved backtest for that market.
    serve_unapproved: bool = False
    # Run the live pipeline inside the API process (hosts with no worker).
    inprocess_scheduler: bool = False  # SIGNAL_INPROCESS_SCHEDULER
    scheduler_interval_sec: int = 60  # SIGNAL_SCHEDULER_INTERVAL_SEC
    inprocess_first_delay_s: int = 0
    pipeline_symbols: Annotated[list[str], NoDecode] = ["BTC-USDT"]
    pipeline_timeframes: Annotated[list[str], NoDecode] = ["15m", "1h", "4h", "1d"]
    # Platform allow-list. Tenants cannot set this. Never-licensed names are dropped.
    licensed_data_sources: Annotated[list[str], NoDecode] = []

    @field_validator("cors_origins", "trusted_proxies", "pipeline_symbols",
                     "pipeline_timeframes", "licensed_data_sources", mode="before")
    @classmethod
    def _parse_lists(cls, v):
        return _parse_str_list(v)

    @field_validator("licensed_data_sources", mode="after")
    @classmethod
    def _drop_never_licensed(cls, v):
        from app.core.licensing import filter_licensed_sources
        return filter_licensed_sources(v)

    def allow_unapproved(self) -> bool:
        return self.env == "dev" and self.serve_unapproved

    @field_validator("data_dir", mode="before")
    @classmethod
    def _blank_data_dir(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v

    @model_validator(mode="after")
    def _resolve_data_dir(self):
        # Dev-only fallback: repo data/store, resolved absolutely.
        # Staging/prod must set SIGNAL_DATA_DIR explicitly.
        if self.data_dir:
            self.data_dir = str(Path(self.data_dir).expanduser().resolve())
            return self
        if self.env == "dev":
            self.data_dir = default_dev_data_dir()
        return self

    def validate_for_prod(self) -> None:
        # Staging and prod both require an explicit data directory.
        if self.env in ("prod", "staging") and not self.data_dir:
            raise RuntimeError(
                "set SIGNAL_DATA_DIR; a data directory is required in staging/prod"
            )
        if self.env != "prod":
            return
        if self.jwt_secret == DEV_JWT_SECRET:
            raise RuntimeError("set SIGNAL_JWT_SECRET; the dev secret is not allowed in prod")
        if len(self.jwt_secret.encode()) < MIN_PROD_JWT_SECRET_BYTES:
            raise RuntimeError(
                f"SIGNAL_JWT_SECRET must be at least {MIN_PROD_JWT_SECRET_BYTES} bytes in prod"
            )
        if self.use_mock_data:
            raise RuntimeError("mock data must be off in prod (SIGNAL_USE_MOCK_DATA=false)")
        if self.serve_unapproved:
            raise RuntimeError("SIGNAL_SERVE_UNAPPROVED is not allowed in prod")
        if not self.redis_url:
            raise RuntimeError("set SIGNAL_REDIS_URL; Redis is required in prod")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate_for_prod()
    return s
