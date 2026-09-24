"use client";

import { ArrowRight, Users } from "lucide-react";
import type { Finding } from "@/lib/avai-mock-data";
import { emptyStates } from "@/lib/avai-mock-data";
import { ConfidenceMeter, UrgencyChip } from "./Status";
import { EvidenceState } from "./EvidenceState";

/**
 * §5.4, the one reusable "finding" unit. Every diagnostic statement in
 * BoardX renders through this; there are no bare stats.
 */
export function FindingCard({ finding, onOpen, compact = false }: { finding: Finding; onOpen?: (f: Finding) => void; compact?: boolean }) {
  const notLocalized = finding.causeStatus === "not_localized";
  return (
    <article className={`finding ${notLocalized ? "finding--not-localized" : ""} ${compact ? "finding--compact" : ""}`}>
      <header className="finding__head">
        <div>
          <div className="finding__subject">{finding.subject}</div>
          <h3 className="finding__title">{finding.topic}</h3>
          <div className="finding__subskill">{finding.subskill ? finding.subskill : "Whole chapter, no single sub-skill"}</div>
        </div>
        <UrgencyChip level={finding.boardUrgency} withLabel={false} />
      </header>

      <div className="finding__metrics">
        <div className="metric">
          <div className="metric__label">Students affected</div>
          <div className="metric__value">
            {finding.studentsAffected}
            <small>
              <Users size={11} style={{ verticalAlign: "-1px" }} /> analysed
            </small>
          </div>
        </div>
        <div className="metric">
          <div className="metric__label">Avg marks lost</div>
          <div className="metric__value">
            {finding.avgMarksLost.toFixed(1)}
            <small>per student</small>
          </div>
        </div>
      </div>

      <div className="finding__status">
        <ConfidenceMeter level={finding.confidence} />
        <span className="tag">{finding.boardRecurrence}</span>
        {notLocalized && <span className="tag tag--gold">Cause not localized</span>}
      </div>

      <p className="finding__obs">{finding.observation}</p>

      {notLocalized && (
        <div style={{ padding: "12px 18px 0" }}>
          <EvidenceState kind="cause" compact>
            {emptyStates.causeNotLocalized}
          </EvidenceState>
        </div>
      )}

      <footer className="finding__foot">
        <div className="small muted">
          {finding.recommendedIntervention?.length
            ? `Suggested: ${finding.recommendedIntervention[0]}`
            : notLocalized
              ? "Manual answer-script review recommended"
              : "No intervention prescribed"}
        </div>
        {onOpen && (
          <button className="btn btn--sm" onClick={() => onOpen(finding)}>
            View details <ArrowRight size={13} />
          </button>
        )}
      </footer>
    </article>
  );
}
