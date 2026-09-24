"use client";

/**
 * The class-overview landing screen: every class, a status split derived from real
 * marks (on track / needs attention / requires review / not yet assessed), an average
 * score and how many papers actually have marks on them. Tap a class to see its
 * students.
 *
 * Restyled to match the reference's ClassOverview page (KPI tile row + segmented
 * distribution bar + a subject/score table look), while keeping this page's own real
 * shape: a school-wide roll-up over every class, not one class's per-subject detail --
 * the backend's AcademicsOverview has status_counts/avg_score_pct/test_count per class,
 * nothing per-subject, so the reference's subject-band table has no honest equivalent
 * here.
 *
 * Deliberately does not show an "aspiration", "action plan" or "recheck" column -- this
 * deployment has no data model for any of those, and this screen only ever shows a
 * number it can trace back to a real MarkEvent.
 *
 * The full per-assessment diagnostic (findings, intervention drawer, board-frequency
 * read) still lives at its own real, working /admin/boardx -- too large and too much
 * of its own thing to fold into this screen in one pass -- but per the reference
 * design's own note ("the standalone BoardX Intelligence page has been removed, the
 * Classes flow is the one navigation into this data now"), it is no longer its own
 * primary-nav destination (see SideNav.tsx); this button is how it is reached instead.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertCircle, AlertTriangle, ClipboardList, Download, TrendingUp, Users } from "lucide-react";
import { Mascot } from "@/components/Mascot";
import { api, type AcademicsOverview, type ClassAcademicSummary } from "@/lib/api";
import { downloadBlob } from "@/lib/download";
import { getApiKey } from "@/lib/session";

export default function AcademicsOverviewPage() {
  const [data, setData] = useState<AcademicsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"pdf" | "xlsx" | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .academicsOverview(key)
      .then(setData)
      .catch(() => setError("Could not load the class overview."));
  }, []);

  async function download(kind: "pdf" | "xlsx") {
    const key = getApiKey();
    if (!key) return;
    setDownloading(kind);
    try {
      const blob = kind === "pdf" ? await api.academicsOverviewPdf(key) : await api.academicsOverviewXlsx(key);
      downloadBlob(blob, `class-overview.${kind}`);
    } catch {
      setError(`Could not generate the ${kind === "pdf" ? "PDF" : "Excel"} file.`);
    } finally {
      setDownloading(null);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <p className="eyebrow">Overview</p>
          <h1 className="page-title">All Classes</h1>
          <p className="page-sub">
            Tap a class to see every student, their subject-wise marks and what needs
            attention.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link href="/admin/boardx">
            <button type="button" className="btn btn--ghost btn--sm">Full diagnostic (BoardX)</button>
          </Link>
          <button type="button" className="btn btn--ghost" disabled={!!downloading} onClick={() => download("xlsx")}>
            {downloading === "xlsx" ? "Preparing…" : "Download Excel"}
          </button>
          <button type="button" className="btn btn--primary" disabled={!!downloading} onClick={() => download("pdf")}>
            {downloading === "pdf" ? <>Preparing…</> : <><Download size={13} /> Download PDF</>}
          </button>
        </div>
      </div>

      {error && <p style={{ color: "var(--risk)", fontSize: 13.5, marginTop: 12 }}>{error}</p>}

      {!data && !error && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 20 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      )}

      {data && data.classes.length === 0 && (
        <p className="muted" style={{ marginTop: 20 }}>No classes yet.</p>
      )}

      {data && data.classes.length > 0 && (
        <>
          <SchoolInsights classes={data.classes} />
          <div className="classgrid">
            {worstFirst(data.classes).map((c) => (
              <ClassCard key={c.section_id} c={c} />
            ))}
          </div>
        </>
      )}

      <style jsx>{`
        .classgrid {
          display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
          gap: 16px; margin-top: 20px;
        }
      `}</style>
    </div>
  );
}

/**
 * Worst class first: a principal opening this screen wants to know where to look, not
 * to scroll for it. Ranked by average score, since that is the one number every scored
 * class has and every other class doesn't -- a class with no marks yet isn't "worst",
 * it's simply not comparable yet, so those are listed after every scored class rather
 * than sorted in among them (a 0% default would rank a genuinely brand-new class as the
 * single worst in the school, which is not true and not useful).
 */
function worstFirst(classes: ClassAcademicSummary[]): ClassAcademicSummary[] {
  const scored = classes.filter((c) => c.avg_score_pct != null);
  const unscored = classes.filter((c) => c.avg_score_pct == null);
  scored.sort((a, b) => (a.avg_score_pct ?? 0) - (b.avg_score_pct ?? 0));
  return [...scored, ...unscored];
}

