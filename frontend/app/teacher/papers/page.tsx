"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  AlertTriangle,
  Calendar,
  Camera,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import { api, ApiError, type ConductedExam, type ExamsOverview, type PaperSummary, type ScheduledExam } from "@/lib/api";
import { usePaperScan } from "@/lib/usePaperScan";
import { useGridSheet } from "@/lib/useGridSheet";
import { FilePickButtons } from "@/components/FilePickButtons";
import { usePageHeader } from "@/lib/pageHeader";
import { MarksEntryGrid } from "@/components/MarksEntryGrid";
import { ConfirmedMarksGrid } from "@/components/ConfirmedMarksGrid";
import { AnimatedBar, Reveal, Stagger, StaggerItem } from "@/components/motion";
import { getApiKey } from "@/lib/session";

/** The exam-cell login: every subject, question papers and marks only, no dashboard, no
 * insights, no per-section views -- wired to the real usePaperScan/useGridSheet pipelines
 * (the same hooks the subject-scoped Papers/Marks tabs use), just without a subject or
 * section fixed in advance.
 *
 * Question papers grouped by test: real, from PaperSummary.exam_id (see
 * app.api.marks.assessment_summaries) joined against GET /admin/exams's own upcoming /
 * awaiting_marks / conducted lists -- both endpoints the exam cell already has real
 * access to (require_exam_read_scope). "Create test" schedules a real Exam
 * (POST /admin/exams) and creates one real, empty Assessment per chosen subject under it
 * (POST /assessments with exam_id) -- nothing here is simulated: a subject with "no file
 * yet" is a real Assessment row waiting for a scan, not a placeholder.
 */
