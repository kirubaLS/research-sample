"""Typed settings. Everything the app needs comes from the environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YAADHUM_", env_file=".env", extra="ignore")

    # storage
    database_url: str = "sqlite+pysqlite:///./yaadhum.db"
    corpus_database_url: str | None = None  # ml_corpus lives in its own schema/instance
    object_store_root: str = "./var/objects"

    # models — see docs/yaadhum-backend-logic.md section 5
    model_high_stakes: str = "claude-opus-5"
    model_high_volume: str = "claude-haiku-4-5"
    anthropic_api_key: str | None = None

    # accuracy posture
    auto_accept_threshold: float = 0.97
    conformal_alpha: float = 0.05
    evidence_floor_marks: int = 2
    evidence_floor_questions: int = 2

    # capture quality gate
    min_blur_score: float = 60.0
    max_glare_fraction: float = 0.06
    min_page_coverage: float = 0.60
    max_skew_degrees: float = 6.0

    @property
    def corpus_url(self) -> str:
        return self.corpus_database_url or self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
