"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, BookOpen } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { api, TeacherAcademicClassRow } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { usePageHeader } from "@/lib/pageHeader";
import { EvidenceState } from "@/components/EvidenceState";
import { LoadingScreen } from "@/components/Shell";

/** §6.1 Teacher home, the signed-in teacher's own subjects -- one row per
 * (subject, section) this teacher key actually holds, backed by real marks
 * (GET /admin/teacher/academics). */
export default function TeacherHome() {
  usePageHeader({ title: "Teacher Home" });
  const { user } = useAuth();
  const [rows, setRows] = useState<TeacherAcademicClassRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherAcademicsOverview(key)
      .then((r) => setRows(r.classes))
      .catch(() => setError("Could not load your subjects."));
  }, []);

  if (!user || user.role !== "teacher") return null;

  const subjectAssignments = user.assignments.filter((a) => a.type === "subject");
  const bySubject = new Map<string, TeacherAcademicClassRow[]>();
  for (const r of rows ?? []) {
    if (!r.subject_code) continue;
    const list = bySubject.get(r.subject_code) ?? [];
    list.push(r);
    bySubject.set(r.subject_code, list);
  }
  const subjects = [...new Set(subjectAssignments.map((a) => a.subject_code).filter((s): s is string => !!s))];

  // The most recently marked test across every class/subject this teacher holds --
  // real, from the same rows the cards below already have (a class/subject with no
  // marks yet contributes nothing here, never a guessed name).
  const mostRecentlyMarked = [...(rows ?? [])]
    .filter((r) => r.test_count > 0)
    .sort((a, b) => b.test_count - a.test_count)[0];

  if (rows === null && !error) return <LoadingScreen label="Loading your subjects…" />;

  return (
    <>
      <p className="page-sub" style={{ marginTop: 0 }}>
        Welcome, {user.name || "Teacher"}.{" "}
        {mostRecentlyMarked
          ? "The latest marked test has been analysed. Here is what it says about your subjects."
          : "Here is what real marks say about your subjects."}
      </p>
      {error && <EvidenceState kind="early">{error}</EvidenceState>}

      <section style={{ marginTop: 24 }}>
        <div className="section__head">
          <h2 className="section-q">
            <BookOpen size={18} style={{ verticalAlign: "-3px", marginRight: 8 }} /> My Subjects
          </h2>
        </div>
        {subjects.length === 0 ? (
          <EvidenceState kind="early">No subject assignments yet.</EvidenceState>
        ) : (
          <div className="grid grid--2" style={{ gap: 12 }}>
            {subjects.map((subject) => {
              const classRows = bySubject.get(subject) ?? [];
              return (
                <div className="card card--hover" key={subject}>
                  <div className="card__body">
                    <h3 style={{ fontSize: 18 }}>{classRows[0]?.subject_label ?? subject}</h3>
                    <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
                      {classRows.length === 0 && <EvidenceState kind="early" compact>No marks recorded for this subject yet.</EvidenceState>}
                      {classRows.map((row) => (
                        <Link key={row.section_id} href={`/teacher/subject/${encodeURIComponent(subject)}/${row.section_id}`} className="subject-row">
                          <div>
                            <div className="strong">{row.label}</div>
                            <div className="small muted">
                              {row.avg_marks_earned != null && row.avg_marks_available != null
                                ? `avg ${row.avg_marks_earned} / ${row.avg_marks_available}`
                                : "no marks yet"}
                              {" · "}
                              {row.avg_score_pct != null ? `${row.avg_score_pct}% overall` : "-"} ·{" "}
                              {row.status_counts.on_track} on track / {row.student_count} students · {row.test_count} test{row.test_count === 1 ? "" : "s"}
                            </div>
                          </div>
                          <ArrowRight size={14} className="muted" />
                        </Link>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </>
  );
}
