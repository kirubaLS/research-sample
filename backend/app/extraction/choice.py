"""Internal choice ('attempt any one of (a) / (b)').

Measured: 6 OR blocks in the English paper, 9 in Science, 6 in Social Science, and both
Maths papers use choice across sections B-E.

Two rules fall out, and the second one is the one that protects the diagnosis:

  1. alternatives in a choice group contribute their marks to every total exactly ONCE
  2. the unattempted alternative is NOT_OFFERED, never zero
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from app.extraction.address import Address

#: 'OR' in the scripts we have measured
OR_MARKERS = re.compile(r"^\s*(or|अथवा|अल्लदु|allathu|athava)\s*$", re.IGNORECASE)


def is_or_marker(line: str) -> bool:
    return bool(OR_MARKERS.match((line or "").strip()))


@dataclass
class ChoiceGroup:
    group_id: str
    addresses: list[Address]
    marks: float

    @property
    def size(self) -> int:
        return len(self.addresses)


def group_choices(
    rows: list[tuple[Address, float]],
) -> tuple[dict[str, str], list[ChoiceGroup]]:
    """Group addresses that differ only by ``choice_alt``.

    Returns ``(address_key -> group_id, groups)``. Alternatives must carry equal marks;
    where they do not, the maximum is used and the discrepancy is left for verification.
    """
    buckets: dict[tuple, list[tuple[Address, float]]] = defaultdict(list)
    for addr, marks in rows:
        if addr.choice_alt:
            buckets[(addr.section, addr.question_no, addr.sub_part)].append((addr, marks))

    mapping: dict[str, str] = {}
    groups: list[ChoiceGroup] = []
    for i, (key, members) in enumerate(sorted(buckets.items(), key=lambda kv: str(kv[0]))):
        if len(members) < 2:
            continue
        gid = f"cg-{key[0] or '_'}-{key[1]}-{key[2] or '_'}-{i}"
        for addr, _ in members:
            mapping[addr.key] = gid
        groups.append(
            ChoiceGroup(gid, [a for a, _ in members], max(m for _, m in members))
        )
    return mapping, groups


def effective_total(
    rows: list[tuple[Address, float]], groups: list[ChoiceGroup]
) -> float:
    """Paper total with each choice group counted once.

    This is the correction that makes the verification gate pass on a real paper: naive
    sums we measured were 90 / 172 / 349 against a stated maximum of 80.
    """
    grouped_keys = {a.key for g in groups for a in g.addresses}
    total = sum(m for a, m in rows if a.key not in grouped_keys)
    total += sum(g.marks for g in groups)
    return total
