"""parse_toc_chapters against every NCERT contents-page convention seen so far.

Four conventions, one function: Science says 'Chapter N' with the title on the next
line; Geography gives just 'N.' on its own line; History numbers in Roman numerals and
never says 'Chapter' at all; Economics lays chapter numbers and titles out as a table
whose columns linear text reads as two unrelated blocks.
"""

from __future__ import annotations

import pymupdf

from app.ingest.book import parse_toc_chapters


def _page(doc, lines: list[tuple[float, float, str]]) -> None:
    page = doc.new_page(width=595, height=842)
    for x, y, text in lines:
        page.insert_text((x, y), text, fontsize=11)


def test_chapter_word_convention(tmp_path):
    doc = pymupdf.open()
    _page(doc, [
        (60, 60, "Contents"),
        (60, 90, "Chapter 1"),
        (60, 105, "Chemical Reactions and Equations"),
        (60, 130, "Chapter 2"),
        (60, 145, "Acids, Bases and Salts"),
    ])
    path = tmp_path / "toc.pdf"
    doc.save(path)
    doc.close()
    assert parse_toc_chapters(path) == {
        1: "Chemical Reactions and Equations",
        2: "Acids, Bases and Salts",
    }


def test_dotted_number_convention(tmp_path):
    doc = pymupdf.open()
    _page(doc, [
        (60, 60, "Contents"),
        (60, 90, "1."),
        (60, 105, "Resources and Development"),
        (60, 118, "1"),
        (60, 140, "2."),
        (60, 155, "Forest and Wildlife Resources"),
        (60, 168, "13"),
    ])
    path = tmp_path / "toc.pdf"
    doc.save(path)
    doc.close()
    assert parse_toc_chapters(path) == {
        1: "Resources and Development",
        2: "Forest and Wildlife Resources",
    }


def test_roman_numeral_convention(tmp_path):
    doc = pymupdf.open()
    _page(doc, [
        (60, 60, "Contents"),
        (60, 90, "I. The Rise of Nationalism in Europe"),
        (60, 103, "3"),
        (60, 130, "II. Nationalism in India"),
        (60, 143, "29"),
    ])
    path = tmp_path / "toc.pdf"
    doc.save(path)
    doc.close()
    assert parse_toc_chapters(path) == {
        1: "The Rise of Nationalism in Europe",
        2: "Nationalism in India",
    }


def test_table_convention_where_labels_and_titles_are_two_separate_blocks(tmp_path):
    """The Economics prelims: every 'Chapter N' label first, then every title, in an order
    that pairs none of them correctly by text alone -- only their position on the page
    does. Built with real coordinates lifted from the actual NCERT file, since the whole
    point of the fallback is what linear reading order gets wrong.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=842)
    for x, y, text in [
        (85, 208, "Chapter"), (139, 208, "1"),
        (91, 289, "Chapter"), (145, 289, "2"),
        (91, 368, "Chapter"), (145, 368, "3"),
        (91, 447, "Chapter"), (145, 447, "4"),
        (91, 528, "Chapter"), (145, 528, "5"),
        (85, 592, "Appendix"), (477, 592, "90"),
    ]:
        page.insert_text((x, y), text, fontsize=11)
    for x, y, text in [
        (91, 230, "DEVELOPMENT"), (472, 228, "2"),
        (91, 309, "SECTORS"), (171, 309, "OF"), (199, 309, "THE"),
        (234, 309, "INDIAN"), (297, 309, "ECONOMY"), (472, 307, "18"),
        (91, 388, "MONEY"), (155, 388, "AND"), (195, 388, "CREDIT"), (472, 387, "38"),
        (91, 468, "GLOBALISATION"), (225, 468, "AND"), (266, 468, "THE"),
        (302, 468, "INDIAN"), (365, 468, "ECONOMY"), (472, 466, "54"),
        (92, 548, "CONSUMER"), (192, 548, "RIGHTS"), (472, 546, "74"),
    ]:
        page.insert_text((x, y), text, fontsize=11)
    path = tmp_path / "toc.pdf"
    doc.save(path)
    doc.close()
    assert parse_toc_chapters(path) == {
        1: "Development",
        2: "Sectors Of The Indian Economy",
        3: "Money And Credit",
        4: "Globalisation And The Indian Economy",
        5: "Consumer Rights",
    }


def test_no_recognisable_convention_is_an_empty_answer_not_a_guess(tmp_path):
    doc = pymupdf.open()
    _page(doc, [(60, 60, "Some unrelated prelims text with no chapter listing at all.")])
    path = tmp_path / "toc.pdf"
    doc.save(path)
    doc.close()
    assert parse_toc_chapters(path) == {}
