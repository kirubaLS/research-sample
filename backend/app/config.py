"""Typed settings. Everything the app needs comes from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalise_database_url(url: str) -> str:
    """Managed hosts hand out ``postgres://``; SQLAlchemy 2 requires a driver.

    Render, Heroku and Neon all emit the bare ``postgres://`` scheme, which SQLAlchemy 2
    refuses to load. Normalising here means the platform's own connection string can be
    pasted in unchanged.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def is_pooled_url(url: str) -> bool:
    """True for a connection that goes through PgBouncer in transaction-pooling mode.

    Neon's pooled endpoint carries ``-pooler`` in the hostname. Transaction pooling breaks
    server-side prepared statements and session-scoped state, which changes how the engine
    must be configured and means migrations need the *direct* endpoint instead.
    """
    return "-pooler." in url or "pgbouncer=true" in url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YAADHUM_", env_file=".env", extra="ignore")

    environment: str = "development"          # development | staging | production

    # --- storage ---
    database_url: str = "sqlite+pysqlite:///./yaadhum.db"
    #: Alembic needs the DIRECT (unpooled) endpoint — DDL and migration locks do not
    #: survive PgBouncer transaction pooling. Falls back to database_url when unset.
    migration_database_url: str | None = None
    corpus_database_url: str | None = None    # ml_corpus gets its own credentials
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_recycle_seconds: int = 280        # under a typical managed-proxy idle timeout

    # object store: 'local' for a laptop, 's3' for anything real (S3, R2, MinIO)
    storage_backend: str = "local"
    object_store_root: str = "./var/objects"
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None        # set for Cloudflare R2 / MinIO
    s3_region: str = "ap-south-1"             # data residency: keep student work in India
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    # --- web ---
    #: exact origins allowed to call this API. Never '*' — the student route is
    #: unauthenticated, so a wildcard would let any site drive it.
    cors_origins: list[str] = ["http://localhost:3000"]
    trusted_hosts: list[str] = ["*"]
    public_rate_limit_per_hour: int = 60      # per IP, on the unauthenticated student route

    # --- models ---
    model_high_stakes: str = "claude-opus-5"
    model_high_volume: str = "claude-haiku-4-5"
    anthropic_api_key: str | None = None

    # --- accuracy posture ---
    auto_accept_threshold: float = 0.97
    conformal_alpha: float = 0.05
    evidence_floor_marks: int = 2
    evidence_floor_questions: int = 2

    # --- capture quality gate ---
    min_blur_score: float = 60.0
    max_glare_fraction: float = 0.06
    min_page_coverage: float = 0.60
    max_skew_degrees: float = 6.0

    @field_validator(
        "database_url", "migration_database_url", "corpus_database_url", mode="after"
    )
    @classmethod
    def _normalise(cls, v: str | None) -> str | None:
        return normalise_database_url(v) if v else v

    @field_validator("cors_origins", "trusted_hosts", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        """Render passes env vars as strings, so accept 'a,b' as well as JSON."""
        if isinstance(v, str):
            stripped = v.strip()
            if stripped.startswith("["):
                return v
            return [part.strip() for part in stripped.split(",") if part.strip()]
        return v

    @property
    def corpus_url(self) -> str:
        return self.corpus_database_url or self.database_url

    @property
    def migration_url(self) -> str:
        """The URL Alembic uses. Never the pooled endpoint if a direct one was given."""
        return self.migration_database_url or self.database_url

    @property
    def uses_connection_pooler(self) -> bool:
        return is_pooled_url(self.database_url)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
