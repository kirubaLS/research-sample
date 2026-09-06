"""Yaadhum API.

Two products, one deployment: the psychometric interest test and the marks engine share
auth, the student table and the report layer.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from app.api import (
    admin,
    books,
    documents,
    gridsheets,
    interest,
    marks,
    placement,
    platform,
    reading,
    reports,
)
from app.config import get_settings
from app.db import engine, init_db

logger = logging.getLogger("yaadhum")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Production applies Alembic migrations in the pre-deploy step; creating tables here
    # would silently diverge from the migration history.
    if not settings.is_production:
        init_db()
    logger.info("yaadhum starting", extra={"environment": settings.environment})
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Yaadhum",
    version="0.1.0",
    description="Assessment diagnostics — interest profiling and question-level marks analysis.",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
)

# The frontend is a separate origin, so CORS is required rather than optional. Never '*':
# the student route is unauthenticated, and a wildcard would let any site drive it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    # PATCH is here because correcting a scanned question uses it, and PUT because the
    # syllabus scope does. A method missing from this list fails in the browser only --
    # every server-side test passes, which is exactly how it goes unnoticed.
    allow_methods=["GET", "POST", "PATCH", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-Platform-Key", "X-School-Id"],
    max_age=600,
)

#: The liveness probe must never depend on the Host header. A platform health check comes
#: from inside the network and does not carry the public hostname, so putting it behind a
#: host allowlist rejects every probe with 400 and the deploy never goes live -- while the
#: process is perfectly healthy. These paths return no data, so exempting them costs
#: nothing: host filtering exists to stop cache poisoning and absolute-URL spoofing, and
#: there is no URL to build and no content to poison here.
_HEALTH_PATHS = frozenset({"/healthz", "/health"})

if settings.trusted_hosts != ["*"]:
    @app.middleware("http")
    async def trusted_host(request: Request, call_next):
        if request.url.path in _HEALTH_PATHS:
            return await call_next(request)
        host = (request.headers.get("host") or "").split(":")[0]
        if not any(
            host == allowed or (allowed.startswith("*.") and host.endswith(allowed[1:]))
            for allowed in settings.trusted_hosts
        ):
            return PlainTextResponse("Invalid host header", status_code=400)
        return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.include_router(admin.router)
app.include_router(interest.router)
app.include_router(marks.router)
app.include_router(books.router)
app.include_router(placement.router)
app.include_router(platform.router)
app.include_router(reports.router)
app.include_router(documents.router)
app.include_router(reading.router)
app.include_router(gridsheets.router)


@app.get("/healthz", tags=["ops"])
def liveness() -> dict:
    """Liveness only — no dependencies.

    This is the path the platform health check should use. Pointing it at a check that
    touches the database means a brief database blip restarts a perfectly healthy process.
    """
    return {"status": "ok"}


@app.get("/health", tags=["ops"])
def readiness() -> dict:
    """Readiness: can this instance actually serve traffic?"""
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {
        "status": "ok",
        "database": "up",
        "environment": settings.environment,
        "models": {
            "high_stakes": settings.model_high_stakes,
            "high_volume": settings.model_high_volume,
        },
        "auto_accept_threshold": settings.auto_accept_threshold,
    }
