# Optional. Render's native Python runtime is simpler; use this if you want an identical
# image locally, in CI and in production, or if you deploy somewhere other than Render.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# libGL and libglib are needed only by the optional opencv extra; keep the layer small.
#
# tesseract-ocr is what lets a scanned marks sheet be read at all. It is a system binary,
# not a Python package, so Render's native Python runtime cannot install it: on that
# runtime the app still works and refuses scans by name, which is why app.extraction
# .marksheet checks for the binary rather than assuming it. Deploy this image instead of
# the native runtime if you want scans read.
#
# tesseract-ocr-hin is what lets a Hindi NCERT book be read at all: the real files
# (Kshitij, Kritika, Sparsh, Sanchayan) embed a pre-Unicode font (Walkman-Chanakya) with
# no ToUnicode CMap, so the PDF's own text layer decodes as mojibake regardless of which
# extraction method reads it -- reading the rendered page as an image sidesteps the
# encoding entirely. app.ingest.hindi_ocr checks for the binary and the language data the
# same way app.extraction.marksheet does, rather than assuming either is present.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq5 tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin \
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
