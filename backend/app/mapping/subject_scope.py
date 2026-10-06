"""Which subjects the new mapping logic runs for.

Every behaviour added to the mapping pipeline for one subject's sake -- the unified
section scope, the major-topic list and prompts, the review-flag rule, cite-by-number,
card mode and the rest -- is a flag that defaults OFF. A flag alone is global, though:
turn it on and every subject's papers take the new path, including subjects whose mapping
is finished and must not move while another subject is reworked.

``mapping_v2_subjects`` is the second key. A flag below takes effect for a paper only when
the paper's subject is in that list; for any other subject every one of them reads False
and the pipeline runs exactly the path it ran before. Adding Science later is one entry in
the list, and nothing about Mathematics or Social Science changes.
"""

from __future__ import annotations

from typing import Any

#: the boolean settings that change how a paper is mapped, chosen per subject. Anything that
#: is not mapping (duplicate holds, the teacher screens) is not here.
SUBJECT_FLAGS = (
    "paper_capture_structure",
    "sst_unified_scope",
    "balanced_group_candidates",
    "cross_scope_fallback",
    "skip_single_chapter_judge",
    "topic_depth_cap",
    "topic_major_only_document",
    "book_map_only_subtopics",
    "topic_card_mode",
    "topic_adaptive_reads",
    "cite_passages_by_number",
    "review_flag_rule",
    "chapter_gate",
    "chapter_gate_enforce",
    "chapter_gate_reranker",
    "chapter_gate_classifier",
    "retrieval_contextual_prefix",
    "memory_recall",
    "memory_reuse",
)


def applies(subject_code: str | None, settings: Any = None) -> bool:
    """Whether the new mapping logic is allowed for this subject, group or chapter code.
    "X.GEO.MINERALSENERGY" belongs to "X.GEO"; a paper of the group "X.SST" is listed as
    "X.SST". An unknown subject is not allowed: isolation first."""
    if not subject_code:
        return False
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    listed = settings.mapping_v2_subjects or []
    return any(subject_code == s or subject_code.startswith(s + ".") for s in listed)


def for_subject(settings: Any, subject_code: str | None):
    """``settings`` as this subject's paper must see it: unchanged for a listed subject,
    with every SUBJECT_FLAGS flag forced False for any other. A copy -- the global settings
    object is never modified."""
    if applies(subject_code, settings):
        return settings
    off = {name: False for name in SUBJECT_FLAGS if hasattr(settings, name)}
    return settings.model_copy(update=off)
