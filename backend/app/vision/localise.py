"""L3 -- Localisation: where the marks and the question numbers are on the page.

Produces the three things L5 consumes: ``Anchor[]`` from the student layer, ``MarkCandidate[]``
and ``TotalCandidate[]`` from the teacher layer.

The design called for OpenCV contours and PaddleOCR detection. Neither is available on the
box this deploys to -- PaddleOCR alone pulls a deep-learning runtime an order of magnitude
larger than the whole service -- so this takes the route ``app.vision.ink`` already took
when it fitted k-means in NumPy rather than importing scikit-learn: connected components
from ``scipy.ndimage``, which is installed, and shape statistics computed directly.

Nothing is lost by that substitution here. Contours and connected components find the same
blobs on a binary mask. And detection proper is a far smaller problem than the design
assumed, because the question paper is now scanned first: the Q-matrix is frozen before a
script is read, so the anchor vocabulary is a known list of about forty labels rather than
open text.

What the shape filter is for: a teacher's page carries ticks, crosses and strikes in the
same red ink as the marks, and they outnumber the marks. Excluding them by shape before
recognition is what keeps L4 from being asked to read a tick as a digit -- and a recogniser
forced to choose a digit for a tick will choose one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from app.mapping.association import Anchor, MarkCandidate

#: A numeral occupies a plausible share of a page. Below the floor it is speckle or the
#: dot of an 'i'; above the ceiling it is a diagram, a signature or a smudge.
MIN_AREA_FRACTION = 2.0e-5
MAX_AREA_FRACTION = 4.0e-3
#: Handwritten digits are taller than wide, or nearly square. A strike-through is many
#: times wider than tall and is rejected here.
MIN_ASPECT = 0.28
MAX_ASPECT = 2.2
#: Fraction of the bounding box the ink actually fills. A tick or a cross is two thin
#: strokes across a large box and fills very little of it; a digit fills much more.
MIN_EXTENT = 0.22


@dataclass(frozen=True)
class Component:
    """One connected blob of ink, with the statistics the shape filter needs."""

    label: int
    x: float
    y: float
    x0: int
    y0: int
    x1: int
    y1: int
    area: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def aspect(self) -> float:
        """Width over height. Below 1 is a tall shape."""
        return self.width / self.height if self.height else 0.0

    @property
    def extent(self) -> float:
        """Share of the bounding box that is ink."""
        box = self.width * self.height
        return self.area / box if box else 0.0


@dataclass(frozen=True)
class TotalCandidate:
    """A numeral that is a total rather than a question's mark.

    Kept apart from MarkCandidate on purpose: a total is not a mark for any question, and
    letting one into the assignment would both steal a binding and corrupt the very sum
    that L6 uses to check the rest.
    """

    candidate_id: str
    page: int
    x: float
    y: float
    value: float | None = None
    confidence: float = 1.0


def components(mask: np.ndarray, *, min_area: int = 1, max_area: int | None = None) -> list[Component]:
    """Every connected blob in a binary mask, in reading order.

    Eight-connectivity, because a handwritten digit routinely joins only at a diagonal and
    four-connectivity splits it into pieces that are each too small to survive the filter.
    """
    if mask.ndim != 2:
        raise ValueError("expected a 2-D boolean mask")
    labelled, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=int))
    if count == 0:
        return []

    out: list[Component] = []
    slices = ndimage.find_objects(labelled)
    areas = ndimage.sum_labels(mask, labelled, index=np.arange(1, count + 1))
    centres = ndimage.center_of_mass(mask, labelled, index=np.arange(1, count + 1))
    for index, (rows, cols) in enumerate(slices):
        if rows is None:
            continue
        area = int(areas[index])
        if area < min_area or (max_area is not None and area > max_area):
            continue
        cy, cx = centres[index]
        out.append(Component(
            label=index + 1, x=float(cx), y=float(cy),
            x0=cols.start, y0=rows.start, x1=cols.stop, y1=rows.stop, area=area,
        ))
    out.sort(key=lambda c: (round(c.y, 1), c.x))
    return out


def looks_like_a_numeral(component: Component) -> bool:
    """Shape alone, before anything tries to read it.

    A tick, a cross and a strike-through are all thin strokes spanning a large box, so the
    extent test removes them; a strike is also far wider than tall, which the aspect test
    removes independently.
    """
    return (
        MIN_ASPECT <= component.aspect <= MAX_ASPECT
        and component.extent >= MIN_EXTENT
    )


def _area_bounds(mask: np.ndarray) -> tuple[int, int]:
    pixels = mask.shape[0] * mask.shape[1]
    return max(int(pixels * MIN_AREA_FRACTION), 4), max(int(pixels * MAX_AREA_FRACTION), 16)


def find_mark_candidates(teacher: np.ndarray, page: int) -> list[MarkCandidate]:
    """Isolated numerals in the teacher's ink. Values are filled in later, by L4."""
    low, high = _area_bounds(teacher)
    return [
        MarkCandidate(
            candidate_id=f"p{page}-m{i}", page=page, x=c.x, y=c.y,
            value=None, confidence=0.0,
        )
        for i, c in enumerate(
            [c for c in components(teacher, min_area=low, max_area=high) if looks_like_a_numeral(c)]
        )
    ]


def find_total_candidates(
    teacher: np.ndarray, page: int, *, bottom_fraction: float = 0.18
) -> list[TotalCandidate]:
    """Numerals in the band where a teacher writes a page or section total.

    Position is the signal available without reading anything: a total sits at the foot of
    the page or in a box of its own, away from the answers. Anything found here is offered
    to L6 as an equation rather than to L5 as a mark.
    """
    height = teacher.shape[0]
    cut = height * (1.0 - bottom_fraction)
    low, high = _area_bounds(teacher)
    return [
        TotalCandidate(candidate_id=f"p{page}-t{i}", page=page, x=c.x, y=c.y)
        for i, c in enumerate(
            [
                c for c in components(teacher, min_area=low, max_area=high)
                if looks_like_a_numeral(c) and c.y >= cut
            ]
        )
    ]


def find_anchor_crops(student: np.ndarray, page: int) -> list[Component]:
    """Blobs in the student's ink that could be a question serial number.

    Returns components rather than Anchors, because an anchor is only an anchor once its
    label has been read and matched against the frozen Q-matrix. Handing back a list of
    Anchors here would assert a question number nobody has read yet.

    The left margin is where CBSE instructs students to write the number, and restricting
    to it removes almost all of the student's own working -- which is the largest source of
    false anchors on any script.
    """
    low, high = _area_bounds(student)
    margin = student.shape[1] * 0.25
    return [
        c for c in components(student, min_area=low, max_area=high)
        if c.x <= margin and looks_like_a_numeral(c)
    ]


def anchors_from_labels(
    labels: dict[str, tuple[int, float, float]],
    q_matrix: dict[str, tuple[float, float]],
) -> list[Anchor]:
    """Turn read labels into anchors, keeping only what the frozen Q-matrix contains.

    ``labels`` is address -> (page, x, y); ``q_matrix`` is address -> (max_marks, step).

    The closed-vocabulary filter is the whole point. A misread '13' where the paper has no
    question 13 is dropped rather than carried, because an anchor for a question that does
    not exist takes a mark away from one that does.
    """
    out: list[Anchor] = []
    for address, (page, x, y) in sorted(labels.items()):
        if address not in q_matrix:
            continue
        max_marks, step = q_matrix[address]
        out.append(Anchor(address=address, page=page, x=x, y=y, max_marks=max_marks, step=step))
    return out
