"""Read a book with Sarvam's Document AI 'digitise' endpoint -- an OCR model trained
specifically on Indic scripts (Sarvam Vision 1.5), tried ahead of Tesseract and Gemini
when accuracy on a language like Hindi is what is being optimised for.

Async job API, not a single request-response call: create the digitise job, poll its
status until it reaches a terminal state, then download a ZIP holding the OCR'd output
and read the plain-text (Markdown) file out of it. Max 10 pages per job (Sarvam's own
limit) -- a chapter or prelims file longer than that is split into 10-page batches
first and OCR'd as separate jobs, joined the same way every other read_text-like
function in this codebase joins pages.
"""

from __future__ import annotations

import io
import time
import zipfile

import httpx
import pymupdf
from sarvamai import SarvamAI

#: Sarvam's own limit on a single digitise job (PDF or ZIP input) -- exceeding it is a
#: 400 invalid_request_error, not a slow success, so batches are split before ever
#: reaching the API rather than relying on it to reject an oversized one.
MAX_PAGES_PER_JOB = 10
POLL_INTERVAL_SECONDS = 5
#: A job over ten Indic-script pages, worth budgeting generously for the same reason
#: Tesseract's own per-page timeout is generous (app.ingest.hindi_ocr) -- correctness
#: matters more than speed for an admin-only, occasional book upload, and this already
#: runs inside a background job (see app.api.books.IngestJob), never a blocking request.
JOB_TIMEOUT_SECONDS = 600
_TERMINAL_STATUSES = {"completed", "partially_completed", "failed", "rejected"}


def _split_into_batches(pdf_bytes: bytes, max_pages: int) -> list[bytes]:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        batches: list[bytes] = []
        for start in range(0, doc.page_count, max_pages):
            end = min(start + max_pages, doc.page_count) - 1
            with pymupdf.open() as batch:
                batch.insert_pdf(doc, from_page=start, to_page=end)
                batches.append(batch.tobytes())
        return batches


def _digitise_one_batch(client: SarvamAI, pdf_bytes: bytes, language: str) -> str:
    """One job, at most MAX_PAGES_PER_JOB pages -- the caller has already split the book
    to respect that limit, this just runs the job lifecycle for one piece of it.
    """
    job = client.doc_ai.digitise(
        file=[("batch.pdf", pdf_bytes, "application/pdf")],
        language=language,
        output_format="md",
        # These are printed NCERT textbook pages, never handwriting -- telling the model
        # so is a real accuracy lever the API offers, not a default worth leaving unset.
        content_type="printed",
    )

    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    status = job.status
    while status.lower() not in _TERMINAL_STATUSES:
        if time.monotonic() > deadline:
            raise RuntimeError(
                f"Sarvam digitise job {job.job_id} did not finish within "
                f"{JOB_TIMEOUT_SECONDS}s (last status: {status})"
            )
        time.sleep(POLL_INTERVAL_SECONDS)
        status = client.doc_ai.get_status(job_id=job.job_id).status

    if status.lower() in ("failed", "rejected"):
        raise RuntimeError(f"Sarvam digitise job {job.job_id} ended as {status!r}")

    download = client.doc_ai.get_download_url(job_id=job.job_id)
    response = httpx.request(
        download.method or "GET", download.url, headers=download.headers or {}, timeout=120,
    )
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        # The primary output file, not a per-page metadata/page_NNN.json sidecar -- see
        # this module's docstring: output_format='md' makes the primary file a .md.
        md_names = [
            name for name in archive.namelist()
            if name.endswith(".md") and not name.startswith("metadata/")
        ]
        if not md_names:
            raise RuntimeError(
                f"Sarvam digitise job {job.job_id}: no Markdown output found in the "
                f"result archive ({archive.namelist()})"
            )
        return archive.read(md_names[0]).decode("utf-8")


def sarvam_read_text(pdf_bytes: bytes, *, api_key: str, language: str = "hi-IN") -> str:
    """The book's real Unicode text, digitised by Sarvam Vision 1.5, page batches joined
    the way every other read_text-like function in this codebase joins pages.
    """
    if not api_key:
        raise ValueError(
            "no Sarvam API key. Set YAADHUM_SARVAM_API_KEY -- without it a book cannot "
            "be read through Sarvam's Document AI at all."
        )
    client = SarvamAI(api_subscription_key=api_key)
    batches = _split_into_batches(pdf_bytes, MAX_PAGES_PER_JOB)
    return "\n\n".join(_digitise_one_batch(client, batch, language) for batch in batches)
