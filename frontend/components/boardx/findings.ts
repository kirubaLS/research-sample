import type { BoardFrequencyRow, CohortReport } from "@/lib/api";
import type { BoardXFinding } from "./types";

/** Real GET /reports/cohort top_losses, enriched (best-effort) with GET /board-frequency
 *  years_appeared/years_eligible, turned into the one reusable finding unit (§5.4). Shared
 *  between the Overview scroll, the Interventions tab and the Board-Urgency-vs-Impact
 *  table so every screen renders the same underlying findings. */
export function findingsFromTopLosses(
  cohort: CohortReport, freq: BoardFrequencyRow[],
): BoardXFinding[] {
  return cohort.top_losses.map((l) => {
    const f = freq.find((r) => r.concept_family === l.concept_family);
    return {
      id: l.concept_family,
      topicPath: [cohort.assessment_title, l.label],
      studentsAffected: l.students_affected,
      avgMarksLost: l.avg_marks_lost,
      urgencyTier: l.board_urgency as BoardXFinding["urgencyTier"],
      yearsAppeared: f?.years_appeared,
      yearsEligible: f?.years_eligible,
      confidence: l.confidence,
      interpretation:
        `${l.students_affected} student${l.students_affected === 1 ? "" : "s"} lost an average ` +
        `of ${l.avg_marks_lost.toFixed(1)} marks on ${l.label} on this paper.`,
      causeLocalized: true,
      mostAffectedSections: cohort.section_bars
        .slice()
        .sort((a, b) => a.pct - b.pct)
        .slice(0, 3)
        .map((s) => ({ label: s.label, pct: Math.round(100 - s.pct) })),
      recommendedAction: `Targeted revision and Board-style practice on ${l.label}.`,
    };
  });
}
