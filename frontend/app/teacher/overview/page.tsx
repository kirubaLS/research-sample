"use client";

/**
 * The same Overview a principal opens, narrowed to exactly this teacher key's own
 * class/subject assignments -- a class assignment shows every subject for that
 * section; a subject assignment shows only its own subject's marks. Real data only:
 * GET /admin/teacher/academics.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { Mascot } from "@/components/Mascot";
import { api, type TeacherAcademicClassRow } from "@/lib/api";
import { getApiKey } from "@/lib/session";

export default function TeacherOverviewPage() {
  const [classes, setClasses] = useState<TeacherAcademicClassRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherAcademicsOverview(key)
      .then((res) => setClasses(res.classes))
      .catch(() => setError("Could not load your classes."));
  }, []);

  return (
    <main className="narrow">
      <div className="hero">
        <p className="eyebrow">Overview</p>
        <h1 style={{ margin: 0 }}>Your Classes</h1>
      </div>

      {error && <p className="error">{error}</p>}
      {!classes && !error && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      )}
      {classes && classes.length === 0 && (
        <p className="muted">No classes or subjects are assigned to this key yet.</p>
      )}

      {classes && classes.length > 0 && <TeacherInsights classes={classes} />}

      {classes && classes.length > 0 && (
        <div className="stack" style={{ gap: 12 }}>
          {classes.map((c) => {
            const counts = c.status_counts;
            const total = c.student_count || 1;
            const segments = [
              { n: counts.on_track, color: "var(--verify)" },
              { n: counts.needs_attention, color: "var(--warn)" },
              { n: counts.requires_review, color: "var(--risk)" },
              { n: counts.not_assessed, color: "var(--rule-2)" },
            ];
            return (
              <Link
                key={`${c.section_id}-${c.subject_code ?? "all"}`}
                href={`/teacher/overview/${c.section_id}${c.subject_code ? `?subject=${c.subject_code}` : ""}`}
                style={{ textDecoration: "none", color: "inherit" }}
              >
                <div className="card">
                  <div className="row between" style={{ alignItems: "flex-start" }}>
                    <div>
                      <strong>{c.label}</strong>
                      <p className="cardnote" style={{ margin: "2px 0 0" }}>
                        {c.subject_label} · {c.student_count} students
                      </p>
                    </div>
                    {c.avg_score_pct != null && <span className="badge blue">{c.avg_score_pct}% avg</span>}
                  </div>
                  <div
                    style={{
                      display: "flex", height: 8, borderRadius: 999, overflow: "hidden",
                      background: "var(--rule)", marginTop: 12,
                    }}
                  >
                    {segments.map((s, i) => s.n > 0 && (
                      <div key={i} style={{ width: `${(s.n / total) * 100}%`, background: s.color }} />
                    ))}
                  </div>
                  <p className="small muted" style={{ marginTop: 8, marginBottom: 0 }}>
                    {c.test_count} paper{c.test_count === 1 ? "" : "s"} with marks recorded
                  </p>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </main>
  );
}

const STATUS_SERIES: { key: keyof TeacherAcademicClassRow["status_counts"]; label: string; color: string }[] = [
  { key: "on_track", label: "On Track", color: "var(--verify)" },
  { key: "needs_attention", label: "Needs Attention", color: "var(--warn)" },
  { key: "requires_review", label: "Requires Review", color: "var(--risk)" },
  { key: "not_assessed", label: "Not Yet Assessed", color: "var(--ink-3)" },
];

/**
 * The same two real, school-wide reads app.admin/academics's own SchoolInsights shows
 * a principal, narrowed to exactly this teacher key's own classes/subjects: how every
 * student across those rows currently splits across the four status bands, and how
 * each class/subject row's average score compares to the others. Same visual language
 * deliberately -- a stacked status bar plus a single-hue score bar, status colors
 * reserved, magnitude in one sequential hue, direct value labels, rows with no score
 * left out rather than shown as zero.
 */
