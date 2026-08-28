"""The capture quality gate.

Four metrics, computed in the browser at ~10 fps before the shutter unlocks. A bad photo
caught here costs five seconds; caught later it costs a wrong report. This module is the
server-side reference implementation the client mirrors.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.config import get_settings

LAPLACIAN = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64)


def _convolve2d(img: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    kh, kw = kernel.shape
    ph, pw = kh // 2, kw // 2
    padded = np.pad(img, ((ph, ph), (pw, pw)), mode="edge")
    out = np.zeros_like(img, dtype=np.float64)
    for i in range(kh):
        for j in range(kw):
            out += kernel[i, j] * padded[i : i + img.shape[0], j : j + img.shape[1]]
    return out


def blur_score(gray: np.ndarray) -> float:
    """Variance of the Laplacian, normalised by image size. Higher is sharper."""
    lap = _convolve2d(gray.astype(np.float64), LAPLACIAN)
    return float(np.var(lap))


def glare_fraction(gray: np.ndarray, margin: int = 6) -> float:
    """Fraction of the frame blown out *relative to the page's own paper level*.

    A naive "pixels above 245" test calls a clean white page 78% glare, because paper is
    white. So we first estimate the paper level as the mode of the bright half of the
    histogram, then count only what sits meaningfully above it.
    """
    flat = gray.reshape(-1)
    bright = flat[flat >= 128]
    if bright.size == 0:
        return 0.0
    paper_level = int(np.bincount(bright.astype(np.int64), minlength=256).argmax())
    if paper_level >= 255 - margin:
        return 0.0  # paper is already at the ceiling; nothing can exceed it
    return float((flat > paper_level + margin).mean())


def page_coverage(quad_area: float, frame_area: float) -> float:
    return float(quad_area / frame_area) if frame_area else 0.0


def skew_degrees(top_edge: tuple[tuple[float, float], tuple[float, float]]) -> float:
    (x0, y0), (x1, y1) = top_edge
    return float(abs(np.degrees(np.arctan2(y1 - y0, max(x1 - x0, 1e-9)))))


@dataclass
class QualityReport:
    blur: float
    glare: float
    coverage: float
    skew: float
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    @property
    def band(self) -> str:
        return "green" if self.passed else ("amber" if len(self.failures) == 1 else "red")

    def as_dict(self) -> dict:
        return {
            "blur": self.blur, "glare": self.glare, "coverage": self.coverage,
            "skew": self.skew, "passed": self.passed, "band": self.band,
            "failures": self.failures,
        }


def assess(
    gray: np.ndarray,
    *,
    quad_area: float | None = None,
    top_edge: tuple[tuple[float, float], tuple[float, float]] | None = None,
) -> QualityReport:
    s = get_settings()
    frame_area = float(gray.shape[0] * gray.shape[1])
    rep = QualityReport(
        blur=blur_score(gray),
        glare=glare_fraction(gray),
        coverage=page_coverage(quad_area if quad_area is not None else frame_area, frame_area),
        skew=skew_degrees(top_edge) if top_edge else 0.0,
    )
    if rep.blur < s.min_blur_score:
        rep.failures.append("blur")
    if rep.glare > s.max_glare_fraction:
        rep.failures.append("glare")
    if rep.coverage < s.min_page_coverage:
        rep.failures.append("coverage")
    if rep.skew > s.max_skew_degrees:
        rep.failures.append("skew")
    return rep
