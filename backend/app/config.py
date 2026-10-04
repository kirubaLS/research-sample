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
    #: A multi-page question paper used to read one page per sequential Claude call --
    #: a 20-page paper cost 20 round trips end to end. Pages don't depend on each
    #: other's content to be read (see paper_vision.py's own read() docstring), so this
    #: many run concurrently instead. Bounded, not unbounded: every concurrent call here
    #: is a concurrent call against the same Anthropic rate limit every other paper or
    #: grid sheet this deployment is reading at that same moment also draws from, so
    #: raising it trades a faster single paper for less headroom under real concurrent
    #: load -- a knob to tune against your organization's actual Anthropic tier, not a
    #: code change.
    vision_page_concurrency: int = 4
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
    #: The classify step's model calls go through the Message Batches API at half price
    #: (see app.llm_batch): nobody waits on this step, so the live API's speed was paid
    #: for and thrown away. Off, the live API is used as before. YAADHUM_BATCH_CLASSIFY.
    batch_classify: bool = True
    #: The chapter judge is one round of one call per question; live it finishes in
    #: minutes, batched it adds a whole batch wait for a quarter of the saving. Off by
    #: default: the topic judge's three to five rounds are where batching pays.
    batch_chapter_judge: bool = False
    #: How long a batch waits for more calls to join it, how often it is polled, and how
    #: long it may run before every caller gives up on it.
    batch_linger_seconds: float = 3.0
    batch_poll_seconds: float = 15.0
    batch_max_wait_seconds: float = 3 * 3600

    #: Zero-touch: a question paper runs scan -> confirm -> map -> classify by itself the
    #: moment its upload is read, and an answer sheet's rows are resolved and its marks
    #: confirmed the moment they are read. Nobody clicks Confirm, Map or Classify, and
    #: nothing waits on a review. Off only for a deployment that wants a person in the
    #: loop (and in the test suite, which exercises each step on its own).
    auto_pipeline: bool = True

    # --- Social Science mapping (branch sst-mapping-fix); every flag OFF by default ------
    #: The vision reader also copies each section header's printed title and any printed
    #: syllabus lines, and both routes store them in assessment.declared as
    #: "section_titles" and "syllabus_lines". Off: the reader's prompt and output format
    #: are exactly as before and nothing new is stored. YAADHUM_PAPER_CAPTURE_STRUCTURE.
    paper_capture_structure: bool = False
    #: One scope function for map and place (app.classify.question_scope): teacher scope,
    #: then the chapters a section title names, then the syllabus lines, then inferred
    #: scope, then the whole subject group. A bare section letter carries no subject
    #: meaning. Off: the fixed A/B/C/D -> History/Geography/Politics/Economics convention.
    sst_unified_scope: bool = False
    #: When a question's scope spans several books, the chapter judge always sees the best
    #: retrieval candidate from each book, not only the global top chapters.
    balanced_group_candidates: bool = False
    #: When the chapter judge says no in-scope chapter can answer a question, one more
    #: pass over the whole subject group may place it outside the declared scope; the
    #: placement is marked cross_scope and flagged for review.
    cross_scope_fallback: bool = False
    #: A question whose scope is exactly one chapter skips the chapter judge and goes
    #: straight to the topic judge, which then also returns the tier.
    skip_single_chapter_judge: bool = False
    #: A major topic is at most this many levels deep ("4" or "4.1", never "4.1.1") for
    #: every subject listed in topic_max_depth_by_subject, everywhere a section is decided
    #: or stored (app.curriculum.depth.collapse_section). A subject not listed keeps
    #: today's behaviour. YAADHUM_TOPIC_DEPTH_CAP; the map is JSON in
    #: YAADHUM_TOPIC_MAX_DEPTH_BY_SUBJECT.
    topic_depth_cap: bool = False
    #: the depth a listed subject gets when its own entry gives none
    topic_max_depth: int = 2
    topic_max_depth_by_subject: dict[str, int] = {
        "X.HIST": 2, "X.GEO": 2, "X.POL": 2, "X.ECO": 2,
    }
    #: The topic judge is offered only major topics (depth <= the subject's cap, boxes
    #: never), deeper sections rendered as plain subheadings inside their parent, and the
    #: chapter's unnumbered introduction as "0 Introduction". Applies to capped subjects.
    topic_major_only_document: bool = False
    #: For book-map subjects, subtopic nodes come from the book map's printed numbers
    #: only: an existing node is never relabelled, and the ingest-created nodes are never
    #: a fallback topic.
    book_map_only_subtopics: bool = False
    #: The chapter judge cites the passages it used by their printed number ([1]..[n])
    #: instead of retyping a reference, and the numbers are checked against what it was
    #: shown. A reference string still works as a tolerant fallback (the printed line, a
    #: bare reference, or a quote from a shown passage). A citation problem is recorded
    #: as a warning only and never lowers the placement's confidence.
    cite_passages_by_number: bool = False
    #: A placement is flagged for review only for one of seven reasons, stored as
    #: question_placement.review_reason (app.classify.review_rule): the chapter judge
    #: failed; the placement left the declared scope; the declared blueprint moved it
    #: to a chapter other than the judge's; the family is unsettled or
    #: blocked; the chapter judge was below 0.7 with more than one chapter to choose
    #: from; the topic judge's section differs from in-chapter retrieval's and was not
    #: verified to answer the question; the topic judge verified nothing. Off: the
    #: existing flags.
    review_flag_rule: bool = False

    # --- what the classifier is shown, which is what it costs ---------------------------
    #: How many book passages go into one classification, and how many chapters they are
    #: drawn from. Both are the price of the call and the quality of the answer at once:
    #: too few and the rival chapter is never shown, so the reading cannot correct
    #: retrieval; too many and every question carries passages that were never in
    #: contention. Settings rather than constants because the right number depends on the
    #: book, and finding it should not need a code change.
    #:
    #: 6 was too few even *within* an already-correctly-chosen chapter: a real audited miss
    #: ("A nuclear power plant located in Tamil Nadu", Geography's Minerals and Energy
    #: Resources) reached the judge without its own Nuclear or Atomic Energy passage at all.
    #: locate()'s round-robin (_evidence_across) spends the budget across
    #: classifier_evidence_chapters candidate chapters before it finishes one chapter's own
    #: list, and within that one correct chapter an activity box ("Locate the 6 nuclear
    #: power stations...") and picture captions outscored the section's own prose on pure
    #: lexical overlap -- so the section the question is actually about was real, correctly
    #: chaptered, voted-for evidence that never reached position 6. It reaches the judge at
    #: position 8 (measured against the real book text -- see
    #: tests/test_geography_section_retrieval.py). Raised to match EVIDENCE_DEPTH
    #: (app/classify/pipeline.py), the deepest pool locate() ever draws candidates from per
    #: retriever, so this is the most headroom a passages setting can use on its own without
    #: also widening depth.
    classifier_evidence_passages: int = 8
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
    #: Sarvam Vision 1.5 (app.ingest.sarvam_ocr), tried ahead of both Tesseract and
    #: Gemini when set -- an OCR model trained specifically on Indic scripts, offered as
    #: the accuracy option rather than the free-and-local or the general-purpose-network
    #: one. Unset falls through to whichever of the other two this deployment can run.
    sarvam_api_key: str | None = None
    #: BCP-47, matching what app.ingest.hindi_ocr's OCR_LANG ('hin', Tesseract's own
    #: three-letter code) means for the Hindi books this was built for -- change this
    #: alongside the subject if this deployment starts loading a book in another of
    #: Sarvam's 23 supported Indic languages.
    sarvam_language: str = "hi-IN"
    #: Matryoshka truncation. Vectors from different models or dimensions are not
    #: comparable, so changing either requires re-embedding the whole corpus.
    embedding_dimensions: int = 512

    # --- WhatsApp (Meta Cloud API, direct -- no BSP) ---
    #: Meta's own phone-number identifier for the school's WhatsApp Business number,
    #: assigned once Meta Business verification is complete and a number is registered.
    #: Unset means every send genuinely attempts the real Meta API call and honestly
    #: surfaces Meta's own "you have not verified..." style error -- never a fabricated
    #: success. See app.integrations.whatsapp.WhatsAppClient.
    whatsapp_phone_number_id: str | None = None
    #: A permanent (System User) access token once Meta issues one. A short-lived token
    #: from the App Dashboard's own "Try the API" panel works too but expires in hours --
    #: fine for a first real test, not for anything left running.
    whatsapp_access_token: str | None = None
    #: The name of the message template Meta has approved for this use (a report card
    #: notification cannot be sent as free-form text -- WhatsApp's business-initiated
    #: rule requires an approved template). This is a placeholder until the user submits
    #: a real template to Meta for approval; changing it is a config edit, not a code
    #: change. See WHATSAPP_TEMPLATE_PARAMS in app.integrations.whatsapp for the body
    #: variable shape the template is expected to have.
    whatsapp_template_name: str = "student_report"
    #: BCP-47/Meta's own template-language code (their catalogue uses "en", "en_US" etc --
    #: whatever the approved template was actually submitted under).
    whatsapp_template_language: str = "en"
    #: Meta signs every webhook delivery with the app secret (X-Hub-Signature-256); kept
    #: separate from whatsapp_access_token because it verifies inbound calls FROM Meta,
    #: not calls this app makes TO Meta.
    whatsapp_app_secret: str | None = None
    #: The shared secret Meta's own webhook verification handshake (GET .../webhooks/
    #: whatsapp?hub.verify_token=...) is checked against when the URL is first registered
    #: in the Meta App Dashboard.
    whatsapp_webhook_verify_token: str | None = None

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
