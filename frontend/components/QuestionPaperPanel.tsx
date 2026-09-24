"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Camera, CheckCircle2, ChevronDown, Loader2, Plus, Sparkles, Trash2, Upload, X } from "lucide-react";
import { api } from "@/lib/api";
import { usePaperScan, toFiles } from "@/lib/usePaperScan";
import { Scanner } from "@/components/Scanner";

/** One subject's real question-paper pipeline: create/open a paper, scan it (photo or
 * file), confirm the reading, map it against the book and classify every question -- the
 * exact state machine in lib/usePaperScan.ts, the same one app/teacher/papers/page.tsx's
 * Papers tab drives. `section` narrows nothing server-side (a question paper is one per
 * subject, not per class), it is kept only so a subject-scoped screen can label itself. */
export function QuestionPaperPanel({ subject, section }: { subject: string; section: string }) {
  const scan = usePaperScan({
    listPapers: (key) => api.teacherPapers(key),
    listSubjects: (key) => api.subjects(key).then((r) => r.subjects),
    prefillSubject: subject,
  });
  const [newTitle, setNewTitle] = useState("Cycle Test I");

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
              <button className="btn btn--sm" onClick={() => scan.loadPapers().then(() => scan.setError(null))}>
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

            {scan.documentId && !scan.confirmed && (
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  className="input"
                  style={{ maxWidth: 220 }}
                  placeholder="Your name"
                  value={scan.confirmedBy}
                  onChange={(e) => scan.setConfirmedBy(e.target.value)}
                />
                <button className="btn btn--primary btn--sm" onClick={() => scan.onConfirm()} disabled={scan.busy != null}>
                  <CheckCircle2 size={13} /> Confirm reading &amp; map
                </button>
                <button className="btn btn--sm" onClick={() => scan.onRemoveScan()} disabled={scan.removingScan}>
                  Remove scan
                </button>
              </div>
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

            {scan.mapped && scan.mapped.blocked > 0 && !scan.placed && (
              <button className="btn btn--sm" onClick={() => scan.onMap()} disabled={scan.busy != null}>
                Re-run mapping
              </button>
            )}
            {scan.mapped && scan.mapped.blocked === 0 && !scan.placed && !scan.alreadyClassified && (
              <button className="btn btn--primary btn--sm" onClick={() => scan.onClassify()} disabled={scan.busy != null}>
                <Sparkles size={13} /> Read &amp; classify every question
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
                      </tr>
                    </thead>
                    <tbody>
                      {scan.rows.map((q) => (
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
                          <td>{q.mapped_to?.needs_review ? <span className="tag tag--gold">{q.mapped_to.review_reason ?? "Review"}</span> : "—"}</td>
                        </tr>
                      ))}
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

      <p className="small muted" style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 6 }}>
        <Plus size={13} /> Real scan, mapping and classification -- every question paper here is read, mapped against the book and classified against
        the real backend.
      </p>
    </div>
  );
}
