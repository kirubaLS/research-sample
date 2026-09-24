"use client";

import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Camera, CheckCircle2, FileUp, Loader2, Save, Upload, X } from "lucide-react";
import { FilePickButtons } from "@/components/FilePickButtons";
import { useGridSheet } from "@/lib/useGridSheet";
import type { GridSheetRowView } from "@/lib/api";

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
  const grid = useGridSheet({ role: "teacher", subjectCode: subject, fixedSectionId: section });

  useEffect(() => {
    if (paperId && grid.paperId !== paperId) grid.pickPaper(paperId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paperId]);

  const rows = grid.review?.rows ?? [];

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

      {grid.paperId && grid.sectionId && (
        <div className="card__body" style={{ display: "grid", gap: 12 }}>
          {!grid.documentId && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <div className="tabs" role="tablist">
                <button role="tab" aria-selected={grid.photoMode === "class"} className={`tab ${grid.photoMode === "class" ? "tab--active" : ""}`} onClick={() => grid.setPhotoMode("class")}>
                  Whole class sheet
                </button>
                <button role="tab" aria-selected={grid.photoMode === "single"} className={`tab ${grid.photoMode === "single" ? "tab--active" : ""}`} onClick={() => grid.setPhotoMode("single")}>
                  Single script
                </button>
              </div>
              {grid.busy ? (
                <span className="small muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Loader2 size={14} className="spin" /> {grid.busy}
                </span>
              ) : (
                <>
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
                </>
              )}
            </div>
          )}

          {grid.uploadSummary && <div className="small muted">{grid.uploadSummary}</div>}

          {rows.length > 0 && (
            <>
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
                    {rows.map((row) => (
                      <tr key={row.row_id}>
                        <td className="mono">{row.roll_no}</td>
                        <td>{row.name_as_written}</td>
                        <td>{statusTag(row)}</td>
                        <td className="num">{row.marks.filter((m) => m.marks != null).length}/{row.marks.length}</td>
                        <td style={{ textAlign: "right" }}>
                          {row.status !== "clean" && (
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
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input className="input" style={{ maxWidth: 220 }} placeholder="Your name" value={grid.by} onChange={(e) => grid.setBy(e.target.value)} />
                <button className="btn btn--primary btn--sm" onClick={() => grid.confirmAll()} disabled={grid.busy != null}>
                  <Save size={13} /> Confirm &amp; save marks
                </button>
              </div>
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
                <FilePickButtons
                  accept="image/*"
                  fileLabel="Choose photo"
                  onPick={(file) => {
                    grid.setShowCamera(false);
                    void grid.uploadPhoto([file]);
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
