"""Apply review_flag_rule offline to the placements already stored for one paper.

READ-ONLY. For each question it takes the latest placement row (what the review screen
shows today) and asks, condition by condition, whether the six-reason rule
(app.classify.review_rule) would flag it -- using only what the row stores. An input the
row does not store is reported as unknown rather than guessed:

  judge_failed      the reasoning starts with the failed-judge text            stored
  cross_scope       the cross_scope column, or the cross-scope reasoning text  stored
  family            the unsettled / blocked family message in the reasoning    stored
  low_confidence    needs the chapter judge's OWN confidence and the number of
                    chapters it was shown. The row stores the reconciled
                    confidence (the judge's own unless the blueprint moved the
                    question) and only the chosen chapter, so: >= 0.7 is a known
                    no; below 0.7, or a blueprint row, is unknown
  topic_differs     needs in-chapter retrieval's section and answerability's
                    verdict. The reasoning carries "Retrieval within the chapter
                    pointed at section N" only when the two disagreed and were
                    not settled, and answerability's verdict only when it failed
                    or switched sections: a note present without a verdict is
                    unknown; no note is a no (see INFERRED below)
  topic_unverified  the "no section of the chapter answers" note (written
                    exactly when answerability verified nothing) or the
                    topic judge's fallback text                               stored

INFERRED: "no disagreement note" is read as topic_differs = no. That holds unless the
answerability check itself failed for a question whose confirming re-read agreed with the
judge -- a case no stored text distinguishes.

    python -m scripts.replay_review_flags --assessment <id>

Run it against a staging copy of the database, never production.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter

from sqlalchemy import select

YES, NO, UNKNOWN = "yes", "no", "unknown"
CONDITIONS = (
    "judge_failed", "cross_scope", "family", "low_confidence", "topic_differs",
    "topic_unverified",
)

_FAILED = "the reading model's answer for this question was invalid"
_CROSSED = "no chapter in the declared scope can answer this question"
_UNSETTLED = re.compile(r"\d+ families of .+ draw on section ")
_BLOCKED = re.compile(r"no concept family exists for |families exist for .+ and none claims ")
_POINTED = "Retrieval within the chapter pointed at section"
_NONE_ANSWERS = "no section of the chapter answers this question from its own text"
_VERIFIED = ("can, and was taken", "the judge found it answered in section")
_TOPIC_FALLBACK = ("the topic judge could not be asked", "the topic judge found no")
_PROVISIONAL = "provisional: the classify step queued behind this map decides the topic"
_HELD = "Not applied: a person settled this question."
_MAP_ROW = re.compile(r"^(?:\w+ retrieval, margin |no book evidence of its own)")


def replay_row(reasoning: str | None, *, confidence: float | None, source: str,
               cross_scope: bool | None) -> dict[str, str]:
    """condition -> yes / no / unknown for one stored placement row, plus "verdict":
    flagged (some condition is yes), not flagged (every condition is no), or unknown."""
    text = reasoning or ""
    if text.startswith(_HELD):
        # a person settled it; the run changed nothing and flags nothing
        return {c: NO for c in CONDITIONS} | {"verdict": "not flagged"}
    map_row = bool(_MAP_ROW.match(text))
    #: the notes are sentence-cased when joined into the rationale; match without case
    low = text.lower()
    out: dict[str, str] = {}
    out["judge_failed"] = YES if text.startswith(_FAILED) else NO
    out["cross_scope"] = YES if (cross_scope or _CROSSED in text) else NO
    out["family"] = YES if (_UNSETTLED.search(text) or _BLOCKED.search(text)) else NO

    if map_row or out["judge_failed"] == YES:
        out["low_confidence"] = NO                     # no chapter judge was asked
    elif source == "blueprint" or confidence is None:
        out["low_confidence"] = UNKNOWN                # the judge's own confidence is lost
    elif confidence >= 0.7:
        out["low_confidence"] = NO
    else:
        out["low_confidence"] = UNKNOWN                # chapters shown are not stored

    topic = "Topic " in text or any(f in low for f in _TOPIC_FALLBACK)
    if not topic or _PROVISIONAL in text:
        out["topic_differs"] = out["topic_unverified"] = NO
    else:
        unverified = _NONE_ANSWERS in low or any(f in low for f in _TOPIC_FALLBACK)
        out["topic_unverified"] = YES if unverified else NO
        if any(f in low for f in _TOPIC_FALLBACK):
            out["topic_differs"] = NO                  # no judge section to differ
        elif _POINTED.lower() not in low:
            out["topic_differs"] = NO                  # INFERRED, see the module docstring
        elif _NONE_ANSWERS in low:
            out["topic_differs"] = YES                 # differs, and verified False
        elif any(v in low for v in _VERIFIED):
            out["topic_differs"] = NO                  # verified True
        else:
            out["topic_differs"] = UNKNOWN             # verified None, or silently True
    values = [out[c] for c in CONDITIONS]
    out["verdict"] = (
        "flagged" if YES in values else "not flagged" if all(v == NO for v in values)
        else "unknown"
    )
    return out


def main(argv: list[str] | None = None) -> int:
    from app.db import SessionLocal
    from app.models import Question, QuestionPlacement

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--assessment", required=True)
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        questions = {q.id: q for q in db.scalars(
            select(Question).where(Question.assessment_id == args.assessment))}
        latest: dict[str, QuestionPlacement] = {}
        for row in db.scalars(select(QuestionPlacement).where(
            QuestionPlacement.question_id.in_(list(questions) or [""]),
        ).order_by(QuestionPlacement.created_at, QuestionPlacement.id)):
            latest[row.question_id] = row
        print("READ-ONLY -- nothing will be written")
        print(f"assessment {args.assessment}: {len(questions)} questions, "
              f"{len(latest)} with a placement row\n")
        print(f"{'question':<14} {'today':<7} {'new rule':<12} "
              + " ".join(f"{c:<16}" for c in CONDITIONS))
        verdicts: Counter = Counter()
        today = 0
        for qid, q in sorted(questions.items(), key=lambda kv: kv[1].address):
            row = latest.get(qid)
            if row is None:
                print(f"{q.address:<14} {'-':<7} {'no row':<12}")
                continue
            if row.source == "human":
                r = {c: NO for c in CONDITIONS} | {"verdict": "not flagged"}
            else:
                r = replay_row(row.reasoning, confidence=row.confidence, source=row.source,
                               cross_scope=row.cross_scope)
            today += bool(row.needs_review)
            verdicts[r["verdict"]] += 1
            print(f"{q.address:<14} {'yes' if row.needs_review else 'no':<7} "
                  f"{r['verdict']:<12} " + " ".join(f"{r[c]:<16}" for c in CONDITIONS))
        print(f"\nTODAY flagged {today}; NEW RULE flagged {verdicts['flagged']}, "
              f"not flagged {verdicts['not flagged']}, unknown {verdicts['unknown']}")
    finally:
        db.rollback()
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
