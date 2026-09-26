"use client";

import { useParams } from "next/navigation";
import { useEffect, useState, type CSSProperties } from "react";
import { ShieldCheck, Target, Users } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { api, AcademicTestRow, ClassStudentRow, CohortReport } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { usePageHeader } from "@/lib/pageHeader";
import { EvidenceState } from "@/components/EvidenceState";
import { LoadingScreen } from "@/components/Shell";
import { MarksEntryGrid } from "@/components/MarksEntryGrid";
import { ConfirmedMarksGrid } from "@/components/ConfirmedMarksGrid";
import { QuestionPaperPanel } from "@/components/QuestionPaperPanel";
import { SubjectRoster } from "@/components/SubjectRoster";
import { DeltaCell } from "@/components/StudentRosterTable";

/** §6.3 Subject view, one subject, one section, with real Question Paper and Enter Marks
 * tabs. Insights come from GET /admin/teacher/academics/{section}/students (subject_code
 * scoped) and, when this subject has a graded test, GET /reports/cohort/{id} for the top
 * losses -- the same real aggregation the principal's own findings are built from. */
export default function SubjectView() {
  const params = useParams<{ subject: string; section: string }>();
  const subject = decodeURIComponent(params.subject);
  const section = params.section;
  const [tab, setTab] = useState<"insights" | "paper" | "marks">("insights");
  const { user } = useAuth();
  const [marksTestId, setMarksTestId] = useState("");
  // Once GET .../marks-grid says a picked test is not fully marked yet, remember that
  // (per test id) so this tab falls back to the live upload flow for it rather than
  // re-checking on every render -- and so a different test picked afterwards still
  // gets its own fresh check.
  const [notReadyIds, setNotReadyIds] = useState<Set<string>>(new Set());

  const [students, setStudents] = useState<ClassStudentRow[] | null>(null);
  const [tests, setTests] = useState<AcademicTestRow[]>([]);
  const [cohort, setCohort] = useState<CohortReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const allowed = user?.role === "teacher" && user.assignments.some((a) => a.type === "subject" && a.subject_code === subject && a.section_id === section);

  // AcademicTestRow.label is this subject's real display name (e.g. "Mathematics"),
  // already returned by GET .../teacher/academics/tests -- never the raw subject_code.
  const subjectLabel = tests.find((t) => t.subject_code === subject)?.label ?? subject;
  usePageHeader({ title: `${subjectLabel} · ${section}`, backHref: "/teacher/home" });

  useEffect(() => {
    const key = getApiKey();
    if (!key || !allowed) return;
    api
      .teacherAcademicsTests(key)
      .then((r) => setTests(r.tests.filter((t) => t.subject_code === subject)))
      .catch(() => {
        /* the test list only feeds the findings panel below -- the roster still works */
      });
  }, [section, subject, allowed]);

  const latestTest = tests[tests.length - 1];

  useEffect(() => {
    if (!marksTestId && latestTest) setMarksTestId(latestTest.assessment_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestTest?.assessment_id]);

  useEffect(() => {
    const key = getApiKey();
    if (!key || !allowed) return;
    // Narrowed to the latest test once it is known, so the roster's "vs last" column and
    // delta_pct come from the same real comparison the cohort findings below use --
    // still fetched (without a test) before that resolves, so the roster isn't blocked
    // on the tests call.
    api
      .teacherAcademicsStudents(key, section, { subjectCode: subject, assessmentId: latestTest?.assessment_id })
      .then((r) => setStudents(r.students))
      .catch(() => setError("Could not load this class's marks."));
  }, [section, subject, allowed, latestTest?.assessment_id]);

  useEffect(() => {
    const key = getApiKey();
    if (!key || !allowed || !latestTest) return;
    api
      .teacherCohortReport(key, latestTest.assessment_id, section)
      .then(setCohort)
      .catch(() => {
        /* cohort report is best-effort -- the students table above still works without it */
      });
  }, [latestTest?.assessment_id, section, allowed]);

  if (!allowed) return <EvidenceState kind="cause">You are not assigned to {subjectLabel} for {section}.</EvidenceState>;
  if (error) return <EvidenceState kind="early">{error}</EvidenceState>;
  if (!students) return <LoadingScreen label="Loading this subject…" />;

  const marked = students.filter((s) => s.avg_score_pct != null);
  const avg = marked.length ? Math.round(marked.reduce((sum, s) => sum + (s.avg_score_pct ?? 0), 0) / marked.length) : null;
  const atExpected = students.filter((s) => s.status === "on_track").length;

  return (
    <>
      <p className="page-sub" style={{ marginTop: 0 }}>
        {latestTest ? latestTest.title : "No graded test yet"} ·{" "}
        {cohort?.top_losses[0] ? `top gap: ${cohort.top_losses[0].label}` : "no gap localized yet"}
      </p>

      <div className="tabs" role="tablist" style={{ marginTop: 18 }}>
        <button role="tab" aria-selected={tab === "insights"} className={`tab ${tab === "insights" ? "tab--active" : ""}`} onClick={() => setTab("insights")}>
          Insights
        </button>
        <button role="tab" aria-selected={tab === "paper"} className={`tab ${tab === "paper" ? "tab--active" : ""}`} onClick={() => setTab("paper")}>
          Question paper
        </button>
        <button role="tab" aria-selected={tab === "marks"} className={`tab ${tab === "marks" ? "tab--active" : ""}`} onClick={() => setTab("marks")}>
          Enter marks
        </button>
      </div>

      {tab === "insights" ? (
        <>
          <div className="grid grid--3" style={{ marginTop: 18 }}>
            <div className="kpi" style={{ "--accent": "var(--brand-blue)" } as CSSProperties}>
              <span className="kpi__icon"><Users size={22} /></span>
              <div className="kpi__text">
                <span className="kpi__label">Students</span>
                <span className="kpi__value" style={{ fontSize: 20 }}>{students.length}</span>
                <span className="kpi__sub">In {section}</span>
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
                {section} students in {subjectLabel}
              </h2>
            </div>
            <SubjectRoster subject={subjectLabel} section={section} students={students} />
          </section>
        </>
      ) : tab === "paper" ? (
        <div style={{ marginTop: 18 }}>
          <QuestionPaperPanel subject={subject} section={section} />
        </div>
      ) : (
        <div style={{ marginTop: 18 }}>
          {tests.length > 0 && (
            <div className="field" style={{ maxWidth: 320 }}>
              <label htmlFor="marks-test-picker">Assessment</label>
              <select
                id="marks-test-picker"
                className="select"
                value={marksTestId}
                onChange={(e) => setMarksTestId(e.target.value)}
              >
                {tests.map((t) => (
                  <option key={t.assessment_id} value={t.assessment_id}>
                    {t.title}
                  </option>
                ))}
              </select>
            </div>
          )}
          {marksTestId && !notReadyIds.has(marksTestId) ? (
            <ConfirmedMarksGrid
              key={marksTestId}
              section={section}
              assessmentId={marksTestId}
              onNotReady={() => setNotReadyIds((prev) => new Set(prev).add(marksTestId))}
            />
          ) : (
            <MarksEntryGrid subject={subject} section={section} />
          )}
        </div>
      )}
    </>
  );
}
