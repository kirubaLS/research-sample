"use client";

/**
 * §6.4 -- Teacher-facing student page: the same cross-subject overview a principal's
 * own app/admin/academics/students/[studentId]/page.tsx shows (same tiles, same
 * subject filter, same table columns), reusing GET /admin/teacher/academics/students/
 * {id} -- the teacher-scoped sibling of the principal's own /admin/academics/students/
 * {id}, restricted to exactly the subjects this teacher key's own assignments on the
 * student's section cover (a class assignment sees every subject; a subject
 * assignment sees only its own, including in the "overall" tiles).
 *
 * "Share with student" issues a real PIN for a report already issued elsewhere (a
 * principal, from the student's admin page) -- see ShareWithStudentModal. Download is
 * CSV only here (the explicit ask for teachers); the principal side keeps PDF/Excel.
 */

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { StatusBadge } from "@/components/academics/StatusBadge";
import { Mascot } from "@/components/Mascot";
import { ShareWithStudentModal } from "@/components/teacher/ShareWithStudentModal";
import { api, type StudentAcademicsOverview } from "@/lib/api";
import { downloadBlob } from "@/lib/download";
import { getApiKey } from "@/lib/session";

export default function TeacherStudentPage({
  params,
}: {
  params: Promise<{ studentId: string }>;
}) {
  const { studentId } = use(params);
  const [data, setData] = useState<StudentAcademicsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [subjectFilter, setSubjectFilter] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherStudentAcademics(key, studentId)
      .then(setData)
      .catch(() => setError("Could not load this student -- they may not be in one of your assigned classes."));
  }, [studentId]);

  async function downloadCsv() {
    const key = getApiKey();
    if (!key) return;
    setDownloading(true);
    try {
      const blob = await api.teacherStudentAcademicsCsv(key, studentId, subjectFilter || undefined);
      downloadBlob(blob, `student-overview.csv`);
    } catch {
      setError("Could not generate the CSV file.");
    } finally {
      setDownloading(false);
    }
  }

  if (error) return <main className="wrap"><p className="error">{error}</p></main>;
  if (!data) {
    return (
      <main className="wrap">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      </main>
    );
  }

  const subjects = subjectFilter
    ? data.subjects.filter((s) => s.subject_code === subjectFilter)
    : data.subjects;

  return (
    <main className="wrap">
      <div className="hero row between" style={{ alignItems: "flex-end" }}>
        <div>
          <p className="eyebrow">
            {data.student.section_label && (
              <>
                <Link href="/teacher/overview">Overview</Link> &rsaquo;{" "}
                <Link href={`/teacher/overview/${data.student.section_id}`}>{data.student.section_label}</Link> &rsaquo;{" "}
              </>
            )}
            {data.student.name}
          </p>
          <h1 style={{ margin: 0 }}>{data.student.name}</h1>
          <p className="lede">Roll {data.student.roll_no}</p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button type="button" className="secondary" onClick={() => setShareOpen(true)}>
            Share with student
          </button>
          <button type="button" disabled={downloading} onClick={downloadCsv}>
            {downloading ? "Preparing…" : "Download CSV"}
          </button>
        </div>
      </div>

      <div className="tiles" style={{ marginBottom: 20 }}>
        <div className="tile">
          <span className="tile-n">{data.overall.avg_score_pct != null ? `${data.overall.avg_score_pct}%` : "—"}</span>
          <span className="tile-l">Overall average</span>
        </div>
        <div className="tile">
          <span className="tile-n">{data.overall.tests_taken}</span>
          <span className="tile-l">Tests taken</span>
        </div>
        <div className="tile">
          <StatusBadge status={data.overall.status} />
          <span className="tile-l" style={{ marginTop: 6 }}>Overall status</span>
        </div>
      </div>

      {data.subjects.length > 0 && (
        <div className="field" style={{ maxWidth: 260, marginBottom: 14 }}>
          <label>Filter by subject</label>
          <select value={subjectFilter} onChange={(e) => setSubjectFilter(e.target.value)}>
            <option value="">All subjects</option>
            {data.subjects.map((s) => (
              <option key={s.subject_code} value={s.subject_code}>{s.label}</option>
            ))}
          </select>
        </div>
      )}

      {subjects.length === 0 ? (
        <p className="muted">No marks recorded for this student yet.</p>
      ) : (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Subject</th>
                <th>Avg Score</th>
                <th>Tests Taken</th>
                <th>Status</th>
                <th>Strengths</th>
                <th>Areas to Improve</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {subjects.map((s) => (
                <tr key={s.subject_code}>
                  <td className="strong">{s.label}</td>
                  <td className="num">{s.avg_score_pct != null ? `${s.avg_score_pct}%` : "—"}</td>
                  <td className="num">{s.tests_taken}</td>
                  <td><StatusBadge status={s.status} /></td>
                  <td className="small">{s.strengths.join(", ") || "—"}</td>
                  <td className="small">{s.improve.join(", ") || "—"}</td>
                  <td>
                    <Link href={`/teacher/student/${studentId}/subjects/${s.subject_code}`}>
                      <button type="button" className="secondary tiny">Details</button>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {shareOpen && (
        <ShareWithStudentModal
          studentId={studentId}
          studentName={data.student.name}
          onClose={() => setShareOpen(false)}
        />
      )}
    </main>
  );
}
