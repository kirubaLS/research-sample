"""Reading marks out of a file somebody else made.

A school already has the marks somewhere: a spreadsheet the class teacher keeps, a PDF the
exam cell printed, a photograph of the mark sheet. Retyping them is where marks get
transposed, and the transposition is invisible afterwards because the typed number looks
exactly like a read one.

Nothing here writes a mark. Every row is a *proposal* carrying where it came from -- the
sheet, the cell, the raw text -- so a person confirms or corrects before anything is
stored. That is not a formality: the difference between 3 and 8 in a hurried hand is one
stroke, and the only defence against being confidently wrong is a person who saw the paper.

Three shapes of file are handled, and one is refused:

  * a **long** sheet: one row per mark, with a question column and a marks column
  * a **wide** sheet: one row per student, one column per question
  * a **text-layer PDF**: the same two shapes, read out of the text rather than the cells
  * a **photograph or scanned PDF** is refused by name, because reading handwriting is not
    something this module can do and pretending otherwise is the one unforgivable failure
"""

from __future__ import annotations

import csv
import io
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from app.extraction.address import Address, normalise, normalise_numerals

#: Below about 150 dpi Tesseract starts inventing punctuation in mark columns.
OCR_DPI = 200

#: Header text that names the student rather than a question.
ROLL_HEADERS = ("roll", "roll no", "rollno", "roll number", "reg", "regno", "admission", "adm no")
#: Header text that names the question column in a long sheet.
QUESTION_HEADERS = ("question", "question no", "q no", "qno", "q", "item", "address")
#: Header text that names the marks column in a long sheet.
MARK_HEADERS = ("marks", "mark", "score", "scored", "obtained", "awarded", "got")
#: Values that mean "not attempted", not "zero".
ABSENT_TOKENS = ("ab", "absent", "-", "--", "na", "n/a", "nil")
#: Values that mean the other half of a choice pair was answered.
NOT_OFFERED_TOKENS = ("no", "not offered", "notoffered", "x", "choice")

#: A scanned page carries almost no text. Below this per page it is a photograph.
SCAN_CHARS_PER_PAGE = 25


@dataclass
class ProposedRow:
    """One mark, and everything needed to check it without trusting us."""

    raw_address: str
    address: str | None
    marks: float | None
    state: str
    #: where in the file this came from, in the file's own terms
    origin: str
    raw_value: str
    #: why it cannot be used, when it cannot. Never silently dropped.
    problem: str | None = None
    #: read by text recognition rather than out of the file's own text. Carried all the
    #: way to the screen, because a recognised number and a typed one must never look
    #: alike to the person deciding whether to accept it.
    via_ocr: bool = False
    #: which student's row this was, when the file names one -- blank when the file is
    #: scoped to a single student from the start (no roll column at all), never guessed
    #: at when a roll column exists but this particular row left it blank.
    roll_no: str = ""

    def as_dict(self) -> dict:
        return {
            "via_ocr": self.via_ocr,
            "raw_address": self.raw_address,
            "address": self.address,
            "marks": self.marks,
            "state": self.state,
            "origin": self.origin,
            "raw_value": self.raw_value,
            "problem": self.problem,
            "roll_no": self.roll_no,
        }


@dataclass
class Reading:
    rows: list[ProposedRow] = field(default_factory=list)
    #: the roll numbers the file mentions, in order of first appearance
    rolls: list[str] = field(default_factory=list)
    source: str = ""
    problems: list[str] = field(default_factory=list)
    #: set when the file cannot be read at all, rather than read badly
    refused: str | None = None
    #: set when the text came from recognition rather than from the file
    used_ocr: bool = False


def _clean(cell: object) -> str:
    return normalise_numerals(str(cell if cell is not None else "")).strip()


def _header_kind(text: str) -> str | None:
    key = _clean(text).lower().strip(".:")
    if key in ROLL_HEADERS:
        return "roll"
    if key in QUESTION_HEADERS:
        return "question"
    if key in MARK_HEADERS:
        return "marks"
    return None


