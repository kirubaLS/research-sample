"use client";

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Camera, CheckCircle2, ClipboardList, FileUp, Save, Trash2, Upload, X } from "lucide-react";
import { FilePickButtons } from "@/components/FilePickButtons";
import { BusyBanner } from "@/components/BusyBanner";
import { Scanner } from "@/components/Scanner";
import { toFiles } from "@/lib/usePaperScan";
import { useGridSheet } from "@/lib/useGridSheet";
import { useAuth } from "@/lib/auth";
import type { GridRowMark, GridSheetRowView } from "@/lib/api";

/** One class's real mark-entry pipeline for one paper: upload a photographed answer-card
 * sheet (or a spreadsheet), resolve any row the OCR could not match to a student, edit any
 * mark that needs a correction, then confirm -- the exact state machine in
 * lib/useGridSheet.ts, the same one app/teacher/papers/page.tsx's Enter Marks tab drives.
 * `roster` is accepted for backward compatibility with callers that already fetched a
 * section's roster, but the grid pulls its own copy through the hook (role-scoped, so it
 * never shows a student this teacher key cannot see). */
export function MarksEntryGrid({
  subject,
  section,
  paperId,
}: {
  subject: string;
  section: string;
  /** Pin the paper: when omitted the grid offers a paper picker itself. */
  paperId?: string;
}) {
  const { user } = useAuth();
  const grid = useGridSheet({ role: "teacher", subjectCode: subject, fixedSectionId: section });

  useEffect(() => {
    if (paperId && grid.paperId !== paperId) grid.pickPaper(paperId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paperId]);

  // Real, but not a step a teacher should have to type through every time -- attributed to
  // whoever is actually signed in. Confirm itself stays a real button press: saving marks
  // is consequential, worth a deliberate tap, unlike the read-only "who read this" name a
  // paper scan asks for.
  useEffect(() => {
    if (!grid.by && user?.name) grid.setBy(user.name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.name]);

  const rows = grid.review?.rows ?? [];
  // Unmatched/name-mismatch rows still need a person to say who they are before any mark
  // means anything -- that resolve-first flow is untouched below. Only a "clean" row (a
  // real, matched student) gets a marks row in the per-question grid.
  const unresolvedRows = rows.filter((r) => r.status !== "clean");
  const cleanRows = rows.filter((r) => r.status === "clean");

  // The union of every question address that appears on any clean row, in a stable sorted
  // order -- there is no separate "paper structure" available to this hook, so the set of
  // columns is exactly the set of addresses the reading actually produced.
  const addresses = useMemo(() => {
    const set = new Set<string>();
    for (const row of cleanRows) for (const m of row.marks) set.add(m.address);
    return Array.from(set).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  }, [cleanRows]);

  const [editingCell, setEditingCell] = useState<{ rowId: string; address: string } | null>(null);
  const [cellValue, setCellValue] = useState("");

  function markFor(row: GridSheetRowView, address: string): GridRowMark | undefined {
    return row.marks.find((m) => m.address === address);
  }

  function openCell(row: GridSheetRowView, address: string, mark: GridRowMark | undefined) {
    setEditingCell({ rowId: row.row_id, address });
    setCellValue(mark?.marks != null ? String(mark.marks) : "");
  }

  async function saveCell(row: GridSheetRowView, address: string) {
    const trimmed = cellValue.trim();
    const marks = trimmed === "" ? null : Number(trimmed);
    // "awarded" is the state edit_proposal() defaults to and the only one a numeric mark
    // makes sense under; a cleared cell still needs a state, and "awarded" with marks=null
    // is what the backend itself does not accept (marks required when awarded), so an
    // empty save is not attempted -- the teacher would clear via a real "missing" state,
    // which this grid has no affordance for and does not fabricate one for.
    if (trimmed === "" ) {
      setEditingCell(null);
      return;
    }
    await grid.editMark(row, address, marks, "awarded");
    setEditingCell(null);
  }

  function statusTag(row: GridSheetRowView) {
    if (row.status === "clean") return <span className="tag tag--green">Ready</span>;
    if (row.status === "name_mismatch") return <span className="tag tag--gold">Check name</span>;
    return <span className="tag tag--risk">Unmatched</span>;
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="card__head marks-head">
        <div className="small muted">
          {grid.ready.length === 0 ? "No papers ready for answer sheets yet." : "Photograph or upload the filled answer card, or a spreadsheet, to read marks."}
        </div>
        {!paperId && (
          <select className="select" value={grid.paperId} onChange={(e) => grid.pickPaper(e.target.value)}>
            <option value="">Choose a paper…</option>
            {grid.ready.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        )}
      </div>

      {grid.error && (
        <div className="evidence evidence--gold" style={{ margin: "0 18px 12px" }}>
          <AlertTriangle size={16} />
          <div>{grid.error}</div>
        </div>
      )}

      {!paperId && !grid.paperId && (
        <div className="card__body">
          <div className="placeholder" style={{ display: "grid", gap: 8, justifyItems: "center" }}>
            <ClipboardList size={22} />
            <div className="small">Choose a paper above to read its answer sheets.</div>
          </div>
        </div>
      )}

      {grid.paperId && grid.sectionId && (
        <div className="card__body" style={{ display: "grid", gap: 12 }}>
          {!grid.documentId && !grid.busy && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <div className="tabs" role="tablist">
                <button role="tab" aria-selected={grid.photoMode === "class"} className={`tab ${grid.photoMode === "class" ? "tab--active" : ""}`} onClick={() => grid.setPhotoMode("class")}>
                  Whole class sheet
                </button>
                <button role="tab" aria-selected={grid.photoMode === "single"} className={`tab ${grid.photoMode === "single" ? "tab--active" : ""}`} onClick={() => grid.setPhotoMode("single")}>
                  Single script
                </button>
              </div>
              <button className="btn btn--sm" onClick={() => grid.setShowCamera(true)}>
                <Camera size={13} /> Photograph
              </button>
              <FilePickButtons size="sm" accept="image/*,.pdf,.xlsx,.csv" fileLabel="Upload file" onPick={(f) => grid.uploadPhoto([f])} />
              <label className="btn btn--sm" style={{ cursor: "pointer" }}>
                <Upload size={13} /> Upload spreadsheet
                <input type="file" accept=".xlsx,.csv" hidden onChange={(e) => grid.uploadSpreadsheet(e.target.files)} />
              </label>
              <button className="btn btn--sm" onClick={() => grid.downloadAnswerCard()}>
                <FileUp size={13} /> Blank answer card
              </button>
            </div>
          )}

          {grid.busy && <BusyBanner label={grid.busy} />}

          {/* Once a sheet is read, "Remove scan" is the only way to start over on a
              mis-scanned or wrong-class upload -- picking a different paper and back did
              nothing, since the same document simply reloaded. Confirmed marks are
              untouched (see removeScan's own comment); only the raw scan goes. */}
          {grid.documentId && !grid.busy && (
            <button className="btn btn--sm" onClick={() => grid.removeScan()} disabled={grid.removingScan} style={{ width: "fit-content" }}>
              <Trash2 size={13} /> Remove scan
            </button>
          )}

          {grid.uploadSummary && <div className="small muted">{grid.uploadSummary}</div>}

          {unresolvedRows.length > 0 && (
            <div className="table-wrap table-wrap--scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Roll</th>
                    <th>Name (as read)</th>
                    <th>Status</th>
                    <th className="num">Marks read</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {unresolvedRows.map((row) => (
                    <tr key={row.row_id}>
                      <td className="mono">{row.roll_no}</td>
                      <td>{row.name_as_written}</td>
                      <td>{statusTag(row)}</td>
                      <td className="num">{row.marks.filter((m) => m.marks != null).length}/{row.marks.length}</td>
                      <td style={{ textAlign: "right" }}>
                        <button
                          className="btn btn--sm"
                          onClick={() => {
                            const rollNo = window.prompt("Roll number to match to", row.roll_no);
                            if (!rollNo) return;
                            const name = window.prompt("Student name (if creating new)", row.name_as_written) ?? row.name_as_written;
                            void grid.resolveWithNewStudent(row, name, rollNo);
                          }}
                        >
                          Resolve
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {cleanRows.length > 0 && (
            <>
              <div className="marks-grid__legend">
                <span className="marks-grid__legend-item">
                  <span className="marks-grid__legend-dot" style={{ background: "var(--risk)" }} /> flagged by the reading -- needs a look
                </span>
              </div>
              <div className="table-wrap table-wrap--scroll">
                <table className="table marks-grid">
                  <thead>
                    <tr>
                      <th>Roll</th>
                      <th>Name</th>
                      {addresses.map((addr) => (
                        <th key={addr} className="num">{addr}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {cleanRows.map((row) => (
                      <tr key={row.row_id}>
                        <td className="mono">{row.roll_no}</td>
                        <td>{row.student?.name ?? row.name_as_written}</td>
                        {addresses.map((addr) => {
                          const mark = markFor(row, addr);
                          const isEditing = editingCell?.rowId === row.row_id && editingCell.address === addr;
                          const flagged = !!mark?.problem;
                          if (isEditing) {
                            return (
                              <td key={addr} className="num">
                                <input
                                  autoFocus
                                  className="input"
                                  style={{ width: 64, padding: "2px 6px" }}
                                  value={cellValue}
                                  onChange={(e) => setCellValue(e.target.value)}
                                  onBlur={() => void saveCell(row, addr)}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") void saveCell(row, addr);
                                    if (e.key === "Escape") setEditingCell(null);
                                  }}
                                />
                              </td>
                            );
                          }
                          return (
                            <td
                              key={addr}
                              className="num"
                              title={mark?.problem ?? undefined}
                              onClick={() => openCell(row, addr, mark)}
                              style={{
                                cursor: "pointer",
                                background: flagged ? "var(--risk-soft)" : undefined,
                                color: flagged ? "var(--risk)" : undefined,
                                border: flagged ? "1px solid var(--risk)" : undefined,
                              }}
                            >
                              {mark?.marks ?? "—"}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {rows.length > 0 && (
            <>
              <button className="btn btn--primary btn--sm" onClick={() => grid.confirmAll()} disabled={grid.busy != null} style={{ width: "fit-content" }}>
                <Save size={13} /> Confirm &amp; save marks
              </button>
              {grid.confirmResult && (
                <div className="flagbar flagbar--ok" role="status">
                  <CheckCircle2 size={16} /> <span>{grid.confirmResult}</span>
                </div>
              )}
            </>
          )}
        </div>
      )}

      <AnimatePresence>
        {grid.showCamera && (
          <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => grid.setShowCamera(false)}>
            <motion.div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
              <div className="modal__head">
                <h3>Photograph the answer card</h3>
                <button className="iconbtn" onClick={() => grid.setShowCamera(false)} aria-label="Close">
                  <X size={16} />
                </button>
              </div>
              <div className="modal__body">
                {/* The real multi-page capture (see components/Scanner.tsx), same as the
                    question-paper flow -- a "whole class sheet" is realistically several
                    pages of scripts, and a single-photo picker could only ever submit one. */}
                <Scanner
                  sessionId={grid.sessionId}
                  mode="script"
                  onComplete={async (pages) => {
                    grid.setShowCamera(false);
                    await grid.uploadPhoto(toFiles(pages));
                  }}
                />
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
