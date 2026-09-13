"use client";

/**
 * Board Intelligence -- the principal/admin-facing read of one assessment's Board
 * readiness, in the pastel EdTech visual language the rest of the dashboard uses.
 *
 * Every number on this page is real: GET /reports/paper/{id} (one paper's own diagnostic
 * quality) and GET /reports/cohort/{id} (bands, section averages, marks lost per family,
 * all real aggregations across every student who sat the paper -- see that endpoint's own
 * docstring for exactly what "Performance by Subject" does and does not mean here). Where
 * this deployment genuinely has no data yet (a school with no cohort-wide marks entered),
 * the honest state is a plain sentence, never an invented figure or a blank chart.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  api, ApiError, ApiUnreachable, type CohortReport, type Overview, type PaperReport,
} from "@/lib/api";
import { getApiKey } from "@/lib/session";

const STRENGTH_COPY: Record<PaperReport["diagnostic_strength"], string> = {
  STRONG: "This paper is a solid basis for the findings below.",
  MODERATE:
    "This paper provides reasonable evidence, but interpret findings in under-tested areas with caution.",
  LIMITED:
    "This paper's tier balance or item consistency is weak enough that findings here should be treated as a starting signal, not a conclusion.",
};

const SUBJECT_COLORS: Record<string, string> = {
  MATH: "var(--mark)", PHYS: "var(--info)", CHEM: "var(--verify)",
  ENG: "var(--warn)", SOC: "var(--risk)", SCI: "var(--verify)",
};

function subjectColor(code: string): string {
  const key = code.split(".").pop() ?? code;
  for (const prefix of Object.keys(SUBJECT_COLORS)) {
    if (key.toUpperCase().startsWith(prefix)) return SUBJECT_COLORS[prefix];
  }
  return "var(--ink-3)";
}

function pct(n: number | null | undefined): string {
  return n == null ? "—" : `${Math.round(n * 100)}%`;
}

/** A four-band donut, drawn as stacked SVG arcs rather than a canvas library -- four
 *  numbers that always sum to 100, which an arc's own stroke-dasharray represents exactly. */
function BandDonut({ band_pct, students }: { band_pct: CohortReport["band_pct"]; students: number }) {
  const segments: { pct: number; color: string }[] = [
    { pct: band_pct.full_mastery, color: "var(--verify)" },
    { pct: band_pct.band_80_89, color: "var(--info)" },
    { pct: band_pct.band_60_79, color: "var(--warn)" },
    { pct: band_pct.below_60, color: "var(--risk)" },
  ];
  const r = 54;
  const circumference = 2 * Math.PI * r;
  let offset = 0;
  return (
    <svg viewBox="0 0 140 140" className="donut" role="img" aria-label="Students by performance band">
      <circle cx="70" cy="70" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="20" />
      {segments.map((s, i) => {
        const len = (s.pct / 100) * circumference;
        const dash = `${len} ${circumference - len}`;
        const el = (
          <circle
            key={i} cx="70" cy="70" r={r} fill="none" stroke={s.color} strokeWidth="20"
            strokeDasharray={dash} strokeDashoffset={-offset} strokeLinecap="butt"
            transform="rotate(-90 70 70)"
          />
        );
        offset += len;
        return el;
      })}
      <text x="70" y="66" textAnchor="middle" className="donut-n">{students}</text>
      <text x="70" y="84" textAnchor="middle" className="donut-l">Students</text>
    </svg>
  );
}

function urgencyBadgeClass(tier: string | null): string {
  if (tier === "VERY HIGH" || tier === "HIGH") return "badge red";
  if (tier === "MEDIUM") return "badge amber";
  return "badge";
}

