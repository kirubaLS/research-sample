"""Board frequency and urgency -- the multiplier, as a pure function over evidence.

Some concept families come up on the board exam almost every year; some almost never do.
A family that keeps coming up should carry more urgency than one that rarely does. This
module turns the per-year evidence into that multiplier, exactly as the design note
"Board Frequency & Urgency" lays it out, and nothing here reads a database: the evidence
comes in as plain values, the answer goes out with every step that produced it.

Three inputs decide the multiplier, in this order:

1. **Frequency** -- years appeared divided by years *eligible*, never by a fixed window.
   A chapter added to the syllabus two years ago did not exist to be tested before that,
   and dividing its appearances by five anyway would make a 2-of-2 pattern look like a
   2-of-5 one.
2. **Stability** -- the range of marks across the years it appeared. A family at 4, 3, 5
   marks is a dependable signal; one at 2, 9, 3 shows up as often but what is at stake
   swings, so the multiplier is pulled back toward 1.0 or capped.
3. **Confidence** -- fewer than three eligible years is too thin to trust a perfect
   pattern, so the multiplier is capped whatever the first two steps said.

The one rule that outranks every number here: **the multiplier never goes below 1.0.**
Low frequency or thin data means "do not boost it further". It never means "suppress
it", because that would quietly hide a real weakness.

Every threshold is configuration, not a constant. The design note is explicit that the
values are a reasonable starting proposal rather than validated cut points, and a row
stores the config version it was computed under so the two can be told apart later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median


@dataclass(frozen=True)
class FrequencyConfig:
    """The design note's tables, as data."""

    #: (minimum share of eligible years, base multiplier), highest share first. A share
    #: is matched to the first row it reaches: 4/5 = 0.80 reaches the 0.75 row.
    base_by_share: tuple[tuple[float, float], ...] = ((1.0, 2.0), (0.75, 1.5), (0.5, 1.25))
    #: below the lowest share above, this is the base
    base_floor: float = 1.0
    #: a range of marks at or under this is "tight": no adjustment
    tight_range: float = 2.0
    #: a range at or over this is "wide": cap the multiplier hard
    wide_range: float = 5.0
    #: the cap applied for a wide range
    wide_range_cap: float = 1.25
    #: fewer eligible years than this is low-confidence
    low_confidence_years: int = 3
    #: the cap applied for low confidence
    low_confidence_cap: float = 1.5
    #: never below this, whatever else happens
    floor: float = 1.0
    #: travels with every stored row, so a change here is visible in the data
    version: str = "v1"


DEFAULT_CONFIG = FrequencyConfig()


@dataclass(frozen=True)
class YearEvidence:
    """One real board year for one family. Sample papers never become one of these."""

    year: int
    #: was the family in the syllabus that year at all
    eligible: bool
    #: marks the family carried that year, or None if it did not appear. Across several
    #: sets of the same year this is the median (see marks_for_year).
    marks: float | None

    @property
    def appeared(self) -> bool:
        return self.eligible and self.marks is not None


@dataclass
class Multiplier:
    value: float
    base: float
    years_eligible: int
    years_appeared: int
    marks_by_year: dict[int, float]
    marks_range: float | None
    #: each adjustment in words, in the order it was applied
    adjustments: list[str] = field(default_factory=list)

    @property
    def share(self) -> float | None:
        return self.years_appeared / self.years_eligible if self.years_eligible else None


def base_multiplier(years_appeared: int, years_eligible: int, config: FrequencyConfig) -> float:
    if years_eligible <= 0 or years_appeared <= 0:
        return config.base_floor
    share = years_appeared / years_eligible
    for minimum, base in config.base_by_share:
        if share >= minimum:
            return base
    return config.base_floor


