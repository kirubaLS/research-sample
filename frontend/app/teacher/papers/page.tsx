"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, ChevronDown, ClipboardList, FileUp, Plus, Sparkles, Upload, X } from "lucide-react";
import {
  paperChapterMapping,
  paperCoverage,
  paperQuestions,
  rosterFor,
  sections,
  subjects,
  testsConducted,
  type ConductedTest,
  type SubjectPaper,
  type SubjectPaperStatus,
} from "@/lib/avai-mock-data";
import { createTest as createLiveTest, paperFor, updatePaper, useLiveVersion } from "@/lib/liveData";
import { downloadAnswerCard } from "@/lib/downloadReport";
import { FilePickButtons } from "@/components/FilePickButtons";
import { useAuth } from "@/lib/auth";
import { usePageHeader } from "@/lib/pageHeader";
import { MarksEntryGrid } from "@/components/MarksEntryGrid";

function StatusTag({ status }: { status: SubjectPaperStatus }) {
  if (status === "Mapped") return <span className="tag tag--green">Mapped</span>;
  if (status === "Processing") return <span className="tag tag--gold">Processing</span>;
  if (status === "Needs mapping") return <span className="tag tag--risk">Needs mapping</span>;
  return <span className="tag">Not uploaded</span>;
}


/** The exam-cell login: every subject, every section, question papers and
 * marks only, no dashboard, no insights, no per-section views. Tests
 * created here (and their papers) show up immediately in the Enter Marks
 * tab below, since both read from the same test list and paper state. */
