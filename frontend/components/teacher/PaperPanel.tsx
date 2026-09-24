"use client";

/**
 * The accordion-card / upload-modal / mapping-drawer visual shape from the reference
 * design's QuestionPaperPanel (src/components/QuestionPaperPanel.tsx), driven by the
 * real scan/confirm/map/classify pipeline (usePaperScan) instead of that reference's
 * simulated state. Every number shown here -- coverage, blocked count, per-question
 * chapter/topic/tier -- comes straight out of api.readScan/mapPaper/placePaper; nothing
 * is invented to fill a shape the reference only mocked.
 *
 * Shared by app/teacher/paper/page.tsx, app/principal/papers/page.tsx and the
 * subject-scoped app/teacher/subjects/[subjectCode]/[sectionId]/page.tsx so there is one
 * real implementation of "what a question-paper screen looks like", not three.
 */

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  CheckCircle2,
  ChevronDown,
  FileUp,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { Scanner } from "@/components/Scanner";
import { Mascot } from "@/components/Mascot";
import { usePaperScan, toFiles, type Stage } from "@/lib/usePaperScan";
import { api, type PaperSummary, type StagedQuestion, type Subject } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { downloadBlob } from "@/lib/download";

type Status = "empty" | "start" | "scanned" | "confirmed" | "mapped" | "classified";

function StatusTag({ status }: { status: Status }) {
  if (status === "classified" || status === "mapped") return <span className="tag tag--green">Mapped</span>;
  if (status === "scanned" || status === "confirmed") return <span className="tag tag--gold">Needs mapping</span>;
  return <span className="tag">Not uploaded</span>;
}

