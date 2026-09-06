"""One place that turns an upload into a file on disk.

Shared by the book-chapter upload and the question-paper scan: two entry points enforcing
different size limits, or one of them forgetting to reject an empty file, is the kind of
difference nobody notices until a user hits it.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

#: NCERT chapter PDFs run to about 3 MB and a scanned board paper to about 8 MB; well
#: above this is not either of those things.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


#: What a phone or a scanner actually produces. A teacher photographing a paper page by
#: page has JPEGs, not a PDF, and telling them to convert first is telling them to give up.
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff")


async def to_tempfile(upload: UploadFile) -> Path:
    if not (upload.filename or "").lower().endswith(".pdf"):
        raise HTTPException(422, "expected a PDF")
    data = await upload.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"file is larger than {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
    if not data:
        raise HTTPException(422, "the file is empty")
    handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    handle.write(data)
    handle.close()
    return Path(handle.name)


async def pages_to_pdf(uploads: list[UploadFile]) -> Path:
    """Any number of PDFs and images, in the order given, as one document.

    Order is the caller's, never the filename's. A phone names photographs by the second
    they were taken and a scanner by a counter that resets, so sorting by name reorders a
    paper silently -- and a question paper read out of order produces question numbers that
    look plausible and are wrong.

    A single file goes through the same path as twenty. Having one code path for "a PDF"
    and another for "some pages" is how the two drift until only the common one works.
    """
    import pymupdf

    if not uploads:
        raise HTTPException(422, "no files were uploaded")

    out = pymupdf.open()
    total = 0
    try:
        for upload in uploads:
            name = (upload.filename or "").lower()
            data = await upload.read()
            total += len(data)
            if total > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    413, f"the pages together are larger than {MAX_UPLOAD_BYTES // 1024 // 1024} MB"
                )
            if not data:
                raise HTTPException(422, f"{upload.filename or 'a file'} is empty")

            if name.endswith(".pdf"):
                with pymupdf.open(stream=data, filetype="pdf") as part:
                    out.insert_pdf(part)
            elif name.endswith(IMAGE_SUFFIXES):
                try:
                    with pymupdf.open(stream=data) as image:
                        as_pdf = image.convert_to_pdf()
                    with pymupdf.open("pdf", as_pdf) as page:
                        out.insert_pdf(page)
                except HTTPException:
                    raise
                except Exception as exc:  # noqa: BLE001 -- the filename is what the user needs
                    raise HTTPException(
                        422, f"{upload.filename or 'an image'} could not be read: {exc}"
                    ) from exc
            else:
                raise HTTPException(
                    422,
                    f"{upload.filename or 'a file'} is not a PDF or an image. "
                    f"Accepted: .pdf and {', '.join(IMAGE_SUFFIXES)}",
                )

        if out.page_count == 0:
            raise HTTPException(422, "the upload contained no pages")

        handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        handle.write(out.tobytes())
        handle.close()
        return Path(handle.name)
    finally:
        out.close()
