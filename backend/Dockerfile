# The production image. render.yaml deploys this rather than Render's native Python
# runtime, because text recognition needs the tesseract binary and the native runtime
# cannot install system packages.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# tesseract-ocr is what lets a scanned marks sheet be read at all. It is a system binary,
# not a Python package, which is the whole reason this image exists: the app checks for
# the binary rather than assuming it, so on a runtime without it scans are refused by name
# instead of silently reading as empty.
#
# The opencv extra is deliberately not installed: nothing imports cv2, and it would add
# tens of megabytes to an image that has to start quickly on a small instance.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq5 tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e . || true

COPY . .
RUN pip install -e ".[storage]"

# Fail the build, not the first upload, if recognition cannot actually run.
#
# Not a version check: `tesseract --version` passes on an install whose language data is
# missing or somewhere this base image does not look, and the failure then arrives as an
# unreadable scan in a staffroom. So the build renders a page, photographs it, and reads
# it back -- the same path a real upload takes.
RUN python -c "\
import pymupdf, sys; \
from app.extraction.marksheet import ocr_available, read_pdf; \
from pathlib import Path; \
assert ocr_available(), 'the tesseract binary is missing'; \
d = pymupdf.open(); p = d.new_page(width=595, height=842); \
p.insert_text((60, 120), 'Roll No    B/2', fontsize=18); \
p.insert_text((60, 165), '041        3', fontsize=18); \
pix = p.get_pixmap(dpi=200); d.close(); \
i = pymupdf.open(); q = i.new_page(width=595, height=842); \
q.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pix); \
i.save('/tmp/ocr-check.pdf'); i.close(); \
r = read_pdf(Path('/tmp/ocr-check.pdf')); \
sys.exit(0 if (r.used_ocr and r.rows) else 'text recognition produced nothing: ' + str(r.refused))"

# Run as a non-root user.
RUN useradd --create-home --uid 10001 yaadhum && chown -R yaadhum:yaadhum /srv
USER yaadhum

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
