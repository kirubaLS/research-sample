"""Write a curriculum into the taxonomy. Idempotent: re-running changes nothing."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.curriculum import Curriculum
from app.models import BoardUnitWeight, ChapterBoardUnit, TaxonomyNode


def apply(db: Session, curriculum: Curriculum, version: str = "CBSE-2026-27") -> dict:
    def node(code: str) -> TaxonomyNode | None:
        return db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))

    created = {"subject": 0, "units": 0, "chapters": 0, "mappings": 0, "families": 0}

    subject = node(curriculum.subject_code)
    if subject is None:
        subject = TaxonomyNode(
            kind="subject", code=curriculum.subject_code, label=curriculum.subject_label,
            path=curriculum.subject_code, curriculum_version=version,
        )
        db.add(subject)
        db.flush()
        created["subject"] = 1

    for unit in curriculum.units:
        if node(unit.code) is None:
            row = TaxonomyNode(
                kind="board_unit", code=unit.code, label=unit.label,
                parent_id=subject.id, path=unit.code, curriculum_version=version,
            )
            db.add(row)
            db.flush()
            db.add(BoardUnitWeight(
                curriculum_version=version, board_unit_id=row.id,
                weight_pct=unit.weight_pct, source_doc_url=curriculum.source_doc_url,
            ))
            created["units"] += 1

    for chapter in curriculum.chapters:
        row = node(chapter.code)
        if row is None:
            row = TaxonomyNode(
                kind="chapter", code=chapter.code, label=chapter.label,
                parent_id=subject.id, path=chapter.code, curriculum_version=version,
            )
            db.add(row)
            db.flush()
            created["chapters"] += 1
        unit = node(chapter.board_unit)
        if unit is not None and db.scalar(
            select(ChapterBoardUnit).where(
                ChapterBoardUnit.chapter_id == row.id,
                ChapterBoardUnit.curriculum_version == version,
            )
        ) is None:
            # explicit, never inferred from the tree: History map marks belong to
            # Geography's unit, and a walk up the hierarchy gets exactly that wrong
            db.add(ChapterBoardUnit(
                curriculum_version=version, chapter_id=row.id, board_unit_id=unit.id,
            ))
            created["mappings"] += 1

    for code, label, chapter_code in curriculum.concept_families:
        parent = node(chapter_code)
        if parent is not None and node(code) is None:
            db.add(TaxonomyNode(
                kind="concept_family", code=code, label=label,
                parent_id=parent.id, path=code, curriculum_version=version,
            ))
            created["families"] += 1

    db.commit()
    return created
