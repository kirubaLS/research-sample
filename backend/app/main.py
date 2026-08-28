"""Yaadhum API.

Two products, one deployment: the psychometric interest test and the marks engine share
auth, the student table and the report layer.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api import interest, marks, reports
from app.config import get_settings
from app.db import engine, init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Yaadhum",
    version="0.1.0",
    description="Assessment diagnostics — interest profiling and question-level marks analysis.",
)

app.include_router(interest.router)
app.include_router(marks.router)
app.include_router(reports.router)


@app.get("/health", tags=["ops"])
def health() -> dict:
    settings = get_settings()
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {
        "status": "ok",
        "database": "up",
        "models": {
            "high_stakes": settings.model_high_stakes,
            "high_volume": settings.model_high_volume,
        },
        "auto_accept_threshold": settings.auto_accept_threshold,
    }
