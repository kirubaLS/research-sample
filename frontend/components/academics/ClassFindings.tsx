"use client";

/**
 * This class's own top losses on one test -- the real part of BoardX's Overview/
 * Interventions findings, folded into the Class detail screen per the reference design
 * ("the Classes flow is the one navigation into this data now"), scoped to real data
 * only. GET /reports/cohort/{assessmentId}?section_id=... (reports.py's cohort_report)
 * -- the same aggregation BoardX itself uses, narrowed to this one class's students
 * instead of the whole school.
 *
 * Deliberately does NOT carry BoardX's "Potential Ladder", "Recoverable marks" or
 * "pattern label" sections -- those are still built against mock data in BoardX itself
 * (components/boardx/mock.ts, each with its own TODO(backend) note), and folding a mock
 * number into a real page would be worse than leaving it out.
 */

import { useEffect, useState } from "react";
import { api, type CohortReport } from "@/lib/api";
import { getApiKey } from "@/lib/session";

const URGENCY_LABEL: Record<string, string> = {
  high: "High board urgency", medium: "Medium board urgency", low: "Low board urgency",
};

export function ClassFindings({ sectionId, assessmentId }: { sectionId: string; assessmentId: string }) {
  const [cohort, setCohort] = useState<CohortReport | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key || !assessmentId) {
      setCohort(null);
      setNote(null);
      return;
    }
    setCohort(null);
    setNote(null);
    api
      .cohortReport(key, assessmentId, sectionId)
      .then(setCohort)
      .catch(() => setNote("No marks entered for this class on this test yet, so there is nothing to find."));
  }, [sectionId, assessmentId]);

  if (!assessmentId) return null;
  if (note) return null;
  if (!cohort) return <p className="muted small">Loading findings…</p>;
  if (cohort.top_losses.length === 0) return null;

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <h2 style={{ marginTop: 0, fontSize: 15 }}>Where this class lost the most marks</h2>
      <p className="cardnote" style={{ margin: "0 0 14px" }}>
        On {cohort.assessment_title}, this class only -- {cohort.students_analysed} student
        {cohort.students_analysed === 1 ? "" : "s"} analysed.
      </p>
      <div className="stack" style={{ gap: 10 }}>
        {cohort.top_losses.slice(0, 5).map((loss) => (
          <div key={loss.concept_family} className="row between" style={{ alignItems: "flex-start", gap: 12 }}>
            <div>
              <div className="strong">{loss.label}</div>
              <div className="small muted">
                {loss.students_affected} student{loss.students_affected === 1 ? "" : "s"} lost an
                average of {loss.avg_marks_lost.toFixed(1)} marks
                {loss.board_urgency && ` · ${URGENCY_LABEL[loss.board_urgency] ?? loss.board_urgency}`}
              </div>
            </div>
            <span className="small muted" style={{ whiteSpace: "nowrap" }}>
              {loss.confidence === "HIGH" ? "High confidence"
                : loss.confidence === "MEDIUM" ? "Medium confidence" : "Emerging (few students)"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
