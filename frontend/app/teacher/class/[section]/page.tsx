"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { api, ClassStudentRow } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { usePageHeader } from "@/lib/pageHeader";
import { AttentionPill } from "@/components/Status";
import { EvidenceState } from "@/components/EvidenceState";
import { LoadingScreen } from "@/components/Shell";

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
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section, mySubjects.join("|"), allowed]);

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

  return (
    <>
      <p className="page-sub" style={{ marginTop: 0 }}>
        Class view · your subject{mySubjects.length > 1 ? "s" : ""}: {mySubjects.join(", ")}
      </p>

      <div className="grid grid--2" style={{ marginTop: 18 }}>
        <div className="stat">
          <div className="stat__label">Students</div>
          <div className="stat__value">{roster.length}</div>
        </div>
        <div className="stat">
          <div className="stat__label">{mySubjects.length > 1 ? "Your subjects, attainment" : `${mySubjects[0]} attainment`}</div>
          <div className="stat__value">{overallAttainment != null ? `${overallAttainment}%` : "—"}</div>
        </div>
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
    </>
  );
}
