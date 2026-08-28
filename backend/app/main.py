"""Yaadhum API.

Two products, one deployment: the psychometric interest test and the marks engine share
auth, the student table and the report layer.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text

from app.api import admin, interest, marks, platform, reports
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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-Platform-Key"],
    max_age=600,
)

if settings.trusted_hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)


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
app.include_router(platform.router)
app.include_router(reports.router)


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