def multiplier(evidence: list[YearEvidence], config: FrequencyConfig = DEFAULT_CONFIG) -> Multiplier:
    """The frequency multiplier for one family, with its working shown."""
    eligible = [e for e in evidence if e.eligible]
    appeared = [e for e in eligible if e.appeared]
    marks_by_year = {e.year: float(e.marks) for e in appeared}  # type: ignore[arg-type]

    base = base_multiplier(len(appeared), len(eligible), config)
    value = base
    notes: list[str] = []
    if eligible:
        notes.append(
            f"appeared in {len(appeared)} of {len(eligible)} eligible years "
            f"-> base multiplier {base:g}"
        )
    else:
        notes.append("no eligible years in the window -> base multiplier 1.0")

    marks_range: float | None = None
    if len(appeared) >= 2:
        marks = list(marks_by_year.values())
        marks_range = max(marks) - min(marks)
        if marks_range <= config.tight_range:
            notes.append(f"marks range {marks_range:g} is tight -> no change")
        elif marks_range >= config.wide_range:
            capped = min(value, config.wide_range_cap)
            notes.append(
                f"marks range {marks_range:g} is wide -> capped at {config.wide_range_cap:g}"
                + (f" (was {value:g})" if capped != value else "")
            )
            value = capped
        else:
            halfway = 1.0 + (value - 1.0) / 2.0
            notes.append(
                f"marks range {marks_range:g} is moderate -> reduced halfway toward 1.0, "
                f"{value:g} to {halfway:g}"
            )
            value = halfway
    elif len(appeared) == 1:
        marks_range = 0.0
        notes.append("appeared once, so there is no range to judge stability on")

    if 0 < len(eligible) < config.low_confidence_years:
        capped = min(value, config.low_confidence_cap)
        notes.append(
            f"only {len(eligible)} eligible year(s), fewer than {config.low_confidence_years} "
            f"-> low confidence, capped at {config.low_confidence_cap:g}"
            + (f" (was {value:g})" if capped != value else "")
        )
        value = capped

    if value < config.floor:
        notes.append(f"raised to the floor of {config.floor:g}: urgency is never suppressed")
        value = config.floor

    return Multiplier(
        value=round(value, 4), base=base,
        years_eligible=len(eligible), years_appeared=len(appeared),
        marks_by_year=marks_by_year, marks_range=marks_range, adjustments=notes,
    )


def urgency(board_weight_pct: float, mult: float) -> float:
    """Urgency Score = the board unit's published weight x the family's multiplier."""
    return round(float(board_weight_pct) * float(mult), 4)


# --------------------------------------------------------------------------------------
# From questions to evidence
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class PaperQuestion:
    """The four things about a mapped question the frequency layer reads."""

    concept_family_id: str
    max_marks: float
    #: questions sharing one are alternatives of an internal choice ("Q27 OR Q27")
    choice_group_id: str | None = None


def marks_by_family(questions: list[PaperQuestion]) -> dict[str, float]:
    """Marks each family carried on one paper.

    An internal choice offers two questions and the student answers one, so the paper is
    worth one of them, not both. Within a choice group each family gets the most marks any
    alternative gave it, never the sum: "27(a) tests X for 3 OR 27(b) tests Y for 3"
    counts X for 3 and Y for 3, and "27(a) tests X for 3 OR 27(b) tests X for 3" counts
    X for 3 once. Everything outside a choice group simply adds up.
    """
    out: dict[str, float] = {}
    grouped: dict[str, dict[str, float]] = {}
    for q in questions:
        if q.choice_group_id:
            fam = grouped.setdefault(q.choice_group_id, {})
            fam[q.concept_family_id] = max(fam.get(q.concept_family_id, 0.0), float(q.max_marks))
        else:
            out[q.concept_family_id] = out.get(q.concept_family_id, 0.0) + float(q.max_marks)
    for fam in grouped.values():
        for family_id, marks in fam.items():
            out[family_id] = out.get(family_id, 0.0) + marks
    return out


def marks_for_year(per_paper: list[float]) -> float:
    """One year has several sets (30/1/1, 30/1/2 ...). The year's figure is their median:
    a set that weighted a family unusually should not become the year's whole story."""
    return float(median(per_paper))
