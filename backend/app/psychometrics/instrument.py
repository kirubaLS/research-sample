"""The RIASEC item bank: 36 items, six per scale, bilingual-plus.

Six items per scale is the shortest length that reaches acceptable internal consistency.
At two or three items per scale — the "15 to 20 questions" temptation — roughly half the
variance in a student's score is measurement noise, and a stream recommendation built on
that would not survive one sceptical parent.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

SCALES = ("R", "I", "A", "S", "E", "C")
#: Holland's hexagon: adjacency encodes how compatible two interest types are
HEXAGON = ("R", "I", "A", "S", "E", "C")


@dataclass(frozen=True)
class Item:
    id: str
    scale: str
    text: dict[str, str]

    def localised(self, locale: str) -> str:
        return self.text.get(locale) or self.text["en"]


@lru_cache(maxsize=1)
def _raw() -> dict:
    return json.loads((DATA / "riasec_items.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def items() -> list[Item]:
    return [Item(i["id"], i["scale"], i["text"]) for i in _raw()["items"]]


@lru_cache(maxsize=1)
def item_index() -> dict[str, Item]:
    return {i.id: i for i in items()}


@lru_cache(maxsize=1)
def reverse_pairs() -> list[tuple[str, str]]:
    return [tuple(p) for p in _raw()["reverse_pairs"]]


@lru_cache(maxsize=1)
def likert() -> dict:
    return _raw()["likert"]


@lru_cache(maxsize=1)
def stream_matrix() -> dict[str, dict[str, float]]:
    return json.loads((DATA / "stream_matrix.json").read_text(encoding="utf-8"))["streams"]


def ordered_items(seed: int) -> list[Item]:
    """Scale-interleaved order with a fixed per-student seed.

    Interleaving prevents block effects; the fixed seed makes a session reproducible for
    audit, which matters when a parent asks why their child saw a particular question.
    """
    by_scale: dict[str, list[Item]] = {s: [] for s in SCALES}
    for it in items():
        by_scale[it.scale].append(it)
    rng = random.Random(seed)
    for s in SCALES:
        rng.shuffle(by_scale[s])

    out: list[Item] = []
    depth = max(len(v) for v in by_scale.values())
    scales = list(SCALES)
    for d in range(depth):
        rng.shuffle(scales)
        for s in scales:
            if d < len(by_scale[s]):
                out.append(by_scale[s][d])
    return out


def screens(seed: int, per_screen: int = 6) -> list[list[Item]]:
    seq = ordered_items(seed)
    return [seq[i : i + per_screen] for i in range(0, len(seq), per_screen)]
