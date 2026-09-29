"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties, type FormEvent } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  Calendar,
  Camera,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Eye,
  FileCheck2,
  Loader2,
  Pencil,
  Plus,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Trash2,
  Upload,
  Users,
  X,
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
  ReviewChapterOption,
  ReviewQuestion,
  ScheduledExam,
  StagedQuestion,
} from "@/lib/api";
import { Stat } from "@/components/Stat";
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
 * subject/class teacher alike. Question papers and Enter marks, including "Create test",
 * are real end to end for both, with no special "exam cell" gate on the flow itself:
 * every teacher key sees and can attach/upload/view every subject's papers and exams
 * (GET /admin/exams, api.teacherPapers, POST /admin/exams/{id}/papers all now treat
 * every teacher key exactly like the exam cell always was). A subject assignment is no
 * longer required for any of this -- it still governs marks entry and the
 * Insights/My-class tabs below, a different, real access boundary this does not touch.
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
        {tab === "papers" && <PapersTab examCell={!!examCell} />}
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

/** The three cognitive tiers a classified question is filed under -- the board's own
 * words, which is what the backend accepts back (see TIER_ALIASES). */
const TIERS = ["Remembering & Understanding", "Applying", "Analysing, Evaluating & Creating"];

function PapersTab({ examCell }: { examCell: boolean }) {
  const { user } = useAuth();
  const scan = usePaperScan({
    listPapers: (key) => api.teacherPapers(key),
    listSubjects: (key) => api.subjects(key).then((r) => r.subjects),
  });

  const [newTitle, setNewTitle] = useState("Cycle Test I");

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

  // A needs-review row (the family or chapter the machine settled on, including a real
  // auto-resolved one, is a machine's first answer, never a person's) is editable through
  // the real POST /assessments/{id}/review/{question_id} route -- the same one
  // review_queue's own pending list is read from. Fetched lazily, keyed to address, so
  // opening the edit modal always has the question_id and the real chapter list to pick
  // from (StagedQuestion itself carries no question_id -- only /review's own rows do).
  const [reviewByAddress, setReviewByAddress] = useState<Record<string, ReviewQuestion>>({});
  const [chapterOptions, setChapterOptions] = useState<ReviewChapterOption[]>([]);

  // A case-study/source passage (is_context) carries no marks of its own and is never
  // promoted to a real, gradable Question row -- there is nothing to place, by design
  // (see app.api.marks's context handling). Its real sub-parts (same section+question_no,
  // is_context false) are what actually get chapter/topic/tier. Showing "Not placed" on
  // the passage row itself is not an error report, it is mislabelling a correct state as
  // a failure -- so for display only, roll up whatever its sub-parts actually settled on,
  // never writing this back as a real placement anywhere.
  function contextRollup(q: StagedQuestion) {
    const children = (scan.review?.questions ?? []).filter(
      (r) => !r.is_context && r.section === q.section && r.question_no === q.question_no,
    );
    const chapters = Array.from(new Set(children.map((c) => c.mapped_to?.chapter).filter((v): v is string => !!v)));
    const topics = Array.from(new Set(children.map((c) => c.mapped_to?.topic).filter((v): v is string => !!v)));
    const placed = children.filter((c) => c.mapped_to?.chapter).length;
    return { children, chapters, topics, placed };
  }

  useEffect(() => {
    const key = getApiKey();
    if (!key || !scan.assessmentId || !scan.mapped) return;
    let cancelled = false;
    void api.reviewQueue(key, scan.assessmentId).then((q) => {
      if (cancelled) return;
      setReviewByAddress(Object.fromEntries(q.questions.map((r) => [r.address, r])));
      setChapterOptions(q.chapters);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scan.assessmentId, scan.mapped, scan.placed]);

  const [settling, setSettling] = useState<{ address: string; question_id: string } | null>(null);
  const [settleForm, setSettleForm] = useState({ chapter_code: "", curriculum_section: "", tier: "" });
  const [savingSettle, setSavingSettle] = useState(false);
  const [settleError, setSettleError] = useState<string | null>(null);

  function openSettle(q: StagedQuestion) {
    const pending = reviewByAddress[q.address];
    if (!pending) return;
    setSettling({ address: q.address, question_id: pending.question_id });
    setSettleForm({
      chapter_code: pending.proposed_chapter_code ?? "",
      curriculum_section: pending.curriculum_section ?? "",
      tier: q.mapped_to?.tier_label ?? "",
    });
    setSettleError(null);
  }

  async function saveSettle() {
    const key = getApiKey();
    if (!settling || !key || !scan.assessmentId) return;
    if (!settleForm.chapter_code) {
      setSettleError("Choose a chapter.");
      return;
    }
    setSavingSettle(true);
    setSettleError(null);
    try {
      await api.settleReview(key, scan.assessmentId, settling.question_id, {
        chapter_code: settleForm.chapter_code,
        curriculum_section: settleForm.curriculum_section || null,
        tier: settleForm.tier || null,
        reviewed_by: user?.name || "Teacher",
      });
      setSettling(null);
      await scan.refresh(scan.assessmentId);
      const q = await api.reviewQueue(key, scan.assessmentId);
      setReviewByAddress(Object.fromEntries(q.questions.map((r) => [r.address, r])));
      setChapterOptions(q.chapters);
    } catch (err) {
      setSettleError(scan.explain(err));
    } finally {
      setSavingSettle(false);
    }
  }

  const [tests, setTests] = useState<TestRow[]>([]);
  const [examsLoading, setExamsLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const loadExams = useCallback(async () => {
    const key = getApiKey();
    if (!key) return;
    try {
      // GET /admin/exams is real and scoped for every teacher now: the exam cell sees
      // every subject, a plain teacher only ever sees exams with a paper of her own
      // subject(s) attached (server-side, via require_exam_read_scope/list_exams).
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

  // Paper authoring/upload/status is open to every teacher key for every subject this
  // deployment carries now, exam cell or not -- see require_paper_scope. A subject
  // assignment still governs marks entry and the Insights/My-class tabs, just not this
  // picker.
  const pickableSubjects = scan.subjects;

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
        {!scan.assessmentId && (
          <button
            className="btn btn--primary"
            onClick={() => setShowCreate(true)}
            disabled={pickableSubjects.length === 0}
            title={pickableSubjects.length === 0 ? "This deployment carries no subjects yet." : undefined}
          >
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
                  {/* card--hover's perspective/preserve-3d only applies while collapsed --
                     the header is a single clickable target then, but once expanded this
                     card holds real per-subject action buttons, and that same 3D
                     transform is what silently ate clicks on the Standalone papers form
                     above (see the note there). */}
                  <div className={`card ${open ? "" : "card--hover"}`}>
                    <button
                      type="button"
                      onClick={() => toggle(t.id)}
                      aria-expanded={open}
                      className="card__head"
                      style={{ width: "100%", background: "none", border: 0, textAlign: "left", cursor: "pointer", font: "inherit", color: "inherit" }}
                    >
                      <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                        <motion.span
                          style={{ display: "inline-flex", marginTop: 2 }}
                          animate={{ rotate: open ? 90 : 0 }}
                          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                        >
                          <ChevronRight size={18} />
                        </motion.span>
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
                          <div className="table-wrap">
                            <table className="table table--hover">
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
                                {papers.map((p) => {
                                  const st = statusTag(p);
                                  const pct = coveragePct(p);
                                  return (
                                    <tr key={p.id}>
                                      <td className="strong">{p.subject_label}</td>
                                      <td>
                                        <div className="small muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                          {p.scanned_questions > 0 ? (
                                            <>
                                              <FileCheck2 size={13} />
                                              {p.scanned_questions} question{p.scanned_questions === 1 ? "" : "s"} read
                                            </>
                                          ) : (
                                            <>
                                              <Upload size={13} /> No file yet
                                            </>
                                          )}
                                        </div>
                                      </td>
                                      <td style={{ minWidth: 160 }}>
                                        <div className="small muted" style={{ marginBottom: 4 }}>
                                          {pct}%
                                        </div>
                                        <AnimatedBar value={pct} accent={pct === 100 ? "var(--brand-green)" : "var(--brand-teal)"} height={7} />
                                      </td>
                                      <td>
                                        <span className={`tag ${st.cls}`}>{st.label}</span>
                                      </td>
                                      <td style={{ textAlign: "right" }}>
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
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </StaggerItem>
              );
            })}

            {!examsLoading && tests.length === 0 && (
              <p className="small muted">
                No test has been scheduled yet. Use &quot;Create test&quot; to add one.
              </p>
            )}
          </Stagger>

          <Reveal delay={0.1}>
            <div className="section" style={{ marginTop: 22 }}>
              <div className="section__head">
                <h2 className="section-q">Standalone papers</h2>
              </div>
              {/* Plain .card, deliberately no --hover: this card holds a native <select>
                 and a hidden file input the "Upload paper file" button programmatically
                 clicks -- card--hover's perspective/preserve-3d transform put those
                 interactive children in a 3D rendering context where clicks silently
                 stopped reaching them in the browser (no console error, no dialog). A
                 card whose whole job is to be clicked (the exam-day cards) is fine with
                 it; a card that's mostly a form is not. */}
              <div className="card">
                <div className="card__body" style={{ display: "grid", gap: 14 }}>
                  <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                    <div className="field" style={{ minWidth: 220 }}>
                      <label htmlFor="new-subject">Subject</label>
                      <select id="new-subject" className="select" value={scan.subject} onChange={(e) => scan.setSubject(e.target.value)}>
                        {pickableSubjects.map((s) => (
                          <option key={s.subject_code} value={s.subject_code}>
                            {s.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="field" style={{ minWidth: 220, flex: 1 }}>
                      <label htmlFor="new-title">Title</label>
                      <input id="new-title" className="input" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
                    </div>
                  </div>
                  {pickableSubjects.length === 0 ? (
                    <p className="small muted">This deployment carries no subjects yet.</p>
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
                    <div className="card card--hover" key={p.id}>
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
                <Loader2 size={14} className="spin" /> {scan.busyLabel}
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
            {scan.scan && (
              <div className="grid grid--3">
                <Stat label="Questions read" value={scan.scan.questions} />
                <Stat label="Marks read" value={scan.scan.total_marks} />
                <Stat label="Pages" value={scan.scan.pages} />
              </div>
            )}

            {scan.mapped && (
              <div className="grid grid--3">
                <Stat
                  label="Mapped" value={scan.mapped.mapped}
                  icon={<FileCheck2 size={12} />} tone={scan.mapped.mapped > 0 ? "green" : undefined}
                />
                <Stat
                  label="Blocked" value={scan.mapped.blocked}
                  icon={<ShieldAlert size={12} />} tone={scan.mapped.blocked > 0 ? "risk" : undefined}
                />
                <Stat
                  label="Needs review" value={scan.mapped.needs_review}
                  icon={<Eye size={12} />} tone={scan.mapped.needs_review > 0 ? "gold" : undefined}
                />
              </div>
            )}

            {scan.mapped && scan.mapped.blocked > 0 && !scan.placed && (
              <button className="btn btn--sm" onClick={() => scan.onMap()} disabled={scan.busy != null}>
                Re-run mapping
              </button>
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
                        <th>Topic</th>
                        <th>Tier</th>
                        <th>Needs review</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {scan.rows.map((q) => {
                        // Backend rule (marks.py edit_scanned_question): editing 409s once
                        // the scan is confirmed, and again once a row has already been
                        // mapped (it has moved past staging into a real Question). So the
                        // Edit action only ever appears for a still-staged, unconfirmed row.
                        const canEdit = !scan.confirmed && !q.mapped_to;
                        // needs_review rows only exist after mapping, which is always
                        // after confirm -- gating this action on !scan.confirmed (the
                        // way canEdit is) would mean it could never actually show.
                        const canSettle = !!q.mapped_to?.needs_review && !!reviewByAddress[q.address];
                        const autoResolved = q.mapped_to?.review_reason?.includes("Auto-resolved");
                        const rollup = q.is_context ? contextRollup(q) : null;
                        return (
                          <tr key={q.address}>
                            <td className="strong">
                              {q.section ?? ""}
                              {q.question_no}
                              {q.sub_part ?? ""}
                            </td>
                            <td className="small" style={{ maxWidth: 280 }}>
                              {q.stem_text ?? "—"}
                            </td>
                            <td className="num">{q.max_marks ?? "—"}</td>
                            <td>
                              {rollup ? (
                                rollup.chapters.length === 1 ? (
                                  <span className="small">{rollup.chapters[0]}</span>
                                ) : rollup.chapters.length > 1 ? (
                                  <span className="small">{rollup.chapters.join(" / ")}</span>
                                ) : (
                                  <span className="small muted">
                                    {rollup.children.length === 0
                                      ? "Source passage -- see sub-parts"
                                      : `Source passage -- ${rollup.placed}/${rollup.children.length} sub-parts placed`}
                                  </span>
                                )
                              ) : (
                                q.mapped_to?.chapter ?? <span className="tag tag--risk">{q.blocked_reason ?? "Not placed"}</span>
                              )}
                            </td>
                            <td className="small">
                              {rollup
                                ? rollup.topics.length === 1
                                  ? rollup.topics[0]
                                  : rollup.topics.length > 1
                                    ? rollup.topics.join(" / ")
                                    : "—"
                                : q.mapped_to?.topic ?? "—"}
                            </td>
                            <td className="small">{rollup ? "—" : q.mapped_to?.tier_label ?? "—"}</td>
                            <td>
                              {q.mapped_to?.needs_review ? (
                                <div style={{ display: "grid", gap: 2 }}>
                                  <span className="tag tag--gold" style={{ width: "fit-content" }}>{q.mapped_to.review_reason ?? "Review"}</span>
                                  <span className="small muted">
                                    {autoResolved
                                      ? "Placed automatically from the book -- worth a glance, not necessarily wrong."
                                      : "A family/mapping problem -- fix the concept-family data, or settle it here."}
                                  </span>
                                </div>
                              ) : "—"}
                            </td>
                            <td style={{ textAlign: "right" }}>
                              {canEdit && (
                                <button className="btn btn--sm" onClick={() => openEdit(q)}>
                                  <Pencil size={12} /> Edit
                                </button>
                              )}
                              {canSettle && (
                                <button className="btn btn--sm" onClick={() => openSettle(q)}>
                                  <Pencil size={12} /> Settle
                                </button>
                              )}
                            </td>
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

      <AnimatePresence>
        {settling && (
          <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setSettling(null)}>
            <motion.div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
              <div className="modal__head">
                <h3>Settle {settling.address}</h3>
                <button className="iconbtn" onClick={() => setSettling(null)} aria-label="Close">
                  <X size={16} />
                </button>
              </div>
              <div className="modal__body" style={{ display: "grid", gap: 10 }}>
                {reviewByAddress[settling.address]?.reasoning && (
                  <p className="small muted" style={{ margin: 0 }}>
                    {reviewByAddress[settling.address].reasoning}
                  </p>
                )}
                {settleError && (
                  <div className="evidence evidence--gold">
                    <AlertTriangle size={16} />
                    <div>{settleError}</div>
                  </div>
                )}
                <div className="field">
                  <label htmlFor="settle-chapter">Chapter</label>
                  <select
                    id="settle-chapter"
                    className="select"
                    value={settleForm.chapter_code}
                    onChange={(e) => setSettleForm((f) => ({ ...f, chapter_code: e.target.value }))}
                  >
                    <option value="">Choose a chapter…</option>
                    {chapterOptions.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="settle-section">Section (optional -- e.g. 12.2)</label>
                  <input
                    id="settle-section"
                    className="input"
                    value={settleForm.curriculum_section}
                    onChange={(e) => setSettleForm((f) => ({ ...f, curriculum_section: e.target.value }))}
                  />
                </div>
                <div className="field">
                  <label htmlFor="settle-tier">Tier</label>
                  <select
                    id="settle-tier"
                    className="select"
                    value={settleForm.tier}
                    onChange={(e) => setSettleForm((f) => ({ ...f, tier: e.target.value }))}
                  >
                    <option value="">Not set</option>
                    {TIERS.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="modal__foot" style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                <button className="btn btn--sm" onClick={() => setSettling(null)} disabled={savingSettle}>
                  Cancel
                </button>
                <button className="btn btn--primary btn--sm" onClick={() => void saveSettle()} disabled={savingSettle}>
                  {savingSettle ? <Loader2 size={13} className="spin" /> : <CheckCircle2 size={13} />} Save
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

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
                    Subjects for this test
                  </label>
                  <div className="chipset">
                    {pickableSubjects.map((s) => (
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
