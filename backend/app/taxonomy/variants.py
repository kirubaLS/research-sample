"""Concept Variant reuse guard.

Concept Family is held constant across test cycles so improvement is comparable; Concept
Variant must change, so that a rising score means learning rather than recognition.

A schema cannot hold that contract on its own. If a variant is reused, nothing errors --
the class simply scores better, and the improvement is indistinguishable from real
learning by the time it reaches a report. That is why this is a block at paper
registration and not a warning: a warning gets clicked past, and the resulting number is
confidently wrong rather than missing.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

#: digits carry the variation between two questions of the same family ("cone + hemisphere,
#: r = 3.5" vs "r = 7"), so normalisation must NOT strip them -- only presentation noise.
_WHITESPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s.]", re.UNICODE)


def normalise_stem(text: str) -> str:
    """Fold presentation differences, keep everything that makes the question different."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    folded = _PUNCT.sub(" ", folded)
    return _WHITESPACE.sub(" ", folded).strip()


def variant_hash(text: str) -> str:
    return hashlib.sha256(normalise_stem(text).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ServedVariant:
    """A (family, variant) already put in front of this section in an earlier cycle."""

    family_id: str
    variant_hash: str
    assessment_id: str
    assessment_title: str
    question_no: str


@dataclass(frozen=True)
class Reuse:
    question_no: str
    family_id: str
    previously_in: str
    previously_as: str

    def describe(self) -> str:
        return (
            f"Q{self.question_no} repeats a question already served to this class in "
            f"{self.previously_in!r} (as Q{self.previously_as}). Same concept family is "
            f"correct; the same variant is not -- an improved score here would measure "
            f"familiarity, not learning."
        )


class VariantReuseError(Exception):
    """Raised at registration. Carries every repeat, so a paper is fixed in one pass."""

    def __init__(self, reuses: list[Reuse]):
        self.reuses = reuses
        super().__init__(
            f"{len(reuses)} question(s) repeat a variant this class has already seen:\n"
            + "\n".join(f"  - {r.describe()}" for r in reuses)
        )


def check_paper(
    questions: list[tuple[str, str, str]],
    already_served: list[ServedVariant],
) -> list[Reuse]:
    """Return every reuse in a paper.

    ``questions``    (question_no, family_id, variant_hash) for the paper being registered
    ``already_served`` what this section has been given before

    Reported rather than raised so a caller can render all of them at once; use
    ``enforce`` for the registration path.
    """
    seen = {(s.family_id, s.variant_hash): s for s in already_served}
    reuses: list[Reuse] = []
    for question_no, family_id, vhash in questions:
        prior = seen.get((family_id, vhash))
        if prior is not None:
            reuses.append(
                Reuse(
                    question_no=question_no,
                    family_id=family_id,
                    previously_in=prior.assessment_title,
                    previously_as=prior.question_no,
                )
            )
    return reuses


def check_internal_duplicates(questions: list[tuple[str, str, str]]) -> list[Reuse]:
    """A paper that asks the same variant twice inflates that family's weight silently."""
    first: dict[tuple[str, str], str] = {}
    reuses: list[Reuse] = []
    for question_no, family_id, vhash in questions:
        key = (family_id, vhash)
        if key in first:
            reuses.append(
                Reuse(
                    question_no=question_no,
                    family_id=family_id,
                    previously_in="this same paper",
                    previously_as=first[key],
                )
            )
        else:
            first[key] = question_no
    return reuses


def enforce(
    questions: list[tuple[str, str, str]],
    already_served: list[ServedVariant],
) -> None:
    """Block registration if any variant repeats. The whole point of the module."""
    reuses = check_paper(questions, already_served) + check_internal_duplicates(questions)
    if reuses:
        raise VariantReuseError(reuses)
