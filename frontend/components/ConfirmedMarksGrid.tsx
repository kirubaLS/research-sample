"use client";

import { useEffect, useState } from "react";
import { CheckCircle2 } from "lucide-react";
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
    <div className="card" style={{ marginTop: 16 }}>
      <div className="card__body" style={{ display: "grid", gap: 10 }}>
        <div className="flagbar flagbar--ok" role="status" style={{ justifyContent: "space-between" }}>
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <CheckCircle2 size={16} />
            {report.questions.length} questions, {report.total_marks} marks total. These answer cards are already
            mapped.
          </span>
          <span className="tag tag--green">Mapped, view only</span>
        </div>

        <div className="marks-grid__legend">
          {groups.map((g) => (
            <span className="marks-grid__legend-item" key={g}>
              <span className="marks-grid__legend-dot" style={{ background: colorFor(g) }} /> {g}
            </span>
          ))}
        </div>

        <div className="table-wrap table-wrap--scroll">
          <table className="table marks-grid">
            <thead>
              <tr>
                <th>Roll</th>
                <th>Student</th>
                {report.questions.map((q) => (
                  <th key={q.address} className="num" title={q.group}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                      <span className="marks-grid__legend-dot" style={{ background: colorFor(q.group) }} />
                      {q.label}../{q.max_marks}
                    </span>
                  </th>
                ))}
                <th className="num">Total</th>
              </tr>
            </thead>
            <tbody>
              {report.students.map((row) => (
                <tr key={row.student_id}>
                  <td className="mono">{row.roll_no}</td>
                  <td>{row.name}</td>
                  {report.questions.map((q) => (
                    <td key={q.address} className="num">
                      {row.marks[q.address] ?? "—"}
                    </td>
                  ))}
                  <td className="num strong">
                    {row.total}/{report.total_marks}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="small muted" style={{ margin: 0 }}>
          Marks for all {report.students.length} students are saved and feed the principal&apos;s dashboard. They
          cannot be edited here.
        </p>
      </div>
    </div>
  );
}
