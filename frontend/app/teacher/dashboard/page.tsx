"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties, type FormEvent } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Calendar,
  Camera,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Loader2,
  Plus,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Trash2,
  Upload,
  Users,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import {
  api,
  ApiError,
  AcademicStatus,
  AcademicTestRow,
  ClassStudentRow,
  CohortReport,
  ConductedExam,
  ExamsOverview,
  PaperSummary,
  ScheduledExam,
  TeacherExamRow,
} from "@/lib/api";
import { usePaperScan } from "@/lib/usePaperScan";
import { useGridSheet } from "@/lib/useGridSheet";
import { FilePickButtons } from "@/components/FilePickButtons";
import { usePageHeader } from "@/lib/pageHeader";
import { MarksEntryGrid } from "@/components/MarksEntryGrid";
import { ConfirmedMarksGrid } from "@/components/ConfirmedMarksGrid";
import { SubjectRoster } from "@/components/SubjectRoster";
import { AttentionPill } from "@/components/Status";
import { EvidenceState } from "@/components/EvidenceState";
import { LoadingScreen } from "@/components/Shell";
import { DeltaCell } from "@/components/StudentRosterTable";
import { STATUS_LABEL, STATUS_PILL_KEY } from "@/lib/statusLabels";
import { AnimatedBar, Reveal, Stagger, StaggerItem } from "@/components/motion";
import { getApiKey } from "@/lib/session";

/** The one common teacher dashboard, every teacher key lands on -- exam-cell or a plain
 * subject/class teacher alike. Question papers and Enter marks are real end to end for
 * both: the exam cell sees every subject (GET /admin/exams, api.teacherPapers already
 * returns every paper for it); a plain teacher sees only papers/exams touching a subject
 * she actually holds (GET /admin/teacher/exams, the same teacher_subject_codes scoping
 * api.teacherPapers already used). Scheduling a brand-new, multi-subject exam day stays
 * exam-cell/principal-only (require_exam_write_scope) -- that action is cross-subject by
 * nature, so the "Create test" button below only ever appears for the exam cell; a plain
 * teacher instead uploads a standalone paper for her own subject(s), same as before.
 *
 * Insights (KPI tiles, cohort findings, SubjectRoster) and the class-teacher homeroom
 * view (KPIs/risk badge/roster/"since last test") are folded in here too, as two more
 * tabs that only appear for a teacher who actually holds that kind of assignment -- real
 * data, reusing the same components/hooks the old per-subject/per-class pages used. */
export default function TeacherDashboardPage() {
  usePageHeader({ title: "Teacher Dashboard" });
  const { user } = useAuth();
  const examCell = user?.role === "teacher" && user.examsOnly;

  const subjectAssignments = useMemo(
    () => (user?.role === "teacher" ? user.assignments.filter((a) => a.type === "subject" && a.subject_code) : []),
    [user],
  );
  const classAssignments = useMemo(
    () => (user?.role === "teacher" ? user.assignments.filter((a) => a.type === "class") : []),
    [user],
  );
  // Real assignment-held subject codes, for narrowing the paper-authoring subject picker
  // client-side (the backend already enforces this on every write; this is just so a
  // plain teacher is never even offered a subject she cannot save a paper for).
  const heldSubjectCodes = useMemo(
    () => new Set(subjectAssignments.map((a) => a.subject_code as string)),
    [subjectAssignments],
  );

  type MainTab = "papers" | "marks" | "insights" | "myclass";
  const [tab, setTab] = useState<MainTab>("papers");

  return (
    <>
      <p className="page-sub" style={{ marginTop: 0 }}>
        {examCell ? "Every subject, question papers and marks." : "Your subjects and classes, real end to end."}
      </p>

      <div className="tabs" role="tablist" style={{ marginTop: 18, flexWrap: "wrap" }}>
        <button role="tab" aria-selected={tab === "papers"} className={`tab ${tab === "papers" ? "tab--active" : ""}`} onClick={() => setTab("papers")}>
          Question papers
        </button>
        <button role="tab" aria-selected={tab === "marks"} className={`tab ${tab === "marks" ? "tab--active" : ""}`} onClick={() => setTab("marks")}>
          Enter marks
        </button>
        {subjectAssignments.length > 0 && (
          <button role="tab" aria-selected={tab === "insights"} className={`tab ${tab === "insights" ? "tab--active" : ""}`} onClick={() => setTab("insights")}>
            Insights
          </button>
        )}
        {classAssignments.length > 0 && (
          <button role="tab" aria-selected={tab === "myclass"} className={`tab ${tab === "myclass" ? "tab--active" : ""}`} onClick={() => setTab("myclass")}>
            My class
          </button>
        )}
      </div>

      <div style={{ marginTop: 18 }}>
        {tab === "papers" && <PapersTab examCell={!!examCell} heldSubjectCodes={heldSubjectCodes} />}
        {tab === "marks" && <MarksTab />}
        {tab === "insights" && <InsightsTab assignments={subjectAssignments} />}
        {tab === "myclass" && <MyClassTab assignments={classAssignments} />}
      </div>
    </>
  );
}

