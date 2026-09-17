"use client";

/**
 * One class, every student, a status derived from real marks -- narrowed by subject,
 * by test, by status band, and by the top 5 scorers. Every filter (including "top 5")
 * is sent to the backend and applied there, so the table on screen and its Excel/PDF
 * downloads can never disagree about which students a filter combination actually
 * means. Tap a student to see their own cross-subject overview.
 */

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/academics/StatusBadge";
import { Mascot } from "@/components/Mascot";
import { api, type AcademicStatus, type ClassStudentsView } from "@/lib/api";
import { downloadBlob } from "@/lib/download";
import { getApiKey } from "@/lib/session";

export default function ClassAcademicsPage({ params }: { params: Promise<{ sectionId: string }> }) {
  const { sectionId } = use(params);
  const [data, setData] = useState<ClassStudentsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [subjectCode, setSubjectCode] = useState("");
  const [assessmentId, setAssessmentId] = useState("");
  const [status, setStatus] = useState<AcademicStatus | "">("");
  const [top5, setTop5] = useState(false);
  const [downloading, setDownloading] = useState<"pdf" | "xlsx" | null>(null);

  const filters = {
    subjectCode: subjectCode || undefined, assessmentId: assessmentId || undefined,
    status: status || undefined, top: top5 ? 5 : undefined,
  };

  const load = useCallback(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .classStudents(key, sectionId, filters)
      .then(setData)
      .catch(() => setError("Could not load this class."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionId, subjectCode, assessmentId, status, top5]);

  useEffect(() => {
    load();
  }, [load]);

  async function download(kind: "pdf" | "xlsx") {
    const key = getApiKey();
    if (!key) return;
    setDownloading(kind);
    try {
      const blob = kind === "pdf"
        ? await api.classStudentsPdf(key, sectionId, filters)
        : await api.classStudentsXlsx(key, sectionId, filters);
      downloadBlob(blob, `class-students.${kind}`);
    } catch {
      setError(`Could not generate the ${kind === "pdf" ? "PDF" : "Excel"} file.`);
    } finally {
      setDownloading(null);
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

  const rows = data.students;

  return (
    <main className="wrap">
      <div className="hero row between" style={{ alignItems: "flex-end" }}>
        <div>
          <p className="eyebrow">
            <Link href="/admin/academics">Overview</Link> &rsaquo; {data.section.label}
          </p>
          <h1 style={{ margin: 0 }}>{data.section.label}</h1>
          <p className="lede">{data.students.length} students</p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button type="button" className="secondary" disabled={!!downloading} onClick={() => download("xlsx")}>
            {downloading === "xlsx" ? "Preparing…" : "Download Excel"}
          </button>
          <button type="button" disabled={!!downloading} onClick={() => download("pdf")}>
            {downloading === "pdf" ? "Preparing…" : "Download PDF"}
          </button>
        </div>
      </div>

      <div className="row" style={{ gap: 10, flexWrap: "wrap", marginBottom: 18 }}>
        <div className="field" style={{ marginBottom: 0, minWidth: 160 }}>
          <label>Subject</label>
          <select value={subjectCode} onChange={(e) => setSubjectCode(e.target.value)}>
            <option value="">All subjects</option>
            {data.filters.subjects.map((s) => (
              <option key={s.subject_code} value={s.subject_code}>{s.label}</option>
            ))}
          </select>
        </div>
        <div className="field" style={{ marginBottom: 0, minWidth: 180 }}>
          <label>Test</label>
          <select value={assessmentId} onChange={(e) => setAssessmentId(e.target.value)}>
            <option value="">All tests</option>
            {data.filters.tests.map((t) => (
              <option key={t.assessment_id} value={t.assessment_id}>{t.title}</option>
            ))}
          </select>
        </div>
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
        <label className="row" style={{ gap: 6, alignItems: "center", marginTop: 20 }}>
          <input type="checkbox" checked={top5} onChange={(e) => setTop5(e.target.checked)} />
          <span className="small">Top 5 scorers</span>
        </label>
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
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.student_id}>
                <td>{s.roll_no}</td>
                <td className="strong">{s.name}</td>
                <td><StatusBadge status={s.status} /></td>
                <td className="num">{s.avg_score_pct != null ? `${s.avg_score_pct}%` : "—"}</td>
                <td className="num">{s.tests_taken}</td>
                <td>{s.top_improvement_area ? `${s.top_improvement_area.chapter} (${s.top_improvement_area.rate}%)` : "—"}</td>
                <td>
                  <Link href={`/admin/academics/students/${s.student_id}`}>
                    <button type="button" className="secondary tiny">View</button>
                  </Link>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={7} className="muted">No students match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
