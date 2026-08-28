"""N-up detection.

Imposition is variable and must be discovered, never assumed: of the eight real CBSE 2026
papers we measured, five are 1-up, Tamil is 2-up (6 PDF pages -> 12 logical) and both Maths
papers are 4-up (6-7 PDF pages -> 23-27 logical).

Detection uses the footer every CBSE paper prints on every logical page:
``Page 13 of 27``. k matches on one PDF page means k-up.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

FOOTER = re.compile(r"page\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class FooterHit:
    page_index: int          # index of the *PDF* page
    logical_index: int       # the printed 'Page N'
    logical_total: int       # the printed 'of M'
    bbox: tuple[float, float, float, float]


@dataclass
class ImpositionResult:
    n_up: int
    logical_total: int | None
    tiles: list[tuple[int, int, tuple[float, float, float, float]]] = field(default_factory=list)
    consistent: bool = True
    detail: str = ""

    @property
    def ordered_logical_pages(self) -> list[int]:
        return [t[1] for t in self.tiles]


def find_footers(page_texts: list[list[tuple[str, tuple[float, float, float, float]]]]) -> list[FooterHit]:
    """``page_texts[i]`` is a list of (text, bbox) spans on PDF page ``i``."""
    hits: list[FooterHit] = []
    for pi, spans in enumerate(page_texts):
        for text, bbox in spans:
            m = FOOTER.search(text or "")
            if m:
                hits.append(FooterHit(pi, int(m.group(1)), int(m.group(2)), bbox))
    return hits


def detect_imposition(
    page_texts: list[list[tuple[str, tuple[float, float, float, float]]]],
    page_size: tuple[float, float],
) -> ImpositionResult:
    """Return the tile grid, ordered by the *printed* logical page number.

    Imposition order is not always left-to-right, so tiles are ordered by what the page
    says it is, never by geometry.
    """
    hits = find_footers(page_texts)
    pdf_pages = len(page_texts)
    if not hits:
        return ImpositionResult(1, None, [], True, "no 'Page N of M' footer found; assuming 1-up")

    per_page: dict[int, list[FooterHit]] = {}
    for h in hits:
        per_page.setdefault(h.page_index, []).append(h)
    counts = [len(v) for v in per_page.values()]
    n_up = max(set(counts), key=counts.count)

    totals = {h.logical_total for h in hits}
    logical_total = max(totals) if totals else None

    consistent = True
    detail = ""
    if logical_total and n_up:
        expected_pdf_pages = math.ceil(logical_total / n_up)
        if abs(expected_pdf_pages - pdf_pages) > 1:
            consistent = False
            detail = (
                f"ceil({logical_total}/{n_up}) = {expected_pdf_pages} but the PDF has "
                f"{pdf_pages} pages"
            )
    if len(totals) > 1:
        consistent = False
        detail += f" conflicting 'of M' values: {sorted(totals)}"

    w, h_ = page_size
    tiles: list[tuple[int, int, tuple[float, float, float, float]]] = []
    for pi, page_hits in sorted(per_page.items()):
        for hit in page_hits:
            tiles.append((pi, hit.logical_index, _tile_bbox(hit.bbox, n_up, w, h_)))
    tiles.sort(key=lambda t: t[1])   # order by printed logical page, never by position

    return ImpositionResult(n_up, logical_total, tiles, consistent, detail.strip())


def _tile_bbox(
    footer_bbox: tuple[float, float, float, float], n_up: int, w: float, h: float
) -> tuple[float, float, float, float]:
    """Recover the tile rectangle that owns a footer, from the grid implied by n_up."""
    if n_up <= 1:
        return (0.0, 0.0, w, h)
    cols = 2 if n_up in (2, 4) else 1
    rows = n_up // cols
    cx, cy = (footer_bbox[0] + footer_bbox[2]) / 2, (footer_bbox[1] + footer_bbox[3]) / 2
    col = min(int(cx / (w / cols)), cols - 1)
    row = min(int(cy / (h / rows)), rows - 1)
    tw, th = w / cols, h / rows
    return (col * tw, row * th, (col + 1) * tw, (row + 1) * th)
