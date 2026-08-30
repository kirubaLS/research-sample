"""Embedding the knowledge base, and turning distance into a familiarity level.

Two things are deliberately separated. `Embedder` is a narrow protocol so the provider is
swappable -- a hosted API today, a local model later, without touching the callers. And the
similarity thresholds are configuration rather than constants, because they are the one
part of this that cannot be derived from first principles: what counts as "practised"
versus "adapted" is an empirical question, and the honest default is to abstain rather
than guess.

What may be sent to a hosted embedder: the NCERT book (public content) and question stems
(not personal data). What may never be: a student's answer script. That boundary is the
reason `embed_texts` takes plain strings and this module has no access to the marks tables.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol


class Embedder(Protocol):
    """Anything that turns text into vectors. One method, so a stub is trivial."""

    #: identifies the vectors in storage -- vectors from different models are not comparable
    model: str
    dimensions: int

    def embed_texts(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        """Embed a batch.

        ``is_query`` matters for asymmetric models, which encode a short question
        differently from a long passage; a provider that does not distinguish ignores it.
        """
        ...


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# --- familiarity ----------------------------------------------------------------------

#: The four levels the tier table reads (app.taxonomy.tier). T_VERBATIM is decided by an
#: exact hash against canonical_procedure and never by distance -- "is this literally
#: Theorem 1.3?" is a yes/no question, and answering it with a threshold would make it
#: tunable, which it should not be.
FAMILIARITY_LEVELS = ("T_VERBATIM", "PRACTISED", "ADAPTED", "NOVEL")


@dataclass(frozen=True)
class FamiliarityThresholds:
    """Cosine similarity boundaries. Provisional until measured on real papers.

    These are the project's only unvalidated numbers, so they are named, defaulted
    conservatively, and carry an abstention band rather than being buried as literals.
    """

    practised: float = 0.72     # close enough to a book item to call it drilled
    adapted: float = 0.50       # recognisably the same method, different dress
    #: within this distance of a boundary, do not decide -- abstain and let a human or the
    #: paper's blueprint settle it, exactly as the tier engine already abstains
    margin: float = 0.04


@dataclass(frozen=True)
class FamiliarityCall:
    level: str | None           # None => abstained
    similarity: float
    nearest_reference: str
    nearest_bucket: str
    reason: str


def classify_familiarity(
    similarity: float,
    nearest_reference: str,
    nearest_bucket: str,
    thresholds: FamiliarityThresholds | None = None,
) -> FamiliarityCall:
    """Distance to the nearest book chunk, as a familiarity level.

    Abstains near a boundary instead of committing. A wrong familiarity produces a wrong
    Competency Tier, which is a field a teacher acts on -- so silence is cheaper than a
    confident mistake.
    """
    t = thresholds or FamiliarityThresholds()

    for boundary in (t.practised, t.adapted):
        if abs(similarity - boundary) < t.margin:
            return FamiliarityCall(
                None, similarity, nearest_reference, nearest_bucket,
                f"similarity {similarity:.2f} sits within {t.margin} of the "
                f"{boundary} boundary -- too close to call",
            )

    if similarity >= t.practised:
        # bucket E is the exercises: drilled. bucket T is chapter body: taught.
        level = "PRACTISED" if nearest_bucket == "E" else "T_VERBATIM"
        return FamiliarityCall(
            level, similarity, nearest_reference, nearest_bucket,
            f"closely matches {nearest_reference}",
        )
    if similarity >= t.adapted:
        return FamiliarityCall(
            "ADAPTED", similarity, nearest_reference, nearest_bucket,
            f"recognisably {nearest_reference}, in an unfamiliar setting",
        )
    return FamiliarityCall(
        "NOVEL", similarity, nearest_reference, nearest_bucket,
        f"nothing in the book is closer than {nearest_reference} at {similarity:.2f}",
    )
