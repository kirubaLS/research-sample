"use client";

import { useEffect, useMemo, useState } from "react";
import { Diagnosis } from "@/components/Diagnosis";
import { api, type Overview, type StudentDiagnosis } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { AttentionPill, attentionFromRate, type Attention } from "@/components/boardx/Status";
import { Avatar } from "@/components/academics/Avatar";

interface StudentRow {
  student_id: string;
  name: string;
  roll_no: string;
  section_label: string;
  earned: number;
  available: number;
  rate: number | null;
  marksLost: number;
  mainBlocker: string;
  attention: Attention;
}

/** §5.6 -- Student Intelligence: filter row + ranked table, built for real off
 *  GET /reports/student/{id} (one call per student who has marks on this assessment).
 *  Rank is present but never the headline -- the row's real payload is "what's stopping
 *  this student", per the founder's UX rule. */
export function StudentsTab({
  overview, assessmentId, initialBandFilter,
}: {
  overview: Overview;
  assessmentId: string;
  initialBandFilter?: string;
}) {
  const [rows, setRows] = useState<StudentRow[]>([]);
  const [diagnoses, setDiagnoses] = useState<Record<string, StudentDiagnosis>>({});
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [sectionFilter, setSectionFilter] = useState("All");
  const [attentionFilter, setAttentionFilter] = useState("All");
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key || !assessmentId) return;
    let cancelled = false;
    setLoading(true);
    setRows([]);
    setDiagnoses({});

    (async () => {
      const out: StudentRow[] = [];
      const diag: Record<string, StudentDiagnosis> = {};
      for (const section of overview.sections) {
        let roster;
        try {
          roster = await api.roster(key, section.section_id);
        } catch {
          continue;
        }
        const candidates = roster.students.filter((s) => s.papers_marked > 0);
        // Small batches so a section of 40 doesn't fire 40 simultaneous requests.
        for (let i = 0; i < candidates.length; i += 6) {
          const batch = candidates.slice(i, i + 6);
          const results = await Promise.allSettled(
            batch.map((s) => api.studentDiagnosis(key, s.student_id, assessmentId)),
          );
          results.forEach((r, j) => {
            if (r.status !== "fulfilled") return;
            const d = r.value;
            diag[batch[j].student_id] = d;
            const focus = d.focus[0];
            out.push({
              student_id: batch[j].student_id,
              name: batch[j].name,
              roll_no: batch[j].roll_no,
              section_label: roster!.section.label,
              earned: d.total.earned,
              available: d.total.available,
              rate: d.total.rate,
              marksLost: d.total.available - d.total.earned,
              mainBlocker: focus ? focus.label : "—",
              attention: attentionFromRate(d.total.rate),
            });
          });
        }
      }
      if (!cancelled) {
        setRows(out);
        setDiagnoses(diag);
        setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [assessmentId, overview.sections]);

  const filtered = useMemo(() => {
    return rows
      .filter((r) => !search || r.name.toLowerCase().includes(search.toLowerCase()) || r.roll_no.includes(search))
      .filter((r) => sectionFilter === "All" || r.section_label === sectionFilter)
      .filter((r) => attentionFilter === "All" || r.attention === attentionFilter)
      .sort((a, b) => b.marksLost - a.marksLost);
  }, [rows, search, sectionFilter, attentionFilter]);

  const sectionLabels = useMemo(
    () => Array.from(new Set(rows.map((r) => r.section_label))).sort(),
    [rows],
  );

  const selectedDiagnosis = selected ? diagnoses[selected] : null;
  const selectedRow = selected ? rows.find((r) => r.student_id === selected) : null;

  if (selectedDiagnosis && selectedRow) {
    const focus = selectedDiagnosis.focus[0];
    // TODO(backend): Dependency Index #4 -- "recoverable marks" (distance-to-next-band)
    // is not computed by the backend; this is an illustrative estimate: half of marks
    // lost in application/higher-order findings, rounded, capped at marks lost.
    const recoverableMock = Math.min(
      selectedRow.marksLost,
      Math.round(selectedRow.marksLost * 0.6),
    );
    return (
      <div className="bx-student-detail">
        <button type="button" className="bx-back" onClick={() => setSelected(null)}>← Back to Student Intelligence</button>
        <div className="bx-student-heading">
          <Avatar name={selectedRow.name} seed={selectedRow.student_id} size={44} />
          <h2>{selectedRow.name} — {selectedRow.section_label}</h2>
        </div>
        <div className="bx-student-summary">
          <span>{selectedDiagnosis.assessment_title} Attainment: {selectedRow.earned}/{selectedRow.available}</span>
          <span>Marks Lost: {selectedRow.marksLost}</span>
          <span className="bx-mock">Recoverable (mocked, Dependency #4): {recoverableMock} marks</span>
        </div>
        {focus?.board && (
          <p className="bx-small bx-muted">
            Highest-priority gap: <strong>{focus.label}</strong> — Board Urgency{" "}
            {focus.board.urgency_tier ?? "unscored"}, {focus.confidence.toLowerCase()} confidence.
          </p>
        )}
        <div className="bx-panel bx-summary-panel">
          <p className="bx-panel-title">BoardX Summary</p>
          <p>
            {selectedRow.name} is at {selectedRow.rate == null ? "an unscored" : `${Math.round(selectedRow.rate * 100)}%`} attainment
            on {selectedDiagnosis.assessment_title}
            {focus ? `, with the highest-priority gap in ${focus.label}` : ""}
            {focus?.board?.urgency_tier ? ` (Board Urgency: ${focus.board.urgency_tier})` : ""}.
          </p>
        </div>
        <Diagnosis
          report={selectedDiagnosis}
          student={{ name: selectedRow.name, roll_no: selectedRow.roll_no }}
        />
        <style jsx>{studentDetailCss}</style>
      </div>
    );
  }

  return (
    <div>
      <div className="bx-filters">
        <label>Search student
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name or roll no." />
        </label>
        <label>Section
          <select value={sectionFilter} onChange={(e) => setSectionFilter(e.target.value)}>
            <option>All</option>
            {sectionLabels.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <label>Attention
          <select value={attentionFilter} onChange={(e) => setAttentionFilter(e.target.value)}>
            <option>All</option>
            <option value="IMMEDIATE ATTENTION">Immediate Attention</option>
            <option value="WATCH">Watch</option>
            <option value="ON TRACK">On Track</option>
            <option value="INSUFFICIENT EVIDENCE">Insufficient Evidence</option>
          </select>
        </label>
      </div>

      {initialBandFilter && (
        <p className="bx-small bx-muted">Pre-filtered from Standard Performance Snapshot: {initialBandFilter}</p>
      )}
      {loading && <p className="bx-small bx-muted">Loading each student&rsquo;s diagnosis…</p>}
      {!loading && filtered.length === 0 && (
        <p className="bx-small bx-muted">No students with marks entered for this assessment yet.</p>
      )}

      <div className="bx-table">
        <div className="bx-trow bx-thead">
          <span>Rank</span><span>Student</span><span>Section</span><span>Attainment</span>
          <span>Marks Lost</span><span>Main Blocker</span><span>Attention</span>
        </div>
        {filtered.map((r, i) => (
          <button key={r.student_id} type="button" className="bx-trow bx-trow-click" onClick={() => setSelected(r.student_id)}>
            <span className="bx-rank">{i + 1}</span>
            <span className="bx-student">
              <Avatar name={r.name} seed={r.student_id} size={30} />
              <span className="bx-student-info">
                <span className="bx-student-name">{r.name}</span>
                <span className="bx-student-roll">{r.roll_no}</span>
              </span>
            </span>
            <span>{r.section_label}</span>
            <span>{r.earned}/{r.available}</span>
            <span>{r.marksLost}</span>
            <span>{r.mainBlocker}</span>
            <span><AttentionPill state={r.attention} /></span>
          </button>
        ))}
      </div>

      <style jsx>{tableCss}</style>
    </div>
  );
}

const tableCss = `
  .bx-filters { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; position: sticky; top: 48px; background: var(--paper); padding: 10px 0; z-index: 4; }
  .bx-filters label { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; color: var(--ink-3); font-weight: 600; }
  .bx-filters input, .bx-filters select { padding: 7px 10px; font-size: 14px; border-radius: var(--radius-sm, 10px); border: 1px solid var(--rule-2); background: var(--surface); color: var(--ink); }
  .bx-table { display: flex; flex-direction: column; gap: 6px; overflow-x: auto; }
  .bx-trow { display: grid; grid-template-columns: 50px 1.6fr 1fr 1fr 1fr 1.4fr 1.4fr; gap: 10px; padding: 10px 12px; align-items: center; background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius-sm, 10px); font-size: 13.5px; transition: border-color var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease); }
  .bx-thead { background: none; border: none; font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.05em; padding: 0 12px; font-weight: 700; }
  .bx-trow-click { text-align: left; font: inherit; cursor: pointer; width: 100%; }
  .bx-trow-click:hover { border-color: var(--brand-ink-2); box-shadow: var(--shadow-xs); }
  .bx-rank { color: var(--ink-3); font-variant-numeric: tabular-nums; font-weight: 700; }
  .bx-student { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .bx-student-info { display: flex; flex-direction: column; min-width: 0; }
  .bx-student-name { font-weight: 700; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bx-student-roll { font-size: 11.5px; color: var(--ink-3); }
  .bx-small { font-size: 13px; }
  .bx-muted { color: var(--ink-3); }
`;

const studentDetailCss = `
  .bx-back { background: none; border: none; color: var(--brand-ink); font-weight: 700; font-size: 13px; cursor: pointer; padding: 0; margin-bottom: 14px; }
  .bx-student-heading { display: flex; align-items: center; gap: 14px; margin-bottom: 10px; }
  .bx-student-detail h2 { font-family: var(--font-display), sans-serif; margin: 0; color: var(--brand-ink); }
  .bx-student-summary { display: flex; gap: 20px; flex-wrap: wrap; font-size: 14px; margin-bottom: 10px; color: var(--ink-2); }
  .bx-mock { color: var(--ink-3); font-style: italic; }
  .bx-small { font-size: 13px; }
  .bx-muted { color: var(--ink-3); }
  .bx-panel { border: 1px solid var(--rule); border-radius: var(--radius, 12px); padding: 14px 16px; margin: 12px 0 18px; box-shadow: var(--shadow-xs); }
  .bx-summary-panel { background: var(--surface-2); }
  .bx-panel-title { font-weight: 700; font-size: 12.5px; text-transform: uppercase; letter-spacing: 0.03em; color: var(--ink-3); margin: 0 0 6px; }
`;