function TeacherInsights({ classes }: { classes: TeacherAcademicClassRow[] }) {
  const totals = classes.reduce(
    (acc, c) => {
      acc.on_track += c.status_counts.on_track;
      acc.needs_attention += c.status_counts.needs_attention;
      acc.requires_review += c.status_counts.requires_review;
      acc.not_assessed += c.status_counts.not_assessed;
      return acc;
    },
    { on_track: 0, needs_attention: 0, requires_review: 0, not_assessed: 0 },
  );
  const totalStudents = Object.values(totals).reduce((a, b) => a + b, 0) || 1;

  const scored = classes
    .filter((c) => c.avg_score_pct != null)
    .sort((a, b) => (b.avg_score_pct ?? 0) - (a.avg_score_pct ?? 0));
  const maxScore = Math.max(100, ...scored.map((c) => c.avg_score_pct ?? 0));

  return (
    <div className="insights">
      <div className="card insight-card">
        <h2 style={{ marginTop: 0, fontSize: 15 }}>Status across your classes</h2>
        <p className="cardnote" style={{ margin: "0 0 12px" }}>{totalStudents} students, every class/subject you hold combined</p>
        <div className="insight-stackbar" role="img" aria-label="Status distribution across your own classes">
          {STATUS_SERIES.map((s) => {
            const n = totals[s.key];
            return n > 0 && (
              <div key={s.key} style={{ width: `${(n / totalStudents) * 100}%`, background: s.color }} title={`${s.label}: ${n}`} />
            );
          })}
        </div>
        <div className="row" style={{ gap: 16, flexWrap: "wrap", marginTop: 12 }}>
          {STATUS_SERIES.map((s) => (
            <span key={s.key} className="small" style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "var(--ink-2)" }}>
              <span style={{ width: 8, height: 8, borderRadius: 999, background: s.color, display: "inline-block" }} />
              {totals[s.key]} {s.label}
            </span>
          ))}
        </div>
      </div>

      <div className="card insight-card">
        <h2 style={{ marginTop: 0, fontSize: 15 }}>Average score by class</h2>
        <p className="cardnote" style={{ margin: "0 0 12px" }}>Rows with no marks yet are left out -- there is no score to compare.</p>
        {scored.length === 0 ? (
          <p className="muted small">No class or subject has a scored paper yet.</p>
        ) : (
          <div className="scorebars">
            {scored.map((c) => (
              <div className="scorebar-row" key={`${c.section_id}-${c.subject_code ?? "all"}`}>
                <span className="scorebar-label">{c.label} · {c.subject_label}</span>
                <div className="scorebar-track">
                  <div
                    className="scorebar-fill"
                    style={{ width: `${((c.avg_score_pct ?? 0) / maxScore) * 100}%` }}
                  />
                </div>
                <span className="scorebar-value">{c.avg_score_pct}%</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <style jsx>{`
        .insights {
          display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
          gap: 16px; margin: 20px 0;
        }
        .insight-card { margin: 0; }
        .insight-stackbar {
          display: flex; height: 14px; border-radius: 999px; overflow: hidden;
          background: var(--rule);
        }
        .insight-stackbar > div { transition: width 0.3s ease; }
        .scorebars { display: flex; flex-direction: column; gap: 9px; }
        .scorebar-row { display: grid; grid-template-columns: 150px 1fr 42px; align-items: center; gap: 10px; }
        .scorebar-label { font-size: 12.5px; font-weight: 600; color: var(--ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .scorebar-track { height: 10px; border-radius: 999px; background: var(--rule); overflow: hidden; }
        .scorebar-fill { height: 100%; border-radius: 999px; background: var(--mark); transition: width 0.3s ease; }
        .scorebar-value { font-size: 12.5px; color: var(--ink-2); text-align: right; font-variant-numeric: tabular-nums; }
      `}</style>
    </div>
  );
}
