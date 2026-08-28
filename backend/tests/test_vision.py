from __future__ import annotations

import numpy as np

from app.vision.imposition import detect_imposition
from app.vision.ink import fit_ink_profile, separate
from app.vision.orientation import detect_orientation
from app.vision.quality import assess, glare_fraction


def _footers(pdf_pages: int, per_page: int, total: int, page_size):
    w, h = page_size
    slots = [(w * 0.2, h * 0.45), (w * 0.7, h * 0.45), (w * 0.2, h * 0.95), (w * 0.7, h * 0.95)]
    out = []
    for pi in range(pdf_pages):
        spans = []
        for t in range(per_page):
            n = pi * per_page + t + 1
            if n <= total:
                x, y = slots[t % 4]
                spans.append((f"30(B)  Page {n} of {total}  P.T.O.", (x, y, x + 140, y + 12)))
        out.append(spans)
    return out


def test_detects_four_up_maths_paper():
    pages = _footers(6, 4, 23, (612.0, 1260.0))
    r = detect_imposition(pages, (612.0, 1260.0))
    assert r.n_up == 4 and r.logical_total == 23 and r.consistent
    assert r.ordered_logical_pages == list(range(1, 24))


def test_detects_two_up_tamil_paper():
    r = detect_imposition(_footers(6, 2, 12, (612.0, 792.0)), (612.0, 792.0))
    assert r.n_up == 2 and r.logical_total == 12 and r.consistent


def test_detects_one_up_english_paper():
    r = detect_imposition(_footers(19, 1, 19, (612.0, 792.0)), (612.0, 792.0))
    assert r.n_up == 1 and r.logical_total == 19


def test_no_footer_defaults_to_one_up():
    r = detect_imposition([[("some prose", (10, 10, 90, 22))]], (612.0, 792.0))
    assert r.n_up == 1 and "assuming 1-up" in r.detail


def _lined_page() -> np.ndarray:
    g = np.full((240, 160), 250, np.uint8)
    for row in range(20, 220, 14):
        g[row : row + 4, 18:142] = 30
    return g


def test_orientation_is_detected_from_content_not_metadata():
    g = _lined_page()
    assert detect_orientation(g).angle in (0, 180)
    rotated = np.rot90(g, k=1)
    assert detect_orientation(rotated).angle in (90, 270)


def test_glare_is_relative_to_the_paper_level():
    """A clean white page must not read as 78% glare."""
    assert glare_fraction(_lined_page()) == 0.0
    flashed = _lined_page().copy()
    flashed[:60, :] = 255
    page = np.where(flashed == 250, 200, flashed).astype(np.uint8)
    assert glare_fraction(page) > 0.1


def test_quality_gate_passes_a_clean_page():
    rep = assess(_lined_page())
    assert rep.passed and rep.band == "green"


def _synthetic_script() -> np.ndarray:
    page = np.full((240, 180, 3), 250, np.uint8)
    page[10:230, 8:11] = [230, 120, 130]          # printed red margin rule
    for y in range(30, 210, 18):
        page[y : y + 5, 30:150] = [25, 25, 30]    # student, black
    page[40:48, 155:168] = [200, 30, 35]          # teacher, red
    page[100:108, 155:168] = [200, 30, 35]
    return page


def test_ink_profile_is_fitted_without_labels():
    prof = fit_ink_profile([_synthetic_script() for _ in range(3)])
    assert prof.method == "kmeans_circular"
    assert prof.fitted_from_pixels > 0


def test_teacher_and_student_layers_separate():
    pages = [_synthetic_script() for _ in range(3)]
    layers = separate(pages[0], fit_ink_profile(pages))
    teacher_cols = set(np.where(layers.teacher)[1].tolist())
    assert teacher_cols and min(teacher_cols) >= 150      # only the margin marks
    assert layers.student.sum() > layers.teacher.sum()    # students write far more
