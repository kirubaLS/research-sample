"""What a teacher has already confirmed, recalled for the next paper.

Past-year, sample and school papers repeat and rephrase one another heavily, and every
placement a person has confirmed is a free, correct label for the question it was made on.
This module turns those labels into three things, all without a model call:

* **reuse** -- a question that is, to within a few words, one already confirmed in the same
  school, with every close neighbour agreeing on the chapter, takes that placement and
  neither judge is asked (``Recall.reusable``);
* **demonstrations** -- the nearest confirmed questions go into the chapter judge's prompt as
  worked examples, which beats a fixed prompt because they are the school's own convention
  (``QuestionMemory.demonstrations``; the retrieved-demonstration result in KnowTS and
  retrieval-style in-context learning for hierarchical classification);
* **a nearest-neighbour vote** -- the weighted chapter vote over the closest confirmed
  questions, a cheap classifier that improves with every confirmation instead of being
  trained (``Recall.vote``).

Similarity is TF-IDF cosine over the confirmed stems' own words, deterministic and local:
there is no embedding call, so recall costs nothing and never fails. What counts as "the
same question" is a threshold, and it is deliberately high; a wrong reuse is a confident
wrong label that a teacher already signed off once, which is worse than a call.

Only placements a person confirmed are remembered. A machine placement that happens to be
right is not evidence of anything.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

_WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?|[^\W\d_]+", re.IGNORECASE)
#: words that carry no topic and would make every question resemble every other
_STOP = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the this to was "
    "were what which who why how with find given if then than into also any all each both "
    "write state explain give mark marks question answer following whether".split()
)


def tokens(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text or "") if w.lower() not in _STOP]


@dataclass(frozen=True)
class Remembered:
    """One confirmed placement."""

    question_id: str
    stem: str
    chapter: str
    section: str | None = None
    tier: str | None = None


@dataclass(frozen=True)
class Hit:
    entry: Remembered
    similarity: float


@dataclass(frozen=True)
class Recall:
    """The closest confirmed questions to one stem, nearest first."""

    hits: tuple[Hit, ...] = ()
    #: the weighted chapter vote over ``hits`` at or above ``vote_floor``; None when none are
    vote: str | None = None
    #: every hit at or above ``vote_floor`` names the voted chapter
    unanimous: bool = False

    @property
    def best(self) -> Hit | None:
        return self.hits[0] if self.hits else None

    def reusable(self, min_similarity: float) -> Hit | None:
        """The hit to reuse, or None. Reusable only when the nearest question is at least
        ``min_similarity`` close AND every neighbour close enough to vote agrees with it on
        the chapter -- two confirmed near-duplicates in different chapters means the
        question is ambiguous, and an ambiguous question is exactly the one to read."""
        best = self.best
        if best is None or best.similarity < min_similarity:
            return None
        if not self.unanimous or self.vote != best.entry.chapter:
            return None
        return best


@dataclass
class QuestionMemory:
    """TF-IDF over confirmed stems. Build once per run, query once per question."""

    entries: list[Remembered]
    #: neighbours at or above this similarity take part in the chapter vote
    vote_floor: float = 0.5
    #: how many neighbours a recall returns
    k: int = 5
    _idf: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _vectors: list[dict[str, float]] = field(default_factory=list, init=False, repr=False)
    _postings: dict[str, list[int]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        docs = [Counter(tokens(e.stem)) for e in self.entries]
        n = len(docs)
        df: Counter[str] = Counter()
        for d in docs:
            df.update(d.keys())
        self._idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}
        postings: dict[str, list[int]] = defaultdict(list)
        for i, d in enumerate(docs):
            vec = self._weigh(d)
            self._vectors.append(vec)
            for t in vec:
                postings[t].append(i)
        self._postings = dict(postings)

    def __len__(self) -> int:
        return len(self.entries)

    def _weigh(self, counts: Counter[str]) -> dict[str, float]:
        raw = {
            t: (1 + math.log(c)) * self._idf[t] for t, c in counts.items() if t in self._idf
        }
        norm = math.sqrt(sum(v * v for v in raw.values()))
        return {t: v / norm for t, v in raw.items()} if norm else {}

    def recall(self, stem: str, *, exclude: str | None = None) -> Recall:
        """The nearest confirmed questions. ``exclude`` drops one question id -- a question
        must never be recalled from its own confirmation."""
        if not self.entries:
            return Recall()
        # a term the memory has never seen cannot match anything, but it still counts in
        # the query's length, so similarity is measured against the whole stem
        counts = Counter(tokens(stem))
        if not counts:
            return Recall()
        raw = {
            t: (1 + math.log(c)) * self._idf.get(t, 1.0) for t, c in counts.items()
        }
        norm = math.sqrt(sum(v * v for v in raw.values()))
        if not norm:
            return Recall()
        query = {t: v / norm for t, v in raw.items()}
        scores: dict[int, float] = defaultdict(float)
        for t, w in query.items():
            for i in self._postings.get(t, ()):
                scores[i] += w * self._vectors[i][t]
        ranked = sorted(
            ((i, s) for i, s in scores.items()
             if exclude is None or self.entries[i].question_id != exclude),
            key=lambda x: (-x[1], self.entries[x[0]].question_id),
        )[: self.k]
        hits = tuple(Hit(self.entries[i], round(min(s, 1.0), 4)) for i, s in ranked)
        voters = [h for h in hits if h.similarity >= self.vote_floor]
        if not voters:
            return Recall(hits)
        weight: Counter[str] = Counter()
        for h in voters:
            weight[h.entry.chapter] += h.similarity
        vote = weight.most_common(1)[0][0]
        return Recall(hits, vote, unanimous=all(h.entry.chapter == vote for h in voters))

    def demonstrations(
        self, stem: str, n: int, *, min_similarity: float, exclude: str | None = None,
    ) -> list[Hit]:
        """Up to ``n`` confirmed questions worth showing the judge for this stem."""
        return [h for h in self.recall(stem, exclude=exclude).hits
                if h.similarity >= min_similarity][:n]


def demonstration_block(hits: list[Hit], stem_chars: int = 300) -> str:
    """The prompt section for ``hits``; empty when there are none."""
    if not hits:
        return ""
    lines = [
        "",
        "SIMILAR QUESTIONS A TEACHER HAS ALREADY PLACED",
        "(for calibration only -- the book passages decide, and this question may differ)",
    ]
    for i, h in enumerate(hits, 1):
        where = h.entry.chapter + (f", section {h.entry.section}" if h.entry.section else "")
        lines.append(f"({i}) {h.entry.stem.strip()[:stem_chars]}\n    -> {where}")
    return "\n".join(lines)


def load_confirmed(db, *, school_id: str, subject_codes, exclude_assessment: str | None = None,
                   limit: int = 5000) -> QuestionMemory:
    """The school's confirmed placements for ``subject_codes``, as a ``QuestionMemory``.

    A question is confirmed when its latest placement was written by a person and still
    names a chapter and a section. Read-only. Scoped to one school: a question's text is
    not personal data, but one school's review decisions are that school's work.
    """
    from sqlalchemy import select

    from app.models import Assessment, Question, QuestionPlacement, TaxonomyNode
    from app.models.assessment import TIER_ALIASES

    seen: set[str] = set()
    entries: list[Remembered] = []
    stmt = (
        select(Question.id, Question.stem_text, QuestionPlacement, TaxonomyNode.label)
        .join(QuestionPlacement, QuestionPlacement.question_id == Question.id)
        .join(Assessment, Assessment.id == Question.assessment_id)
        .join(TaxonomyNode, TaxonomyNode.id == QuestionPlacement.chapter_id)
        .where(
            Assessment.school_id == school_id,
            Assessment.subject_code.in_(list(subject_codes)),
            Question.stem_text.is_not(None),
        )
        .order_by(Question.id, QuestionPlacement.created_at.desc())
    )
    if exclude_assessment is not None:
        stmt = stmt.where(Assessment.id != exclude_assessment)
    for qid, stem, placement, chapter_label in db.execute(stmt):
        if qid in seen:
            continue                      # only a question's newest placement counts
        seen.add(qid)
        if placement.source != "human" or not placement.curriculum_section:
            continue
        entries.append(Remembered(
            qid, stem, chapter_label, placement.curriculum_section,
            TIER_ALIASES.get(placement.tier, placement.tier),
        ))
        if len(entries) >= limit:
            break
    return QuestionMemory(entries)


def summarise(log: dict[str, dict], remembered: int) -> dict:
    """The run's memory report: how many questions had a near-identical confirmed twin
    (``reusable``), how many took it (``reused``), and where the judge was asked as well,
    how often it named the same chapter."""
    reusable = [e for e in log.values() if e["reusable"]]
    compared = [e for e in reusable if "judge_chapter" in e]
    agreed = sum(1 for e in compared if e["judge_chapter"] == e["chapter"])
    return {
        "remembered": remembered,
        "evaluated": len(log),
        "reusable": len(reusable),
        "reused": sum(1 for e in log.values() if e["reused"]),
        "compared": len(compared),
        "agreed_with_judge": agreed,
        "disagreed_with_judge": len(compared) - agreed,
        "with_demonstrations": sum(1 for e in log.values() if e.get("demos")),
    }
