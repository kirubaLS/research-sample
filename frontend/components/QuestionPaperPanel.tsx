"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Camera, CheckCircle2, ChevronDown, Loader2, Pencil, Plus, Trash2, Upload, X } from "lucide-react";
import { api } from "@/lib/api";
import { usePaperScan, toFiles } from "@/lib/usePaperScan";
import { Scanner } from "@/components/Scanner";
import { useAuth } from "@/lib/auth";
import type { StagedQuestion } from "@/lib/api";

/** One subject's real question-paper pipeline: create/open a paper, scan it (photo or
 * file), confirm the reading, map it against the book and classify every question -- the
 * exact state machine in lib/usePaperScan.ts, the same one app/teacher/papers/page.tsx's
 * Papers tab drives. `section` narrows nothing server-side (a question paper is one per
 * subject, not per class), it is kept only so a subject-scoped screen can label itself. */
export function QuestionPaperPanel({ subject, section }: { subject: string; section: string }) {
  const { user } = useAuth();
  const scan = usePaperScan({
    listPapers: (key) => api.teacherPapers(key),
    listSubjects: (key) => api.subjects(key).then((r) => r.subjects),
    prefillSubject: subject,
  });
  const [newTitle, setNewTitle] = useState("Cycle Test I");

  // "Upload/scan, then wait a minute for the final result" -- a teacher does not need to
  // see or act on the confirm step, it is real (it records who read the paper) but there
  // is no decision for a person to make there, so it fires the moment a name is known
  // instead of waiting on a button press. Confirm -> map -> classify then auto-chains
  // inside the hook itself, stopping only where a question genuinely could not be placed.
  useEffect(() => {
    if (scan.documentId && !scan.confirmed && scan.busy == null) {
      scan.setConfirmedBy(user?.name || "Teacher");
      void scan.onConfirm();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scan.documentId, scan.confirmed, scan.busy]);
  // The row currently open for editing -- only ever a pre-confirmation, unmapped row (see
  // the Edit button's own guard below); editScanned() 409s past either point, so the
  // affordance never appears once it would fail.
  const [editing, setEditing] = useState<StagedQuestion | null>(null);
  const [editForm, setEditForm] = useState({ question_no: "", section: "", max_marks: "", stem_text: "" });
  const [savingEdit, setSavingEdit] = useState(false);

  function openEdit(q: StagedQuestion) {
    setEditing(q);
    setEditForm({
      question_no: q.question_no ?? "",
      section: q.section ?? "",
      max_marks: q.max_marks != null ? String(q.max_marks) : "",
      stem_text: q.stem_text ?? "",
    });
  }

  async function saveEdit() {
    if (!editing) return;
    setSavingEdit(true);
    const patch: Record<string, unknown> = {};
    if (editForm.question_no !== (editing.question_no ?? "")) patch.question_no = editForm.question_no;
    if (editForm.section !== (editing.section ?? "")) patch.section = editForm.section || null;
    if (editForm.stem_text !== (editing.stem_text ?? "")) patch.stem_text = editForm.stem_text || null;
    const maxMarksNum = editForm.max_marks.trim() === "" ? null : Number(editForm.max_marks);
    if (maxMarksNum !== editing.max_marks) patch.max_marks = maxMarksNum;
    try {
      if (Object.keys(patch).length > 0) await scan.onEdit(editing.address, patch);
      setEditing(null);
    } finally {
      setSavingEdit(false);
    }
  }

  async function removeEdit() {
    if (!editing) return;
    if (!window.confirm(`Remove ${editing.section ?? ""}${editing.question_no}${editing.sub_part ?? ""}? The extractor sometimes invents a row from a heading -- this removes it entirely.`)) return;
    setSavingEdit(true);
    try {
      await scan.onEdit(editing.address, { remove: true });
      setEditing(null);
    } finally {
      setSavingEdit(false);
    }
  }

  const papersForSubject = scan.papers.filter((p) => p.subject_code === subject);

  function startNew() {
    scan.setSubject(subject);
    scan.setTitle(newTitle || "Cycle Test I");
    scan.fileInput.current?.click();
  }

  return (
    <div>
      {scan.error && (
        <div className="evidence evidence--gold" style={{ marginBottom: 12 }}>
          <AlertTriangle size={16} />
          <div>{scan.error}</div>
        </div>
      )}

      {!scan.assessmentId ? (
        <div className="card">
          <div className="card__body" style={{ display: "grid", gap: 12 }}>
            <p className="small muted" style={{ margin: 0 }}>
              {section} · {subject}. Open a paper already created for {subject} below, or start a new one.
            </p>
            {papersForSubject.length > 0 && (
              <div style={{ display: "grid", gap: 8 }}>
                {papersForSubject.map((p) => (
                  <button key={p.id} className="subject-row" onClick={() => scan.openPaper(p)}>
                    <div>
                      <div className="strong">{p.title}</div>
                      <div className="small muted">
                        {p.stage} · {p.questions} question{p.questions === 1 ? "" : "s"} · {p.mapped_questions} mapped
                      </div>
                    </div>
                    <ChevronDown size={14} className="muted" style={{ transform: "rotate(-90deg)" }} />
                  </button>
                ))}
              </div>
            )}
            <div className="field">
              <label htmlFor="new-paper-title">New paper title</label>
              <input id="new-paper-title" className="input" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn--primary" onClick={startNew} disabled={scan.busy != null}>
                <Upload size={14} /> Upload paper file
              </button>
              <button
                className="btn"
                onClick={() => {
                  scan.setSubject(subject);
                  scan.setTitle(newTitle || "Cycle Test I");
                  scan.setShowCamera(true);
                }}
              >
                <Camera size={14} /> Photograph paper
              </button>
            </div>
            <input
              ref={scan.fileInput}
              type="file"
              accept=".pdf,image/*"
              multiple
              hidden
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                if (files.length) void scan.onFiles(files);
              }}
            />
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="card__head">
            <div>
              <div className="strong" style={{ fontSize: 15 }}>
                {scan.title}
              </div>
              <div className="small muted" style={{ marginTop: 2 }}>
                {subject} · {scan.stage}
                {scan.review?.marks && ` · ${scan.review.marks.read} marks read`}
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn--sm" onClick={() => scan.onRename()} disabled={scan.renaming}>
                Rename
              </button>
              <button className="btn btn--sm" onClick={() => scan.onDelete()}>
                <Trash2 size={13} /> Delete paper
              </button>
              <button className="btn btn--sm" onClick={() => scan.closePaper()}>
                Back to list
              </button>
            </div>
          </div>

          <div className="card__body" style={{ display: "grid", gap: 14 }}>
            {scan.deleted && <div className="evidence">Paper deleted.</div>}

            {!scan.scan && !scan.documentId && (
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn--primary" onClick={() => scan.fileInput.current?.click()} disabled={scan.busy != null}>
                  <Upload size={14} /> Upload scanned pages
                </button>
                <button className="btn" onClick={() => scan.setShowCamera(true)}>
                  <Camera size={14} /> Photograph pages
                </button>
                <input
                  ref={scan.fileInput}
                  type="file"
                  accept=".pdf,image/*"
                  multiple
                  hidden
                  onChange={(e) => {
                    const files = Array.from(e.target.files ?? []);
                    if (files.length) void scan.onFiles(files);
                  }}
                />
              </div>
            )}

            {scan.busy && (
              <div className="small muted" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Loader2 size={14} className="spin" /> {scan.busy}
              </div>
            )}

            {scan.pendingResume && (
              <div className="evidence evidence--gold">
                <AlertTriangle size={16} />
                <div>
                  {scan.pendingPageCount} captured page(s) could not reach the server yet. Retrying automatically.
                  <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                    <button className="btn btn--sm" onClick={() => scan.retryPendingNow()} disabled={scan.retrying}>
                      Retry now
                    </button>
                    <button className="btn btn--sm" onClick={() => scan.discardPending()}>
                      Discard
                    </button>
                  </div>
                </div>
              </div>
            )}

            {scan.scan && (
              <div className="grid grid--3">
                <div className="stat">
                  <div className="stat__label">Questions read</div>
                  <div className="stat__value">{scan.scan.questions}</div>
                </div>
                <div className="stat">
                  <div className="stat__label">Marks read</div>
                  <div className="stat__value">{scan.scan.total_marks}</div>
                </div>
                <div className="stat">
                  <div className="stat__label">Pages</div>
                  <div className="stat__value">{scan.scan.pages}</div>
                </div>
              </div>
            )}

            {/* Confirming is real (it records who read the paper) but not a decision a
                teacher needs to make -- the effect above fires it automatically the
                moment a scan lands. "Remove scan" stays available the whole time a scan
                exists and is not yet confirmed, in case the wrong file was uploaded. */}
            {scan.documentId && !scan.confirmed && (
              <button className="btn btn--sm" onClick={() => scan.onRemoveScan()} disabled={scan.removingScan}>
                Remove scan
              </button>
            )}

            {scan.mapped && (
              <div className="grid grid--3">
                <div className="stat">
                  <div className="stat__label">Mapped</div>
                  <div className="stat__value">{scan.mapped.mapped}</div>
                </div>
                <div className="stat">
                  <div className="stat__label">Blocked</div>
                  <div className="stat__value">{scan.mapped.blocked}</div>
                </div>
                <div className="stat">
                  <div className="stat__label">Needs review</div>
                  <div className="stat__value">{scan.mapped.needs_review}</div>
                </div>
              </div>
            )}

            {/* Classifying auto-chains inside the hook the moment mapping comes back with
                nothing blocked -- no button for the ordinary case. Re-run mapping stays as
                a real recovery action for the one case that does need a person: a blocked
                question, which usually means the underlying concept families need fixing
                before mapping can find it a home. */}
            {scan.mapped && scan.mapped.blocked > 0 && !scan.placed && (
              <button className="btn btn--sm" onClick={() => scan.onMap()} disabled={scan.busy != null}>
                Re-run mapping
              </button>
            )}

            {(scan.placed || scan.alreadyClassified) && (
              <div className="tag tag--green" style={{ width: "fit-content" }}>
                <CheckCircle2 size={12} /> Classified
              </div>
            )}

            {scan.review && scan.review.questions.length > 0 && (
              <div className="drawer__section" style={{ padding: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <h4 style={{ margin: 0 }}>Questions ({scan.blockedCount} not yet placed)</h4>
                  <div className="tabs" role="tablist">
                    {(["all", "mapped", "blocked"] as const).map((f) => (
                      <button
                        key={f}
                        role="tab"
                        aria-selected={scan.filter === f}
                        className={`tab ${scan.filter === f ? "tab--active" : ""}`}
                        onClick={() => scan.setFilter(f)}
                      >
                        {f}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="table-wrap table-wrap--scroll" style={{ maxHeight: 360 }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Q</th>
                        <th>Stem</th>
                        <th className="num">Marks</th>
                        <th>Chapter</th>
                        <th>Needs review</th>
                        {!scan.confirmed && <th></th>}
                      </tr>
                    </thead>
                    <tbody>
                      {scan.rows.map((q) => {
                        // Backend rule (marks.py edit_scanned_question): editing 409s once
                        // the scan is confirmed, and again once a row has already been
                        // mapped (it has moved past staging into a real Question). So the
                        // Edit action only ever appears for a still-staged, unconfirmed row.
                        const canEdit = !scan.confirmed && !q.mapped_to;
                        return (
                          <tr key={q.address}>
                            <td className="strong">
                              {q.section ?? ""}
                              {q.question_no}
                              {q.sub_part ?? ""}
                            </td>
                            <td className="small" style={{ maxWidth: 320 }}>
                              {q.stem_text ?? "—"}
                            </td>
                            <td className="num">{q.max_marks ?? "—"}</td>
                            <td>{q.mapped_to?.chapter ?? <span className="tag tag--risk">{q.blocked_reason ?? "Not placed"}</span>}</td>
                            <td>
                              {q.mapped_to?.needs_review ? (
                                <div style={{ display: "grid", gap: 2 }}>
                                  <span className="tag tag--gold" style={{ width: "fit-content" }}>{q.mapped_to.review_reason ?? "Review"}</span>
                                  <span className="small muted">A family/mapping problem -- fix the concept-family data, not this row.</span>
                                </div>
                              ) : "—"}
                            </td>
                            {!scan.confirmed && (
                              <td style={{ textAlign: "right" }}>
                                {canEdit && (
                                  <button className="btn btn--sm" onClick={() => openEdit(q)}>
                                    <Pencil size={12} /> Edit
                                  </button>
                                )}
                              </td>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Camera capture -- the real multi-page flow (lib/pageStore.ts + lib/quality.ts):
          live camera, a quality gate that locks the shutter until a page is actually
          readable, per-page retake/undo/redo, then one Complete hands every captured page
          to scan.onFiles at once -- not a single-photo picker that could only ever submit
          one page per upload. */}
      <AnimatePresence>
        {scan.showCamera && (
          <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => scan.setShowCamera(false)}>
            <motion.div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
              <div className="modal__head">
                <h3>Photograph the paper</h3>
                <button className="iconbtn" onClick={() => scan.setShowCamera(false)} aria-label="Close">
                  <X size={16} />
                </button>
              </div>
              <div className="modal__body">
                <Scanner
                  sessionId={scan.scanSessionId}
                  mode="script"
                  onComplete={async (pages) => {
                    scan.setShowCamera(false);
                    await scan.onFiles(toFiles(pages));
                  }}
                />
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {editing && (
          <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setEditing(null)}>
            <motion.div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
              <div className="modal__head">
                <h3>Edit question {editing.section ?? ""}{editing.question_no}{editing.sub_part ?? ""}</h3>
                <button className="iconbtn" onClick={() => setEditing(null)} aria-label="Close">
                  <X size={16} />
                </button>
              </div>
              <div className="modal__body" style={{ display: "grid", gap: 10 }}>
                <div className="field">
                  <label htmlFor="edit-qno">Question no.</label>
                  <input id="edit-qno" className="input" value={editForm.question_no} onChange={(e) => setEditForm((f) => ({ ...f, question_no: e.target.value }))} />
                </div>
                <div className="field">
                  <label htmlFor="edit-section">Section</label>
                  <input id="edit-section" className="input" value={editForm.section} onChange={(e) => setEditForm((f) => ({ ...f, section: e.target.value }))} />
                </div>
                <div className="field">
                  <label htmlFor="edit-max">Max marks</label>
                  <input id="edit-max" className="input" type="number" value={editForm.max_marks} onChange={(e) => setEditForm((f) => ({ ...f, max_marks: e.target.value }))} />
                </div>
                <div className="field">
                  <label htmlFor="edit-stem">Stem text</label>
                  <textarea id="edit-stem" className="input" rows={3} value={editForm.stem_text} onChange={(e) => setEditForm((f) => ({ ...f, stem_text: e.target.value }))} />
                </div>
              </div>
              <div className="modal__foot" style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <button className="btn btn--sm" onClick={removeEdit} disabled={savingEdit}>
                  <Trash2 size={13} /> Remove this row
                </button>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn btn--sm" onClick={() => setEditing(null)} disabled={savingEdit}>
                    Cancel
                  </button>
                  <button className="btn btn--primary btn--sm" onClick={() => void saveEdit()} disabled={savingEdit}>
                    {savingEdit ? <Loader2 size={13} className="spin" /> : <CheckCircle2 size={13} />} Save
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <p className="small muted" style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 6 }}>
        <Plus size={13} /> Real scan, mapping and classification -- every question paper here is read, mapped against the book and classified against
        the real backend.
      </p>
    </div>
  );
}
