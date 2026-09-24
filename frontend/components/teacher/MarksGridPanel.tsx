"use client";

import { useMemo, useState } from "react";
import { CameraCapture } from "@/components/CameraCapture";
import { Scanner } from "@/components/Scanner";
import { pagesToFiles } from "@/lib/pageStore";
import { GridSheetRowView, RosterRow } from "@/lib/api";
import { useGridSheet, UseGridSheetOptions } from "@/lib/useGridSheet";

/**
 * The real class mark-entry-sheet pipeline (one photograph, many students, read in a
 * single call) presented as a pinned-column grid: Roll/Student stay fixed on the left
 * while question columns scroll, matching the visual shape of the reference design's
 * MarksEntryGrid. Unlike that reference, every value here is real -- read by the real
 * OCR/OMR pipeline behind lib/api.ts's gridsheet endpoints, confirmed against the real
 * backend, nothing simulated.
 *
 * A cell the scan could not read, or that carries some other problem (an amount over
 * what the question is worth, a stray character), is highlighted and stays that way
 * until it is edited or resolved -- the same "flagged until fixed" behaviour the
 * reference's fake OCR read demonstrated, driven here by the real `problem` field the
 * backend returns per mark.
 *
 * A row whose roll or name does not match the roster cleanly (`name_mismatch` /
 * `unmatched`) cannot be shown as a plain grid row -- it has no confirmed student to
 * key a column on yet -- so those stay as the existing resolve-first cards above the
 * grid; once resolved they drop straight into it.
 *
 * KNOWN GAP: the gridsheet API's per-cell marks (GridRowMark) do not carry a real
 * max_marks or chapter for their question address, unlike the single-paper answers
 * pipeline's AnswerRow. Rather than fabricate a client-side cap or a fake chapter
 * colour, this grid leaves columns uncoloured and enforces no client-side max here --
 * the backend's own real max_marks check (returned as `problem` on the mark, e.g. an
 * over-max edit) is still the source of truth and still blocks a bad edit.
 */

const STATUS_LABEL: Record<GridSheetRowView["status"], string> = {
  clean: "Ready",
  name_mismatch: "Name doesn't match the roster",
  unmatched: "No student with this roll",
};

