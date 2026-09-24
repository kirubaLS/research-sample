"use client";

/**
 * One student, every subject they have real marks in -- an overall status plus, per
 * subject, an average score, a status and the chapters they are strongest/weakest in.
 * Tap a subject to see its full chapter/tier breakdown (Page 4).
 *
 * The reference's equivalent is a drawer opened from the roster table (StudentDrawer /
 * the classes/[section]/[studentId] page); it's a full page here since we reach it from
 * its own URL, not a slide-out. Adapted: header block, a `.stat` grid-4 row (matching
 * the reference's own stat tiles), a filter, then the subject table. The reference's
 * page also shows "against the class" and "marks lost" stats and a chapter-level "where
 * marks were lost" table -- those come from a per-assessment student report the mock
 * fabricates; our real StudentAcademicsOverview has no per-assessment/class-average
 * fields at this level (that detail lives one level down, at the subject breakdown this
 * page already links to), so those two stats and that table are left out rather than
 * invented.
 */

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Download } from "lucide-react";
import { Avatar } from "@/components/academics/Avatar";
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

  const subjects = subjectFilter
    ? data.subjects.filter((s) => s.subject_code === subjectFilter)
    : data.subjects;
  const scoredSubjects = data.subjects.filter((s) => s.avg_score_pct != null);
  const strongest = scoredSubjects.length
    ? scoredSubjects.reduce((a, b) => ((b.avg_score_pct ?? 0) > (a.avg_score_pct ?? 0) ? b : a))
    : null;
  const weakest = scoredSubjects.length
    ? scoredSubjects.reduce((a, b) => ((b.avg_score_pct ?? 0) < (a.avg_score_pct ?? 0) ? b : a))
    : null;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <p className="eyebrow">
            {data.student.section_label && (
              <>
                <Link href="/principal/classes">Overview</Link> &rsaquo;{" "}
                <Link href={`/principal/classes/${data.student.section_id}`}>{data.student.section_label}</Link> &rsaquo;{" "}
              </>
            )}
            {data.student.name}
          </p>
          <h1 className="page-title" style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <Avatar name={data.student.name} seed={data.student.id} size={40} />
            {data.student.name}
          </h1>
          <p className="page-sub">
            {data.student.section_label ? `${data.student.section_label} · ` : ""}Roll {data.student.roll_no}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <button type="button" className="btn btn--ghost" disabled={!!downloading} onClick={() => download("xlsx")}>
            {downloading === "xlsx" ? "Preparing…" : "Download Excel"}
          </button>
          <button type="button" className="btn btn--primary" disabled={!!downloading} onClick={() => download("pdf")}>
            {downloading === "pdf" ? <>Preparing…</> : <><Download size={13} /> Download PDF</>}
          </button>
          <StatusBadge status={data.overall.status} />
        </div>
      </div>

      {data.subjects.length > 0 && (
        <div className="filterbar" style={{ marginTop: 20 }}>
          <div className="filter">
            <label htmlFor="subject-picker">Filter by subject</label>
            <select id="subject-picker" className="select" value={subjectFilter} onChange={(e) => setSubjectFilter(e.target.value)}>
              <option value="">All subjects</option>
              {data.subjects.map((s) => (
                <option key={s.subject_code} value={s.subject_code}>{s.label}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      <div className="grid grid--4" style={{ marginTop: 16 }}>
        <div className="stat">
          <div className="stat__label">Overall Average</div>
          <div className="stat__value stat__value--sm">
            {data.overall.avg_score_pct != null ? `${data.overall.avg_score_pct}%` : "N/A"}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">Tests Taken</div>
          <div className="stat__value stat__value--sm">{data.overall.tests_taken}</div>
        </div>
        <div className="stat">
          <div className="stat__label">Strongest Subject</div>
          <div className="stat__value stat__value--sm">
            {strongest ? strongest.label : "-"}
            {strongest && <span className="small muted" style={{ fontWeight: 400 }}> {strongest.avg_score_pct}%</span>}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">Needs Most Support</div>
          <div className="stat__value stat__value--sm">
            {weakest ? weakest.label : "-"}
            {weakest && <span className="small muted" style={{ fontWeight: 400 }}> {weakest.avg_score_pct}%</span>}
          </div>
        </div>
      </div>

      <section className="section">
        <div className="section__head">
          <div>
            <h2 className="section-q">Subject-wise performance</h2>
            <p className="section__lead">Every subject with recorded marks, strongest and weakest chapters at a glance. Tap Details for the full chapter/tier breakdown.</p>
          </div>
        </div>

        {subjects.length === 0 ? (
          <p className="muted">No marks recorded for this student yet.</p>
        ) : (
          <div className="card">
            <div className="table-wrap">
              <table className="table table--hover">
                <thead>
                  <tr>
                    <th>Subject</th>
                    <th className="num">Avg Score</th>
                    <th className="num">Tests Taken</th>
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
                      <td className="num">
                        {s.avg_score_pct != null ? (
                          <span className="pillnum pillnum--solid" style={{ "--accent": scoreAccent(s.avg_score_pct) } as React.CSSProperties}>
                            {s.avg_score_pct}
                          </span>
                        ) : (
                          <span className="muted">N/A</span>
                        )}
                      </td>
                      <td className="num">{s.tests_taken}</td>
                      <td><StatusBadge status={s.status} /></td>
                      <td className="small">{s.strengths.join(", ") || "N/A"}</td>
                      <td className="small">{s.improve.join(", ") || "N/A"}</td>
                      <td style={{ textAlign: "right" }}>
                        <Link href={`/principal/students/${studentId}/subjects/${s.subject_code}`}>
                          <button type="button" className="btn btn--ghost btn--sm">Details</button>
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function scoreAccent(pct: number): string {
  if (pct >= 78) return "var(--brand-green)";
  if (pct >= 60) return "var(--brand-gold)";
  return "var(--risk)";
}
