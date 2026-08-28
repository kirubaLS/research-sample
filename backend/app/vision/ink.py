"""Separating the teacher's ink from the student's.

Confirmed with the school: teachers mark in red, students write in black or blue. That one
fact converts one hard problem into two easy ones — question numbers are searched for in
the STUDENT layer, marks in the TEACHER layer — and it removes the largest source of false
positives in any generic OCR pipeline: the student's own arithmetic working.

The hue bands are not hardcoded. They are fitted per school by k-means on ink pixels from
three unlabelled pages, so a faded red pen, a green pen or a yellow tube light all work.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    """Vectorised RGB->HSV. ``rgb`` is (..., 3) uint8. Returns H in [0,180), S,V in [0,255]."""
    arr = rgb.astype(np.float64) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mx, mn = arr.max(axis=-1), arr.min(axis=-1)
    diff = mx - mn

    h = np.zeros_like(mx)
    mask = diff > 1e-12
    rm = mask & (mx == r)
    gm = mask & (mx == g)
    bm = mask & (mx == b)
    h[rm] = (60 * ((g[rm] - b[rm]) / diff[rm]) + 360) % 360
    h[gm] = 60 * ((b[gm] - r[gm]) / diff[gm]) + 120
    h[bm] = 60 * ((r[bm] - g[bm]) / diff[bm]) + 240

    s = np.where(mx > 0, diff / np.where(mx > 0, mx, 1), 0.0)
    return np.stack([h / 2.0, s * 255.0, mx * 255.0], axis=-1)


def white_balance(rgb: np.ndarray) -> np.ndarray:
    """Grey-world correction. Runs BEFORE any colour work — it is what makes the red
    separation robust across staffroom lighting."""
    arr = rgb.astype(np.float64)
    means = arr.reshape(-1, 3).mean(axis=0)
    grey = means.mean()
    scale = np.where(means > 1e-6, grey / means, 1.0)
    return np.clip(arr * scale, 0, 255).astype(np.uint8)


def ink_mask(hsv: np.ndarray, value_max: int = 200) -> np.ndarray:
    """Everything darker than the paper. The starting point for every other step."""
    return hsv[..., 2] < value_max


@dataclass
class InkProfile:
    """Fitted per school. Persisted on ``school.ink_profile``."""

    teacher_hue: float = 0.0        # OpenCV hue units, 0..180 (red wraps at 0/180)
    teacher_hue_tol: float = 12.0
    teacher_sat_min: float = 70.0
    student_hue: float | None = None
    fitted_from_pixels: int = 0
    method: str = "default"

    def as_dict(self) -> dict:
        return {
            "teacher_hue": self.teacher_hue,
            "teacher_hue_tol": self.teacher_hue_tol,
            "teacher_sat_min": self.teacher_sat_min,
            "student_hue": self.student_hue,
            "fitted_from_pixels": self.fitted_from_pixels,
            "method": self.method,
        }


def _kmeans_1d_circular(hues: np.ndarray, k: int = 3, iters: int = 25, seed: int = 7) -> np.ndarray:
    """k-means on a circular hue axis (0..180 wraps), via unit vectors."""
    rng = np.random.default_rng(seed)
    ang = hues * (2 * np.pi / 180.0)
    pts = np.stack([np.cos(ang), np.sin(ang)], axis=1)
    idx = rng.choice(len(pts), size=min(k, len(pts)), replace=False)
    centres = pts[idx]
    for _ in range(iters):
        d = ((pts[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
        lab = d.argmin(axis=1)
        new = np.array(
            [pts[lab == j].mean(axis=0) if (lab == j).any() else centres[j] for j in range(len(centres))]
        )
        if np.allclose(new, centres):
            break
        centres = new
    hue_centres = (np.degrees(np.arctan2(centres[:, 1], centres[:, 0])) % 360) / 2.0
    return hue_centres


def fit_ink_profile(pages_rgb: list[np.ndarray], *, max_pixels: int = 200_000) -> InkProfile:
    """Unsupervised. Three unlabelled pages, no annotation, under a second.

    The teacher's pen is identified by its properties, not by a fixed threshold: it is the
    high-saturation cluster with the *smallest* pixel count, because a teacher writes far
    less than a student.
    """
    sat_pixels: list[np.ndarray] = []
    for page in pages_rgb:
        hsv = rgb_to_hsv(white_balance(page))
        m = ink_mask(hsv)
        sel = hsv[m]
        if sel.size:
            sat_pixels.append(sel)
    if not sat_pixels:
        return InkProfile()

    px = np.concatenate(sat_pixels, axis=0)
    if len(px) > max_pixels:
        px = px[np.random.default_rng(3).choice(len(px), max_pixels, replace=False)]

    coloured = px[px[:, 1] >= 60]           # saturated ink only; black is not coloured
    if len(coloured) < 50:
        return InkProfile(fitted_from_pixels=len(px), method="fallback_default")

    centres = _kmeans_1d_circular(coloured[:, 0], k=min(3, max(2, len(coloured) // 50)))

    stats = []
    for c in centres:
        d = np.minimum(np.abs(coloured[:, 0] - c), 180 - np.abs(coloured[:, 0] - c))
        member = coloured[d <= 15]
        if len(member) == 0:
            continue
        stats.append((c, len(member), float(member[:, 1].mean())))
    if not stats:
        return InkProfile(fitted_from_pixels=len(px), method="fallback_default")

    # highest mean saturation, tie-broken toward the smaller cluster
    teacher = max(stats, key=lambda s: (s[2], -s[1]))
    others = [s for s in stats if s is not teacher]
    student_hue = max(others, key=lambda s: s[1])[0] if others else None

    return InkProfile(
        teacher_hue=float(teacher[0]),
        teacher_sat_min=max(60.0, teacher[2] * 0.55),
        student_hue=float(student_hue) if student_hue is not None else None,
        fitted_from_pixels=int(len(px)),
        method="kmeans_circular",
    )


@dataclass
class InkLayers:
    teacher: np.ndarray
    student: np.ndarray
    printed: np.ndarray
    removed_rules: int = 0
    notes: list[str] = field(default_factory=list)


def _remove_long_runs(mask: np.ndarray, min_run_fraction: float = 0.45) -> tuple[np.ndarray, int]:
    """Strip long straight structures — the printed red margin rule on Indian answer books
    lands squarely in the teacher mask and destroys naive blob detection."""
    out = mask.copy()
    removed = 0
    h, w = mask.shape
    row_runs = mask.sum(axis=1)
    for r in np.where(row_runs > w * min_run_fraction)[0]:
        out[r, :] = False
        removed += 1
    col_runs = mask.sum(axis=0)
    for c in np.where(col_runs > h * min_run_fraction)[0]:
        out[:, c] = False
        removed += 1
    return out, removed


def separate(rgb: np.ndarray, profile: InkProfile | None = None) -> InkLayers:
    """Split one page into teacher / student / printed masks."""
    prof = profile or InkProfile()
    hsv = rgb_to_hsv(white_balance(rgb))
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]

    ink = ink_mask(hsv)
    dhue = np.minimum(np.abs(hue - prof.teacher_hue), 180 - np.abs(hue - prof.teacher_hue))
    teacher = ink & (dhue <= prof.teacher_hue_tol) & (sat >= prof.teacher_sat_min)
    teacher, removed = _remove_long_runs(teacher)

    dark = ink & (sat < 90) & (val < 140)                       # black
    blue = ink & (np.abs(hue - 110) <= 25) & (sat >= 60)        # blue
    student = (dark | blue) & ~teacher

    printed = ink & ~teacher & ~student
    return InkLayers(teacher, student, printed, removed_rules=removed)