def parse_address(text: str) -> tuple[str | None, str]:
    """A written question label, as an address string, or a reason it is not one.

    Deliberately permissive about how it is written -- ``Q16(b)``, ``16 b``, ``B/16//b``
    all mean the same question -- and completely rigid about what it produces, because the
    address is later checked against the frozen Q-matrix and an address that parses into
    something plausible but wrong is worse than one that does not parse.
    """
    raw = _clean(text)
    if not raw:
        return None, "blank"

    #: already an address, as this system writes them: SECTION/NO/SUB/ALT
    if raw.count("/") == 3:
        return raw, ""

    body = normalise(raw)
    section = None
    # 'B 16(b)' or 'B/16(b)': a leading single letter is the section
    lead = re.match(r"^([A-Ea-e])[\s/\-.]+(.+)$", body)
    if lead:
        section, body = lead.group(1).upper(), lead.group(2)
    body = re.sub(r"^(?:q|que|question|item)\s*[.:\-]?\s*", "", body, flags=re.IGNORECASE)

    parsed = Address.parse(body, section=section)
    if parsed is None:
        return None, f"{raw!r} is not a question number"
    return str(parsed), ""


def parse_value(text: str) -> tuple[float | None, str, str | None]:
    """(marks, state, problem). A value that is not a number is never guessed at."""
    raw = _clean(text)
    low = raw.lower().strip(".")
    if not raw:
        return None, "blank", None
    if low in ABSENT_TOKENS:
        return None, "absent", None
    if low in NOT_OFFERED_TOKENS:
        return None, "not_offered", None
    # '3/5' means three out of five: the mark is the numerator
    fraction = re.match(r"^(\d+(?:\.\d+)?)\s*/\s*\d+(?:\.\d+)?$", raw)
    if fraction:
        return float(fraction.group(1)), "awarded", None
    try:
        return float(raw), "awarded", None
    except ValueError:
        return None, "blank", f"{raw!r} is not a mark"


def _rows_from_table(table: list[list[str]], source: str) -> Reading:
    """One parser for both shapes, because the difference is only where the labels are."""
    out = Reading(source=source)
    if not table:
        out.refused = "the file has no rows"
        return out

    header_index, header = None, []
    for i, row in enumerate(table[:10]):
        kinds = [_header_kind(c) for c in row]
        if "marks" in kinds or "question" in kinds or "roll" in kinds:
            header_index, header = i, row
            break
        # a wide sheet's header is question labels, which are not words we know
        parsed = [parse_address(c)[0] for c in row]
        if sum(1 for p in parsed if p) >= 2:
            header_index, header = i, row
            break

    if header_index is None:
        out.refused = (
            "no header row was found. The sheet needs either a question column and a marks "
            "column, or one column per question."
        )
        return out

    kinds = [_header_kind(c) for c in header]
    body = table[header_index + 1 :]

    if "marks" in kinds and ("question" in kinds or "address" in [_clean(c).lower() for c in header]):
        # --- long: one row per mark ---
        q_col = kinds.index("question")
        m_col = kinds.index("marks")
        r_col = kinds.index("roll") if "roll" in kinds else None
        for n, row in enumerate(body, start=header_index + 2):
            if not any(_clean(c) for c in row):
                continue
            raw_q = row[q_col] if q_col < len(row) else ""
            raw_v = row[m_col] if m_col < len(row) else ""
            roll = ""
            if r_col is not None and r_col < len(row):
                roll = _clean(row[r_col])
                if roll and roll not in out.rolls:
                    out.rolls.append(roll)
            address, why = parse_address(raw_q)
            marks, state, problem = parse_value(raw_v)
            if not _clean(raw_q):
                continue
            out.rows.append(ProposedRow(
                raw_address=_clean(raw_q), address=address, marks=marks, state=state,
                origin=f"row {n}", raw_value=_clean(raw_v), problem=why or problem or None,
                roll_no=roll,
            ))
        return out

    # --- wide: one row per student, one column per question ---
    columns: list[tuple[int, str, str]] = []
    ignored: list[str] = []
    for i, cell in enumerate(header):
        if _header_kind(cell) == "roll":
            continue
        address, _ = parse_address(cell)
        if address:
            columns.append((i, _clean(cell), address))
        elif _clean(cell):
            ignored.append(_clean(cell))
    if ignored:
        # Named, not dropped in silence. A 'Total' column belongs here; so does a heading
        # text recognition misread, and the difference is obvious to whoever is looking at
        # the sheet but invisible from a shorter list of results.
        out.problems.append(
            "these headings were not read as questions, so their columns were left out: "
            + ", ".join(repr(c) for c in ignored)
        )
    if not columns:
        out.refused = (
            "the header names no questions. Label each column with its question number, "
            "or use a question column and a marks column."
        )
        return out

    # None, not a guessed column 0: a sheet with no column actually headed "roll" (or
    # "reg", "admission", ...) names no student at all, and treating its first column as
    # one anyway is how a mark ends up filed under a roll number nobody wrote down.
    roll_col = kinds.index("roll") if "roll" in kinds else None
    for n, row in enumerate(body, start=header_index + 2):
        if not any(_clean(c) for c in row):
            continue
        roll = _clean(row[roll_col]) if roll_col is not None and roll_col < len(row) else ""
        if roll and roll not in out.rolls:
            out.rolls.append(roll)
        for i, label, address in columns:
            raw_v = row[i] if i < len(row) else ""
            if not _clean(raw_v):
                continue
            marks, state, problem = parse_value(raw_v)
            out.rows.append(ProposedRow(
                raw_address=label, address=address, marks=marks, state=state,
                origin=f"row {n}, column {label}" + (f", roll {roll}" if roll else ""),
                raw_value=_clean(raw_v), problem=problem, roll_no=roll,
            ))
    return out


