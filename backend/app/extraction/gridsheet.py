"""Reading a class mark-entry sheet: one photograph, many students.

A school that marks by hand often keeps one sheet per section rather than one script per
student -- rows are students, columns are questions, and a cell is a mark in a teacher's
hand. Nothing here can read handwriting the way ``marksheet.py`` reads a printed table:
Tesseract already refuses that job by name, because misreading a printed digit and
misreading a handwritten one are different kinds of wrong. A model that has actually been
shown handwritten digits does the reading instead -- but every cell it returns is still a
proposal, never an assertion: checked against the paper, matched to a student, and
confirmed by a person, exactly as any other reading in this codebase is.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel


@dataclass
class GridCell:
    question_label: str
    raw_value: str


@dataclass
class GridRow:
    roll_no: str
    name_as_written: str
    cells: list[GridCell] = field(default_factory=list)


@dataclass
class GridReading:
    rows: list[GridRow] = field(default_factory=list)
    #: set when nothing usable could be read at all, rather than read badly
    refused: str | None = None
    problems: list[str] = field(default_factory=list)


class _CellOut(BaseModel):
    question_label: str
    raw_value: str


class _RowOut(BaseModel):
    roll_no: str
    name_as_written: str = ""
    cells: list[_CellOut] = []


class _SheetOut(BaseModel):
    rows: list[_RowOut] = []


SYSTEM = (
    "You are reading a handwritten class mark-entry sheet: a grid with one row per "
    "student and one column per question number. Roll numbers and question labels are "
    "printed; marks are handwritten. Read exactly what is written in each cell -- do not "
    "compute totals, do not carry a value from a neighbouring cell, and do not guess a "
    "value you cannot make out. For a cell you cannot read, return raw_value as an empty "
    "string rather than a guess. Read the student's name exactly as written, spelling and "
    "all -- it is used only to double check the roll number, never in place of it."
)


class GridReader(Protocol):
    def read(self, pages: list[tuple[bytes, str]]) -> GridReading: ...


class AnthropicGridReader:
    """One call, one sheet, structured output -- the same shape as the other Anthropic
    call in this codebase (``app.classify.anthropic_judge.AnthropicJudge``), because
    reading a photograph accurately is exactly as uncertain as classifying a question, and
    both get the same discipline: a person confirms before anything counts.
    """

    def __init__(self, api_key: str, model: str = "claude-opus-5") -> None:
        if not api_key:
            raise ValueError(
                "no Anthropic API key. Set YAADHUM_ANTHROPIC_API_KEY. Without it a "
                "handwritten mark-entry sheet cannot be read at all -- send a spreadsheet "
                "or one script per student instead."
            )
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def read(self, pages: list[tuple[bytes, str]]) -> GridReading:
        content: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": content_type,
                    "data": base64.b64encode(data).decode(),
                },
            }
            for data, content_type in pages
        ]
        content.append({
            "type": "text",
            "text": "Read every student row on this mark-entry sheet.",
        })
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=8000,
            system=SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_format=_SheetOut,
        )
        parsed: _SheetOut = response.parsed_output
        out = GridReading()
        for row in parsed.rows:
            roll = row.roll_no.strip()
            if not roll:
                continue
            out.rows.append(GridRow(
                roll_no=roll,
                name_as_written=row.name_as_written.strip(),
                cells=[
                    GridCell(c.question_label.strip(), c.raw_value.strip())
                    for c in row.cells if c.question_label.strip()
                ],
            ))
        if not out.rows:
            out.refused = "nothing readable as a mark-entry sheet was found in the image(s) sent"
        return out


def read_grid(
    pages: list[tuple[bytes, str]],
    *,
    api_key: str | None,
    model: str = "claude-opus-5",
) -> GridReading:
    """Dispatch to the vision reader, or refuse by name when there is none configured."""
    if not api_key:
        out = GridReading()
        out.refused = (
            "no Anthropic API key is configured, so a handwritten mark-entry sheet cannot "
            "be read. Send a spreadsheet, or one script per student, instead."
        )
        return out
    return AnthropicGridReader(api_key, model).read(pages)
