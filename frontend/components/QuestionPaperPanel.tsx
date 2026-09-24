"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, ChevronDown, FileUp, Sparkles, Upload, X } from "lucide-react";
import {
  paperChapterMapping,
  paperCoverage,
  paperQuestions,
  testsConducted,
  type SubjectPaper,
  type SubjectPaperStatus,
} from "@/lib/avai-mock-data";
import { downloadAnswerCard } from "@/lib/downloadReport";
import { FilePickButtons } from "@/components/FilePickButtons";
import { useAuth } from "@/lib/auth";
import { paperFor, updatePaper, useLiveVersion } from "@/lib/liveData";

function StatusTag({ status }: { status: SubjectPaperStatus }) {
  if (status === "Mapped") return <span className="tag tag--green">Mapped</span>;
  if (status === "Processing") return <span className="tag tag--gold">Processing</span>;
  if (status === "Needs mapping") return <span className="tag tag--risk">Needs mapping</span>;
  return <span className="tag">Not uploaded</span>;
}

/** One subject's question-paper tracker, upload, blueprint mapping, and
 * answer-card generation, scoped to a single (subject, section) the way
 * a subject teacher actually works, instead of the whole school's paper
 * list a principal used to see. Trimmed from the old principal-wide
 * Question Papers page: no cross-subject accordion, no test creation. */
