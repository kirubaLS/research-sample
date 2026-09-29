"use client";

import { useEffect, useState } from "react";
import { Lock } from "lucide-react";
import { api, MarksGridReport } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { BusyBanner } from "@/components/BusyBanner";
import { EvidenceState } from "@/components/EvidenceState";

/** A small, fixed palette -- every color a legend dot can ever be. Which real chapter/
 * concept_family name gets which color is derived deterministically below (a hash of
 * the name into this array), never hand-assigned per chapter, so a new subject's real
 * groups still get a stable, distinct color without anyone hardcoding a mapping. */
const PALETTE = [
  "var(--brand-blue)", "var(--brand-teal)", "var(--brand-gold)", "var(--brand-green)",
  "#9b6bd6", "#e0668a", "#3f8f76", "#c17a2e",
];

function colorFor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

/** The read-only "already mapped" per-question grid for a paper whose marks are fully
 * entered and confirmed for this section: real awarded marks (GET .../marks-grid),
 * a real chapter/concept_family color legend, and a real per-student total. Renders
 * nothing (returns null) when the paper is not yet fully marked -- callers fall back
 * to the live MarksEntryGrid upload flow in that case, never a fabricated grid. */
export function ConfirmedMarksGrid({
  section,
  assessmentId,
  onNotReady,
}: {
  section: string;
  assessmentId: string;
  /** Called once, after the fetch resolves, if this paper is not fully marked yet --
   *  the caller's cue to show the live entry flow instead. */
  onNotReady?: () => void;
}) {
  const [report, setReport] = useState<MarksGridReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setReport(null);
    setError(null);
    const key = getApiKey();
    if (!key) return;
    let cancelled = false;
    api
      .teacherMarksGrid(key, section, assessmentId)
      .then((r) => {
        if (cancelled) return;
        if (!r.fully_marked) {
          onNotReady?.();
          return;
        }
        setReport(r);
      })
      .catch(() => {
        if (cancelled) return;
        onNotReady?.();
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section, assessmentId]);

  if (error) return <EvidenceState kind="early">{error}</EvidenceState>;
  if (!report) return <BusyBanner label="Loading marks…" />;

  const groups = Array.from(new Set(report.questions.map((q) => q.group)));

  return (
    <div className="pm-marks-card">
      <div className="pm-marks-head" role="status">
        <span className="pm-marks-head__text">
          {report.questions.length} questions, {report.total_marks} marks total. These answer cards are already
          mapped.
        </span>
        <span className="pm-pill pm-pill--mapped">
          <Lock size={12} /> Mapped, view only
        </span>
      </div>

      <div className="pm-legend">
        {groups.map((g) => (
          <span className="pm-legend-item" key={g}>
            <span className="pm-legend-dot" style={{ background: colorFor(g) }} /> {g}
          </span>
        ))}
      </div>

      <div className="pm-grid-wrap">
        <table className="pm-grid">
          <thead>
            {/* one colour band per question, so a chapter reads as a run of columns */}
            <tr className="pm-grid__strip" aria-hidden="true">
              <td />
              <td />
              {report.questions.map((q) => (
                <td key={q.address} style={{ background: colorFor(q.group) }} />
              ))}
              <td />
            </tr>
            <tr>
              <th className="pm-grid__left">Roll</th>
              <th className="pm-grid__left">Student</th>
              {report.questions.map((q) => (
                <th key={q.address} title={q.group}>
                  <div className="pm-grid__q">{q.label}</div>
                  <div className="pm-grid__max">/{q.max_marks}</div>
                </th>
              ))}
              <th className="pm-grid__total-head">Total</th>
            </tr>
          </thead>
          <tbody>
            {report.students.map((row) => (
              <tr key={row.student_id}>
                <td className="pm-grid__left pm-grid__roll">{row.roll_no}</td>
                <td className="pm-grid__left strong">{row.name}</td>
                {report.questions.map((q) => (
                  <td key={q.address}>
                    <span className="pm-cell">{row.marks[q.address] ?? "—"}</span>
                  </td>
                ))}
                <td className="pm-grid__total-cell">
                  <span className="pm-total">{row.total}</span>
                  <span className="pm-total__max">/{report.total_marks}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="small muted pm-marks-foot">
        Marks for all {report.students.length} students are saved and feed the principal&apos;s dashboard. They
        cannot be edited here.
      </p>
    </div>
  );
}
