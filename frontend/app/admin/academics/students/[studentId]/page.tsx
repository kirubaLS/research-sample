"use client";

/**
 * One student, every subject they have real marks in -- an overall status plus, per
 * subject, an average score, a status and the chapters they are strongest/weakest in.
 * Tap a subject to see its full chapter/tier breakdown (Page 4).
 */

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { StatusBadge } from "@/components/academics/StatusBadge";
import { Mascot } from "@/components/Mascot";
import { api, type StudentAcademicsOverview } from "@/lib/api";
import { downloadBlob } from "@/lib/download";
import { getApiKey } from "@/lib/session";

export default function StudentAcademicsPage({ params }: { params: Promise<{ studentId: string }> }) {
  const { studentId } = use(params);
  const [data, setData] = useState<StudentAcademicsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [subjectFilter, setSubjectFilter] = useState("");
  const [downloading, setDownloading] = useState<"pdf" | "xlsx" | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .studentAcademics(key, studentId)
      .then(setData)
      .catch(() => setError("Could not load this student."));
  }, [studentId]);

  async function download(kind: "pdf" | "xlsx") {
    const key = getApiKey();
    if (!key) return;
    setDownloading(kind);
    try {
      const filter = subjectFilter || undefined;
      const blob = kind === "pdf"
        ? await api.studentAcademicsPdf(key, studentId, filter)
        : await api.studentAcademicsXlsx(key, studentId, filter);
      downloadBlob(blob, `student-overview.${kind}`);
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
                <Link href="/admin/academics">Overview</Link> &rsaquo;{" "}
                <Link href={`/admin/academics/${data.student.section_id}`}>{data.student.section_label}</Link> &rsaquo;{" "}
              </>
            )}
            {data.student.name}
          </p>
          <h1 style={{ margin: 0 }}>{data.student.name}</h1>
          <p className="lede">Roll {data.student.roll_no}</p>
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
                    <Link href={`/admin/academics/students/${studentId}/subjects/${s.subject_code}`}>
                      <button type="button" className="secondary tiny">Details</button>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
