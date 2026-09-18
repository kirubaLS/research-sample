"use client";

import type { BoardFrequencyRow, CohortReport } from "@/lib/api";
import { AttentionPill, attentionFromRate } from "@/components/boardx/Status";
import { FindingCard } from "@/components/boardx/FindingCard";
import type { BoardXFinding } from "@/components/boardx/types";
import { INTERVENTION_PRIORITY_NOTE } from "@/components/boardx/mock";

/** §5.6's internal nav also lists Sections and Subjects as their own tabs. These are the
 *  "thinner passes" the task allows -- same real cohort data as the Overview scroll's
 *  Section Comparison / Subject Conversion blocks, laid out as a dedicated screen a
 *  principal can jump straight to from BoardX's own nav. */
export function SectionsTab({ cohort, onGoToStudents }: {
  cohort: CohortReport | null;
  onGoToStudents: (section: string) => void;
}) {
  if (!cohort) return <p className="bx-small bx-muted">No cohort data for this assessment yet.</p>;
  return (
    <div className="bx-table">
      <div className="bx-trow bx-thead"><span>Section</span><span>Students</span><span>Attainment</span><span>Attention</span><span /></div>
      {cohort.section_bars.map((s) => (
        <div className="bx-trow" key={s.section_id}>
          <span>{s.label}</span>
          <span>{s.students}</span>
          <span>{s.pct.toFixed(0)}%</span>
          <span><AttentionPill state={attentionFromRate(s.pct / 100)} /></span>
          <button type="button" className="bx-btn-secondary" onClick={() => onGoToStudents(s.label)}>
            View students
          </button>
        </div>
      ))}
      <p className="bx-small bx-muted" style={{ marginTop: 8 }}>
        A section&rsquo;s attention level reflects attainment on this paper only -- never an
        implication about teacher quality.
      </p>
      <style jsx>{tabCss}</style>
    </div>
  );
}

export function SubjectsTab({ cohort }: { cohort: CohortReport | null }) {
  if (!cohort) return <p className="bx-small bx-muted">No cohort data for this assessment yet.</p>;
  return (
    <div className="bx-table">
      <p className="bx-small bx-muted">{cohort.subject_bars_note}</p>
      <div className="bx-trow bx-thead"><span>Subject</span><span>Assessment</span><span>Avg. attainment</span></div>
      {cohort.subject_bars.map((s) => (
        <div className="bx-trow" key={s.subject_code}>
          <span className="bx-subject">{s.subject_label}</span>
          <span className="bx-muted bx-small">{s.assessment_title}</span>
          <span className="bx-pct">{s.pct.toFixed(0)}%</span>
        </div>
      ))}
      <style jsx>{tabCss}</style>
    </div>
  );
}

export function InterventionsTab({
  findings, onOpenDrawer, onGoToStudents,
}: {
  findings: BoardXFinding[];
  onOpenDrawer: (f: BoardXFinding) => void;
  onGoToStudents: () => void;
}) {
  return (
    <div>
      <p className="bx-small bx-muted" style={{ marginBottom: 14 }}>{INTERVENTION_PRIORITY_NOTE}</p>
      {findings.length === 0 && <p className="bx-small bx-muted">No findings yet for this assessment.</p>}
      <div className="bx-findings">
        {findings.map((f, i) => (
          <div key={f.id}>
            <p className="bx-priority-why">Priority {i + 1} of {findings.length}</p>
            <FindingCard finding={f} onViewStudents={onGoToStudents} onViewDetails={onOpenDrawer} />
          </div>
        ))}
      </div>
      <style jsx>{`
        .bx-findings { display: grid; gap: 14px; }
        .bx-priority-why { font-size: 12.5px; color: var(--ink-3); margin: 0 0 6px; }
      `}</style>
    </div>
  );
}

const tabCss = `
  .bx-table { display: flex; flex-direction: column; gap: 6px; overflow-x: auto; }
  .bx-trow { display: grid; grid-template-columns: repeat(auto-fit, minmax(90px, 1fr)); gap: 10px; padding: 12px 14px; align-items: center; background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius-sm, 10px); font-size: 13.5px; transition: border-color var(--dur-fast, 0.16s) var(--ease, ease); }
  .bx-trow:not(.bx-thead):hover { border-color: var(--brand-ink-2); }
  .bx-thead { background: none; border: none; font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.05em; padding: 0 14px; font-weight: 700; }
  .bx-small { font-size: 13px; }
  .bx-muted { color: var(--ink-3); }
  .bx-subject { font-weight: 700; color: var(--ink); }
  .bx-pct { font-variant-numeric: tabular-nums; font-weight: 700; color: var(--brand-ink); }
  .bx-btn-secondary { background: none; border: 1.5px solid var(--brand-ink); color: var(--brand-ink); border-radius: 8px; padding: 5px 10px; font-size: 12.5px; font-weight: 700; cursor: pointer; justify-self: start; }
`;