export function PaperPanel({
  listPapers,
  listSubjects,
  prefillSubject,
  sectionLabel,
  sectionId,
}: {
  listPapers: (key: string) => Promise<{ assessments: PaperSummary[] }>;
  listSubjects: (key: string) => Promise<Subject[]>;
  /** Preselects and, once its papers load, opens this subject's most recent paper. */
  prefillSubject?: string | null;
  /** Shown on the answer-card drawer. */
  sectionLabel?: string;
  /** When given (e.g. from a subject-scoped screen that already knows the class), the
   * answer card is downloaded for real via api.answerCardPdf; without it (e.g. the
   * principal-wide papers screen, which spans every section) the drawer says plainly
   * that a section must be chosen from Enter Marks/Gridsheet instead. */
  sectionId?: string;
}) {
  const h = usePaperScan({ listPapers, listSubjects, prefillSubject });
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [uploadFor, setUploadFor] = useState<PaperSummary | "new" | null>(null);
  const [mappingFor, setMappingFor] = useState<PaperSummary | null>(null);
  const [cardFor, setCardFor] = useState<PaperSummary | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [showCamera, setShowCamera] = useState(false);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2800);
    return () => clearTimeout(t);
  }, [toast]);

  // Toast on real state transitions, not simulated ones.
  const prevStage = useRef<Stage | null>(null);
  useEffect(() => {
    if (prevStage.current && prevStage.current !== h.stage) {
      if (h.stage === "mapped") setToast(`${h.subject} mapped to the blueprint.`);
      if (h.stage === "classified") setToast("Paper classified.");
    }
    prevStage.current = h.stage;
  }, [h.stage, h.subject]);

  function statusFor(p: PaperSummary): Status {
    return p.stage === "empty" ? "start" : p.stage;
  }

  function toggleExpand(id: string) {
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function openAndExpand(p: PaperSummary) {
    await h.openPaper(p);
    setExpanded((s) => new Set(s).add(p.id));
  }

  async function startUploadFlow() {
    // "new": no paper exists yet for the chosen subject -- create it inline once files
    // are picked, exactly like the old start screen, just inside the modal now.
    if (!h.subject) {
      h.setError("Choose a subject before reading the paper.");
      return;
    }
    setUploadFor("new");
  }

  async function handleUploadFiles(files: File[]) {
    if (files.length === 0) return;
    if (uploadFor && uploadFor !== "new") {
      await h.submitScan(uploadFor.subject_code, uploadFor.title, uploadFor.id, files, null);
    } else {
      await h.onFiles(files);
    }
    setUploadFor(null);
    setShowCamera(false);
  }

  const isMappingOpen = !!mappingFor && mappingFor.id === h.assessmentId;
  const isCardOpen = !!cardFor && cardFor.id === h.assessmentId;

  return (
    <>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <button type="button" className="btn btn--primary btn--sm" onClick={startUploadFlow} disabled={!!h.busy}>
          <Upload size={13} /> Upload a paper
        </button>
      </div>

      {h.subjects.length > 1 && (
        <div className="field" style={{ maxWidth: 320, marginBottom: 14 }}>
          <label>Subject for a new paper</label>
          <select className="select" value={h.subject} onChange={(e) => h.setSubject(e.target.value)}>
            {h.subjects.map(({ subject_code: code, label: name }) => (
              <option key={code} value={code}>{name}</option>
            ))}
          </select>
        </div>
      )}

      {h.pendingResume && (
        <div className="evidence evidence--gold" style={{ marginBottom: 14, flexDirection: "column", alignItems: "flex-start" }}>
          <p style={{ margin: 0 }}>
            <strong>
              {h.pendingPageCount} page{h.pendingPageCount === 1 ? "" : "s"} of &ldquo;{h.pendingResume.title}&rdquo;
            </strong>{" "}
            {h.pendingResume.assessmentId ? "were captured but a re-scan" : "were captured but the paper"} could
            not reach the server last time -- nothing was lost, they are still on this device.
            {h.retrying ? " Trying again now…" : " Retrying automatically every 20 seconds."}
          </p>
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button type="button" className="btn btn--ghost btn--sm" disabled={h.retrying || !!h.busy} onClick={() => void h.retryPendingNow()}>
              Retry now
            </button>
            <button type="button" className="btn btn--ghost btn--sm" disabled={h.retrying} onClick={() => void h.discardPending()}>
              Discard
            </button>
          </div>
        </div>
      )}

      {h.error && (
        <p role="alert" style={{ color: "var(--risk)", marginBottom: 14 }}>
          {h.error}
        </p>
      )}

      {h.deleted && (
        <div className="evidence evidence--neutral" style={{ marginBottom: 14 }}>
          The paper was deleted.
        </div>
      )}

      {h.papers.length === 0 ? (
        <div className="evidence evidence--neutral">No papers yet. Upload one to get started.</div>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {h.papers.map((p) => {
            const isOpen = expanded.has(p.id);
            const status = statusFor(p);
            const isActive = h.assessmentId === p.id;
            return (
              <div className="card" key={p.id}>
                <button
                  onClick={() => (isOpen ? toggleExpand(p.id) : void openAndExpand(p))}
                  style={{ width: "100%", textAlign: "left", background: "none", border: "none", padding: 0, cursor: "pointer" }}
                  aria-expanded={isOpen}
                >
                  <div className="card__head">
                    <div>
                      <div className="strong" style={{ fontSize: 15 }}>{p.title}</div>
                      <div className="small muted" style={{ marginTop: 2 }}>{p.subject_label}</div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <StatusTag status={status} />
                      <ChevronDown size={16} className="muted" style={{ transform: isOpen ? "rotate(180deg)" : undefined, transition: "transform .15s" }} />
                    </div>
                  </div>
                </button>

                {isOpen && (
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Subject</th>
                          <th>Status</th>
                          <th>Coverage</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td className="strong">{p.subject_label}</td>
                          <td><StatusTag status={status} /></td>
                          <td style={{ minWidth: 140 }}>
                            {isActive && h.mapped ? (
                              <div className="bar-row" style={{ gridTemplateColumns: "1fr 40px", padding: 0 }}>
                                <div className="bar">
                                  <div className="bar__fill" style={{ width: `${h.mapped.mapped + h.mapped.blocked > 0 ? Math.round((h.mapped.mapped / (h.mapped.mapped + h.mapped.blocked)) * 100) : 0}%` }} />
                                </div>
                                <div className="bar-row__val">
                                  {h.mapped.mapped + h.mapped.blocked > 0 ? Math.round((h.mapped.mapped / (h.mapped.mapped + h.mapped.blocked)) * 100) : 0}%
                                </div>
                              </div>
                            ) : (
                              <span className="muted small">{status === "start" ? "Not yet available" : "Open to view"}</span>
                            )}
                          </td>
                          <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                            <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                              {status === "start" && (
                                <button type="button" className="btn btn--sm" onClick={() => setUploadFor(p)} disabled={!!h.busy}>
                                  <Upload size={13} /> Upload
                                </button>
                              )}
                              {(status === "scanned" || status === "confirmed" || status === "mapped" || status === "classified") && (
                                <button
                                  type="button"
                                  className="btn btn--sm"
                                  onClick={async () => {
                                    if (!isActive) await h.openPaper(p);
                                    setMappingFor(p);
                                  }}
                                >
                                  View mapping
                                </button>
                              )}
                              {status === "classified" && (
                                <button
                                  type="button"
                                  className="btn btn--sm"
                                  onClick={async () => {
                                    if (!isActive) await h.openPaper(p);
                                    setCardFor(p);
                                  }}
                                >
                                  <FileUp size={13} /> Answer card
                                </button>
                              )}
                              <button type="button" className="btn btn--ghost btn--sm" disabled={h.renaming || !!h.busy} onClick={(e) => { e.stopPropagation(); void h.onRename(p.id, p.title); }}>
                                Rename
                              </button>
                              <button type="button" className="btn btn--danger btn--sm" disabled={!!h.busy} onClick={(e) => { e.stopPropagation(); void h.onDelete(p.id); }}>
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Upload modal -- real scan pipeline: picking files (or capturing with the
          camera) calls the same submitScan() the old wizard used, and the modal closes
          once the scan lands, handing off to the mapping drawer below. */}
      <AnimatePresence>
        {uploadFor && (
          <motion.div
            className="modal-backdrop"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => { if (!h.busy) { setUploadFor(null); setShowCamera(false); } }}
          >
            <motion.div
              className="modal" role="dialog" aria-modal="true"
              initial={{ y: 16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 16, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="modal__head">
                <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Upload size={16} /> Upload {uploadFor === "new" ? h.subject : uploadFor.subject_label} paper
                </h3>
                <button className="iconbtn" onClick={() => { setUploadFor(null); setShowCamera(false); }} aria-label="Close" disabled={!!h.busy}>
                  <X size={16} />
                </button>
              </div>
              <div className="modal__body">
                {uploadFor === "new" && (
                  <div className="field">
                    <label>What is this test called?</label>
                    <input className="input" value={h.title} onChange={(e) => h.setTitle(e.target.value)} />
                  </div>
                )}
                <div className="field">
                  <label>Paper file</label>
                  <p className="small muted" style={{ margin: "0 0 8px" }}>
                    One page or many, as PDFs or photographs, in the order you add them. A
                    paper with selectable text is read now; a photographed one is reported
                    plainly rather than returned as an empty result.
                  </p>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button type="button" className="btn" onClick={() => fileInput.current?.click()} disabled={!!h.busy}>
                      {h.busy ?? "Choose files"}
                    </button>
                    <button type="button" className="btn btn--ghost" onClick={() => setShowCamera((v) => !v)} disabled={!!h.busy}>
                      {showCamera ? "Close camera" : "Use camera instead"}
                    </button>
                  </div>
                  <input
                    ref={fileInput}
                    type="file"
                    accept="application/pdf,image/*"
                    multiple
                    className="sr"
                    onChange={(e) => {
                      const chosen = Array.from(e.target.files ?? []);
                      if (chosen.length) void handleUploadFiles(chosen);
                    }}
                  />
                  {showCamera && (
                    <div style={{ marginTop: 10 }}>
                      <p className="muted small" style={{ margin: "0 0 8px" }}>
                        Captured pages are kept on this device until you press Complete, even
                        with no signal -- pick up where you left off if the connection drops
                        mid-scan.
                      </p>
                      <Scanner
                        sessionId={h.scanSessionId}
                        mode="script"
                        onComplete={async (pages) => {
                          await handleUploadFiles(toFiles(pages));
                        }}
                      />
                    </div>
                  )}
                </div>
              </div>
              <div className="modal__foot">
                <button className="btn" onClick={() => { setUploadFor(null); setShowCamera(false); }} disabled={!!h.busy}>
                  Cancel
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Mapping drawer -- real per-question review, confirm/map/classify actions, and
          blueprint coverage, all read off usePaperScan's live state for the paper that
          is open (never a mock chapter/question table). */}
      <AnimatePresence>
        {isMappingOpen && mappingFor && (
          <>
            <motion.div className="drawer-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMappingFor(null)} />
            <motion.aside
              className="drawer" role="dialog" aria-modal="true" aria-label={`${mappingFor.subject_label} blueprint mapping`}
              initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }}
              transition={{ type: "spring", stiffness: 380, damping: 34 }}
            >
              <div className="drawer__head">
                <div>
                  <div className="finding__subject">{mappingFor.subject_label}</div>
                  <h3 style={{ fontSize: 20 }}>{mappingFor.title}</h3>
                </div>
                <button className="iconbtn" onClick={() => setMappingFor(null)} aria-label="Close">
                  <X size={18} />
                </button>
              </div>
              <div className="drawer__body">
                {h.mapped ? (
                  <div className="drawer__section">
                    <h4>Blueprint coverage</h4>
                    <dl className="kv">
                      <dt>Mapped</dt>
                      <dd className="strong">{h.mapped.mapped}</dd>
                      <dt>Could not be mapped</dt>
                      <dd>{h.mapped.blocked}</dd>
                      <dt>Want a second look</dt>
                      <dd>{h.mapped.needs_review}</dd>
                      <dt>Matched by</dt>
                      <dd>{h.mapped.retrieval === "hybrid" ? "keyword and meaning search" : "keyword search"}</dd>
                    </dl>
                  </div>
                ) : h.scan ? (
                  <div className="drawer__section">
                    <p className="small muted" style={{ margin: 0 }}>Not mapped yet.</p>
                  </div>
                ) : (
                  <div className="drawer__section">
                    <p className="small muted" style={{ margin: 0 }}>No scan read yet for this paper.</p>
                  </div>
                )}

                {h.placed && (
                  <div className="drawer__section">
                    <h4>Classification</h4>
                    <dl className="kv">
                      <dt>Chapter/topic/sub topic settled</dt>
                      <dd className="strong">{h.placed.labelled}</dd>
                      <dt>Given a category</dt>
                      <dd>{h.placed.tiers}</dd>
                      <dt>Sub topic wants a second look</dt>
                      <dd>{h.placed.unsettled_family}</dd>
                    </dl>
                    <p className="small muted" style={{ marginTop: 8 }}>
                      {h.placed.spend.calls} reading{h.placed.spend.calls === 1 ? "" : "s"} by {h.placed.spend.model}
                      {" "}at {h.placed.spend.effort} effort.
                    </p>
                  </div>
                )}

                {h.review && h.review.questions.length > 0 && (
                  <div className="drawer__section">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                      <h4 style={{ margin: 0 }}>Questions in this paper</h4>
                      <div className="tabs" role="group" aria-label="Filter questions" style={{ border: "none", boxShadow: "none" }}>
                        {(
                          [
                            ["all", `All ${h.review.questions.length}`],
                            ["mapped", `Mapped ${h.review.mapped}`],
                            ["blocked", `Unmapped ${h.blockedCount}`],
                          ] as const
                        ).map(([value, label]) => (
                          <button key={value} type="button" className={`tab${h.filter === value ? " tab--active" : ""}`} onClick={() => h.setFilter(value)}>
                            {label}
                          </button>
                        ))}
                      </div>
                    </div>
                    {h.review.confirmed_at && (
                      <div className="evidence" style={{ margin: "10px 0" }}>
                        Confirmed by {h.review.confirmed_by ?? "someone"}
                        {h.review.edited > 0 && ` · ${h.review.edited} row(s) corrected first`}.
                      </div>
                    )}
                    <div className="table-wrap--scroll" style={{ maxHeight: 320, marginTop: 8 }}>
                      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
                        {h.rows.map((q) => (
                          <QuestionRow key={q.address} q={q} editable={!h.confirmed && !q.mapped_to} onEdit={h.onEdit} />
                        ))}
                      </ul>
                    </div>
                  </div>
                )}

                <div className="drawer__section" style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  {h.stage === "scanned" && (
                    <div style={{ display: "grid", gap: 8, width: "100%" }}>
                      <div className="field" style={{ maxWidth: 320 }}>
                        <label>Who checked this paper?</label>
                        <input className="input" value={h.confirmedBy} onChange={(e) => h.setConfirmedBy(e.target.value)} placeholder="Your name" autoComplete="name" />
                      </div>
                      <button type="button" className="btn btn--primary btn--sm" onClick={h.onConfirm} disabled={!!h.busy}>
                        {h.busy && <Mascot pose="loading" size={16} />} {h.busy ?? "Confirm & map to blueprint"}
                      </button>
                    </div>
                  )}
                  {h.stage === "confirmed" && (
                    <button type="button" className="btn btn--primary btn--sm" onClick={h.onMap} disabled={!!h.busy}>
                      {h.busy && <Mascot pose="loading" size={16} />} {h.busy ?? "Map these questions onto the book"}
                    </button>
                  )}
                  {h.stage === "mapped" && !h.placed && !h.alreadyClassified && h.mapped && h.mapped.mapped > 0 && (
                    <button type="button" className="btn btn--primary btn--sm" onClick={h.onClassify} disabled={!!h.busy}>
                      {h.busy && <Mascot pose="loading" size={16} />} <Sparkles size={13} /> {h.busy ?? "Read and classify"}
                    </button>
                  )}
                  {h.stage === "classified" && (
                    <button type="button" className="btn btn--primary btn--sm" onClick={() => { setMappingFor(null); setCardFor(mappingFor); }}>
                      <Sparkles size={13} /> Generate answer card
                    </button>
                  )}
                  {documentIdActions(h)}
                </div>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Answer card drawer -- links straight to the real api.answerCardPdf download,
          nothing simulated. */}
      <AnimatePresence>
        {isCardOpen && cardFor && (
          <>
            <motion.div className="drawer-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setCardFor(null)} />
            <motion.aside
              className="drawer" role="dialog" aria-modal="true" aria-label={`${cardFor.subject_label} answer card`}
              initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }}
              transition={{ type: "spring", stiffness: 380, damping: 34 }}
            >
              <div className="drawer__head">
                <div>
                  <div className="finding__subject">{cardFor.subject_label}</div>
                  <h3 style={{ fontSize: 20 }}>Answer card</h3>
                  <div className="muted small">{cardFor.title}{sectionLabel ? ` · ${sectionLabel}` : ""}</div>
                </div>
                <button className="iconbtn" onClick={() => setCardFor(null)} aria-label="Close">
                  <X size={18} />
                </button>
              </div>
              <div className="drawer__body">
                <div className="drawer__section">
                  <h4>What this is</h4>
                  <p className="small muted" style={{ margin: 0 }}>
                    A blank mark-entry sheet for {cardFor.subject_label} · {cardFor.title}, one row per
                    student, one column per question. Print it, fill it by hand, then scan it
                    back in from Enter Marks -- the app reads the marks automatically and
                    flags any it can&apos;t.
                  </p>
                </div>
                <div className="drawer__section">
                  <AnswerCardDownload assessmentId={cardFor.id} paperTitle={cardFor.title} sectionId={sectionId} sectionLabel={sectionLabel} />
                </div>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {toast && (
          <motion.div className="toast" role="status" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}>
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function documentIdActions(h: ReturnType<typeof usePaperScan>) {
  if (!h.documentId) return null;
  return (
    <button
      type="button"
      className="btn btn--ghost btn--sm"
      onClick={h.onRemoveScan}
      disabled={h.removingScan || !!h.busy}
      title="Discard the scanned pages and start the scan over, without losing questions already mapped or confirmed"
    >
      {h.removingScan ? "Removing…" : "Remove scan"}
    </button>
  );
}

/** api.answerCardPdf needs a real section id, which this panel does not always have
 * (a principal-wide paper spans every section). Real gap, called out rather than
 * fabricated: the download is offered once a section is known, e.g. from a
 * subject-scoped screen (sectionId is passed down); elsewhere this states plainly that a
 * section must be chosen from Enter Marks/Gridsheet first, rather than faking a button
 * that has nowhere real to point. */
function AnswerCardDownload({
  assessmentId, paperTitle, sectionId, sectionLabel,
}: { assessmentId: string; paperTitle: string; sectionId?: string; sectionLabel?: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!sectionId) {
    return (
      <p className="small muted" style={{ margin: 0 }}>
        Download the answer card for a specific class from Enter Marks &rarr; Gridsheet,
        once this paper is classified.
      </p>
    );
  }
  return (
    <>
      <button
        type="button"
        className="btn btn--primary"
        disabled={busy}
        onClick={async () => {
          const key = getApiKey();
          if (!key) return;
          setBusy(true);
          setError(null);
          try {
            const blob = await api.answerCardPdf(key, assessmentId, sectionId);
            downloadBlob(blob, `${paperTitle}-${sectionLabel ?? sectionId}-answer-card.pdf`);
          } catch {
            setError("Could not prepare the answer card.");
          } finally {
            setBusy(false);
          }
        }}
      >
        <FileUp size={14} /> {busy ? "Preparing…" : `Download answer card${sectionLabel ? ` (${sectionLabel})` : ""}`}
      </button>
      {error && <p className="small" style={{ color: "var(--risk)", marginTop: 6 }}>{error}</p>}
    </>
  );
}

function QuestionRow({
  q,
  editable,
  onEdit,
}: {
  q: StagedQuestion;
  editable: boolean;
  onEdit: (address: string, patch: Record<string, unknown>) => void;
}) {
  const placed = q.mapped_to;
  const missing = q.max_marks == null && !q.is_context;
  const borderColor = placed || q.is_context ? "var(--line)" : "var(--risk)";
  return (
    <li className="card card--flat" style={{ borderLeft: `4px solid ${borderColor}`, listStyle: "none" }}>
      <div className="card__body">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <span className="strong">
            {q.section ? `${q.section} · ` : ""}
            {q.question_no}
            {q.sub_part ? ` (${q.sub_part})` : ""}
            {q.choice_alt ? ` (${q.choice_alt})` : ""}
            {q.choice_alt === "b" && <span className="small muted"> instead of (a)</span>}
            {q.edited_by && <span className="small muted"> corrected by {q.edited_by}</span>}
          </span>
          {q.is_context ? (
            <span className="small muted"><em>the stem its parts share</em></span>
          ) : editable ? (
            <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <label className="sr">Marks for question {q.question_no}</label>
              <input
                className="input"
                style={{ width: 80 }}
                type="number"
                inputMode="decimal"
                min={0}
                step={0.5}
                defaultValue={q.max_marks ?? ""}
                placeholder="marks"
                onBlur={(e) => {
                  const value = e.target.value.trim();
                  if (value === "" || Number(value) === q.max_marks) return;
                  onEdit(q.address, { max_marks: Number(value) });
                }}
              />
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => onEdit(q.address, { remove: true })} aria-label={`Remove question ${q.question_no}, it is not a question`}>
                Not a question
              </button>
            </span>
          ) : (
            <span className="small muted">
              {missing ? <em style={{ color: "var(--risk)" }}>no marks read</em> : `${q.max_marks} marks`}
            </span>
          )}
        </div>

        <p className="small" style={{ marginTop: 6 }}>{q.stem_text || <em className="muted">no text was extracted for this question</em>}</p>

        {placed ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            <Chip label="Chapter" value={placed.chapter} />
            {placed.topic && <Chip label="Topic" value={placed.curriculum_section ? `${placed.curriculum_section} ${placed.topic}` : placed.topic} />}
            {!placed.topic && placed.curriculum_section && <Chip label="Topic" value={placed.curriculum_section} />}
            <Chip label="Sub topic" value={placed.concept_family} strong />
            <Chip label="Category" value={placed.tier ?? "not classified yet"} title={placed.tier_label ?? undefined} />
          </div>
        ) : (
          <p className="small" style={{ color: "var(--risk)", marginTop: 8 }}>{q.blocked_reason ?? "not mapped"}</p>
        )}
      </div>
    </li>
  );
}

function Chip({ label, value, strong, title }: { label: string; value: string | null; strong?: boolean; title?: string }) {
  if (!value) return null;
  return (
    <span className={`tag${strong ? " tag--teal" : ""}`} title={title}>
      <span className="small muted">{label}:</span> {value}
    </span>
  );
}