export function MarksGridPanel(options: UseGridSheetOptions) {
  const g = useGridSheet(options);
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const showPickers = !options.fixedSectionId;

  const resolvedRows = useMemo(() => g.review?.rows.filter((r) => r.status === "clean") ?? [], [g.review]);
  const unresolvedRows = useMemo(() => g.review?.rows.filter((r) => r.status !== "clean") ?? [], [g.review]);

  // Every address that appears on any resolved row, in first-seen order -- the real
  // question columns for this paper, pivoted out of the per-row marks the backend sent.
  const addresses = useMemo(() => {
    const seen: string[] = [];
    for (const row of resolvedRows) for (const m of row.marks) if (!seen.includes(m.address)) seen.push(m.address);
    return seen;
  }, [resolvedRows]);

  const flaggedCount = useMemo(
    () => resolvedRows.reduce((sum, row) => sum + row.marks.filter((m) => m.problem).length, 0),
    [resolvedRows],
  );

  const shownRows = onlyFlagged ? resolvedRows.filter((row) => row.marks.some((m) => m.problem)) : resolvedRows;

  return (
    <>
      <div className="card" style={{ marginTop: 18, marginBottom: 16 }}>
        <div className="card__body">
          <div className="tabs" style={{ marginBottom: 14, border: "none", boxShadow: "none" }}>
            <button type="button" className={`tab${g.photoMode === "class" ? " tab--active" : ""}`} onClick={() => g.setPhotoMode("class")}>
              Whole class
            </button>
            <button type="button" className={`tab${g.photoMode === "single" ? " tab--active" : ""}`} onClick={() => g.setPhotoMode("single")}>
              One student&rsquo;s script
            </button>
          </div>

          {showPickers && (
            <div className="grid grid--2">
              <div className="field">
                <label>Paper</label>
                <select className="select" value={g.paperId} onChange={(e) => g.pickPaper(e.target.value)}>
                  <option value="">Choose a paper…</option>
                  {g.ready.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title} · {p.subject_label} · {p.questions} questions
                      {p.stage === "mapped" ? "" : " (not linked to the book yet)"}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Class</label>
                <select className="select" value={g.sectionId} onChange={(e) => g.pickSection(e.target.value)} disabled={!g.paperId}>
                  <option value="">Choose a class…</option>
                  {g.sections.map((s) => (
                    <option key={s.section_id} value={s.section_id}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {!showPickers && (
            <div className="grid grid--2">
              <div className="field">
                <label>Paper</label>
                <select className="select" value={g.paperId} onChange={(e) => g.pickPaper(e.target.value)}>
                  <option value="">Choose a paper…</option>
                  {g.ready.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title} · {p.questions} questions{p.stage === "mapped" ? "" : " (not linked to the book yet)"}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
            <button type="button" className="btn btn--ghost" disabled={!g.paperId || !g.sectionId || !!g.busy} onClick={() => void g.downloadAnswerCard()}>
              Generate blank answer card
            </button>
            <span className="small muted">
              One row per student, one column per question -- print it, hand it out, then scan the filled-in sheet back in below.
            </span>
          </div>

          <div className="grid grid--2" style={{ marginTop: 14 }}>
            <div className="field">
              <label>{g.photoMode === "class" ? "Upload answer card" : "Photo(s) of the script"}</label>
              <input
                type="file"
                multiple
                accept="image/*"
                disabled={!g.paperId || !g.sectionId || !!g.busy}
                onChange={(e) => void g.uploadPhoto(Array.from(e.target.files ?? []))}
              />
              {g.photoMode === "single" && (
                <span className="small muted">Select every page of this student&rsquo;s script at once -- they&rsquo;re stored and read together as one script.</span>
              )}
            </div>
            <div className="field">
              <label>Spreadsheet or PDF</label>
              <input
                type="file"
                accept=".csv,.tsv,.txt,.xlsx,.xlsm,.pdf"
                disabled={!g.paperId || !g.sectionId || !!g.busy}
                onChange={(e) => void g.uploadSpreadsheet(e.target.files)}
              />
              <span className="small muted">One row per student, one column per question -- a CSV, an Excel file, or a printed PDF.</span>
            </div>
          </div>

          <div style={{ display: "flex", marginTop: 10 }}>
            <button type="button" className="btn btn--ghost" disabled={!g.paperId || !g.sectionId || !!g.busy} onClick={() => g.setShowCamera((v) => !v)}>
              {g.showCamera ? "Close camera" : "Use camera instead"}
            </button>
          </div>
          {g.showCamera && g.photoMode === "class" && (
            <CameraCapture onCapture={(file) => void g.uploadPhoto([file])} onCancel={() => g.setShowCamera(false)} />
          )}
          {g.showCamera && g.photoMode === "single" && (
            <div style={{ marginTop: 12 }}>
              <p className="muted">Capture each page of the script in order. Retake replaces a single page and keeps its position.</p>
              <Scanner sessionId={g.sessionId} mode="script" onComplete={(pages) => g.uploadPhoto(pagesToFiles(pages))} />
            </div>
          )}

          {g.papers.length > 0 && g.ready.length === 0 && (
            <div className="evidence evidence--gold" style={{ marginTop: 14 }}>
              No paper has been read yet. Scan and confirm one on the Question paper screen first. Marks have nothing to attach to until then.
            </div>
          )}
          {g.uploadSummary && <p style={{ color: "var(--brand-green)", marginTop: 10 }}>{g.uploadSummary}</p>}
        </div>
      </div>

      {g.error && <p style={{ color: "var(--risk)" }}>{g.error}</p>}
      {g.busy && <p className="muted">{g.busy}…</p>}

      {g.review && (
        <>
          <div className="card" style={{ position: "sticky", top: 0, zIndex: 5, marginBottom: 16 }}>
            <div className="card__body">
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", fontSize: 16 }}>
                <div>
                  <strong>{g.review.assessment.title}</strong>
                </div>
                <div>
                  <strong>{g.review.ready_to_confirm}</strong>
                  <span className="muted"> of {g.review.rows.length} ready to confirm</span>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                <div className="field" style={{ flex: "1 1 180px" }}>
                  <label className="sr">Your name</label>
                  <input className="input" value={g.by} onChange={(e) => g.setBy(e.target.value)} placeholder="Your name" autoComplete="name" />
                </div>
                <button type="button" className="btn btn--primary" onClick={g.confirmAll} disabled={!!g.busy || g.review.ready_to_confirm === 0}>
                  Confirm all ready rows
                </button>
              </div>
              {g.confirmResult && <p style={{ color: "var(--brand-green)", marginTop: 8 }}>{g.confirmResult}</p>}
            </div>
          </div>

          {unresolvedRows.length > 0 && (
            <>
              <p className="small muted" style={{ margin: "0 0 8px" }}>
                {unresolvedRows.length} row{unresolvedRows.length === 1 ? "" : "s"} need settling before they can join the grid below.
              </p>
              <ol style={{ listStyle: "none", margin: "0 0 16px", padding: 0, display: "grid", gap: 10 }}>
                {unresolvedRows.map((row) => (
                  <UnresolvedRow
                    key={row.row_id}
                    row={row}
                    students={g.students}
                    busy={!!g.busy}
                    onPick={(studentId) => void g.resolveWithStudent(row, studentId)}
                    onCreate={(name, rollNo) => void g.resolveWithNewStudent(row, name, rollNo)}
                  />
                ))}
              </ol>
            </>
          )}

          {resolvedRows.length > 0 && (
            <div className="card">
              <div className="card__head marks-head">
                <div className="small muted">
                  {addresses.length} question{addresses.length === 1 ? "" : "s"} read, {resolvedRows.length} student{resolvedRows.length === 1 ? "" : "s"} ready.
                </div>
                {flaggedCount > 0 && (
                  <button type="button" className="btn btn--sm" onClick={() => setOnlyFlagged((v) => !v)}>
                    {onlyFlagged ? "Show all students" : `Show only flagged (${flaggedCount})`}
                  </button>
                )}
              </div>
              <div className="table-wrap table-wrap--scroll marks-grid">
                <table className="table">
                  <colgroup>
                    <col style={{ width: 52 }} />
                    <col style={{ width: 150 }} />
                    {addresses.map((a) => (
                      <col key={a} style={{ width: 64 }} />
                    ))}
                  </colgroup>
                  <thead>
                    <tr>
                      <th>Roll</th>
                      <th>Student</th>
                      {addresses.map((a) => (
                        <th key={a} className="num">
                          {a}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {shownRows.map((row) => (
                      <GridDataRow key={row.row_id} row={row} addresses={addresses} busy={!!g.busy} onEditMark={(address, marks, state) => void g.editMark(row, address, marks, state)} />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}

function GridDataRow({
  row,
  addresses,
  busy,
  onEditMark,
}: {
  row: GridSheetRowView;
  addresses: string[];
  busy: boolean;
  onEditMark: (address: string, marks: number | null, state: string) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const byAddress = new Map(row.marks.map((m) => [m.address, m]));

  return (
    <tr>
      <td className="mono">{row.roll_no}</td>
      <td className="strong">{row.student?.name ?? row.name_as_written}</td>
      {addresses.map((a) => {
        const m = byAddress.get(a);
        if (!m) return <td key={a} className="num muted">-</td>;
        const flagged = !!m.problem;
        if (editing === a) {
          return (
            <td key={a} className="num">
              <input
                className="input input--flag"
                style={{ width: 56, padding: "3px 6px" }}
                value={editValue}
                autoFocus
                inputMode="decimal"
                onChange={(e) => setEditValue(e.target.value)}
                onBlur={() => {
                  const trimmed = editValue.trim();
                  onEditMark(a, trimmed === "" ? null : Number(trimmed), trimmed === "" ? "not_offered" : "awarded");
                  setEditing(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                  if (e.key === "Escape") setEditing(null);
                }}
              />
            </td>
          );
        }
        return (
          <td key={a} className="num">
            <button
              type="button"
              className={`input marks-cell ${flagged ? "input--flag" : ""}`}
              style={{ width: 56, cursor: busy ? "default" : "pointer" }}
              disabled={busy}
              title={m.problem ?? "Tap to correct this mark"}
              onClick={() => {
                setEditValue(m.marks != null ? String(m.marks) : "");
                setEditing(a);
              }}
            >
              {m.marks ?? (m.raw_value || "?")}
            </button>
          </td>
        );
      })}
    </tr>
  );
}

function UnresolvedRow({
  row,
  students,
  busy,
  onPick,
  onCreate,
}: {
  row: GridSheetRowView;
  students: RosterRow[];
  busy: boolean;
  onPick: (studentId: string) => void;
  onCreate: (name: string, rollNo: string) => void;
}) {
  const [picked, setPicked] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState(row.name_as_written);
  const borderColor = row.status === "unmatched" ? "var(--risk)" : "var(--brand-gold)";
  const attnCls = row.status === "unmatched" ? "attn--high" : "attn--medium";

  return (
    <li className="card" style={{ borderLeft: `4px solid ${borderColor}`, background: row.status === "unmatched" ? "var(--risk-soft)" : undefined, listStyle: "none" }}>
      <div className="card__body">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <span className="strong">
            Roll {row.roll_no}
            {row.student ? ` · ${row.student.name}` : row.name_as_written ? ` · written as "${row.name_as_written}"` : ""}
          </span>
          <span className={`attn ${attnCls}`}>{STATUS_LABEL[row.status]}</span>
        </div>

        {row.status === "name_mismatch" && row.student && (
          <p className="small muted" style={{ marginTop: 8 }}>
            The sheet reads &ldquo;{row.name_as_written}&rdquo; but roll {row.roll_no} on the roster is {row.student.name}. If that&rsquo;s the same student, say so below; otherwise pick or create the right one.
          </p>
        )}

        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10, alignItems: "center" }}>
          {row.status === "name_mismatch" && row.student && (
            <button type="button" className="btn btn--primary btn--sm" onClick={() => onPick(row.student!.id)} disabled={busy}>
              This is {row.student.name}
            </button>
          )}
          {!creating && (
            <>
              <select className="select" value={picked} onChange={(e) => setPicked(e.target.value)} disabled={busy || !students.length}>
                <option value="">Pick a different student…</option>
                {students.map((s) => (
                  <option key={s.student_id} value={s.student_id}>
                    {s.roll_no}. {s.name}
                  </option>
                ))}
              </select>
              <button type="button" className="btn btn--primary btn--sm" onClick={() => picked && onPick(picked)} disabled={busy || !picked}>
                Use this student
              </button>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setCreating(true)} disabled={busy}>
                Create a new student
              </button>
            </>
          )}
          {creating && (
            <>
              <input className="input" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Student's name" style={{ width: "auto" }} />
              <button type="button" className="btn btn--primary btn--sm" onClick={() => newName.trim() && onCreate(newName.trim(), row.roll_no)} disabled={busy || !newName.trim()}>
                Create roll {row.roll_no}
              </button>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setCreating(false)} disabled={busy}>
                Cancel
              </button>
            </>
          )}
        </div>
      </div>
    </li>
  );
}