export function QuestionPaperPanel({ subject, section }: { subject: string; section: string }) {
  const { user } = useAuth();
  useLiveVersion();
  const papers: Record<string, SubjectPaper> = Object.fromEntries(
    testsConducted.filter((t) => (t.subjects ?? [subject]).includes(subject)).map((t) => [t.key, paperFor(t.key, subject)]),
  );
  // Nothing expanded by default, click a test to see its paper.
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  const [uploadFor, setUploadFor] = useState<string | null>(null);
  const [uploadFileName, setUploadFileName] = useState("");
  const [mappingFor, setMappingFor] = useState<string | null>(null);
  const [cardFor, setCardFor] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2800);
    return () => clearTimeout(t);
  }, [toast]);

  function setPaper(testKey: string, patch: Partial<SubjectPaper>) {
    updatePaper(testKey, subject, patch);
  }

  function upload() {
    if (!uploadFor) return;
    const testKey = uploadFor;
    const fileName = uploadFileName || `${subject.toLowerCase().replace(/\s+/g, "-")}-paper.pdf`;
    setPaper(testKey, { fileName, uploadedBy: user?.name ?? "You", uploadedAt: new Date().toISOString().slice(0, 10), status: "Processing" });
    setUploadFor(null);
    setUploadFileName("");
    setToast(`Uploaded ${fileName}. Mapping ${subject} against the Board blueprint…`);
    setTimeout(() => setPaper(testKey, { status: "Needs mapping" }), 1600);
  }

  function confirmMapping(testKey: string) {
    setPaper(testKey, { status: "Mapped" });
    setToast(`${subject} mapping confirmed.`);
  }

  function generateAnswerCard(testKey: string) {
    setPaper(testKey, { answerCardGenerated: true });
    setMappingFor(null);
    setCardFor(testKey);
    setToast("Answer card generated.");
  }

  function toggleExpand(testKey: string) {
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(testKey)) next.delete(testKey);
      else next.add(testKey);
      return next;
    });
  }

  const testForMapping = mappingFor ? testsConducted.find((t) => t.key === mappingFor) : null;
  const paperForMapping = mappingFor ? papers[mappingFor] : null;
  const testForCard = cardFor ? testsConducted.find((t) => t.key === cardFor) : null;
  const testForUpload = uploadFor ? testsConducted.find((t) => t.key === uploadFor) : null;
  const coverage = paperCoverage(subject);

  return (
    <>
      <div style={{ display: "grid", gap: 12 }}>
        {testsConducted.map((t) => {
          const p = papers[t.key];
          if (!p) return null;
          const isOpen = expanded.has(t.key);
          return (
            <div className="card" key={t.key}>
              <button
                onClick={() => toggleExpand(t.key)}
                style={{ width: "100%", textAlign: "left", background: "none", border: "none", padding: 0, cursor: "pointer" }}
                aria-expanded={isOpen}
              >
                <div className="card__head">
                  <div>
                    <div className="strong" style={{ fontSize: 15 }}>
                      {t.name}
                    </div>
                    <div className="small muted" style={{ marginTop: 2 }}>
                      {t.date} · {subject}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <StatusTag status={p.status} />
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
                        <th>File</th>
                        <th>Blueprint coverage</th>
                        <th>Status</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td className="strong">{subject}</td>
                        <td>
                          {p.fileName ? (
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              <FileUp size={13} style={{ color: "var(--muted)" }} />
                              <span className="small">{p.fileName}</span>
                            </div>
                          ) : (
                            <span className="muted small">No file yet</span>
                          )}
                        </td>
                        <td style={{ minWidth: 140 }}>
                          {p.status === "Mapped" || p.status === "Needs mapping" ? (
                            <div className="bar-row" style={{ gridTemplateColumns: "1fr 40px", padding: 0 }}>
                              <div className="bar">
                                <div className="bar__fill" style={{ width: `${coverage?.pct ?? 0}%` }} />
                              </div>
                              <div className="bar-row__val">{coverage?.pct ?? 0}%</div>
                            </div>
                          ) : (
                            <span className="muted small">Not yet available</span>
                          )}
                        </td>
                        <td>
                          <StatusTag status={p.status} />
                        </td>
                        <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                          {p.status === "Not uploaded" && (
                            <button className="btn btn--sm" onClick={() => setUploadFor(t.key)}>
                              <Upload size={13} /> Upload
                            </button>
                          )}
                          {p.status === "Processing" && <span className="small muted">Processing…</span>}
                          {(p.status === "Needs mapping" || p.status === "Mapped") && (
                            <button className="btn btn--sm" onClick={() => setMappingFor(t.key)}>
                              View mapping
                            </button>
                          )}
                          {p.status === "Mapped" && p.answerCardGenerated && (
                            <button className="btn btn--sm" style={{ marginLeft: 6 }} onClick={() => setCardFor(t.key)}>
                              <FileUp size={13} /> Answer card
                            </button>
                          )}
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

      <p className="small muted" style={{ marginTop: 14 }}>
        Uploads, mapping and answer cards are all simulated for this demo, nothing is parsed or stored, and the list resets on reload.
      </p>

      {/* Upload paper modal */}
      <AnimatePresence>
        {uploadFor && (
          <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setUploadFor(null)}>
            <motion.div className="modal" role="dialog" aria-modal="true" initial={{ y: 16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 16, opacity: 0 }} onClick={(e) => e.stopPropagation()}>
              <div className="modal__head">
                <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Upload size={16} /> Upload {subject} paper
                </h3>
                <button className="iconbtn" onClick={() => setUploadFor(null)} aria-label="Close">
                  <X size={16} />
                </button>
              </div>
              <div className="modal__body">
                <p className="small muted" style={{ margin: 0 }}>
                  {testForUpload?.name} · {subject}
                </p>
                <div className="field">
                  <label>Paper file</label>
                  <FilePickButtons accept=".pdf,.doc,.docx,image/*" onPick={(f) => setUploadFileName(f.name)} />
                  {uploadFileName && (
                    <div className="small muted" style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
                      <CheckCircle2 size={13} style={{ color: "var(--brand-green)" }} /> {uploadFileName}
                    </div>
                  )}
                </div>
              </div>
              <div className="modal__foot">
                <button className="btn" onClick={() => setUploadFor(null)}>
                  Cancel
                </button>
                <button className="btn btn--primary" onClick={upload}>
                  <Sparkles size={14} /> Upload &amp; map to blueprint
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Mapping drawer */}
      <AnimatePresence>
        {mappingFor && testForMapping && paperForMapping && (
          <>
            <motion.div className="drawer-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMappingFor(null)} />
            <motion.aside
              className="drawer"
              role="dialog"
              aria-modal="true"
              aria-label={`${subject} blueprint mapping`}
              initial={{ x: 40, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 40, opacity: 0 }}
              transition={{ type: "spring", stiffness: 380, damping: 34 }}
            >
              <div className="drawer__head">
                <div>
                  <div className="finding__subject">{subject}</div>
                  <h3 style={{ fontSize: 20 }}>{testForMapping.name}</h3>
                  <div className="muted small">{paperForMapping.fileName}</div>
                </div>
                <button className="iconbtn" onClick={() => setMappingFor(null)} aria-label="Close">
                  <X size={18} />
                </button>
              </div>
              <div className="drawer__body">
                <div className="drawer__section">
                  <h4>Blueprint coverage</h4>
                  <dl className="kv">
                    <dt>Coverage</dt>
                    <dd className="strong">{paperCoverage(subject)?.pct}%</dd>
                    <dt>Chapters covered</dt>
                    <dd>
                      {paperCoverage(subject)?.covered} of {paperCoverage(subject)?.total}
                    </dd>
                  </dl>
                  <p className="small muted" style={{ marginTop: 8 }}>
                    Measured against the whole Board blueprint for {subject}, not against this one paper, a unit test is expected to cover part of it.
                  </p>
                </div>
                <div className="drawer__section">
                  <h4>Chapter-by-chapter</h4>
                  <div className="table-wrap--scroll" style={{ maxHeight: 260 }}>
                    {paperChapterMapping[subject].map((c) => (
                      <div className="bar-row" key={c.chapter} style={{ gridTemplateColumns: "1fr 90px" }}>
                        <div className="bar-row__label">{c.chapter}</div>
                        <div className="small" style={{ textAlign: "right" }}>
                          {c.covered ? <span className="tag tag--green">{c.questionsMapped} Q mapped</span> : <span className="tag">Not tested</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="drawer__section">
                  <h4>Questions in this paper</h4>
                  <div className="card card--flat">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Q. No</th>
                          <th>Chapter</th>
                          <th className="num">Marks</th>
                        </tr>
                      </thead>
                      <tbody>
                        {paperQuestions[subject].map((q) => (
                          <tr key={q.no}>
                            <td className="strong">{q.no}</td>
                            <td>{q.chapter}</td>
                            <td className="num">{q.marks}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="small muted" style={{ marginTop: 8, display: "flex", justifyContent: "space-between" }}>
                    <span>{paperQuestions[subject].length} questions</span>
                    <span className="strong" style={{ color: "var(--text)" }}>
                      Total: {paperQuestions[subject].reduce((sum, q) => sum + q.marks, 0)} marks
                    </span>
                  </div>
                </div>
                <div className="drawer__section" style={{ display: "flex", gap: 10 }}>
                  {paperForMapping.status === "Needs mapping" && (
                    <button className="btn btn--primary btn--sm" onClick={() => confirmMapping(mappingFor)}>
                      <CheckCircle2 size={13} /> Confirm mapping
                    </button>
                  )}
                  {paperForMapping.status === "Mapped" && (
                    <button className="btn btn--primary btn--sm" onClick={() => generateAnswerCard(mappingFor)}>
                      <Sparkles size={13} /> {paperForMapping.answerCardGenerated ? "Regenerate answer card" : "Generate answer card"}
                    </button>
                  )}
                </div>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Answer card drawer */}
      <AnimatePresence>
        {cardFor && testForCard && (
          <>
            <motion.div className="drawer-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setCardFor(null)} />
            <motion.aside
              className="drawer"
              role="dialog"
              aria-modal="true"
              aria-label={`${subject} answer card`}
              initial={{ x: 40, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 40, opacity: 0 }}
              transition={{ type: "spring", stiffness: 380, damping: 34 }}
            >
              <div className="drawer__head">
                <div>
                  <div className="finding__subject">{subject}</div>
                  <h3 style={{ fontSize: 20 }}>Answer card</h3>
                  <div className="muted small">
                    {testForCard.name} · {section}
                  </div>
                </div>
                <button className="iconbtn" onClick={() => setCardFor(null)} aria-label="Close">
                  <X size={18} />
                </button>
              </div>
              <div className="drawer__body">
                <div className="drawer__section">
                  <h4>What this is</h4>
                  <p className="small muted" style={{ margin: 0 }}>
                    A blank mark-entry sheet for {subject} · {testForCard.name} · {section}, one row per student, one column per question. Print it, fill
                    it by hand, then scan it back in from Enter Marks, the app reads the marks automatically and flags any it can&apos;t.
                  </p>
                </div>
                <div className="drawer__section">
                  <button className="btn btn--primary" onClick={() => downloadAnswerCard(cardFor, subject, section)}>
                    <FileUp size={14} /> Download answer card ({section})
                  </button>
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
