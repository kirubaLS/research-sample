# Optional. Render's native Python runtime is simpler; use this if you want an identical
# image locally, in CI and in production, or if you deploy somewhere other than Render.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# libGL and libglib are needed only by the optional opencv extra; keep the layer small.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e . || true

COPY . .
RUN pip install -e .

# Run as a non-root user.
RUN useradd --create-home --uid 10001 yaadhum && chown -R yaadhum:yaadhum /srv
USER yaadhum

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
