"use client";

import { TrendingDown } from "lucide-react";
import { Stagger, StaggerItem } from "@/components/motion";
import type { CohortReport } from "@/lib/api";

export type TopLoss = CohortReport["top_losses"][number];

/** The "worth a look" grid: real top-losses from GET /reports/cohort/{id}, each
 * carrying the students-affected/avg-marks-lost numbers it was computed from --
 * never a bare claim. */
export function AnomalyGrid({ losses }: { losses: TopLoss[] }) {
  if (losses.length === 0) {
    return <p className="small muted">No concept losses stand out against this assessment&apos;s data.</p>;
  }

  return (
    <Stagger className="grid grid--2" gap={0.06}>
      {losses.map((a) => (
        <StaggerItem key={a.concept_family}>
          <div
            className="card hoverlift"
            style={{ height: "100%", display: "flex", flexDirection: "column", borderTop: "3px solid var(--risk)" }}
          >
            <div className="card__body" style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span className="finding__subject">{a.label}</span>
                <span className="tag" style={{ color: "var(--risk)" }}>
                  <TrendingDown size={13} /> Concept loss
                </span>
              </div>
              <div className="strong" style={{ marginTop: 4, fontSize: 15, lineHeight: 1.35 }}>
                {a.students_affected} student{a.students_affected === 1 ? "" : "s"} losing marks on {a.label}
              </div>
              <p className="small muted" style={{ marginTop: 6 }}>
                {a.board_urgency ? `Board urgency: ${a.board_urgency}. ` : ""}
                Confidence: {a.confidence}.
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(104px, 1fr))", gap: 8, marginTop: 12 }}>
                <div className="metric">
                  <div className="metric__label">Students affected</div>
                  <div className="metric__value" style={{ fontSize: 16 }}>{a.students_affected}</div>
                </div>
                <div className="metric">
                  <div className="metric__label">Avg marks lost</div>
                  <div className="metric__value" style={{ fontSize: 16 }}>{a.avg_marks_lost}</div>
                </div>
              </div>
            </div>
          </div>
        </StaggerItem>
      ))}
    </Stagger>
  );
}
