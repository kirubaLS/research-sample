"""Pydantic contracts. The boundary between every stage of the pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


# --- use case 1 -----------------------------------------------------------------------
class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    roll_no: str = Field(min_length=1, max_length=16)
    grade: int = 10
    section: str = "A"
    age: int | None = Field(default=None, ge=8, le=25)
    gender: str | None = None
    locale: str = "en"

    @field_validator("gender")
    @classmethod
    def _gender(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"female", "male", "other", "prefer_not_to_say"}
        if v.lower() not in allowed:
            raise ValueError(f"gender must be one of {sorted(allowed)}")
        return v.lower()


class SessionOut(BaseModel):
    session_id: str
    locale: str
    total_items: int
    screens: list[list[dict]]


class ResponseIn(BaseModel):
    item_id: str
    value: int = Field(ge=1, le=5)
    shown_at: float | None = None     # epoch seconds, from the client
    answered_at: float | None = None


class ResponseBatchIn(BaseModel):
    responses: list[ResponseIn]


class CompletionOut(BaseModel):
    """Deliberately carries no score, code or stream. The student journey ends here."""

    message: str
    submitted: int


# --- use case 2 -----------------------------------------------------------------------
class AssessmentIn(BaseModel):
    subject_code: str
    title: str
    paper_code: str | None = None
    total_marks: float | None = None
    curriculum_version: str = "CBSE-2026-27"
    declared: dict | None = None


class QuestionIn(BaseModel):
    section: str | None = None
    question_no: str
    sub_part: str | None = None
    choice_alt: str | None = None
    max_marks: float = Field(gt=0)
    mark_step: float = 1.0
    question_type: str | None = None
    stem_text: str | None = None
    skills: list[str] = Field(default_factory=list)
    logical_page: int | None = None


class QuestionBatchIn(BaseModel):
    questions: list[QuestionIn]
    section_arithmetic: dict[str, list[float]] | None = None


class MarkIn(BaseModel):
    student_roll: str
    address: str
    marks: float | None = None
    state: str = "awarded"
    confidence: float = 1.0
    source: str = "teacher"

    @field_validator("state")
    @classmethod
    def _state(cls, v: str) -> str:
        if v not in {"awarded", "absent", "not_offered"}:
            raise ValueError("state must be awarded | absent | not_offered")
        return v


class MarkBatchIn(BaseModel):
    section: str = "A"
    marks: list[MarkIn]


class ReconcileIn(BaseModel):
    student_roll: str
    #: address -> {value: probability}
    distributions: dict[str, dict[str, float]]
    grand_total: float | None = None
    section_totals: dict[str, float] | None = None
