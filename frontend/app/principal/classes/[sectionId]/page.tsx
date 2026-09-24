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
import { Avatar } from "@/components/academics/Avatar";
import { ClassFindings } from "@/components/academics/ClassFindings";
import { BarChartIcon, ClipboardIcon, PeopleIcon } from "@/components/academics/Icons";
import { ScoreDistribution } from "@/components/academics/ScoreDistribution";
import { StatTile, StatTileRow } from "@/components/academics/StatTile";
import { StatusBadge } from "@/components/academics/StatusBadge";
import { StatusOverviewBar } from "@/components/academics/StatusOverviewBar";
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

  if (error) return <div><p style={{ color: "var(--risk)", fontSize: 13.5 }}>{error}</p></div>;
  if (!data) {
    return (
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      </div>
    );
  }

  const rows = data.students;

  const counts = rows.reduce(
    (acc, s) => {
      acc[s.status] += 1;
      return acc;
    },
    { on_track: 0, needs_attention: 0, requires_review: 0, not_assessed: 0 },
  );
  const scored = rows.filter((s) => s.avg_score_pct != null);
  const avgScore = scored.length
    ? Math.round(scored.reduce((sum, s) => sum + (s.avg_score_pct ?? 0), 0) / scored.length)
    : null;
  const totalTestsTaken = rows.reduce((sum, s) => sum + s.tests_taken, 0);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <p className="eyebrow">
            <Link href="/principal/classes">Overview</Link> &rsaquo; {data.section.label}
          </p>
          <h1 className="page-title">{data.section.label}</h1>
          <p className="page-sub">{data.students.length} students</p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" className="btn btn--ghost" disabled={!!downloading} onClick={() => download("xlsx")}>
            {downloading === "xlsx" ? "Preparing…" : "Download Excel"}
          </button>
          <button type="button" className="btn btn--primary" disabled={!!downloading} onClick={() => download("pdf")}>
            {downloading === "pdf" ? "Preparing…" : "Download PDF"}
          </button>
        </div>
      </div>

      <div className="card" style={{ margin: "20px 0" }}>
        <div className="card__body classoverview-grid">
          <StatusOverviewBar counts={counts} title="Class Overview" />
          <div className="classoverview-stats">
            <StatTile icon={<PeopleIcon />} value={rows.length} label="Students" tone="violet" />
            <StatTile icon={<ClipboardIcon />} value={totalTestsTaken} label="Tests Recorded" tone="info" />
            <StatTile
              icon={<BarChartIcon />}
              value={avgScore != null ? `${avgScore}%` : "N/A"}
              label="Class Avg. Score"
              tone="gold"
            />
          </div>
        </div>
        <style jsx>{`
          .classoverview-grid { display: flex; gap: 24px; flex-wrap: wrap; align-items: center; }
          .classoverview-grid > :global(.sob) { flex: 1 1 320px; min-width: 260px; }
          .classoverview-stats {
            display: flex; gap: 14px; flex-wrap: wrap; flex: 2 1 420px;
          }
          .classoverview-stats > :global(.stattile) { flex: 1 1 130px; border: none; box-shadow: none; padding: 4px 0; }
        `}</style>
      </div>

      <ScoreDistribution students={rows} />
      {assessmentId && <ClassFindings sectionId={sectionId} assessmentId={assessmentId} />}

      <div className="filterbar" style={{ marginTop: 20 }}>
        <div className="filter" style={{ minWidth: 160 }}>
          <label>Subject</label>
          <select className="select" value={subjectCode} onChange={(e) => setSubjectCode(e.target.value)}>
            <option value="">All subjects</option>
            {data.filters.subjects.map((s) => (
              <option key={s.subject_code} value={s.subject_code}>{s.label}</option>
            ))}
          </select>
        </div>
        <div className="filter" style={{ minWidth: 180 }}>
          <label>Test</label>
          <select className="select" value={assessmentId} onChange={(e) => setAssessmentId(e.target.value)}>
            <option value="">All tests</option>
            {data.filters.tests.map((t) => (
              <option key={t.assessment_id} value={t.assessment_id}>{t.title}</option>
            ))}
          </select>
        </div>
        <div className="filter" style={{ minWidth: 170 }}>
          <label>Status</label>
          <select className="select" value={status} onChange={(e) => setStatus(e.target.value as AcademicStatus | "")}>
            <option value="">All statuses</option>
            <option value="on_track">On Track</option>
            <option value="needs_attention">Needs Attention</option>
            <option value="requires_review">Requires Review</option>
            <option value="not_assessed">Not Yet Assessed</option>
          </select>
        </div>
        <label className="check" style={{ marginTop: 18 }}>
          <input type="checkbox" checked={top5} onChange={(e) => setTop5(e.target.checked)} />
          <span>Top 5 scorers</span>
        </label>
      </div>

      <div className="table-wrap">
        <table className="table table--hover">
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
                <td className="strong">
                  <span style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "nowrap" }}>
                    <Avatar name={s.name} seed={s.student_id} size={30} />
                    {s.name}
                  </span>
                </td>
                <td><StatusBadge status={s.status} /></td>
                <td className="num">{s.avg_score_pct != null ? `${s.avg_score_pct}%` : "N/A"}</td>
                <td className="num">{s.tests_taken}</td>
                <td>{s.top_improvement_area ? `${s.top_improvement_area.chapter} (${s.top_improvement_area.rate}%)` : "N/A"}</td>
                <td>
                  <Link href={`/principal/students/${s.student_id}`}>
                    <button type="button" className="btn btn--ghost btn--sm">View</button>
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
    </div>
  );
}
