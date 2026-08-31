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
