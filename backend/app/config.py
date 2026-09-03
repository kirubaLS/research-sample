"""Typed settings. Everything the app needs comes from the environment."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    #: Exact origins allowed to call this API. Never '*' — the student route is
    #: unauthenticated, so a wildcard would let any site drive it.
    #:
    #: NoDecode matters: pydantic-settings JSON-decodes complex types straight from the
    #: environment, *before* any validator runs. A platform sets these as a plain string
    #: ("https://app.example"), so without NoDecode the process raises SettingsError on
    #: boot and the deploy never comes up.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    trusted_hosts: Annotated[list[str], NoDecode] = ["*"]
    public_rate_limit_per_hour: int = 60      # per IP, on the unauthenticated student route

    #: The platform operator's credential -- the one that can create schools and mint a
    #: principal's key. Strictly above a school key: a principal must never be able to
    #: reach another school's data, so this is a separate secret, not a flag on a school.
    #: Unset means the whole /platform surface is off, which is the right default: a
    #: deployment that never sets it cannot have the route abused.
    platform_admin_key: str | None = None
    platform_rate_limit_per_hour: int = 20   # per IP, on the platform sign-in

    # --- models ---
    model_high_stakes: str = "claude-opus-5"
    model_high_volume: str = "claude-haiku-4-5"
    #: the classifier's judge. Without it, placement falls back to nearest-neighbour
    #: retrieval, which cannot tell a question about a theorem from the theorem.
    anthropic_api_key: str | None = None
    #: One call per question, around forty per paper. This call decides the chapter, the
    #: topic and the cognitive tier that a school reads about a child, so it is not the
    #: place to take the cheapest thing available -- but it is not the place to take the
    #: dearest without evidence either. Overridable per deployment, and the run reports
    #: what it actually spent so the choice can be made on measurement rather than on a
    #: guess about what a paper costs.
    model_classifier: str = "claude-sonnet-5"
    #: How hard the model is asked to work, sent only to models that accept it -- Haiku 4.5
    #: rejects the parameter and the request drops it. See app.llm. Thinking tokens are the
    #: larger half of what a paper costs, so this is the strongest price lever here, and
    #: the one most worth measuring before moving.
    model_effort: str = "medium"

    # --- what the classifier is shown, which is what it costs ---------------------------
    #: How many book passages go into one classification, and how many chapters they are
    #: drawn from. Both are the price of the call and the quality of the answer at once:
    #: too few and the rival chapter is never shown, so the reading cannot correct
    #: retrieval; too many and every question carries passages that were never in
    #: contention. Settings rather than constants because the right number depends on the
    #: book, and finding it should not need a code change.
    classifier_evidence_passages: int = 6
    classifier_evidence_chapters: int = 3
    #: Characters kept from each passage. A whole exercise runs to 8500 and the signal is
    #: at the start; the tail is later questions that pull the reading off.
    classifier_passage_chars: int = 1200

    # --- embeddings ---
    #: Multilingual by requirement, not preference: the papers are bilingual and Tamil is
    #: in scope. Unset means the knowledge base answers exact matches only.
    jina_api_key: str | None = None
    embedding_model: str = "jina-embeddings-v4"
    #: The Hindi NCERT books (Kshitij, Kritika, Sparsh, Sanchayan) embed a pre-Unicode
    #: font with no ToUnicode CMap, so their own text layer decodes as mojibake regardless
    #: of extraction method -- see app.ingest.gemini_ocr. Tesseract would read the
    #: rendered page correctly too, but needs a system binary the free-tier Render Python
    #: runtime cannot install; Gemini reads the PDF directly over the API, no system
    #: dependency. Unset means Hindi contents/chapter uploads are refused by name rather
    #: than silently falling through to the broken text layer.
    gemini_api_key: str | None = None
    #: A model name shifts under a deployment in a way jina_api_key's model does not.
    #: gemini-2.5-flash (this module's first default) started 404ing with "no longer
    #: available to new users" -- Google's own error named the replacement, gemini-3.6-
    #: flash, which is what this is now. Verify this is still current before relying on it
    #: rather than trusting this default blind a second time.
    gemini_model: str = "gemini-3.6-flash"
    #: Matryoshka truncation. Vectors from different models or dimensions are not
    #: comparable, so changing either requires re-embedding the whole corpus.
    embedding_dimensions: int = 512

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
        """Accept every shape a platform might hand us.

        NoDecode turns off pydantic-settings' own JSON decoding for these fields, so this
        validator has to handle all three forms itself:
            "https://a.example"                      one origin
            "https://a.example, https://b.example"   comma separated
            '["https://a.example"]'                  JSON
        """
        if not isinstance(v, str):
            return v
        stripped = v.strip()
        if stripped.startswith("["):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"not valid JSON and not a comma-separated list: {v!r}") from exc
        return [part.strip() for part in stripped.split(",") if part.strip()]

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