def read_csv(data: bytes, source: str = "csv") -> Reading:
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return _rows_from_table([list(r) for r in csv.reader(io.StringIO(text), dialect)], source)


def read_xlsx(data: bytes, source: str = "spreadsheet") -> Reading:
    try:
        import openpyxl  # noqa: PLC0415
    except ModuleNotFoundError:  # pragma: no cover - install-time, not runtime
        out = Reading(source=source)
        out.refused = "this deployment cannot read .xlsx files. Save the sheet as CSV."
        return out

    book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheet = book.worksheets[0]
    table = [[_clean(c) for c in row] for row in sheet.iter_rows(values_only=True)]
    book.close()
    reading = _rows_from_table(table, source)
    if len(book.worksheets) > 1:
        reading.problems.append(
            f"the workbook has {len(book.worksheets)} sheets; only the first "
            f"({sheet.title!r}) was read"
        )
    return reading


#: Two words whose tops differ by less than this are on the same printed line.
ROW_TOLERANCE = 6.0
#: Two words starting within this many points of each other are in the same column.
COLUMN_TOLERANCE = 18.0


def table_from_words(words: list[tuple]) -> list[list[str]]:
    """Rebuild a printed table from positioned words.

    A PDF has no rows and no columns, only glyphs at coordinates. Reading it as lines of
    text and splitting on runs of whitespace looks reasonable and does not work: PyMuPDF
    emits each cell of a table on its own line, so a five-column mark sheet arrives as five
    one-word lines and every row is lost.

    So the grid is recovered from the geometry. Words sharing a baseline are a row;
    x-positions that recur down the page are a column. That is what a person reading the
    sheet does, and unlike counting whitespace it survives columns one space apart.
    """
    if not words:
        return []

    rows: list[list[tuple]] = []
    for word in sorted(words, key=lambda w: (round(w[1], 1), w[0])):
        if rows and abs(rows[-1][0][1] - word[1]) <= ROW_TOLERANCE:
            rows[-1].append(word)
        else:
            rows.append([word])

    # Column anchors: every x a word starts at, merged when near enough to be one column,
    # then used as the grid for every row.
    anchors: list[float] = []
    for x in sorted(w[0] for row in rows for w in row):
        if not anchors or x - anchors[-1] > COLUMN_TOLERANCE:
            anchors.append(x)

    table: list[list[str]] = []
    for row in rows:
        cells = [""] * len(anchors)
        for word in sorted(row, key=lambda w: w[0]):
            i = min(range(len(anchors)), key=lambda j: abs(anchors[j] - word[0]))
            cells[i] = f"{cells[i]} {word[4]}".strip()
        table.append(cells)
    return table


