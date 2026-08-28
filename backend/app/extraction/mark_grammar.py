"""Recognising a mark label on a question paper.

Measured across the eight CBSE 2026 papers: a mark label is right-aligned at
x ≈ 0.88 x page-width (p10 = p50 = p90 = 0.88 on all three text-layer papers), and it
takes one of three forms.

  bare integer      '3'                       -> 3 marks
  product           '6x3=18' / '5 × 2 = 10'   -> 18 marks, and 6 sub-parts of 3 each
  section header    '(Grammar) 12 Marks'      -> a section total, i.e. a verification equation

The product form is a gift: it states the sub-part count and the per-part marks, and
``a x b = c`` is its own self-check.

Page furniture is the trap: the Tamil paper's Q.P. code is literally ``10`` — a perfectly
plausible mark — printed in the margin of every page. Any numeral repeating at the same
normalised coordinates on >= 3 pages is furniture, not a mark.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

#: right-aligned band, as a fraction of page width. Measured, not guessed.
MARK_BAND = (0.845, 0.925)

_BARE = re.compile(r"^(\d{1,2})$")
_PRODUCT = re.compile(
    r"^(\d{1,2})\s*[x×*]\s*(\d{1,2}(?:\.\d)?)\s*=\s*(\d{1,3})$", re.IGNORECASE
)
_SECTION_TOTAL = re.compile(r"(\d{1,3})\s*(?:marks?|अंक|மதிப்பெண்)", re.IGNORECASE)

MarkForm = Literal["bare", "product", "section_total"]


@dataclass(frozen=True)
class MarkLabel:
    value: float
    form: MarkForm
    sub_parts: int | None = None
    per_part: float | None = None
    raw: str = ""
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None

    @property
    def is_self_consistent(self) -> bool:
        """``a x b = c`` must actually hold."""
        if self.form != "product":
            return True
        return abs((self.sub_parts or 0) * (self.per_part or 0) - self.value) < 1e-6


@dataclass
class TextSpan:
    text: str
    page: int
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 in page units
    page_width: float
    page_height: float = 792.0

    @property
    def right_fraction(self) -> float:
        return self.bbox[2] / self.page_width if self.page_width else 0.0

    @property
    def norm_key(self) -> tuple[int, int]:
        """Coarse normalised position, for furniture detection."""
        return (
            round(self.bbox[0] / self.page_width, 2).__mul__(100).__int__(),
            round(self.bbox[1] / self.page_height, 2).__mul__(100).__int__(),
        )


def parse_label(text: str) -> MarkLabel | None:
    """Parse one candidate string into a MarkLabel, or return None."""
    s = " ".join(text.split())
    if not s:
        return None

    m = _PRODUCT.match(s)
    if m:
        n, per, total = int(m.group(1)), float(m.group(2)), float(m.group(3))
        return MarkLabel(
            value=total, form="product", sub_parts=n, per_part=per, raw=s
        )

    m = _BARE.match(s)
    if m:
        return MarkLabel(value=float(m.group(1)), form="bare", raw=s)

    m = _SECTION_TOTAL.search(s)
    if m:
        return MarkLabel(value=float(m.group(1)), form="section_total", raw=s)

    return None


def find_page_furniture(spans: Iterable[TextSpan], min_pages: int = 3) -> set[tuple[int, int, str]]:
    """Numerals repeating at the same normalised position across >= ``min_pages`` pages.

    Returns a set of (x_key, y_key, text) tuples to exclude. This is what stops the Tamil
    paper's Q.P. code ``10`` being read as a 10-mark question on all twelve pages.
    """
    seen: dict[tuple[int, int, str], set[int]] = defaultdict(set)
    for sp in spans:
        s = " ".join(sp.text.split())
        if _BARE.match(s):
            seen[(*sp.norm_key, s)].add(sp.page)
    return {key for key, pages in seen.items() if len(pages) >= min_pages}


@dataclass
class MarkExtraction:
    labels: list[MarkLabel] = field(default_factory=list)
    furniture_rejected: int = 0
    band_rejected: int = 0
    inconsistent_products: list[MarkLabel] = field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(lb.value for lb in self.labels if lb.form in ("bare", "product"))


def extract_marks(
    spans: Iterable[TextSpan],
    *,
    use_band: bool = True,
    min_pages_for_furniture: int = 3,
) -> MarkExtraction:
    """Full extraction pass: furniture filter, then band filter, then grammar."""
    spans = list(spans)
    furniture = find_page_furniture(spans, min_pages_for_furniture)
    out = MarkExtraction()

    for sp in spans:
        s = " ".join(sp.text.split())
        label = parse_label(s)
        if label is None:
            continue

        if _BARE.match(s) and (*sp.norm_key, s) in furniture:
            out.furniture_rejected += 1
            continue

        # Bare integers must sit in the measured right-aligned band. Products and section
        # headers carry their own semantics and are accepted anywhere on the line.
        if use_band and label.form == "bare":
            if not (MARK_BAND[0] <= sp.right_fraction <= MARK_BAND[1]):
                out.band_rejected += 1
                continue

        label = MarkLabel(
            value=label.value,
            form=label.form,
            sub_parts=label.sub_parts,
            per_part=label.per_part,
            raw=label.raw,
            page=sp.page,
            bbox=sp.bbox,
        )
        if not label.is_self_consistent:
            out.inconsistent_products.append(label)
            continue
        out.labels.append(label)

    return out
