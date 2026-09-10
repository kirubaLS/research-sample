"use client";

/**
 * Board Intelligence -- the principal-facing read of one assessment's Board readiness.
 *
 * Everything on this page is either read straight from GET /reports/paper/{id} (the
 * paper's own diagnostic quality -- item statistics, tier alignment, a real STRONG /
 * MODERATE / LIMITED verdict) or is an honest "not available yet" state. Nothing here is
 * a mock number standing in for intelligence this deployment cannot compute yet: the
 * cohort-wide sections of the BoardX spec -- marks-loss across every student, Board
 * Urgency vs Impact, the Student Potential Ladder, section comparison, a cohort
 * intervention plan -- need a new aggregation layer across every student's marks that
 * does not exist in this codebase yet (see the per-student report instead, linked below,
 * which already computes board urgency and confidence for one student's own paper).
 *
 * Per the spec's own rule (Section 25): an unbuilt section is a plain sentence saying so,
 * never a blank chart or an invented figure.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError, ApiUnreachable, type Overview, type PaperReport } from "@/lib/api";
import { getApiKey } from "@/lib/session";

const STRENGTH_COPY: Record<PaperReport["diagnostic_strength"], string> = {
  STRONG: "This paper is a solid basis for the findings below.",
  MODERATE:
    "This paper provides reasonable evidence, but interpret findings in under-tested areas with caution.",
  LIMITED:
    "This paper's tier balance or item consistency is weak enough that findings here should be treated as a starting signal, not a conclusion.",
};

function pct(n: number | null | undefined): string {
  return n == null ? "—" : `${Math.round(n * 100)}%`;
}

export default function BoardXPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [assessmentId, setAssessmentId] = useState<string>("");
  const [report, setReport] = useState<PaperReport | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
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
  }, [assessmentId]);

  if (loadError) return <main className="wrap"><p className="error">{loadError}</p></main>;
  if (!overview) return <main className="wrap"><p className="muted">Loading…</p></main>;

  const assessment = overview.assessments.find((a) => a.id === assessmentId);
  const subjectsAnalysed = assessment ? 1 : 0;

  return (
    <main className="wrap">
      <section className="hello">
        <p className="eyebrow">{overview.school.name}</p>
        <h1>Board Intelligence</h1>
        <p className="lede">
          Convert one assessment into actionable Board intelligence -- where students are
          losing marks that matter for the Board, and how much to trust the paper that
          found them.
        </p>
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
          <section className="card">
            <h2>{assessment.title}</h2>
            <div className="statrow">
              <div>
                <p className="statvalue">{report ? report.students : "—"}</p>
                <p className="small muted">Students Analysed</p>
              </div>
              <div>
                <p className="statvalue">{subjectsAnalysed}</p>
                <p className="small muted">Subjects Analysed</p>
              </div>
              <div>
                <p className="statvalue" title="No section-level join exists yet for this view">—</p>
                <p className="small muted">Sections Analysed</p>
              </div>
              <div>
                <p className="statvalue">1 Test</p>
                <p className="small muted">Assessment Evidence</p>
              </div>
            </div>
            <p className="notice">
              <strong>Early Intelligence:</strong> this analysis is based on {assessment.title}.
              Trend, consistency and multi-test prediction insights will become available
              after additional assessments are analysed.
            </p>
          </section>

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
                  <p className="small muted">
                    Application Questions
                    {report.typology_alignment.target.AP != null && (
                      <> · Board Expectation {pct(report.typology_alignment.target.AP)}</>
                    )}
                  </p>
                </div>
                <div>
                  <p className="statvalue">{pct(report.higher_order_share)}</p>
                  <p className="small muted">
                    Higher-Order / Competency Questions
                    {report.typology_alignment.target.AEC != null && (
                      <> · Board Expectation {pct(report.typology_alignment.target.AEC)}</>
                    )}
                  </p>
                </div>
                <div>
                  <p className="statvalue">
                    {report.cronbach_alpha == null ? "—" : report.cronbach_alpha.toFixed(2)}
                  </p>
                  <p className="small muted">Item Consistency (α)</p>
                </div>
                <div>
                  <p className="statvalue">{report.flagged_items.length}</p>
                  <p className="small muted">Items Flagged for Review</p>
                </div>
              </div>

              <p className="verdict">{report.typology_alignment.verdict}</p>
            </div>
          )}

          <section className="section-head">
            <h2>Where are we losing Board marks?</h2>
          </section>
          <div className="card notice-card">
            <p>
              Cohort-wide marks-loss, Board Urgency vs Impact, the Student Potential
              Ladder, and section comparison all need one student&rsquo;s marks compared
              against every other student&rsquo;s on the same paper -- an aggregation this
              deployment does not compute yet, so nothing is shown here rather than a
              number that cannot be checked.
            </p>
            <p className="small muted">
              Available today: every individual student&rsquo;s own report already
              computes Board urgency and confidence for their own findings.
            </p>
            <Link href="/admin" className="secondary tiny">
              Find a student&rsquo;s report →
            </Link>
          </div>
        </>
      )}

      <style jsx>{`
        .wrap { max-width: 980px; margin: 0 auto; padding: 22px 0 60px; }
        .hello { padding: 6px 0 18px; }
        .lede { font-size: 16px; color: var(--ink-2); max-width: 62ch; }
        .filterbar {
          position: sticky; top: 0; z-index: 5;
          background: var(--bg, #fff); padding: 10px 0; margin-bottom: 18px;
          border-bottom: 1px solid var(--line, #e6e6e6);
        }
        .filterbar label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; max-width: 360px; }
        .filterbar select { padding: 8px 10px; font-size: 15px; }
        .statrow { display: flex; flex-wrap: wrap; gap: 28px; margin: 14px 0; }
        .statvalue { font-size: 22px; font-weight: 600; margin: 0; }
        .strength {
          display: inline-flex; flex-direction: column; gap: 2px;
          padding: 6px 14px; border-radius: 8px; margin-bottom: 10px;
        }
        .strength-strong { background: #e7f2ea; }
        .strength-moderate { background: #fdf1de; }
        .strength-limited { background: #fbe8e8; }
        .strengthvalue { font-size: 20px; font-weight: 700; margin: 0; }
        .verdict { color: var(--ink-2); font-size: 14.5px; margin-top: 10px; }
        .notice-card { background: var(--warn-soft, #fdf6ea); }
        .error { color: #b00020; }
      `}</style>
    </main>
  );
}
