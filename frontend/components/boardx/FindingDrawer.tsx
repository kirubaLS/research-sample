"use client";

import { useEffect } from "react";
import { AttentionPill, BoardUrgencyIndicator, ConfidencePill, attentionFromRate } from "./Status";
import { CauseNotLocalized } from "./EmptyStates";
import type { BoardXFinding } from "./types";

/**
 * §5.5 -- right-side slide-in drawer, not a new route/page, so the principal stays in
 * context on a long scroll. Opened from any FindingCard's "View Finding Details" button.
 */
export function FindingDrawer({
  finding, onClose, onViewStudents,
}: {
  finding: BoardXFinding | null;
  onClose: () => void;
  onViewStudents?: (f: BoardXFinding) => void;
}) {
  useEffect(() => {
    if (!finding) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [finding, onClose]);

  if (!finding) return null;
  const attention = attentionFromRate(1 - Math.min(1, finding.avgMarksLost / 10));

  return (
    <div className="bx-drawer-overlay" onClick={onClose}>
      <aside className="bx-drawer" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="bx-drawer-close" onClick={onClose} aria-label="Close">×</button>

        <p className="bx-drawer-eyebrow">{finding.topicPath.slice(0, -1).join(" → ")}</p>
        <h2 className="bx-drawer-title">{finding.topicPath[finding.topicPath.length - 1]}</h2>

        <div className="bx-drawer-stats">
          <div>
            <p className="bx-drawer-n">{finding.studentsAffected}</p>
            <p className="bx-drawer-l">students affected</p>
          </div>
          <div>
            <p className="bx-drawer-n">{finding.avgMarksLost.toFixed(1)}</p>
            <p className="bx-drawer-l">marks avg. exposure</p>
          </div>
        </div>

        <div className="bx-drawer-badges">
          <BoardUrgencyIndicator
            tier={finding.urgencyTier}
            yearsAppeared={finding.yearsAppeared}
            yearsEligible={finding.yearsEligible}
          />
          <ConfidencePill tier={finding.confidence} />
          <AttentionPill state={attention} />
        </div>

        <section className="bx-drawer-section">
          <h3>What BoardX Observed</h3>
          {finding.causeLocalized ? (
            <p>{finding.interpretation}</p>
          ) : (
            <CauseNotLocalized />
          )}
        </section>

        {finding.mostAffectedSections && finding.mostAffectedSections.length > 0 && (
          <section className="bx-drawer-section">
            <h3>Most Affected Sections</h3>
            <div className="bx-drawer-sections">
              {finding.mostAffectedSections.map((s) => (
                <span key={s.label} className="bx-drawer-section-chip">
                  {s.label} <strong>{s.pct}%</strong>
                </span>
              ))}
            </div>
          </section>
        )}

        <button
          type="button"
          className="bx-btn-primary"
          onClick={() => onViewStudents?.(finding)}
          style={{ marginTop: 4 }}
        >
          View {finding.studentsAffected} Students
        </button>

        {finding.recommendedAction && (
          <section className="bx-drawer-section">
            <h3>Recommended Intervention</h3>
            <p>{finding.recommendedAction}</p>
          </section>
        )}

        <a href="#" className="bx-drawer-link" onClick={(e) => e.preventDefault()}>
          View Full Analysis →
        </a>

        <style jsx>{`
          .bx-drawer-overlay {
            position: fixed; inset: 0; background: rgba(20, 33, 61, 0.32); z-index: 60;
            display: flex; justify-content: flex-end;
          }
          .bx-drawer {
            background: var(--surface); width: min(420px, 92vw); height: 100%;
            padding: 28px 24px 40px; overflow-y: auto; position: relative;
            box-shadow: -8px 0 32px rgba(0,0,0,0.14);
          }
          .bx-drawer-close {
            position: absolute; top: 16px; right: 16px; background: none; border: none;
            font-size: 22px; color: var(--ink-3); cursor: pointer; line-height: 1;
          }
          .bx-drawer-eyebrow { margin: 0; font-size: 12.5px; color: var(--ink-3); }
          .bx-drawer-title {
            margin: 2px 0 16px; font-family: var(--font-display), sans-serif; font-size: 22px;
            color: var(--brand-ink);
          }
          .bx-drawer-stats { display: flex; gap: 26px; margin-bottom: 14px; }
          .bx-drawer-n { margin: 0; font-size: 22px; font-weight: 800; font-family: var(--font-display), sans-serif; }
          .bx-drawer-l { margin: 0; font-size: 12px; color: var(--ink-3); }
          .bx-drawer-badges { display: flex; flex-direction: column; gap: 10px; margin-bottom: 18px; }
          .bx-drawer-section { margin: 18px 0; }
          .bx-drawer-section h3 {
            margin: 0 0 6px; font-size: 12.5px; text-transform: uppercase; letter-spacing: 0.04em;
            color: var(--ink-3); font-weight: 700;
          }
          .bx-drawer-section p { margin: 0; font-size: 14px; color: var(--ink-2); line-height: 1.55; }
          .bx-drawer-sections { display: flex; gap: 8px; flex-wrap: wrap; }
          .bx-drawer-section-chip {
            background: var(--surface-2); border-radius: 999px; padding: 4px 10px; font-size: 12.5px;
          }
          .bx-btn-primary {
            background: var(--brand-ink); color: #fff; border: none; border-radius: 8px;
            padding: 9px 16px; font-size: 13.5px; font-weight: 700; cursor: pointer;
          }
          .bx-drawer-link {
            display: inline-block; margin-top: 22px; font-size: 13.5px; font-weight: 700;
            color: var(--brand-ink);
          }
        `}</style>
      </aside>
    </div>
  );
}
