"use client";

/**
 * One class as this teacher key is scoped to see it -- every subject for a class
 * assignment, or just the one subject a subject assignment names (the backend always
 * runs it as that subject, regardless of what's in the URL). Real data only:
 * GET /admin/teacher/academics/{sectionId}/students.
 */

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/academics/StatusBadge";
import { Mascot } from "@/components/Mascot";
import { api, type AcademicStatus, type ClassStudentRow } from "@/lib/api";
import { getApiKey } from "@/lib/session";

export default function TeacherClassPage({ params }: { params: Promise<{ sectionId: string }> }) {
  const { sectionId } = use(params);
  const [section, setSection] = useState<{ id: string; label: string } | null>(null);
  const [subjectCode, setSubjectCode] = useState<string | null>(null);
  const [students, setStudents] = useState<ClassStudentRow[] | null>(null);
  const [status, setStatus] = useState<AcademicStatus | "">("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherAcademicsStudents(key, sectionId, { status: status || undefined })
      .then((res) => {
        setSection(res.section);
        setSubjectCode(res.subject_code);
        setStudents(res.students);
      })
      .catch(() => setError("Could not load this class."));
  }, [sectionId, status]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <main className="wrap"><p className="error">{error}</p></main>;
  if (!students || !section) {
    return (
      <main className="wrap">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      </main>
    );
  }

  return (
    <main className="wrap">
      <div className="hero">
        <p className="eyebrow">
          <Link href="/teacher/overview">Overview</Link> &rsaquo; {section.label}
        </p>
        <h1 style={{ margin: 0 }}>{section.label}</h1>
        <p className="lede">
          {subjectCode ? `${subjectCode} only` : "All subjects"} · {students.length} students
        </p>
      </div>

      <div className="row" style={{ gap: 10, flexWrap: "wrap", marginBottom: 18 }}>
        <div className="field" style={{ marginBottom: 0, minWidth: 170 }}>
          <label>Status</label>
          <select value={status} onChange={(e) => setStatus(e.target.value as AcademicStatus | "")}>
            <option value="">All statuses</option>
            <option value="on_track">On Track</option>
            <option value="needs_attention">Needs Attention</option>
            <option value="requires_review">Requires Review</option>
            <option value="not_assessed">Not Yet Assessed</option>
          </select>
        </div>
      </div>

      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Roll</th>
              <th>Name</th>
              <th>Status</th>
              <th>Avg Score</th>
              <th>Tests Taken</th>
              <th>Top Area to Improve</th>
            </tr>
          </thead>
          <tbody>
            {students.map((s) => (
              <tr key={s.student_id}>
                <td>{s.roll_no}</td>
                <td className="strong">{s.name}</td>
                <td><StatusBadge status={s.status} /></td>
                <td className="num">{s.avg_score_pct != null ? `${s.avg_score_pct}%` : "—"}</td>
                <td className="num">{s.tests_taken}</td>
                <td>{s.top_improvement_area ? `${s.top_improvement_area.chapter} (${s.top_improvement_area.rate}%)` : "—"}</td>
              </tr>
            ))}
            {students.length === 0 && (
              <tr><td colSpan={6} className="muted">No students match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