export default function TeacherPapersPage() {
  usePageHeader({ title: "Question Papers & Marks" });
  const [tab, setTab] = useState<"papers" | "marks">("papers");

  const scan = usePaperScan({
    listPapers: (key) => api.teacherPapers(key),
    listSubjects: (key) => api.subjects(key).then((r) => r.subjects),
  });
  const grid = useGridSheet({ role: "teacher" });

  const [newTitle, setNewTitle] = useState("Cycle Test I");

  // --- Exam-day grouping ------------------------------------------------------------
  const [exams, setExams] = useState<ExamsOverview | null>(null);
  const [examsLoading, setExamsLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const loadExams = useCallback(async () => {
    const key = getApiKey();
    if (!key) return;
    try {
      setExams(await api.exams(key));
    } catch {
      /* the flat papers list below still works without the test grouping */
    } finally {
      setExamsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadExams();
  }, [loadExams]);

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // Every scheduled/conducted exam day, name + date + a real status, regardless of which
  // of GET /admin/exams's three buckets it fell in.
  type TestRow = { id: string; name: string; date: string | null; status: "Analysed" | "Awaiting marks" | "Scheduled" };
  const tests: TestRow[] = useMemo(() => {
    if (!exams) return [];
    const conducted: TestRow[] = exams.conducted
      .filter((c): c is ConductedExam & { kind: "exam" } => c.kind === "exam")
      .map((c) => ({ id: c.id, name: c.name, date: c.date, status: "Analysed" }));
    const awaiting: TestRow[] = exams.awaiting_marks.map((e: ScheduledExam) => ({
      id: e.id, name: e.name, date: e.scheduled_date, status: "Awaiting marks",
    }));
    const upcoming: TestRow[] = exams.upcoming.map((e: ScheduledExam) => ({
      id: e.id, name: e.name, date: e.scheduled_date, status: "Scheduled",
    }));
    return [...conducted, ...awaiting, ...upcoming].sort((a, b) => (b.date ?? "").localeCompare(a.date ?? ""));
  }, [exams]);

  const papersByExam = useMemo(() => {
    const map = new Map<string, PaperSummary[]>();
    for (const p of scan.papers) {
      if (!p.exam_id) continue;
      const list = map.get(p.exam_id) ?? [];
      list.push(p);
      map.set(p.exam_id, list);
    }
    return map;
  }, [scan.papers]);

  const standalonePapers = scan.papers.filter((p) => !p.exam_id);

  // --- Create test modal -------------------------------------------------------------
  const [showCreate, setShowCreate] = useState(false);
  const [examName, setExamName] = useState("");
  const [examDate, setExamDate] = useState("");
  const [pickedSubjects, setPickedSubjects] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  function toggleSubject(code: string) {
    setPickedSubjects((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  async function createTest(e: FormEvent) {
    e.preventDefault();
    const key = getApiKey();
    if (!key) return;
    if (!examName.trim() || !examDate) {
      setCreateError("Give the test a name and a date.");
      return;
    }
    if (pickedSubjects.size === 0) {
      setCreateError("Pick at least one subject.");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const created = await api.createExam(key, { name: examName.trim(), scheduled_date: examDate });
      for (const subject_code of pickedSubjects) {
        await api.createAssessment(key, { subject_code, title: examName.trim(), exam_id: created.id });
      }
      setShowCreate(false);
      setExamName("");
      setExamDate("");
      setPickedSubjects(new Set());
      setExpanded((prev) => new Set(prev).add(created.id));
      await Promise.all([loadExams(), scan.loadPapers()]);
    } catch (err) {
      setCreateError(err instanceof ApiError ? "Could not create the test." : "Could not reach the API.");
    } finally {
      setCreating(false);
    }
  }

  // --- Per-row status/coverage, derived honestly from the real PaperSummary fields ---
  function statusTag(p: PaperSummary): { label: string; cls: string } {
    if (p.stage === "mapped") return { label: "Mapped", cls: "tag--green" };
    if (p.stage === "confirmed" || p.stage === "scanned") return { label: "Needs mapping", cls: "tag--gold" };
    return { label: "Not uploaded", cls: "" };
  }
  function coveragePct(p: PaperSummary): number {
    return p.questions > 0 ? Math.round((p.mapped_questions / p.questions) * 100) : 0;
  }

  // --- Marks tab: prefer the read-only confirmed grid once a paper+section is fully
  // marked, falling back to the live entry grid, exactly like the subject-scoped screen.
  const [notReady, setNotReady] = useState<Set<string>>(new Set());
  const marksKey = `${grid.paperId}:${grid.sectionId}`;

  return (
    <>
      <p className="page-sub" style={{ marginTop: 0 }}>
        Every subject, question papers and marks only.
      </p>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 18 }}>
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "papers"} className={`tab ${tab === "papers" ? "tab--active" : ""}`} onClick={() => setTab("papers")}>
            Question papers
          </button>
          <button role="tab" aria-selected={tab === "marks"} className={`tab ${tab === "marks" ? "tab--active" : ""}`} onClick={() => setTab("marks")}>
            Enter marks
          </button>
        </div>
        {tab === "papers" && !scan.assessmentId && (
          <button className="btn btn--primary" onClick={() => setShowCreate(true)}>
            <Plus size={14} /> Create test
          </button>
        )}
      </div>

      {tab === "papers" ? (
        <div style={{ marginTop: 18 }}>
          {scan.error && (
            <div className="evidence evidence--gold" style={{ marginBottom: 12 }}>
              <AlertTriangle size={16} />
              <div>{scan.error}</div>
            </div>
          )}

          {!scan.assessmentId ? (
            <>
              <Stagger style={{ display: "grid", gap: 14 }}>
                {examsLoading && <p className="small muted">Loading tests…</p>}

                {tests.map((t) => {
                  const papers = papersByExam.get(t.id) ?? [];
                  const mappedCount = papers.filter((p) => p.stage === "mapped").length;
                  const open = expanded.has(t.id);
                  return (
                    <StaggerItem key={t.id}>
                      <div className="card card--hover">
                        <button
                          type="button"
                          onClick={() => toggle(t.id)}
                          aria-expanded={open}
                          className="card__head"
                          style={{ width: "100%", background: "none", border: 0, textAlign: "left", cursor: "pointer", font: "inherit", color: "inherit" }}
                        >
                          <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                            {open ? <ChevronDown size={18} style={{ marginTop: 2 }} /> : <ChevronRight size={18} style={{ marginTop: 2 }} />}
                            <div>
                              <div className="strong" style={{ fontSize: 15, fontWeight: 650 }}>{t.name}</div>
                              <div className="small muted" style={{ marginTop: 2, display: "flex", alignItems: "center", gap: 6 }}>
                                <Calendar size={12} /> {t.date ?? "no date"} · {papers.length} subject{papers.length === 1 ? "" : "s"} ·{" "}
                                {mappedCount} of {papers.length} mapped
                              </div>
                            </div>
                          </div>
                          <span className={`tag ${t.status === "Analysed" ? "tag--green" : ""}`}>{t.status}</span>
                        </button>

                        {open && (
                          <div className="card__body" style={{ paddingTop: 0, display: "grid", gap: 10 }}>
                            {papers.length === 0 ? (
                              <p className="small muted">No papers attached to this test yet.</p>
                            ) : (
                              papers.map((p) => {
                                const st = statusTag(p);
                                const pct = coveragePct(p);
                                return (
                                  <div
                                    key={p.id}
                                    style={{
                                      display: "grid",
                                      gridTemplateColumns: "1fr 1fr auto auto",
                                      gap: 14,
                                      alignItems: "center",
                                      padding: "10px 0",
                                      borderTop: "1px solid var(--line)",
                                    }}
                                  >
                                    <div>
                                      <div className="strong" style={{ fontSize: 13.5 }}>{p.subject_label}</div>
                                      <div className="small muted" style={{ marginTop: 2 }}>
                                        {p.scanned_questions > 0
                                          ? `Scanned · ${p.scanned_questions} question${p.scanned_questions === 1 ? "" : "s"} read`
                                          : "No file yet"}
                                      </div>
                                    </div>
                                    <div>
                                      <div className="small muted" style={{ marginBottom: 4 }}>
                                        Blueprint coverage · {pct}%
                                      </div>
                                      <AnimatedBar value={pct} accent={pct === 100 ? "var(--brand-green)" : "var(--brand-teal)"} height={7} />
                                    </div>
                                    <span className={`tag ${st.cls}`}>{st.label}</span>
                                    <button className="btn btn--sm" onClick={() => void scan.openPaper(p)}>
                                      {p.stage === "empty" ? (
                                        <>
                                          <Upload size={13} /> Upload
                                        </>
                                      ) : (
                                        <>
                                          <ClipboardList size={13} /> View mapping
                                        </>
                                      )}
                                    </button>
                                  </div>
                                );
                              })
                            )}
                          </div>
                        )}
                      </div>
                    </StaggerItem>
                  );
                })}

                {!examsLoading && tests.length === 0 && (
                  <p className="small muted">No test has been scheduled yet. Use "Create test" to add one.</p>
                )}
              </Stagger>

              <Reveal delay={0.1}>
                <div className="section" style={{ marginTop: 22 }}>
                  <div className="section__head">
                    <h2 className="section-q">Standalone papers</h2>
                  </div>
                  <div className="card">
                    <div className="card__body" style={{ display: "grid", gap: 12 }}>
                      <div className="filterbar">
                        <div className="filter">
                          <label htmlFor="new-subject">Subject</label>
                          <select id="new-subject" className="select" value={scan.subject} onChange={(e) => scan.setSubject(e.target.value)}>
                            {scan.subjects.map((s) => (
                              <option key={s.subject_code} value={s.subject_code}>
                                {s.label}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="field">
                          <label htmlFor="new-title">Title</label>
                          <input id="new-title" className="input" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: 8 }}>
                        <button
                          className="btn btn--primary"
                          onClick={() => {
                            scan.setTitle(newTitle || "Cycle Test I");
                            scan.fileInput.current?.click();
                          }}
                        >
                          <Upload size={14} /> Upload paper file
                        </button>
                        <button
                          className="btn"
                          onClick={() => {
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
                      {scan.showCamera && (
                        <FilePickButtons
                          accept="image/*"
                          fileLabel="Choose photo"
                          onPick={(file) => {
                            scan.setShowCamera(false);
                            void scan.onFiles([file]);
                          }}
                        />
                      )}
                    </div>
                  </div>

                  {standalonePapers.length > 0 && (
                    <div style={{ display: "grid", gap: 14, marginTop: 14 }}>
                      {standalonePapers.map((p) => (
                        <div className="card" key={p.id}>
                          <button
                            onClick={() => scan.openPaper(p)}
                            style={{ width: "100%", textAlign: "left", background: "none", border: "none", padding: 0, cursor: "pointer" }}
                          >
                            <div className="card__head">
                              <div>
                                <div className="strong" style={{ fontSize: 15 }}>
                                  {p.title}
                                </div>
                                <div className="small muted" style={{ marginTop: 2 }}>
                                  {p.subject_label} · {p.questions} question{p.questions === 1 ? "" : "s"} · {p.mapped_questions} mapped ·{" "}
                                  {p.students_with_marks} student{p.students_with_marks === 1 ? "" : "s"} marked
                                </div>
                              </div>
                              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                <span className={`tag ${p.stage === "mapped" ? "tag--green" : p.stage === "confirmed" ? "tag--gold" : ""}`}>{p.stage}</span>
                                <ChevronDown size={16} className="muted" />
                              </div>
                            </div>
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </Reveal>
            </>
          ) : (
            <div className="card">
              <div className="card__head">
                <div>
                  <div className="strong" style={{ fontSize: 15 }}>
                    {scan.title}
                  </div>
                  <div className="small muted" style={{ marginTop: 2 }}>
                    {scan.subject} · {scan.stage}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn btn--sm" onClick={() => scan.onRename()}>
                    Rename
                  </button>
                  <button className="btn btn--sm" onClick={() => scan.onDelete()}>
                    <Trash2 size={13} /> Delete
                  </button>
                  <button
                    className="btn btn--sm"
                    onClick={() => scan.loadPapers().then(() => scan.setError(null))}
                  >
                    Back to list
                  </button>
                </div>
              </div>
              <div className="card__body" style={{ display: "grid", gap: 14 }}>
                {scan.busy && (
                  <div className="small muted" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Loader2 size={14} className="spin" /> {scan.busy}
                  </div>
                )}
                {!scan.scan && !scan.documentId && (
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="btn btn--primary" onClick={() => scan.fileInput.current?.click()}>
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
                {scan.documentId && !scan.confirmed && (
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <input
                      className="input"
                      style={{ maxWidth: 220 }}
                      placeholder="Your name"
                      value={scan.confirmedBy}
                      onChange={(e) => scan.setConfirmedBy(e.target.value)}
                    />
                    <button className="btn btn--primary btn--sm" onClick={() => scan.onConfirm()}>
                      <CheckCircle2 size={13} /> Confirm reading &amp; map
                    </button>
                  </div>
                )}
                {scan.mapped && scan.mapped.blocked === 0 && !scan.placed && !scan.alreadyClassified && (
                  <button className="btn btn--primary btn--sm" onClick={() => scan.onClassify()}>
                    <Sparkles size={13} /> Read &amp; classify every question
                  </button>
                )}
                {(scan.placed || scan.alreadyClassified) && (
                  <div className="tag tag--green" style={{ width: "fit-content" }}>
                    <CheckCircle2 size={12} /> Classified
                  </div>
                )}
              </div>
            </div>
          )}

          <p className="small muted" style={{ marginTop: 14 }}>
            Real scan, mapping and classification against the backend -- nothing here is simulated.
          </p>
        </div>
      ) : (
        <div style={{ marginTop: 18 }}>
          <div className="filterbar">
            <div className="filter">
              <label htmlFor="marks-paper">Assessment</label>
              <select id="marks-paper" className="select" value={grid.paperId} onChange={(e) => grid.pickPaper(e.target.value)}>
                <option value="">Choose a paper…</option>
                {grid.ready.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title} · {p.subject_label}
                  </option>
                ))}
              </select>
            </div>
            <div className="filter">
              <label htmlFor="marks-section">Section</label>
              <select id="marks-section" className="select" value={grid.sectionId} onChange={(e) => grid.pickSection(e.target.value)}>
                <option value="">Choose a class…</option>
                {grid.sections.map((s) => (
                  <option key={s.section_id} value={s.section_id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {grid.paperId && grid.sectionId && (
            notReady.has(marksKey) ? (
              <MarksEntryGrid
                key={marksKey}
                subject={grid.ready.find((p) => p.id === grid.paperId)?.subject_code ?? ""}
                section={grid.sectionId}
                paperId={grid.paperId}
              />
            ) : (
              <ConfirmedMarksGrid
                key={marksKey}
                section={grid.sectionId}
                assessmentId={grid.paperId}
                onNotReady={() => setNotReady((prev) => new Set(prev).add(marksKey))}
              />
            )
          )}
        </div>
      )}

      {showCreate && (
        <div className="modal-backdrop" onClick={() => !creating && setShowCreate(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal__head">
              <div className="strong">Create test</div>
              <button className="btn btn--sm" onClick={() => setShowCreate(false)} disabled={creating}>
                Close
              </button>
            </div>
            <form onSubmit={createTest}>
              <div className="modal__body">
                <div className="field">
                  <label htmlFor="test-name">Test name</label>
                  <input
                    id="test-name"
                    className="input"
                    value={examName}
                    onChange={(e) => setExamName(e.target.value)}
                    placeholder="e.g. Unit Test 2"
                    maxLength={200}
                  />
                </div>
                <div className="field">
                  <label htmlFor="test-date">Date</label>
                  <input id="test-date" className="input" type="date" value={examDate} onChange={(e) => setExamDate(e.target.value)} />
                </div>
                <div>
                  <label className="small muted" style={{ display: "block", marginBottom: 8 }}>
                    Subjects
                  </label>
                  <div className="chipset">
                    {scan.subjects.map((s) => (
                      <button
                        type="button"
                        key={s.subject_code}
                        className={`chip ${pickedSubjects.has(s.subject_code) ? "chip--on" : ""}`}
                        onClick={() => toggleSubject(s.subject_code)}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </div>
                {createError && <p className="small" style={{ color: "var(--danger, #b91c1c)", margin: 0 }}>{createError}</p>}
              </div>
              <div className="modal__foot">
                <button type="button" className="btn" onClick={() => setShowCreate(false)} disabled={creating}>
                  Cancel
                </button>
                <button type="submit" className="btn btn--primary" disabled={creating}>
                  {creating ? "Creating…" : "Create test"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
