"""The things that break silently when the frontend and backend are hosted separately."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.config import Settings, normalise_database_url
from app.ratelimit import FixedWindowLimiter


def test_managed_postgres_urls_are_normalised():
    """Render, Heroku and Neon all emit bare 'postgres://', which SQLAlchemy 2 refuses."""
    assert normalise_database_url("postgres://u:p@host:5432/db") == (
        "postgresql+psycopg://u:p@host:5432/db"
    )
    assert normalise_database_url("postgresql://u:p@host/db") == (
        "postgresql+psycopg://u:p@host/db"
    )
    # already-qualified and sqlite URLs pass through untouched
    assert normalise_database_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"
    assert normalise_database_url("sqlite+pysqlite:///./x.db") == "sqlite+pysqlite:///./x.db"


def test_settings_normalise_the_url_from_the_environment(monkeypatch):
    monkeypatch.setenv("YAADHUM_DATABASE_URL", "postgres://a:b@c/d")
    assert Settings().database_url.startswith("postgresql+psycopg://")


def test_csv_env_vars_parse_as_lists():
    """Render passes env vars as plain strings, not JSON."""
    s = Settings(cors_origins="https://a.example, https://b.example")
    assert s.cors_origins == ["https://a.example", "https://b.example"]


def test_cors_defaults_are_not_a_wildcard():
    """The student route is unauthenticated; '*' would let any site drive it."""
    assert "*" not in Settings().cors_origins


def test_liveness_does_not_touch_the_database(client):
    """healthz must stay up through a database blip, or the platform restarts a healthy
    process every time the database hiccups."""
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_readiness_reports_the_database(client):
    body = client.get("/health").json()
    assert body["database"] == "up"


def test_security_headers_are_set(client):
    headers = client.get("/healthz").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"


def test_cors_preflight_allows_the_configured_origin(client):
    r = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_an_unknown_origin(client):
    r = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in r.headers


def test_rate_limiter_blocks_after_the_ceiling():
    limiter = FixedWindowLimiter(limit=3, window_seconds=3600)
    for _ in range(3):
        limiter.check("1.2.3.4", now=1000.0)
    with pytest.raises(HTTPException) as exc:
        limiter.check("1.2.3.4", now=1000.0)
    assert exc.value.status_code == 429
    assert "Retry-After" in (exc.value.headers or {})


def test_rate_limiter_is_per_client_and_windowed():
    limiter = FixedWindowLimiter(limit=1, window_seconds=60)
    limiter.check("a", now=0.0)
    limiter.check("b", now=0.0)          # a different client is unaffected
    with pytest.raises(HTTPException):
        limiter.check("a", now=30.0)
    limiter.check("a", now=61.0)         # the window has rolled


def test_the_public_start_route_is_rate_limited(client, school):
    from app.api.interest import _start_limiter

    _start_limiter.reset()
    original = _start_limiter.limit
    _start_limiter.limit = 2
    try:
        payload = {"name": "N", "roll_no": "900"}
        assert client.post(f"/t/{school['section_id']}/start", json=payload).status_code == 200
        assert client.post(f"/t/{school['section_id']}/start", json=payload).status_code == 200
        blocked = client.post(f"/t/{school['section_id']}/start", json=payload)
        assert blocked.status_code == 429
    finally:
        _start_limiter.limit = original
        _start_limiter.reset()


def test_local_object_store_round_trip(tmp_path):
    import io

    from app.storage import LocalObjectStore

    store = LocalObjectStore(str(tmp_path))
    stored = store.put("scripts/s1/page-1.jpg", io.BytesIO(b"jpeg-bytes"), "image/jpeg")
    assert stored.size == 10 and len(stored.sha256) == 64
    assert store.exists("scripts/s1/page-1.jpg")
    assert store.open("scripts/s1/page-1.jpg").read() == b"jpeg-bytes"
    store.delete("scripts/s1/page-1.jpg")
    assert not store.exists("scripts/s1/page-1.jpg")


def test_object_store_rejects_a_traversing_key(tmp_path):
    import io

    from app.storage import LocalObjectStore

    store = LocalObjectStore(str(tmp_path))
    with pytest.raises(ValueError):
        store.put("../escape.jpg", io.BytesIO(b"x"))
