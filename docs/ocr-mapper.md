# OCR mapper

An admin tool (**Ops console → OCR mapper**, `/admin/ocr-lab`): upload a question paper (a PDF, or
photographs of its pages in order), watch it read **the way the teacher dashboard reads one**, then map every
question to chapter and topic (the prompt mapper, Haiku, from the book's complete topic list; see
`docs/prompt-mapper.md`).

## Same reading, by import

It does not copy the teacher flow's reading code; it calls it:

| Step | Reused from |
|---|---|
| merge the uploads into one document, in the order given | `app.api.upload.pages_to_pdf` |
| read the text layer | `app.extraction.paper.extract_paper` |
| decide whether the text read is trustworthy, else re-read as a scan | `app.api.marks._text_route_is_confident` |
| rasterize and read with the vision model (and the same cheap-model cascade and structure capture when those settings are on) | `app.extraction.paper_vision.rasterize_pdf` / `read_paper_vision` |
| keep a shared passage with its sub-questions when mapping | `app.extraction.paper.context_addresses` |

A paper with a text layer is read for free; a scan costs one vision call per page on `YAADHUM_MODEL_HIGH_STAKES`
(Opus). The vision reader does not report tokens, so the OCR cost shown is an **estimate**.

## What it checks

The total marks it read against the total the paper prints, the number of questions read against the number
printed, any section titles it found, and every problem the reader reported.

## Stores nothing, changes nothing

- No assessment, scanned question, question, placement, job row or document-store file is created. It never
  opens a database session of its own; the operator-key check is the only database read.
- The reading runs as a background job (it can take minutes), but the job lives in a temporary directory,
  `<tmp>/yaadhum-ocr-lab/<id>/state.json`, read by every server process, and is deleted after 3 hours. The
  uploaded pages are deleted the moment the read finishes.
- Behind the operator key; 20 reads an hour; at most 30 pages.
- No existing file's behaviour was changed: the only edits to existing files register the route, add the nav
  entry and append API types.

## Limits

Social Science (the mapper's topic list). A job's state is a file in the server's temp directory, so it assumes
one server instance; behind several instances a poll could land on one that does not hold the job.
