"use client";

import { useEffect, useState, type CSSProperties } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowRight, ShieldCheck, TrendingDown, TrendingUp, Users } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { api, AcademicTestRow, ClassStudentRow, CohortReport } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { usePageHeader } from "@/lib/pageHeader";
import { AttentionPill } from "@/components/Status";
import { EvidenceState } from "@/components/EvidenceState";
import { LoadingScreen } from "@/components/Shell";
import { DeltaCell } from "@/components/StudentRosterTable";

const STATUS_LABEL: Record<string, string> = {
  on_track: "On Track",
  needs_attention: "Needs Attention",
  requires_review: "Requires Review",
  not_assessed: "Not assessed",
};

/** §6.2 Class view, a class teacher's own section, scoped to only the
 * subject(s) she actually teaches there -- real marks, one call per subject
 * she holds in this class (GET /admin/teacher/academics/{section}/students,
 * narrowed with subject_code). */
export default function ClassView() {
  const { section } = useParams<{ section: string }>();
  usePageHeader({ title: `Class ${section}`, backHref: "/teacher/home" });
  const { user } = useAuth();
  const [bySubject, setBySubject] = useState<Record<string, ClassStudentRow[]> | null>(null);
  const [sectionLabel, setSectionLabel] = useState(section);
  const [error, setError] = useState<string | null>(null);
  const [tests, setTests] = useState<AcademicTestRow[]>([]);
  const [cohort, setCohort] = useState<CohortReport | null>(null);
  const [previousTitle, setPreviousTitle] = useState<string | null>(null);
  const [movementRows, setMovementRows] = useState<ClassStudentRow[] | null>(null);

  const allowed = user?.role === "teacher" && user.assignments.some((a) => a.type === "class" && a.section_id === section);
  const mySubjects =
    user?.role === "teacher"
      ? [...new Set(user.assignments.filter((a) => a.type === "subject" && a.section_id === section && a.subject_code).map((a) => a.subject_code as string))]
      : [];

  useEffect(() => {
    const key = getApiKey();
    if (!key || !allowed || mySubjects.length === 0) return;
    let cancelled = false;
    Promise.all(mySubjects.map((s) => api.teacherAcademicsStudents(key, section, { subjectCode: s })))
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
  }, [section, mySubjects.join("|"), allowed]);

  // The most recently marked test in the first subject this teacher holds here --
  // real, ordered the same way the subject view already orders tests.
  const primarySubject = mySubjects[0];
  const latestTest = [...tests].filter((t) => t.subject_code === primarySubject).pop();

  useEffect(() => {
    const key = getApiKey();
    if (!key || !allowed || !latestTest) return;
    let cancelled = false;
    api
      .teacherCohortReport(key, latestTest.assessment_id, section)
      .then((r) => !cancelled && setCohort(r))
      .catch(() => !cancelled && setCohort(null));
    api
      .teacherAcademicsStudents(key, section, { subjectCode: primarySubject, assessmentId: latestTest.assessment_id })
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
  }, [latestTest?.assessment_id, section, allowed, primarySubject]);

  if (!allowed) return <EvidenceState kind="cause">You are not assigned as class teacher for {section}.</EvidenceState>;
  if (mySubjects.length === 0) {
    return (
      <EvidenceState kind="early">
        You are the class teacher for {section}, but aren&apos;t assigned to teach any subject there, nothing subject-specific to show.
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
  const attentionOf = (studentId: string): string => {
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

  // "Since {previous test}" is only shown once there are two real marked tests of the
  // same subject to compare -- both sides must be real averages, never a guessed one.
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
      label: mySubjects.length > 1 ? "Your subjects, attainment" : `${mySubjects[0]} attainment`,
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
      label: `Top gap in ${primarySubject ?? "your subject"}`,
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
          Class view · your subject{mySubjects.length > 1 ? "s" : ""}: {mySubjects.join(", ")}
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
            All {roster.length} students · {mySubjects.join(", ")} only
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
                      {s}
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
                      <td>{blocker ? `${blocker.chapter} (${Math.round(blocker.rate * 100)}%)` : "—"}</td>
                      <td>
                        <AttentionPill level={STATUS_LABEL[attentionOf(s.id)]} />
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
              Since {previousTitle} <span className="small muted" style={{ fontWeight: 400 }}>({primarySubject})</span>
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
