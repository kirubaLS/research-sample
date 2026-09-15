from app.insights.blueprint_validator import validate_paper, min_questions_for_ratio
from app.insights.model import CompetencyTier, Complexity, Dependency
from .fixtures import q


def test_min_questions_for_ratio_matches_h3_table():
    assert min_questions_for_ratio(0.50) == 10
    assert min_questions_for_ratio(0.40) == 13
    assert min_questions_for_ratio(0.25) == 20


def test_undersized_chapter_is_marked_non_diagnostic():
    questions = [
        q("Q1", "Surface Areas and Volumes", "v1", CompetencyTier.RECALL,
          Complexity.L1, Dependency.D0, 1),
    ]
    report = validate_paper(questions, recall_ratio=0.40)
    assert "Surface Areas and Volumes" in report.non_diagnostic_chapters
    assert report.diagnosable_chapters == []
    assert "covered for syllabus completeness" in report.coverage_statement
