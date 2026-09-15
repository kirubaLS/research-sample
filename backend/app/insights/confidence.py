"""
Part D3/D4: the confidence function.

Structurally enforced: board_urgency is NOT a parameter of `compute_confidence`.
There is no way to pass it in — the signature only accepts the four inputs the
spec names.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .insight import Band
from . import constants as C


@dataclass
class GroupCount:
    label: str
    count: int
    threshold: int


def compute_confidence(
    # Input 1: question count per compared group, against the threshold.
    group_counts: list[GroupCount],
    # Input 2: distinct variants, against the minimum.
    distinct_variants: int,
    min_distinct_variants: int,
    # Input 3: share of supporting marks that are marker_dependent (0..1).
    marker_dependent_share: float,
    # Input 4: subject_scope.
    subject_scope: str,
    *,
    # Extra flags for rule-specific caps, still no board_urgency.
    variant_weakness_n3: bool = False,
    class_wide_absence_above_max: bool = False,
    flatness_untestable: bool = False,
    reference_band_below_full_but_at_or_above_min: bool = False,
) -> tuple[Optional[Band], list[str]]:
    """Returns (observation_band_or_None, list_of_cap_reason_fragments).

    Returns (None, reasons) when any count threshold is unmet: "do not emit".
    """
    reasons: list[str] = []

    for gc in group_counts:
        if gc.count < gc.threshold:
            reasons.append(
                f"{gc.label} count {gc.count} is below the minimum of {gc.threshold}."
            )
    if reasons:
        return None, reasons

    band = Band.HIGH
    caps: list[str] = []

    def cap_to(new_band: Band, why: str) -> None:
        nonlocal band
        order = {Band.HIGH: 2, Band.MEDIUM: 1, Band.LOW: 0}
        if order[new_band] < order[band]:
            band = new_band
        caps.append(why)

    if marker_dependent_share > 0.50:
        cap_to(Band.MEDIUM, (
            f"{marker_dependent_share:.0%} of supporting marks are partially "
            "credited and therefore depend on marking convention."
        ))

    if subject_scope == "STUDENT" and marker_dependent_share >= 0.50:
        cap_to(Band.MEDIUM, "Subject scope is STUDENT and the evidence is not "
                              "majority marker-independent.")

    if distinct_variants < min_distinct_variants:
        cap_to(Band.MEDIUM, (
            f"Coverage is {distinct_variants} distinct variants, below the "
            f"minimum of {min_distinct_variants}. Scope narrowed to VARIANT."
        ))

    if variant_weakness_n3:
        cap_to(Band.MEDIUM, "Variant Weakness at n=3.")

    if class_wide_absence_above_max:
        cap_to(Band.MEDIUM, f"Class-wide absence rate above "
                             f"{C.MAX_ABSENCE_RATE:.0%}.")

    if flatness_untestable:
        cap_to(Band.MEDIUM, "A flatness or contrast test could not be run at all.")

    if reference_band_below_full_but_at_or_above_min:
        cap_to(Band.MEDIUM, (
            f"Reference band is below {C.REFERENCE_BAND_SIZE} but at or above "
            f"{C.MIN_REFERENCE_BAND}."
        ))

    return band, caps