export default function TeacherPapersPage() {
  usePageHeader({ title: "Question Papers & Marks" });
  const { user } = useAuth();
  const [tab, setTab] = useState<"papers" | "marks">("papers");

  useLiveVersion();
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  const [createOpen, setCreateOpen] = useState(false);
  const [createDraft, setCreateDraft] = useState<{ name: string; date: string; subjects: string[] }>({ name: "", date: "", subjects: [] });

  const [uploadFor, setUploadFor] = useState<{ testKey: string; subject: string } | null>(null);
  const [uploadFileName, setUploadFileName] = useState("");

  const [mappingFor, setMappingFor] = useState<{ testKey: string; subject: string } | null>(null);
  const [cardFor, setCardFor] = useState<{ testKey: string; subject: string } | null>(null);
  const [cardSection, setCardSection] = useState<string>(sections[0]);

  const [marksTestKey, setMarksTestKey] = useState<string>(testsConducted[0]?.key ?? "");
  const [marksSubject, setMarksSubject] = useState<string>(subjects[0]);
  const [marksSection, setMarksSection] = useState<string>(sections[0]);

  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2800);
    return () => clearTimeout(t);
  }, [toast]);

  const allTests: ConductedTest[] = testsConducted;

  function toggleExpand(testKey: string) {
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(testKey)) next.delete(testKey);
      else next.add(testKey);
      return next;
    });
  }

  function setPaper(testKey: string, subject: string, patch: Partial<SubjectPaper>) {
    updatePaper(testKey, subject, patch);
  }

  function createTest() {
    const name = createDraft.name.trim();
    if (!name || createDraft.subjects.length === 0) return;
    const key = `custom_${name.toLowerCase().replace(/[^a-z0-9]+/g, "_")}_${Date.now()}`;
    const test: ConductedTest = {
      key,
      name,
      date: createDraft.date || new Date().toISOString().slice(0, 10),
      status: "Scheduled",
      subjects: subjects.filter((s) => createDraft.subjects.includes(s)),
    };
    createLiveTest(test);
    setExpanded((s) => new Set(s).add(key));
    setMarksTestKey(key);
    setCreateOpen(false);
    setCreateDraft({ name: "", date: "", subjects: [] });
    setToast(`${name} created with ${createDraft.subjects.length} subject${createDraft.subjects.length === 1 ? "" : "s"}. It's also ready in Enter Marks.`);
  }

  function upload() {
    if (!uploadFor) return;
    const { testKey, subject } = uploadFor;
    const fileName = uploadFileName || `${subject.toLowerCase().replace(/\s+/g, "-")}-paper.pdf`;
    setPaper(testKey, subject, { fileName, uploadedBy: user?.name ?? "You", uploadedAt: new Date().toISOString().slice(0, 10), status: "Processing" });
    setUploadFor(null);
    setUploadFileName("");
    setToast(`Uploaded ${fileName}. Mapping ${subject} against the Board blueprint…`);
    setTimeout(() => setPaper(testKey, subject, { status: "Needs mapping" }), 1600);
  }

  function confirmMapping(testKey: string, subject: string) {
    setPaper(testKey, subject, { status: "Mapped" });
    setToast(`${subject} mapping confirmed.`);
  }

  function generateAnswerCard(testKey: string, subject: string) {
    setPaper(testKey, subject, { answerCardGenerated: true });
    setMappingFor(null);
    setCardFor({ testKey, subject });
    setToast(`Answer card generated for ${subject}.`);
  }

  const testForMapping = mappingFor ? allTests.find((t) => t.key === mappingFor.testKey) : null;
  const paperForMapping = mappingFor ? paperFor(mappingFor.testKey, mappingFor.subject) : null;
  const testForCard = cardFor ? allTests.find((t) => t.key === cardFor.testKey) : null;
  const testForUpload = uploadFor ? allTests.find((t) => t.key === uploadFor.testKey) : null;

  const marksRoster = rosterFor(marksSection, marksTestKey || testsConducted[0]?.key);
  const marksTest = allTests.find((t) => t.key === marksTestKey);
  const subjectOptions = marksTest?.subjects ?? [...subjects];
  const activeSubject = subjectOptions.includes(marksSubject) ? marksSubject : subjectOptions[0];

  return (
    <>
      <p className="page-sub" style={{ marginTop: 0 }}>
        Every subject, every section, question papers and marks only. Create a test here and it shows up in Enter Marks immediately.
      </p>

      <div className="tabs" role="tablist" style={{ marginTop: 18 }}>
        <button role="tab" aria-selected={tab === "papers"} className={`tab ${tab === "papers" ? "tab--active" : ""}`} onClick={() => setTab("papers")}>
          Question papers
        </button>
        <button role="tab" aria-selected={tab === "marks"} className={`tab ${tab === "marks" ? "tab--active" : ""}`} onClick={() => setTab("marks")}>
          Enter marks
        </button>
      </div>

      {tab === "papers" ? (
        <>
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 18 }}>
            <button className="btn btn--primary" onClick={() => setCreateOpen(true)}>
              <Plus size={15} /> Create test
            </button>
          </div>

          <div style={{ display: "grid", gap: 14, marginTop: 14 }}>
            {allTests.map((t) => {
              const subjectList = t.subjects ?? [...subjects];
              const subjectPapers: Record<string, SubjectPaper> = Object.fromEntries(subjectList.map((s) => [s, paperFor(t.key, s)]));
              const mappedCount = subjectList.filter((s) => subjectPapers[s].status === "Mapped").length;
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
                          {t.date} · {subjectList.length} subject{subjectList.length === 1 ? "" : "s"} · {mappedCount} of {subjectList.length} mapped
                        </div>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        {t.status === "Analysed" ? <span className="tag tag--green">Analysed</span> : <span className="tag">Scheduled</span>}
                        <ChevronDown size={16} className="muted" style={{ transform: isOpen ? "rotate(180deg)" : undefined, transition: "transform .15s" }} />
                      </div>
                    </div>
                  </button>

                  <AnimatePresence initial={false}>
                    {isOpen && (
                      <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} style={{ overflow: "hidden" }}>
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
                              {subjectList.length === 0 && (
                                <tr>
                                  <td colSpan={5} className="muted small" style={{ padding: "14px 16px" }}>
                                    No subjects on this test yet.
                                  </td>
                                </tr>
                              )}
                              {subjectList.map((subject) => {
                                const p = subjectPapers[subject];
                                const coverage = paperCoverage(subject);
                                return (
                                  <tr key={subject}>
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
                                        <button className="btn btn--sm" onClick={() => setUploadFor({ testKey: t.key, subject })}>
                                          <Upload size={13} /> Upload
                                        </button>
                                      )}
                                      {p.status === "Processing" && <span className="small muted">Processing…</span>}
                                      {(p.status === "Needs mapping" || p.status === "Mapped") && (
                                        <button className="btn btn--sm" onClick={() => setMappingFor({ testKey: t.key, subject })}>
                                          View mapping
                                        </button>
                                      )}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>

          <p className="small muted" style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 6 }}>
            <ClipboardList size={13} /> Uploads, mapping and answer cards are all simulated for this demo, nothing is parsed or stored, and the list resets
            on reload.
          </p>
        </>
      ) : (
        <div style={{ marginTop: 18 }}>
          <div className="filterbar">
            <div className="filter">
              <label htmlFor="marks-test">Assessment</label>
              <select id="marks-test" className="select" value={marksTestKey} onChange={(e) => setMarksTestKey(e.target.value)}>
                {allTests.map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.name}
                    {t.status !== "Analysed" ? " (not yet analysed)" : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="filter">
              <label htmlFor="marks-subject">Subject</label>
              <select id="marks-subject" className="select" value={activeSubject} onChange={(e) => setMarksSubject(e.target.value)}>
                {subjectOptions.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </div>
            <div className="filter">
              <label htmlFor="marks-section">Section</label>
              <select id="marks-section" className="select" value={marksSection} onChange={(e) => setMarksSection(e.target.value)}>
                {sections.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </div>
          </div>

          {marksTestKey && (
            <MarksEntryGrid
              key={`${marksTestKey}-${activeSubject}-${marksSection}`}
              subject={activeSubject}
              roster={marksRoster}
              scopeLabel={`${marksSection} · ${activeSubject} · ${marksTest?.name ?? marksTestKey}`}
              testKey={marksTestKey}
            />
          )}
        </div>
      )}

      {/* Create test modal */}
      <AnimatePresence>
        {createOpen && (
          <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setCreateOpen(false)}>
            <motion.div className="modal" role="dialog" aria-modal="true" initial={{ y: 16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 16, opacity: 0 }} onClick={(e) => e.stopPropagation()}>
              <div className="modal__head">
                <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Plus size={16} /> Create test
                </h3>
                <button className="iconbtn" onClick={() => setCreateOpen(false)} aria-label="Close">
                  <X size={16} />
                </button>
              </div>
              <div className="modal__body">
                <div className="field">
                  <label htmlFor="ct-name">Test name</label>
                  <input id="ct-name" className="input" placeholder="e.g. Weekly Test 3" value={createDraft.name} onChange={(e) => setCreateDraft({ ...createDraft, name: e.target.value })} />
                </div>
                <div className="field">
                  <label htmlFor="ct-date">Date</label>
                  <input id="ct-date" className="input" type="date" value={createDraft.date} onChange={(e) => setCreateDraft({ ...createDraft, date: e.target.value })} />
                </div>
                <div className="field">
                  <label>Subjects for this test</label>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
                    {subjects.map((s) => {
                      const checked = createDraft.subjects.includes(s);
                      return (
                        <button
                          key={s}
                          type="button"
                          className={`tag ${checked ? "tag--teal" : ""}`}
                          style={{ cursor: "pointer", border: "1px solid var(--line)" }}
                          onClick={() =>
                            setCreateDraft((d) => ({ ...d, subjects: checked ? d.subjects.filter((x) => x !== s) : [...d.subjects, s] }))
                          }
                        >
                          {checked && <CheckCircle2 size={12} />} {s}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
              <div className="modal__foot">
                <button className="btn" onClick={() => setCreateOpen(false)}>
                  Cancel
                </button>
                <button className="btn btn--primary" disabled={!createDraft.name.trim() || createDraft.subjects.length === 0} onClick={createTest}>
                  <Plus size={14} /> Create test
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Upload paper modal */}
      <AnimatePresence>
        {uploadFor && (
          <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setUploadFor(null)}>
            <motion.div className="modal" role="dialog" aria-modal="true" initial={{ y: 16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 16, opacity: 0 }} onClick={(e) => e.stopPropagation()}>
              <div className="modal__head">
                <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Upload size={16} /> Upload {uploadFor.subject} paper
                </h3>
                <button className="iconbtn" onClick={() => setUploadFor(null)} aria-label="Close">
                  <X size={16} />
                </button>
              </div>
              <div className="modal__body">
                <p className="small muted" style={{ margin: 0 }}>
                  {testForUpload?.name} · {uploadFor.subject}
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
              aria-label={`${mappingFor.subject} blueprint mapping`}
              initial={{ x: 40, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 40, opacity: 0 }}
              transition={{ type: "spring", stiffness: 380, damping: 34 }}
            >
              <div className="drawer__head">
                <div>
                  <div className="finding__subject">{mappingFor.subject}</div>
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
                  <>
                    <dl className="kv">
                      <dt>Coverage</dt>
                      <dd className="strong">{paperCoverage(mappingFor.subject)?.pct}%</dd>
                      <dt>Chapters covered</dt>
                      <dd>
                        {paperCoverage(mappingFor.subject)?.covered} of {paperCoverage(mappingFor.subject)?.total}
                      </dd>
                    </dl>
                    <p className="small muted" style={{ marginTop: 8 }}>
                      Measured against the whole Board blueprint for {mappingFor.subject}, not against this one paper, a unit test is expected to cover
                      part of it.
                    </p>
                  </>
                </div>
                <div className="drawer__section">
                  <h4>Chapter-by-chapter</h4>
                  <div className="table-wrap--scroll" style={{ maxHeight: 260 }}>
                    {paperChapterMapping[mappingFor.subject].map((c) => (
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
                        {paperQuestions[mappingFor.subject].map((q) => (
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
                    <span>{paperQuestions[mappingFor.subject].length} questions</span>
                    <span className="strong" style={{ color: "var(--text)" }}>
                      Total: {paperQuestions[mappingFor.subject].reduce((sum, q) => sum + q.marks, 0)} marks
                    </span>
                  </div>
                </div>
                <div className="drawer__section" style={{ display: "flex", gap: 10 }}>
                  {paperForMapping.status === "Needs mapping" && (
                    <button className="btn btn--primary btn--sm" onClick={() => confirmMapping(mappingFor.testKey, mappingFor.subject)}>
                      <CheckCircle2 size={13} /> Confirm mapping
                    </button>
                  )}
                  {paperForMapping.status === "Mapped" && (
                    <button className="btn btn--primary btn--sm" onClick={() => generateAnswerCard(mappingFor.testKey, mappingFor.subject)}>
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
              aria-label={`${cardFor.subject} answer card`}
              initial={{ x: 40, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 40, opacity: 0 }}
              transition={{ type: "spring", stiffness: 380, damping: 34 }}
            >
              <div className="drawer__head">
                <div>
                  <div className="finding__subject">{cardFor.subject}</div>
                  <h3 style={{ fontSize: 20 }}>Answer card</h3>
                  <div className="muted small">{testForCard.name}</div>
                </div>
                <button className="iconbtn" onClick={() => setCardFor(null)} aria-label="Close">
                  <X size={18} />
                </button>
              </div>
              <div className="drawer__body">
                <div className="drawer__section">
                  <h4>Section</h4>
                  <select className="select" value={cardSection} onChange={(e) => setCardSection(e.target.value)}>
                    {sections.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </div>
                <div className="drawer__section">
                  <h4>What this is</h4>
                  <p className="small muted" style={{ margin: 0 }}>
                    A blank mark-entry sheet for {cardFor.subject} · {testForCard.name} · Class X {cardSection}, one row per student, one column per
                    question. Print it, fill it by hand, then scan it back in from Enter Marks, the app reads the marks automatically and flags any
                    it can&apos;t.
                  </p>
                </div>
                <div className="drawer__section">
                  <button className="btn btn--primary" onClick={() => downloadAnswerCard(cardFor.testKey, cardFor.subject, cardSection)}>
                    <FileUp size={14} /> Download answer card ({cardSection})
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
