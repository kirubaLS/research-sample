"""Bloom action lexicon.

The lexicon deliberately does NOT output a tier. It outputs an *action class*, because
Bloom level is a function of action AND familiarity: "Applying" means carrying out a known
procedure in a new situation, so the same verb is Remembering when the exact task was
taught and memorised.

That is the fix for the trap: "Prove that root 5 is an irrational number" carries the verb
PROVE, but it is a named theorem in the NCERT chapter body, so its real demand is
reproduction.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "verb_lexicon.json"

ACTIONS = (
    "RECALL",
    "EXPLAIN",
    "EXECUTE",
    "PROVE",
    "APPLY_IN_CONTEXT",
    "ANALYSE_EVALUATE_CREATE",
)

#: when several actions fire, the strongest cognitive demand wins
ACTION_PRIORITY = {
    "RECALL": 0,
    "EXPLAIN": 1,
    "EXECUTE": 2,
    "PROVE": 3,
    "APPLY_IN_CONTEXT": 4,
    "ANALYSE_EVALUATE_CREATE": 5,
}


@lru_cache(maxsize=1)
def _lexicon() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class ActionMatch:
    action: str
    trigger: str
    locale: str


def detect_actions(stem: str) -> list[ActionMatch]:
    """All action classes whose triggers appear in the stem, any supported script."""
    text = " ".join((stem or "").lower().split())
    hits: list[ActionMatch] = []
    for action, by_locale in _lexicon()["actions"].items():
        for locale, triggers in by_locale.items():
            for trig in triggers:
                needle = trig.lower()
                if locale == "en":
                    pattern = r"\b" + re.escape(needle) + r"\b"
                    found = re.search(pattern, text) is not None
                else:
                    found = needle in text
                if found:
                    hits.append(ActionMatch(action, trig, locale))
                    break
    return hits


def primary_action(stem: str) -> str | None:
    """The strongest action class present, or None when nothing matches."""
    hits = detect_actions(stem)
    if not hits:
        return None
    return max(hits, key=lambda h: ACTION_PRIORITY[h.action]).action