/** Whole-percent shares of a set of counts, rounded so they still add to 100 --
 * matches the reference's own `percentShares` rounding behaviour. */
function percentShares(counts: number[]): number[] {
  const total = counts.reduce((a, b) => a + b, 0);
  if (total === 0) return counts.map(() => 0);
  const raw = counts.map((c) => (c / total) * 100);
  const floors = raw.map(Math.floor);
  let remainder = 100 - floors.reduce((a, b) => a + b, 0);
  const order = raw
    .map((v, i) => ({ i, frac: v - Math.floor(v) }))
    .sort((a, b) => b.frac - a.frac);
  const shares = [...floors];
  for (let k = 0; k < remainder; k++) shares[order[k % order.length].i] += 1;
  return shares;
}

/**
 * Two real, school-wide reads on the same class rows the cards below list one at a
 * time, restyled to the reference's KPI-tile row + segmented-distribution-bar look:
 * a headline tile row (students / on track / needs support / at risk), the same
 * split as one full-width segmented bar with a legend, and average score by class as
 * a table of pill values. Nothing here is a second computation -- every number is the
 * exact `status_counts`/`avg_score_pct` each `ClassAcademicSummary` already carries,
 * just rolled up or laid out differently.
 */
function SchoolInsights({ classes }: { classes: ClassAcademicSummary[] }) {
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
  const totalStudents = Object.values(totals).reduce((a, b) => a + b, 0);
  const [onTrackShare, supportShare, riskShare] = percentShares([totals.on_track, totals.needs_attention, totals.requires_review]);

  const tiles = [
    { key: "total", label: "Total Students", value: totalStudents, sub: `Across ${classes.length} classes`, accent: "var(--brand-blue)", icon: <Users size={21} /> },
    { key: "ontrack", label: "On Track", value: totals.on_track, sub: `${onTrackShare}% of students`, accent: "var(--brand-green)", icon: <TrendingUp size={21} /> },
    { key: "support", label: "Needs Attention", value: totals.needs_attention, sub: `${supportShare}% of students`, accent: "var(--brand-gold)", icon: <AlertTriangle size={21} /> },
    { key: "risk", label: "Requires Review", value: totals.requires_review, sub: `${riskShare}% of students`, accent: "var(--risk)", icon: <AlertCircle size={21} /> },
  ];

  const totalTests = classes.reduce((sum, c) => sum + c.test_count, 0);
  const scored = classes
    .filter((c) => c.avg_score_pct != null)
    .sort((a, b) => (a.avg_score_pct ?? 0) - (b.avg_score_pct ?? 0));

  const segments = [
    { key: "on_track", label: "On Track", count: totals.on_track, color: "var(--brand-green)" },
    { key: "needs_attention", label: "Needs Attention", count: totals.needs_attention, color: "var(--brand-gold)" },
    { key: "requires_review", label: "Requires Review", count: totals.requires_review, color: "var(--risk)" },
    { key: "not_assessed", label: "Not Yet Assessed", count: totals.not_assessed, color: "var(--muted)" },
  ];
  const segTotal = segments.reduce((s, x) => s + x.count, 0) || 1;

  return (
    <div>
      <div className="grid grid--4" style={{ marginTop: 20 }}>
        {tiles.map((tile) => (
          <div key={tile.key} className="kpi" style={{ "--accent": tile.accent } as React.CSSProperties}>
            <span className="kpi__icon">{tile.icon}</span>
            <div className="kpi__text">
              <div className="kpi__label">{tile.label}</div>
              <div className="kpi__value">{tile.value}</div>
              <div className="kpi__sub">{tile.sub}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card__head">
          <div>
            <h3 style={{ fontSize: 16 }}>Status across the whole school</h3>
            <p className="small muted" style={{ marginTop: 2 }}>{totalStudents} students, every class combined.</p>
          </div>
          <span className="tag">{totalTests} paper{totalTests === 1 ? "" : "s"} with marks</span>
        </div>
        <div className="card__body">
          <div className="segbar">
            {segments.map((seg) =>
              seg.count === 0 ? null : (
                <div
                  key={seg.key}
                  className="segbar__seg"
                  style={{ "--seg": seg.color, flexGrow: seg.count, flexBasis: 0 } as React.CSSProperties}
                  title={`${seg.label}: ${seg.count}`}
                >
                  {(seg.count / segTotal) * 100 >= 8 ? `${Math.round((seg.count / segTotal) * 100)}%` : ""}
                </div>
              )
            )}
          </div>
          <div className="segbar__legend">
            {segments.map((seg) => (
              <div key={seg.key} className="segbar__legend-item" style={{ "--seg": seg.color } as React.CSSProperties}>
                <span style={{ display: "grid", gap: 1, minWidth: 0 }}>
                  <span style={{ display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
                    <b style={{ fontSize: 19, letterSpacing: "-0.01em" }}>{seg.count}</b>
                    <span style={{ fontSize: 12 }}>({seg.label})</span>
                  </span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card__head">
          <div>
            <h3 style={{ fontSize: 16 }}>Average score by class</h3>
            <p className="small muted" style={{ marginTop: 2 }}>Classes with no marks yet are left out -- there is no score to compare.</p>
          </div>
        </div>
        <div className="card__body" style={{ paddingTop: 14 }}>
          {scored.length === 0 ? (
            <p className="muted small">No class has a scored paper yet.</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Class</th>
                    <th className="num">Average Score</th>
                    <th className="num">Students</th>
                    <th className="num">Papers With Marks</th>
                  </tr>
                </thead>
                <tbody>
                  {scored.map((c) => (
                    <tr key={c.section_id}>
                      <td className="strong">{c.grade}{c.name}</td>
                      <td className="num">
                        <span className="pillnum pillnum--solid" style={{ "--accent": scoreAccent(c.avg_score_pct ?? 0) } as React.CSSProperties}>
                          {(c.avg_score_pct ?? 0).toFixed(1)}
                        </span>
                      </td>
                      <td className="num">{c.student_count}</td>
                      <td className="num">{c.test_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function scoreAccent(pct: number): string {
  if (pct >= 78) return "var(--brand-green)";
  if (pct >= 60) return "var(--brand-gold)";
  return "var(--risk)";
}

function ClassCard({ c }: { c: ClassAcademicSummary }) {
  const counts = c.status_counts;
  const total = c.student_count || 1;
  const segments: { key: string; n: number; color: string }[] = [
    { key: "on_track", n: counts.on_track, color: "var(--brand-green)" },
    { key: "needs_attention", n: counts.needs_attention, color: "var(--brand-gold)" },
    { key: "requires_review", n: counts.requires_review, color: "var(--risk)" },
    { key: "not_assessed", n: counts.not_assessed, color: "var(--line-strong)" },
  ];

  // The reference's own attn dimension: one dominant read per class, standing in for
  // the four-way status split the bar below already shows in full -- a glance at the
  // card grid needs one word, not four numbers, to say where to look first.
  const attn = counts.requires_review > 0
    ? { label: "Needs review", cls: "attn--high" }
    : counts.needs_attention > 0
      ? { label: "Needs attention", cls: "attn--medium" }
      : total > counts.not_assessed
        ? { label: "On track", cls: "attn--low" }
        : null;

  return (
    <Link href={`/principal/classes/${c.section_id}`} className="classcard-link">
      <div className="card card--hover">
        <div className="card__head">
          <div>
            <h2 style={{ margin: 0 }}>{c.grade}{c.name}</h2>
            <p className="small muted" style={{ margin: "2px 0 0" }}>{c.student_count} Students</p>
          </div>
          {attn && <span className={`attn ${attn.cls}`}>{attn.label}</span>}
        </div>
        <div className="card__body" style={{ paddingTop: 14 }}>
          {c.avg_score_pct != null && (
            <p style={{ margin: "0 0 10px", fontSize: 20, fontWeight: 650 }}>{c.avg_score_pct}% avg</p>
          )}
          <div className="stackbar" aria-hidden>
            {segments.map((s) => (
              s.n > 0 && (
                <div
                  key={s.key}
                  style={{ width: `${(s.n / total) * 100}%`, background: s.color }}
                />
              )
            ))}
          </div>

          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 10 }}>
            <Legend label="On Track" n={counts.on_track} color="var(--brand-green)" />
            <Legend label="Attention" n={counts.needs_attention} color="var(--brand-gold)" />
            <Legend label="Review" n={counts.requires_review} color="var(--risk)" />
            {counts.not_assessed > 0 && (
              <Legend label="Not Assessed" n={counts.not_assessed} color="var(--muted)" />
            )}
          </div>

          <p className="small muted" style={{ marginTop: 10, marginBottom: 0 }}>
            {c.test_count} paper{c.test_count === 1 ? "" : "s"} with marks recorded
          </p>
        </div>
      </div>

      <style jsx>{`
        .classcard-link { text-decoration: none; color: inherit; display: block; }
        .stackbar {
          display: flex; height: 8px; border-radius: 999px; overflow: hidden;
          background: var(--rule);
        }
      `}</style>
    </Link>
  );
}

function Legend({ label, n, color }: { label: string; n: number; color: string }) {
  return (
    <span className="small" style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "var(--brand-ink-soft)" }}>
      <span style={{ width: 8, height: 8, borderRadius: 999, background: color, display: "inline-block" }} />
      {n} {label}
    </span>
  );
}
