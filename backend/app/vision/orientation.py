"""Orientation detection from content, not metadata.

Every one of the eight papers reports ``rotation = 0`` in its PDF metadata, yet the Tamil
paper is printed at 90 degrees. Metadata cannot be trusted.

Text lines produce sharp periodic peaks in a horizontal projection profile only when they
are horizontal, so the angle whose profile has the highest variance is the right one. The
same routine handles a phone photo taken sideways, so it serves both pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ANGLES = (0, 90, 180, 270)


@dataclass(frozen=True)
class OrientationResult:
    angle: int
    scores: dict[int, float]

    @property
    def confidence(self) -> float:
        vals = sorted(self.scores.values(), reverse=True)
        if len(vals) < 2 or vals[0] <= 0:
            return 0.0
        return float((vals[0] - vals[1]) / vals[0])


def _profile_variance(gray: np.ndarray) -> float:
    """Variance of the row-ink profile. High when text lines are horizontal."""
    ink = 1.0 - (gray.astype(np.float64) / 255.0)
    rows = ink.sum(axis=1)
    if rows.size < 2:
        return 0.0
    rows = rows - rows.mean()
    # normalise by page height so different rotations are comparable
    return float(np.var(rows) / max(gray.shape[0], 1))


def detect_orientation(gray: np.ndarray) -> OrientationResult:
    """``gray`` is a 2-D uint8 array, 0 = ink, 255 = paper."""
    scores: dict[int, float] = {}
    for angle in ANGLES:
        k = (angle // 90) % 4
        rotated = np.rot90(gray, k=k)
        scores[angle] = _profile_variance(rotated)

    # 0 vs 180 (and 90 vs 270) are near-identical under this measure; break the tie toward
    # the upright reading using the vertical ink centre of mass — printed pages carry more
    # ink in their upper half
    best = max(scores, key=lambda a: scores[a])
    pair = (best + 180) % 360
    if abs(scores[best] - scores[pair]) / max(scores[best], 1e-9) < 0.02:
        for cand in (best, pair):
            rot = np.rot90(gray, k=(cand // 90) % 4)
            ink = 1.0 - rot.astype(np.float64) / 255.0
            top = ink[: rot.shape[0] // 2].sum()
            bottom = ink[rot.shape[0] // 2 :].sum()
            scores[cand] += 1e-6 * (top - bottom)
        best = max((best, pair), key=lambda a: scores[a])

    return OrientationResult(int(best), scores)