def ocr_available() -> bool:
    """Whether text recognition can run here.

    A capability, not an assumption: Tesseract is a system binary, so a deployment either
    has it or does not, and the difference has to reach the person uploading rather than
    surfacing as an empty result.
    """
    return shutil.which("tesseract") is not None


def _ocr_words(page) -> list[tuple]:
    """Recognised words with their positions, so the same grid logic applies."""
    textpage = page.get_textpage_ocr(dpi=OCR_DPI, full=True)
    return page.get_text("words", textpage=textpage)


def read_pdf(path: Path, source: str = "pdf", *, allow_ocr: bool = True) -> Reading:
    """A PDF, whether its text is in the file or has to be recognised.

    Text already in the file is exact. Text that had to be recognised is a proposal, and
    is marked as one all the way to the screen: on a real scan Tesseract reads ``Q1`` as
    ``Qi`` often enough that treating the two alike would be dishonest.
    """
    import pymupdf  # noqa: PLC0415

    out = Reading(source=source)
    table: list[list[str]] = []
    with pymupdf.open(path) as doc:
        pages = doc.page_count
        characters, images = 0, 0
        for page in doc:
            words = page.get_text("words")
            characters += sum(len(w[4]) for w in words)
            images += len(page.get_images(full=True))
            table.extend(table_from_words(words))

        scanned = bool(pages) and characters < SCAN_CHARS_PER_PAGE * pages and images >= pages
        if scanned:
            if not (allow_ocr and ocr_available()):
                out.refused = (
                    "this PDF is a picture of a page rather than a document with text in "
                    "it, and text recognition is not available on this deployment. Rescan "
                    "it with the scanner's text recognition turned on, or send the marks "
                    "as a spreadsheet."
                )
                return out
            table = []
            for page in doc:
                table.extend(table_from_words(_ocr_words(page)))
            out.used_ocr = True

    reading = _rows_from_table(table, source)
    reading.used_ocr = out.used_ocr
    if out.used_ocr:
        for row in reading.rows:
            row.via_ocr = True
        if reading.refused:
            # Recognition ran and found nothing usable. Say that, rather than the generic
            # "no header row", which sends somebody to fix a header that is perfectly fine
            # on the paper in front of them.
            reading.refused = (
                "text recognition read this page but could not find a marks table in it: "
                + reading.refused
                + " Handwriting in particular is not something it can read."
            )
    return reading


def read_any(filename: str, data: bytes, path: Path | None = None) -> Reading:
    """Dispatch on the file, and refuse by name what cannot be read."""
    suffix = (filename or "").rsplit(".", 1)[-1].lower()
    if suffix in ("csv", "tsv", "txt"):
        return read_csv(data, source=filename or "csv")
    if suffix in ("xlsx", "xlsm"):
        return read_xlsx(data, source=filename or "spreadsheet")
    if suffix == "xls":
        out = Reading(source=filename)
        out.refused = (
            "this is the old Excel format, which cannot be read here. Open it and save as "
            ".xlsx or CSV."
        )
        return out
    if suffix == "pdf" and path is not None:
        return read_pdf(path, source=filename or "pdf")
    out = Reading(source=filename or "file")
    out.refused = (
        f"a {suffix or 'file'} of this kind cannot be read for marks. Upload a CSV, an "
        f".xlsx sheet, or a PDF that has text in it."
    )
    return out