export default function BoardXPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [assessmentId, setAssessmentId] = useState<string>("");
  const [report, setReport] = useState<PaperReport | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [cohort, setCohort] = useState<CohortReport | null>(null);
  const [cohortNote, setCohortNote] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api.overview(key).then(setOverview).catch(() => setLoadError("Could not load your assessments."));
  }, []);

  useEffect(() => {
    if (!overview) return;
    if (!assessmentId && overview.assessments.length > 0) {
      setAssessmentId(overview.assessments[0].id);
    }
  }, [overview, assessmentId]);

  useEffect(() => {
    const key = getApiKey();
    if (!key || !assessmentId) return;
    setReport(null);
    setReportError(null);
    api.paperReport(key, assessmentId).then(setReport).catch((err: unknown) => {
      if (err instanceof ApiError && err.status === 404) {
        setReportError("No marks have been entered for this assessment yet.");
      } else if (err instanceof ApiUnreachable) {
        setReportError("Could not reach the API.");
      } else {
        setReportError("Could not load this assessment's diagnostic report.");
      }
    });
    setCohort(null);
    setCohortNote(null);
    api.cohortReport(key, assessmentId).then(setCohort).catch((err: unknown) => {
      setCohortNote(
        err instanceof ApiError && err.status === 404
          ? "No marks have been entered for this assessment yet, so there is nothing to aggregate across students."
          : "Could not load the class-wide read of this assessment.",
      );
    });
  }, [assessmentId]);

  if (loadError) return <main className="wrap"><p className="error">{loadError}</p></main>;
  if (!overview) return <main className="wrap"><p className="muted">Loading…</p></main>;

  const assessment = overview.assessments.find((a) => a.id === assessmentId);
  const topLoss = cohort?.top_losses[0];

  return (
    <main className="wrap">
      <section className="hello">
        <div>
          <p className="eyebrow">{overview.school.name}</p>
          <h1>Welcome back!</h1>
          <p className="lede">
            {assessment
              ? <>Here&rsquo;s how <strong>{assessment.title}</strong> is performing.</>
              : "Choose an assessment below to see how it's performing."}
          </p>
        </div>
        <div className="insight">
          <p className="insight-eyebrow">✦ BoardX Insight</p>
          <p className="insight-body">
            This test gives a reliable snapshot of current performance and clear
            opportunities for improvement.
          </p>
        </div>
      </section>

      <div className="filterbar">
        <label>
          Assessment
          <select value={assessmentId} onChange={(e) => setAssessmentId(e.target.value)}>
            {overview.assessments.map((a) => (
              <option key={a.id} value={a.id}>{a.title}</option>
            ))}
          </select>
        </label>
      </div>

      {overview.assessments.length === 0 && (
        <p className="notice mark">No assessments have been created for this school yet.</p>
      )}

      {assessment && (
        <>
          <div className="kpis">
            <div className="kpi">
              <p className="kpi-n">{cohort?.students_analysed ?? report?.students ?? "—"}</p>
              <p className="kpi-l">Students Analysed</p>
            </div>
            <div className="kpi">
              <p className="kpi-n">{cohort?.band_counts.full_mastery ?? "—"}</p>
              <p className="kpi-l">Full Mastery (90%+)</p>
              {cohort && <p className="kpi-sub good">{cohort.band_pct.full_mastery}% of total</p>}
            </div>
            <div className="kpi">
              <p className="kpi-n">
                {cohort ? cohort.band_counts.full_mastery + cohort.band_counts.band_80_89 : "—"}
              </p>
              <p className="kpi-l">Students at 80%+</p>
            </div>
            <div className="kpi">
              <p className="kpi-n">{cohort?.band_counts.below_60 ?? "—"}</p>
              <p className="kpi-l">Students below 60%</p>
              {cohort && <p className="kpi-sub warn">{cohort.band_pct.below_60}% of total</p>}
            </div>
          </div>

          <section className="section-head">
            <h2>Can I trust this test to tell me enough?</h2>
          </section>
          {reportError && <p className="notice mark">{reportError}</p>}
          {report && (
            <div className="card">
              <div className={`strength strength-${report.diagnostic_strength.toLowerCase()}`}>
                <p className="small muted">Assessment Diagnostic Strength</p>
                <p className="strengthvalue">{report.diagnostic_strength}</p>
              </div>
              <p className="small">{STRENGTH_COPY[report.diagnostic_strength]}</p>
              <div className="statrow">
                <div>
                  <p className="statvalue">{pct(report.application_share)}</p>
                  <p className="small muted">Application Questions</p>
                </div>
                <div>
                  <p className="statvalue">{pct(report.higher_order_share)}</p>
                  <p className="small muted">Higher-Order Questions</p>
                </div>
                <div>
                  <p className="statvalue">
                    {report.cronbach_alpha == null ? "—" : report.cronbach_alpha.toFixed(2)}
                  </p>
                  <p className="small muted">Item Consistency (α)</p>
                </div>
                <div>
                  <p className="statvalue">{report.flagged_items.length}</p>
                  <p className="small muted">Items Flagged</p>
                </div>
              </div>
              <p className="verdict">{report.typology_alignment.verdict}</p>
            </div>
          )}

          <section className="section-head">
            <h2>Where are we losing Board marks?</h2>
          </section>
          {cohortNote && <p className="notice mark">{cohortNote}</p>}
          {topLoss && (
            <div className="lossbanner">
              <div className="loss-icon" aria-hidden>◎</div>
              <div className="loss-body">
                <p className="loss-title">{topLoss.label}</p>
                <p className="small muted">Highest average marks lost per student on this paper</p>
              </div>
              <div className="loss-stat">
                <p className="statvalue">{topLoss.students_affected}</p>
                <p className="small muted">Students affected</p>
              </div>
              <div className="loss-stat">
                <p className="statvalue">{topLoss.avg_marks_lost.toFixed(1)}</p>
                <p className="small muted">Avg. marks lost</p>
              </div>
              <div className="loss-stat">
                <span className={urgencyBadgeClass(topLoss.board_urgency)}>
                  {topLoss.board_urgency ?? "UNSCORED"}
                </span>
                <p className="small muted" style={{ marginTop: 6 }}>
                  {topLoss.confidence} confidence
                </p>
              </div>
            </div>
          )}

          {cohort && cohort.top_losses.length > 1 && (
            <ul className="losslist">
              {cohort.top_losses.slice(1).map((l) => (
                <li key={l.concept_family}>
                  <span className="losslist-label">{l.label}</span>
                  <span className="muted small">
                    {l.students_affected} student{l.students_affected === 1 ? "" : "s"} ·
                    {" "}{l.avg_marks_lost.toFixed(1)} marks avg
                  </span>
                  <span className={urgencyBadgeClass(l.board_urgency)}>
                    {l.board_urgency ?? "—"}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {cohort && (
            <div className="grid3">
              <div className="card">
                <h3>Performance by Subject</h3>
                <p className="small muted" style={{ marginTop: -6, marginBottom: 12 }}>
                  {cohort.subject_bars_note}
                </p>
                <div className="bars">
                  {cohort.subject_bars.map((s) => (
                    <div className="barrow" key={s.subject_code}>
                      <span className="barrow-l" title={s.assessment_title}>{s.subject_code}</span>
                      <div className="track">
                        <div
                          className="fill"
                          style={{ width: `${s.pct}%`, background: subjectColor(s.subject_code) }}
                        />
                      </div>
                      <span className="barrow-v">{s.pct.toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="card center">
                <h3>Students by Performance Band</h3>
                <BandDonut band_pct={cohort.band_pct} students={cohort.students_analysed} />
                <ul className="legend">
                  <li><span className="dot" style={{ background: "var(--verify)" }} />Full Mastery (90+) · {cohort.band_counts.full_mastery} ({cohort.band_pct.full_mastery}%)</li>
                  <li><span className="dot" style={{ background: "var(--info)" }} />80&ndash;89 · {cohort.band_counts.band_80_89} ({cohort.band_pct.band_80_89}%)</li>
                  <li><span className="dot" style={{ background: "var(--warn)" }} />60&ndash;79 · {cohort.band_counts.band_60_79} ({cohort.band_pct.band_60_79}%)</li>
                  <li><span className="dot" style={{ background: "var(--risk)" }} />Below 60 · {cohort.band_counts.below_60} ({cohort.band_pct.below_60}%)</li>
                </ul>
              </div>

              <div className="card">
                <h3>Section Performance</h3>
                <div className="bars">
                  {cohort.section_bars.map((s) => (
                    <div className="barrow" key={s.section_id}>
                      <span className="barrow-l">{s.label}</span>
                      <div className="track">
                        <div className="fill" style={{ width: `${s.pct}%`, background: "var(--mark)" }} />
                      </div>
                      <span className="barrow-v">{s.pct.toFixed(0)}%</span>
                    </div>
                  ))}
                  {cohort.section_bars.length === 0 && (
                    <p className="muted small">No section is on record for these students.</p>
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="card notice-card">
            <p>
              <strong>Available today:</strong> every individual student&rsquo;s own report
              already computes Board urgency and confidence for their own findings, and a
              per-paper diagnostic-strength verdict above. A cohort intervention plan and a
              multi-test trend still need more than one assessment analysed for this class.
            </p>
            <Link href="/admin" className="secondary tiny">
              Find a student&rsquo;s report →
            </Link>
          </div>
        </>
      )}

      <style jsx>{`
        .wrap { max-width: 1180px; margin: 0 auto; padding: 22px 0 60px; }
        .hello {
          display: flex; justify-content: space-between; gap: 18px; flex-wrap: wrap;
          align-items: flex-start; padding: 6px 0 18px;
        }
        .lede { font-size: 16px; color: var(--ink-2); max-width: 56ch; margin: 0; }
        .insight {
          background: var(--mark-soft); border-radius: var(--radius); padding: 16px 18px;
          max-width: 280px; flex: 0 0 260px;
        }
        .insight-eyebrow { margin: 0 0 6px; font-weight: 700; color: var(--mark); font-size: 14px; }
        .insight-body { margin: 0; font-size: 13.5px; color: var(--ink-2); }

        .filterbar {
          position: sticky; top: 0; z-index: 5;
          background: var(--surface); padding: 10px 0; margin-bottom: 18px;
          border-bottom: 1px solid var(--rule);
        }
        .filterbar label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; max-width: 360px; }
        .filterbar select { padding: 8px 10px; font-size: 15px; }

        .kpis {
          display: grid; gap: 14px; margin-bottom: 22px;
          grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        }
        .kpi {
          background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius);
          padding: 18px 20px;
        }
        .kpi-n {
          font-family: var(--font-display), sans-serif; font-size: 32px; font-weight: 800;
          margin: 0 0 4px; letter-spacing: -0.02em;
        }
        .kpi-l { margin: 0; font-size: 13px; color: var(--ink-3); }
        .kpi-sub { margin: 6px 0 0; font-size: 12.5px; font-weight: 600; }
        .kpi-sub.good { color: var(--verify); }
        .kpi-sub.warn { color: var(--risk); }

        .statrow { display: flex; flex-wrap: wrap; gap: 28px; margin: 14px 0; }
        .statvalue { font-size: 22px; font-weight: 700; margin: 0; }
        .strength {
          display: inline-flex; flex-direction: column; gap: 2px;
          padding: 6px 14px; border-radius: var(--radius-sm); margin-bottom: 10px;
        }
        .strength-strong { background: var(--verify-soft); }
        .strength-moderate { background: var(--warn-soft); }
        .strength-limited { background: var(--risk-soft); }
        .strengthvalue { font-size: 20px; font-weight: 700; margin: 0; }
        .verdict { color: var(--ink-2); font-size: 14.5px; margin-top: 10px; }
        .notice-card { background: var(--surface-2); margin-top: 20px; }

        .lossbanner {
          display: flex; align-items: center; gap: 22px; flex-wrap: wrap;
          background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius);
          padding: 18px 22px; margin-bottom: 8px;
        }
        .loss-icon {
          width: 44px; height: 44px; border-radius: var(--radius-sm); background: var(--mark-soft);
          color: var(--mark); display: grid; place-items: center; font-size: 20px; flex: none;
        }
        .loss-body { flex: 1 1 220px; min-width: 0; }
        .loss-title { margin: 0; font-size: 17px; font-weight: 700; font-family: var(--font-display), sans-serif; }
        .loss-stat { text-align: right; }

        .losslist { list-style: none; margin: 10px 0 24px; padding: 0; display: grid; gap: 6px; }
        .losslist li {
          display: flex; align-items: center; gap: 10px; padding: 10px 14px;
          background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius-sm);
        }
        .losslist-label { font-weight: 600; flex: 1 1 auto; }

        .grid3 {
          display: grid; gap: 16px; margin: 20px 0;
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        }
        .card.center { display: flex; flex-direction: column; align-items: center; }
        .donut { width: 160px; height: 160px; margin: 6px 0; }
        .donut-n { font-size: 28px; font-weight: 800; fill: var(--ink); }
        .donut-l { font-size: 11px; fill: var(--ink-3); }
        .legend { list-style: none; margin: 10px 0 0; padding: 0; display: grid; gap: 6px; width: 100%; }
        .legend li { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--ink-2); }
        .dot { width: 9px; height: 9px; border-radius: 999px; flex: none; }

        .bars { display: grid; gap: 12px; }
        .barrow { display: grid; grid-template-columns: 60px 1fr 40px; gap: 10px; align-items: center; }
        .barrow-l { font-size: 13px; font-weight: 600; color: var(--ink-2); }
        .track { height: 8px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
        .fill { height: 100%; border-radius: 999px; }
        .barrow-v { font-size: 12.5px; color: var(--ink-3); text-align: right; }

        .error { color: var(--risk); }

        @media (max-width: 640px) {
          .hello { flex-direction: column; }
          .insight { max-width: 100%; flex: 1 1 auto; }
          .lossbanner { flex-direction: column; align-items: flex-start; }
          .loss-stat { text-align: left; }
        }
      `}</style>
    </main>
  );
}
