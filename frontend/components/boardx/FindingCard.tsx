"use client";

import { AttentionPill, BoardUrgencyIndicator, ConfidencePill, attentionFromRate } from "./Status";
import { CauseNotLocalized } from "./EmptyStates";
import type { BoardXFinding } from "./types";

/**
 * §5.4 -- the one reusable finding unit. Every finding on every BoardX screen (Marks
 * Loss, Urgency-vs-Impact, Anomalies, Interventions) renders through this component --
 * never a bare stat. When cause isn't localized the card changes shape (§5.7).
 */
export function FindingCard({
  finding, onViewStudents, onViewDetails,
}: {
  finding: BoardXFinding;
  onViewStudents?: (f: BoardXFinding) => void;
  onViewDetails?: (f: BoardXFinding) => void;
}) {
  const attention = attentionFromRate(
    finding.avgMarksLost > 0 ? 1 - Math.min(1, finding.avgMarksLost / 10) : 1,
  );

  return (
    <div className="bx-card">
      <p className="bx-path">
        {finding.topicPath.map((seg, i) => (
          <span key={i}>
            {i > 0 && <span className="bx-sep"> → </span>}
            {seg}
          </span>
        ))}
      </p>

      <div className="bx-stats">
        <div>
          <p className="bx-stat-n">{finding.studentsAffected}</p>
          <p className="bx-stat-l">students affected</p>
        </div>
        <div>
          <p className="bx-stat-n">{finding.avgMarksLost.toFixed(1)}</p>
          <p className="bx-stat-l">avg. marks lost</p>
        </div>
      </div>

      <div className="bx-badges">
        <BoardUrgencyIndicator
          tier={finding.urgencyTier}
          yearsAppeared={finding.yearsAppeared}
          yearsEligible={finding.yearsEligible}
        />
        <ConfidencePill tier={finding.confidence} />
        <AttentionPill state={attention} />
      </div>

      {finding.causeLocalized ? (
        <p className="bx-interp">{finding.interpretation}</p>
      ) : (
        <CauseNotLocalized />
      )}

      <div className="bx-actions">
        <button type="button" className="bx-btn-primary" onClick={() => onViewStudents?.(finding)}>
          View {finding.studentsAffected} Students
        </button>
        <button type="button" className="bx-btn-secondary" onClick={() => onViewDetails?.(finding)}>
          View Finding Details
        </button>
      </div>

      <style jsx>{`
        .bx-card {
          background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius);
          padding: 18px 20px; display: flex; flex-direction: column; gap: 10px;
        }
        .bx-path {
          margin: 0; font-family: var(--font-display), sans-serif; font-weight: 700;
          font-size: 16px; color: var(--brand-ink);
        }
        .bx-sep { color: var(--ink-3); font-weight: 500; }
        .bx-stats { display: flex; gap: 28px; flex-wrap: wrap; }
        .bx-stat-n { margin: 0; font-size: 20px; font-weight: 800; font-family: var(--font-display), sans-serif; }
        .bx-stat-l { margin: 0; font-size: 12px; color: var(--ink-3); }
        .bx-badges { display: flex; gap: 16px; flex-wrap: wrap; align-items: center; }
        .bx-interp { margin: 0; font-size: 13.5px; color: var(--ink-2); line-height: 1.5; }
        .bx-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 4px; }
        .bx-btn-primary {
          background: var(--brand-ink); color: #fff; border: none; border-radius: 8px;
          padding: 8px 14px; font-size: 13px; font-weight: 700; cursor: pointer;
        }
        /* The global button:hover rule (globals.css) beats this on specificity for
           background alone, so without an explicit hover rule here the secondary button
           picks up that dark hover background while keeping its own dark text -- navy on
           navy. Pin both color and background together on hover so they never diverge. */
        .bx-btn-primary:hover {
          background: var(--brand-ink-2); color: #fff;
        }
        .bx-btn-secondary {
          background: none; border: 1.5px solid var(--brand-ink); color: var(--brand-ink);
          border-radius: 8px; padding: 8px 14px; font-size: 13px; font-weight: 700; cursor: pointer;
        }
        .bx-btn-secondary:hover {
          background: var(--brand-ink-soft); color: var(--brand-ink);
        }
      `}</style>
    </div>
  );
}
