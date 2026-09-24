"use client";

/**
 * One test, every student who has a mark on it -- the same status bands the rest of
 * the academics screens use, computed from this one paper alone.
 *
 * Restyled to the reference's per-test page: a `.stat` grid-4 KPI strip (class
 * average, students, need attention, critical) above the roster. Our TestSummary is
 * single-subject (one assessment = one subject_label), so the reference's per-subject
 * strip has no equivalent to adapt here -- that breakdown lives one level up, across
 * tests, not within one.
 */

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Avatar } from "@/components/academics/Avatar";
import { StatusBadge } from "@/components/academics/StatusBadge";
import { Mascot } from "@/components/Mascot";
import { api, type TestSummary } from "@/lib/api";
import { downloadBlob } from "@/lib/download";
import { getApiKey } from "@/lib/session";

export default function TestSummaryPage({ params }: { params: Promise<{ assessmentId: string }> }) {
  const { assessmentId } = use(params);
  const [data, setData] = useState<TestSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"pdf" | "xlsx" | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .testSummary(key, assessmentId)
      .then(setData)
      .catch(() => setError("Could not load this test."));
  }, [assessmentId]);

  async function download(kind: "pdf" | "xlsx") {
    const key = getApiKey();
    if (!key) return;
    setDownloading(kind);
    try {
      const blob = kind === "pdf" ? await api.testSummaryPdf(key, assessmentId) : await api.testSummaryXlsx(key, assessmentId);
      downloadBlob(blob, `test-results.${kind}`);
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

  const counts = data.status_counts;
  const totalStudents = data.students.length;
  const scored = data.students.filter((s) => s.avg_score_pct != null);
  const avgScore = scored.length
    ? Math.round(scored.reduce((sum, s) => sum + (s.avg_score_pct ?? 0), 0) / scored.length)
    : null;
  const needAttention = counts.needs_attention + counts.requires_review;
  const critical = counts.requires_review;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <p className="eyebrow"><Link href="/principal/exams">Test</Link> &rsaquo; {data.assessment.title}</p>
          <h1 className="page-title">{data.assessment.title}</h1>
          <p className="page-sub">{data.assessment.subject_label}</p>
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

      <div className="grid grid--4" style={{ marginTop: 20 }}>
        <div className="stat">
          <div className="stat__label">Average score</div>
          <div className="stat__value">{avgScore != null ? `${avgScore}%` : "N/A"}</div>
        </div>
        <div className="stat">
          <div className="stat__label">Students marked</div>
          <div className="stat__value">{totalStudents}</div>
        </div>
        <div className="stat">
          <div className="stat__label">Need attention</div>
          <div className="stat__value">{needAttention}</div>
        </div>
        <div className="stat">
          <div className="stat__label">Critical</div>
          <div className="stat__value">{critical}</div>
        </div>
      </div>

      <div className="card" style={{ margin: "20px 0" }}>
        <div className="card__head">
          <div>
            <h3 style={{ fontSize: 16 }}>Test overview</h3>
            <p className="small muted" style={{ marginTop: 2 }}>Status split across every student marked on this paper.</p>
          </div>
        </div>
        <div className="card__body">
          <div className="segbar">
            {[
              { key: "on_track", label: "On Track", n: counts.on_track, color: "var(--brand-green)" },
              { key: "needs_attention", label: "Needs Attention", n: counts.needs_attention, color: "var(--brand-gold)" },
              { key: "requires_review", label: "Requires Review", n: counts.requires_review, color: "var(--risk)" },
              { key: "not_assessed", label: "Not Yet Assessed", n: counts.not_assessed, color: "var(--muted)" },
            ].map((seg) =>
              seg.n === 0 ? null : (
                <div
                  key={seg.key}
                  className="segbar__seg"
                  style={{ "--seg": seg.color, flexGrow: seg.n, flexBasis: 0 } as React.CSSProperties}
                  title={`${seg.label}: ${seg.n}`}
                >
                  {totalStudents && (seg.n / totalStudents) * 100 >= 8 ? `${Math.round((seg.n / totalStudents) * 100)}%` : ""}
                </div>
              )
            )}
          </div>
          <div className="segbar__legend">
            {[
              { key: "on_track", label: "On Track", n: counts.on_track, color: "var(--brand-green)" },
              { key: "needs_attention", label: "Needs Attention", n: counts.needs_attention, color: "var(--brand-gold)" },
              { key: "requires_review", label: "Requires Review", n: counts.requires_review, color: "var(--risk)" },
              { key: "not_assessed", label: "Not Yet Assessed", n: counts.not_assessed, color: "var(--muted)" },
            ].map((seg) => (
              <div key={seg.key} className="segbar__legend-item" style={{ "--seg": seg.color } as React.CSSProperties}>
                <span style={{ display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
                  <b style={{ fontSize: 19, letterSpacing: "-0.01em" }}>{seg.n}</b>
                  <span style={{ fontSize: 12 }}>({seg.label})</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <section className="section">
        <div className="section__head">
          <div>
            <h2 className="section-q">Students</h2>
            <p className="section__lead">Tap a student to open their subject-wise report.</p>
          </div>
        </div>
        <div className="card">
          <div className="table-wrap">
            <table className="table table--hover">
              <thead>
                <tr>
                  <th>Roll</th>
                  <th>Name</th>
                  <th className="num">Score</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.students.map((s) => (
                  <tr key={s.student_id}>
                    <td className="muted">{s.roll_no}</td>
                    <td className="strong">
                      <span style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "nowrap" }}>
                        <Avatar name={s.name} seed={s.student_id} size={30} />
                        {s.name}
                      </span>
                    </td>
                    <td className="num">{s.earned}/{s.available}{s.avg_score_pct != null ? ` (${s.avg_score_pct}%)` : ""}</td>
                    <td><StatusBadge status={s.status} /></td>
                    <td style={{ textAlign: "right" }}>
                      <Link href={`/principal/students/${s.student_id}`}>
                        <button type="button" className="btn btn--ghost btn--sm">View</button>
                      </Link>
                    </td>
                  </tr>
                ))}
                {data.students.length === 0 && (
                  <tr><td colSpan={5} className="muted">No marks recorded for this test yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
