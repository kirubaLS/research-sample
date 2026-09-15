"""Internal choice ('attempt any one of (a) / (b)'), and its 'attempt any N of M' cousin.

Measured: 6 OR blocks in the English paper, 9 in Science, 6 in Social Science, and both
Maths papers use choice across sections B-E.

Two rules fall out, and the second one is the one that protects the diagnosis:

  1. alternatives in a choice group contribute their marks to every total exactly ONCE
  2. the unattempted alternative is NOT_OFFERED, never zero

A second, structurally different choice shape exists alongside the binary OR: a numbered
list of M sub-items, introduced by an instruction naming a required count N less than the
list's size, with the group's per-item mark printed once as a group-level 'N x M = Total'
expression rather than a bracketed mark on each item. None of the members carries a
distinguishing ``choice_alt`` -- they are letters or numbers of a plain list, not a
two-way alternative sharing one sub-item -- so the binary grouping above has nothing to
key on and counted every printed sub-item as if all M of them were answered.
``group_choices`` also groups this shape, keyed by ``attempt_required`` (the paper's own
N) rather than ``choice_alt``, and dedupes it the same way: N items' worth of marks,
counted once. This is also the shape used when OR itself joins two or more WHOLE
sub-items rather than two lettered options inside one -- (i) ... OR ... (ii) ..., not
(a)/(b) within a single (i) -- read as attempt_required=1 over a group of that size,
same as any other 'attempt any N of M'; the word OR being present does not by itself
mean choice_alt.
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
    #: None for a binary OR group (attempt one of two, size always 2). Set to the
    #: paper's own N for an 'attempt any N of M' group, where size is M -- clamped to
    #: never exceed M, since a paper cannot require more attempts than it printed items.
    required_count: int | None = None
    #: What the model actually said N was, before that clamp. Equal to required_count
    #: unless the model's reading was physically impossible (N > M) -- see verification
    #: .py's G5, which flags exactly that disagreement for a human rather than trusting
    #: either number silently.
    required_as_read: int | None = None

    @property
    def size(self) -> int:
        return len(self.addresses)


def group_choices(
    rows: list[tuple[Address, float]],
    attempt_required: dict[str, int] | None = None,
) -> tuple[dict[str, str], list[ChoiceGroup]]:
    """Group addresses that form a choice, of either shape this pipeline knows about.

    Returns ``(address_key -> group_id, groups)``.

    Binary OR: addresses that differ only by ``choice_alt``. Alternatives must carry
    equal marks; where they do not, the maximum is used and the discrepancy is left for
    verification.

    'Attempt any N of M': addresses sharing (section, question_no) whose key appears in
    ``attempt_required`` -- the paper's own printed N for that group, carried on every
    member (see ``ExtractedQuestion.attempt_required`` / the ``scanned_question`` and
    ``question`` columns of the same name). Per-item marks must be equal across the
    group for the same reason a binary choice's must be; where they are not, the maximum
    is used. The group's total is N times that per-item mark, not the sum of all M --
    that sum is exactly the double-count this function exists to prevent.
    """
    attempt_required = attempt_required or {}
    buckets: dict[tuple, list[tuple[Address, float]]] = defaultdict(list)
    attempt_buckets: dict[tuple, list[tuple[Address, float]]] = defaultdict(list)
    for addr, marks in rows:
        if addr.choice_alt:
            buckets[(addr.section, addr.question_no, addr.sub_part)].append((addr, marks))
        elif addr.key in attempt_required:
            attempt_buckets[(addr.section, addr.question_no)].append((addr, marks))

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

    for i, (key, members) in enumerate(
        sorted(attempt_buckets.items(), key=lambda kv: str(kv[0]))
    ):
        if len(members) < 2:
            continue
        # The paper states one N for the whole group; a member that disagrees is kept
        # rather than dropped (that would silently under-count how many sub-items the
        # paper printed), using the largest N seen so the group is never worth less than
        # what any one member claims.
        required = max(attempt_required[addr.key] for addr, _ in members)
        # Hard backstop against a hallucinated N, independent of whether anything later
        # in the pipeline happens to catch it: a paper cannot require more attempts than
        # it printed sub-items for. This is not a guess or an estimate -- len(members) is
        # exactly how many rows this group actually has, ground truth from the same
        # extraction, so clamping to it can only ever reduce an impossible number to a
        # possible one, never invent a value. required_as_read is kept on the group so a
        # caller that wants to flag the mismatch for a human (see verification.py's G5)
        # still can.
        required_as_read = required
        required = min(required, len(members))
        gid = f"ag-{key[0] or '_'}-{key[1]}-{i}"
        for addr, _ in members:
            mapping[addr.key] = gid
        per_item = max(m for _, m in members)
        groups.append(
            ChoiceGroup(
                gid, [a for a, _ in members], required * per_item, required,
                required_as_read=required_as_read,
            )
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