// =====================================================================================
// Question papers
// =====================================================================================

type TestRow = { id: string; name: string; date: string | null; status: "Analysed" | "Awaiting marks" | "Scheduled" };

function PapersTab({ examCell, heldSubjectCodes }: { examCell: boolean; heldSubjectCodes: Set<string> }) {
  const scan = usePaperScan({
    listPapers: (key) => api.teacherPapers(key),
    listSubjects: (key) => api.subjects(key).then((r) => r.subjects),
  });

  const [newTitle, setNewTitle] = useState("Cycle Test I");

  const [tests, setTests] = useState<TestRow[]>([]);
  const [examsLoading, setExamsLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const loadExams = useCallback(async () => {
    const key = getApiKey();
    if (!key) return;
    try {
      if (examCell) {
        const exams: ExamsOverview = await api.exams(key);
        const conducted: TestRow[] = exams.conducted
          .filter((c): c is ConductedExam & { kind: "exam" } => c.kind === "exam")
          .map((c) => ({ id: c.id, name: c.name, date: c.date, status: "Analysed" }));
        const awaiting: TestRow[] = exams.awaiting_marks.map((e: ScheduledExam) => ({
          id: e.id, name: e.name, date: e.scheduled_date, status: "Awaiting marks",
        }));
        const upcoming: TestRow[] = exams.upcoming.map((e: ScheduledExam) => ({
          id: e.id, name: e.name, date: e.scheduled_date, status: "Scheduled",
        }));
        setTests([...conducted, ...awaiting, ...upcoming].sort((a, b) => (b.date ?? "").localeCompare(a.date ?? "")));
      } else {
        const { exams }: { exams: TeacherExamRow[] } = await api.teacherExams(key);
        setTests(exams.map((e) => ({ id: e.id, name: e.name, date: e.scheduled_date, status: e.status })));
      }
    } catch {
      /* the flat papers list below still works without the test grouping */
    } finally {
      setExamsLoading(false);
    }
  }, [examCell]);

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

  // A plain teacher's own held subjects only -- the exam cell still sees every subject
  // this deployment carries, exactly as before.
  const pickableSubjects = examCell ? scan.subjects : scan.subjects.filter((s) => heldSubjectCodes.has(s.subject_code));

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

  function statusTag(p: PaperSummary): { label: string; cls: string } {
    if (p.stage === "mapped") return { label: "Mapped", cls: "tag--green" };
    if (p.stage === "confirmed" || p.stage === "scanned") return { label: "Needs mapping", cls: "tag--gold" };
    return { label: "Not uploaded", cls: "" };
  }
  function coveragePct(p: PaperSummary): number {
    return p.questions > 0 ? Math.round((p.mapped_questions / p.questions) * 100) : 0;
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
        {!scan.assessmentId && examCell && (
          <button className="btn btn--primary" onClick={() => setShowCreate(true)}>
            <Plus size={14} /> Create test
          </button>
        )}
      </div>

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
              <p className="small muted">
                {examCell ? 'No test has been scheduled yet. Use "Create test" to add one.' : "No test day has a paper of yours attached yet."}
              </p>
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
                        {pickableSubjects.map((s) => (
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
                  {pickableSubjects.length === 0 ? (
                    <p className="small muted">You have no subject assignment to author a paper for.</p>
                  ) : (
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
                  )}
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
              <button className="btn btn--sm" onClick={() => scan.loadPapers().then(() => scan.setError(null))}>
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
    </div>
  );
}

// =====================================================================================
// Enter marks
// =====================================================================================

function MarksTab() {
  const grid = useGridSheet({ role: "teacher" });
  const [notReady, setNotReady] = useState<Set<string>>(new Set());
  const marksKey = `${grid.paperId}:${grid.sectionId}`;

  return (
    <div>
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
  );
}

// =====================================================================================
// Insights (folded in from the old per-subject/per-section page)
// =====================================================================================

function InsightsTab({ assignments }: { assignments: { subject_code?: string | null; subject_label?: string | null; section_id: string; section_label?: string | null }[] }) {
  const combos = useMemo(
    () =>
      assignments.map((a) => ({
        key: `${a.subject_code}::${a.section_id}`,
        subject: a.subject_code as string,
        section: a.section_id,
        label: `${a.subject_label ?? a.subject_code} · ${a.section_label ?? a.section_id}`,
      })),
    [assignments],
  );
  const [comboKey, setComboKey] = useState(combos[0]?.key ?? "");
  useEffect(() => {
    if (!combos.some((c) => c.key === comboKey) && combos[0]) setComboKey(combos[0].key);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [combos.map((c) => c.key).join("|")]);
  const active = combos.find((c) => c.key === comboKey) ?? combos[0];

  const [students, setStudents] = useState<ClassStudentRow[] | null>(null);
  const [tests, setTests] = useState<AcademicTestRow[]>([]);
  const [cohort, setCohort] = useState<CohortReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sectionLabel, setSectionLabel] = useState(active?.section ?? "");

  useEffect(() => {
    const key = getApiKey();
    if (!key || !active) return;
    setStudents(null);
    api
      .teacherAcademicsTests(key)
      .then((r) => setTests(r.tests.filter((t) => t.subject_code === active.subject)))
      .catch(() => {
        /* the test list only feeds the findings panel -- the roster still works */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.key]);

  const latestTest = tests[tests.length - 1];

  useEffect(() => {
    const key = getApiKey();
    if (!key || !active) return;
    api
      .teacherAcademicsStudents(key, active.section, { subjectCode: active.subject, assessmentId: latestTest?.assessment_id })
      .then((r) => {
        setStudents(r.students);
        setSectionLabel(r.section.label);
      })
      .catch(() => setError("Could not load this class's marks."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.key, latestTest?.assessment_id]);

  useEffect(() => {
    const key = getApiKey();
    if (!key || !active || !latestTest) return;
    api
      .teacherCohortReport(key, latestTest.assessment_id, active.section)
      .then(setCohort)
      .catch(() => {
        /* cohort report is best-effort -- the students table above still works without it */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.key, latestTest?.assessment_id]);

  if (!active) return <EvidenceState kind="early">No subject assignments yet.</EvidenceState>;
  if (error) return <EvidenceState kind="early">{error}</EvidenceState>;

  const subjectLabel = tests.find((t) => t.subject_code === active.subject)?.label ?? active.subject;

  return (
    <div>
      {combos.length > 1 && (
        <div className="field" style={{ maxWidth: 320, marginBottom: 14 }}>
          <label htmlFor="insights-combo">Subject · section</label>
          <select id="insights-combo" className="select" value={comboKey} onChange={(e) => setComboKey(e.target.value)}>
            {combos.map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {!students ? (
        <LoadingScreen label="Loading this subject…" />
      ) : (
        (() => {
          const marked = students.filter((s) => s.avg_score_pct != null);
          const avg = marked.length ? Math.round(marked.reduce((sum, s) => sum + (s.avg_score_pct ?? 0), 0) / marked.length) : null;
          const atExpected = students.filter((s) => s.status === "on_track").length;
          return (
            <>
              <p className="page-sub" style={{ marginTop: 0 }}>
                {latestTest ? latestTest.title : "No graded test yet"} ·{" "}
                {cohort?.top_losses[0] ? `top gap: ${cohort.top_losses[0].label}` : "no gap localized yet"}
              </p>
              <div className="grid grid--3" style={{ marginTop: 12 }}>
                <div className="kpi" style={{ "--accent": "var(--brand-blue)" } as CSSProperties}>
                  <span className="kpi__icon"><Users size={22} /></span>
                  <div className="kpi__text">
                    <span className="kpi__label">Students</span>
                    <span className="kpi__value" style={{ fontSize: 20 }}>{students.length}</span>
                    <span className="kpi__sub">In {sectionLabel}</span>
                  </div>
                </div>
                <div className="kpi" style={{ "--accent": "var(--brand-teal)" } as CSSProperties}>
                  <span className="kpi__icon"><ShieldCheck size={22} /></span>
                  <div className="kpi__text">
                    <span className="kpi__label">Avg attainment</span>
                    <span className="kpi__value" style={{ fontSize: 20 }}>
                      {avg != null ? `${avg}%` : "—"}
                      {latestTest?.delta_pct !== undefined && latestTest?.delta_pct !== null && <DeltaCell delta={Math.round(latestTest.delta_pct)} />}
                    </span>
                    <span className="kpi__sub">{latestTest ? `As of ${latestTest.title}` : "No graded test yet"}</span>
                  </div>
                </div>
                <div className="kpi" style={{ "--accent": "var(--brand-gold)" } as CSSProperties}>
                  <span className="kpi__icon"><Target size={22} /></span>
                  <div className="kpi__text">
                    <span className="kpi__label">At expected level</span>
                    <span className="kpi__value" style={{ fontSize: 20 }}>
                      {atExpected} <span className="small muted" style={{ fontWeight: 400 }}>of {students.length}</span>
                    </span>
                    <span className="kpi__sub">On Track status</span>
                  </div>
                </div>
              </div>

              <section className="section">
                <div className="section__head">
                  <h2 className="section-q">Findings in {subjectLabel}</h2>
                </div>
                {cohort && cohort.top_losses.length ? (
                  <div className="grid grid--2">
                    {cohort.top_losses.map((f) => (
                      <div className="finding finding--compact" key={f.concept_family}>
                        <header className="finding__head">
                          <div>
                            <div className="finding__subject">{subjectLabel}</div>
                            <h3 className="finding__title">{f.label}</h3>
                          </div>
                        </header>
                        <div className="finding__metrics">
                          <div className="metric">
                            <div className="metric__label">Students affected</div>
                            <div className="metric__value">{f.students_affected}</div>
                          </div>
                          <div className="metric">
                            <div className="metric__label">Avg marks lost</div>
                            <div className="metric__value">{f.avg_marks_lost.toFixed(1)}</div>
                          </div>
                        </div>
                        <div className="finding__status">
                          <span className="tag">{f.confidence}</span>
                          {f.board_urgency && <span className="tag tag--gold">{f.board_urgency}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EvidenceState kind="early">No findings in {subjectLabel} rise above the evidence threshold from a single test.</EvidenceState>
                )}
              </section>

              <section className="section">
                <div className="section__head">
                  <h2 className="section-q">
                    {sectionLabel} students in {subjectLabel}
                  </h2>
                </div>
                <SubjectRoster subject={subjectLabel} section={sectionLabel} students={students} />
              </section>
            </>
          );
        })()
      )}
    </div>
  );
}

// =====================================================================================
// My class (folded in from the old class-teacher homeroom page)
// =====================================================================================

function MyClassTab({ assignments }: { assignments: { section_id: string; section_label?: string | null }[] }) {
  const [sectionId, setSectionId] = useState(assignments[0]?.section_id ?? "");
  useEffect(() => {
    if (!assignments.some((a) => a.section_id === sectionId) && assignments[0]) setSectionId(assignments[0].section_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignments.map((a) => a.section_id).join("|")]);

  return (
    <div>
      {assignments.length > 1 && (
        <div className="field" style={{ maxWidth: 280, marginBottom: 14 }}>
          <label htmlFor="myclass-section">Class</label>
          <select id="myclass-section" className="select" value={sectionId} onChange={(e) => setSectionId(e.target.value)}>
            {assignments.map((a) => (
              <option key={a.section_id} value={a.section_id}>
                {a.section_label ?? a.section_id}
              </option>
            ))}
          </select>
        </div>
      )}
      {sectionId && <MyClassBody sectionId={sectionId} />}
    </div>
  );
}

function MyClassBody({ sectionId }: { sectionId: string }) {
  const { user } = useAuth();
  const [bySubject, setBySubject] = useState<Record<string, ClassStudentRow[]> | null>(null);
  const [sectionLabel, setSectionLabel] = useState(sectionId);
  const [error, setError] = useState<string | null>(null);
  const [tests, setTests] = useState<AcademicTestRow[]>([]);
  const [cohort, setCohort] = useState<CohortReport | null>(null);
  const [previousTitle, setPreviousTitle] = useState<string | null>(null);
  const [movementRows, setMovementRows] = useState<ClassStudentRow[] | null>(null);

  const mySubjects =
    user?.role === "teacher"
      ? [...new Set(user.assignments.filter((a) => a.type === "subject" && a.section_id === sectionId && a.subject_code).map((a) => a.subject_code as string))]
      : [];

  useEffect(() => {
    const key = getApiKey();
    setBySubject(null);
    if (!key || mySubjects.length === 0) return;
    let cancelled = false;
    Promise.all(mySubjects.map((s) => api.teacherAcademicsStudents(key, sectionId, { subjectCode: s })))
      .then((results) => {
        if (cancelled) return;
        const map: Record<string, ClassStudentRow[]> = {};
        results.forEach((r, i) => {
          map[mySubjects[i]] = r.students;
          setSectionLabel(r.section.label);
        });
        setBySubject(map);
      })
      .catch(() => !cancelled && setError("Could not load this class's marks."));
    api
      .teacherAcademicsTests(key)
      .then((r) => !cancelled && setTests(r.tests.filter((t) => mySubjects.includes(t.subject_code))))
      .catch(() => {
        /* movement/gap panels are best-effort -- the roster above still works */
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionId, mySubjects.join("|")]);

  const primarySubject = mySubjects[0];
  const latestTest = [...tests].filter((t) => t.subject_code === primarySubject).pop();
  const subjectLabel = (code: string): string => tests.find((t) => t.subject_code === code)?.label ?? code;

  useEffect(() => {
    const key = getApiKey();
    if (!key || !latestTest) return;
    let cancelled = false;
    api
      .teacherCohortReport(key, latestTest.assessment_id, sectionId)
      .then((r) => !cancelled && setCohort(r))
      .catch(() => !cancelled && setCohort(null));
    api
      .teacherAcademicsStudents(key, sectionId, { subjectCode: primarySubject, assessmentId: latestTest.assessment_id })
      .then((r) => {
        if (cancelled) return;
        setMovementRows(r.students);
        setPreviousTitle(r.previous_test?.title ?? null);
      })
      .catch(() => {
        /* the "since last test" panel is best-effort */
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestTest?.assessment_id, sectionId, primarySubject]);

  if (mySubjects.length === 0) {
    return (
      <EvidenceState kind="early">
        You are the class teacher for {sectionLabel}, but aren&apos;t assigned to teach any subject there, nothing subject-specific to show.
      </EvidenceState>
    );
  }
  if (error) return <EvidenceState kind="early">{error}</EvidenceState>;
  if (!bySubject) return <LoadingScreen label="Loading the class…" />;

  const studentIds = [...new Set(Object.values(bySubject).flatMap((rows) => rows.map((r) => r.student_id)))];
  const rowFor = (studentId: string, subject: string) => bySubject[subject]?.find((r) => r.student_id === studentId);
  const overallFor = (studentId: string) => {
    const scores = mySubjects.map((s) => rowFor(studentId, s)?.avg_score_pct).filter((v): v is number => v != null);
    return scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null;
  };
  const attentionOf = (studentId: string): AcademicStatus => {
    const statuses = mySubjects.map((s) => rowFor(studentId, s)?.status).filter((v): v is NonNullable<typeof v> => !!v);
    if (statuses.some((s) => s === "requires_review")) return "requires_review";
    if (statuses.some((s) => s === "needs_attention")) return "needs_attention";
    if (statuses.every((s) => s === "not_assessed")) return "not_assessed";
    return "on_track";
  };
  const roster = studentIds.map((id) => {
    const first = mySubjects.map((s) => rowFor(id, s)).find((r) => r);
    return { id, name: first?.name ?? id, rollNo: first?.roll_no ?? "" };
  });
  const overallScores = roster.map((s) => overallFor(s.id)).filter((v): v is number => v != null);
  const overallAttainment = overallScores.length ? Math.round(overallScores.reduce((a, b) => a + b, 0) / overallScores.length) : null;

  const attentionCounts = { on_track: 0, needs_attention: 0, requires_review: 0, not_assessed: 0 } as Record<string, number>;
  for (const s of roster) attentionCounts[attentionOf(s.id)] += 1;
  const atRisk = attentionCounts.needs_attention + attentionCounts.requires_review;
  const riskBadge: { label: string; tone: string } =
    atRisk === 0
      ? { label: "On Track", tone: "var(--brand-teal)" }
      : atRisk <= Math.max(2, Math.round(roster.length * 0.15))
        ? { label: "Watch", tone: "#c2a02a" }
        : { label: "Needs Attention", tone: "#c2410c" };

  const topGap = cohort?.top_losses[0] ?? null;

  const showMovement = !!(latestTest && latestTest.delta_pct !== null && latestTest.avg_score_pct !== null && previousTitle && movementRows);
  const previousPct = showMovement ? Math.round((latestTest!.avg_score_pct as number) - (latestTest!.delta_pct as number)) : null;
  const latestPct = showMovement ? Math.round(latestTest!.avg_score_pct as number) : null;
  const improved = movementRows?.filter((r) => r.delta_pct !== null && r.delta_pct > 0).length ?? 0;
  const declined = movementRows?.filter((r) => r.delta_pct !== null && r.delta_pct < 0).length ?? 0;

  const kpis: { label: string; icon: React.ReactNode; accent: string; value: React.ReactNode; sub: string }[] = [
    {
      label: "Students",
      icon: <Users size={22} />,
      accent: "var(--brand-blue)",
      value: roster.length,
      sub: `In ${sectionLabel}`,
    },
    {
      label: mySubjects.length > 1 ? "Your subjects, attainment" : `${subjectLabel(mySubjects[0])} attainment`,
      icon: <ShieldCheck size={22} />,
      accent: "var(--brand-teal)",
      value: (
        <>
          {overallAttainment != null ? `${overallAttainment}%` : "—"}
          {latestTest && mySubjects.length === 1 && latestTest.delta_pct !== null && <DeltaCell delta={Math.round(latestTest.delta_pct)} />}
        </>
      ),
      sub: latestTest ? `As of ${latestTest.title}` : "No graded test yet",
    },
    {
      label: `Top gap in ${primarySubject ? subjectLabel(primarySubject) : "your subject"}`,
      icon: <TrendingDown size={22} />,
      accent: "#c2410c",
      value: topGap ? topGap.label : "—",
      sub: topGap ? `${topGap.students_affected} students affected · ${topGap.avg_marks_lost.toFixed(1)} marks lost on avg` : "No gap localized yet",
    },
  ];

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <p className="page-sub" style={{ margin: 0 }}>
          Class view · your subject{mySubjects.length > 1 ? "s" : ""}: {mySubjects.map(subjectLabel).join(", ")}
        </p>
        <span className="chip chip--on" style={{ "--accent": riskBadge.tone } as CSSProperties}>
          {riskBadge.label}
        </span>
      </div>

      <div className="grid grid--3" style={{ marginTop: 18 }}>
        {kpis.map((t) => (
          <div className="kpi" key={t.label} style={{ "--accent": t.accent } as CSSProperties}>
            <span className="kpi__icon">{t.icon}</span>
            <div className="kpi__text">
              <span className="kpi__label">{t.label}</span>
              <span className="kpi__value" style={{ fontSize: 20 }}>{t.value}</span>
              <span className="kpi__sub">{t.sub}</span>
            </div>
          </div>
        ))}
      </div>

      <section className="section">
        <div className="section__head">
          <h2 className="section-q">Students in {sectionLabel}</h2>
          <span className="small muted">
            All {roster.length} students · {mySubjects.map(subjectLabel).join(", ")} only
          </span>
        </div>
        <div className="card">
          <div className="table-wrap table-wrap--scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Roll</th>
                  <th>Student</th>
                  {mySubjects.map((s) => (
                    <th key={s} className="num">
                      {subjectLabel(s)}
                    </th>
                  ))}
                  <th>Top improvement area</th>
                  <th>Attention</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {roster.map((s) => {
                  const blocker = mySubjects.map((sub) => rowFor(s.id, sub)?.top_improvement_area).find((b) => b);
                  return (
                    <tr key={s.id}>
                      <td className="muted">{s.rollNo}</td>
                      <td className="strong">{s.name}</td>
                      {mySubjects.map((sub) => {
                        const pct = rowFor(s.id, sub)?.avg_score_pct;
                        return (
                          <td key={sub} className="num">
                            {pct != null ? Math.round(pct) : "—"}
                          </td>
                        );
                      })}
                      <td>{blocker ? `${blocker.chapter} (${Math.round(blocker.rate)}%)` : "—"}</td>
                      <td>
                        <AttentionPill level={STATUS_PILL_KEY[attentionOf(s.id)]} label={STATUS_LABEL[attentionOf(s.id)]} />
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <Link href={`/teacher/student/${s.id}`} className="btn btn--sm">
                          Report <ArrowRight size={12} />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {showMovement && (
        <section className="section">
          <div className="section__head">
            <h2 className="section-q">
              Since {previousTitle} <span className="small muted" style={{ fontWeight: 400 }}>({primarySubject ? subjectLabel(primarySubject) : ""})</span>
            </h2>
          </div>
          <div className="grid grid--4" style={{ gap: 12 }}>
            <div className="stat">
              <div className="stat__label">Previous test</div>
              <div className="stat__value">{previousPct}%</div>
            </div>
            <div className="stat">
              <div className="stat__label">Latest test</div>
              <div className="stat__value">{latestPct}%</div>
            </div>
            <div className="stat">
              <div className="stat__label">Improved</div>
              <div className="stat__value" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <TrendingUp size={16} color="var(--brand-teal)" /> {improved}
              </div>
            </div>
            <div className="stat">
              <div className="stat__label">Declined</div>
              <div className="stat__value" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <TrendingDown size={16} color="#c2410c" /> {declined}
              </div>
            </div>
          </div>
        </section>
      )}
    </>
  );
}
