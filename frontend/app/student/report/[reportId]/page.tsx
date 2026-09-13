"use client";

/**
 * §7.3 -- Student report detail, the "Exam Feedback" brand card. Deliberately narrower
 * than any staff view: no comparison to classmates, no percentile, no board urgency
 * ranking, plain language only (no "R&U/AP/AEC tier" jargon), no share/compare/class-
 * average affordance anywhere on this screen.
 *
 * TODO(backend): Dependency Index #2 -- reads from MOCK_STUDENT_REPORTS, already in the
 * plain-language shape a real student-facing endpoint would return (this translation is a
 * frontend-layer concern per the spec, not a new backend computation).
 */

import { notFound, useRouter } from "next/navigation";
import { use } from "react";
import { Mascot } from "@/components/Mascot";
import { mockStudentReport, mockTrendPose } from "@/lib/mocks/student";

export default function StudentReportDetail({
  params,
}: {
  params: Promise<{ reportId: string }>;
}) {
  const { reportId } = use(params);
  const router = useRouter();
  const report = mockStudentReport(reportId);
  if (!report) return notFound();

  const pose = mockTrendPose(report);
  const improved = report.previousScore != null && report.score > report.previousScore;
  const declined = report.previousScore != null && report.score < report.previousScore;
  const arrow = improved ? "↑" : declined ? "↓" : "→";

  // TODO(backend): Dependency Index #2 -- reuses the existing issued-report PDF export
  // shape (api.issuedReportPdf(key, reportId)) once a real, student-scoped report_id
  // exists. There is no real student session/report_id here, so this stays a mocked
  // download rather than calling a real endpoint with a fabricated id.
  function downloadPdf() {
    window.alert(
      "Download PDF (demo) — this would call the existing issued-report PDF export, " +
        "scoped to this student's own report_id, once real student-issued reports exist.",
    );
  }

  return (
    <main>
      <button type="button" className="secondary tiny" onClick={() => router.push("/student")} style={{ marginBottom: 14 }}>
        ← Your reports
      </button>

      <h1 style={{ marginBottom: 18 }}>{report.subjectLabel} — {report.term} Assessment</h1>

      <div className="examfeedback">
        {pose && <Mascot pose={pose} size={64} />}
        <div className="scorecard">
          <div className="scoreline">
            <strong>{report.score} / {report.outOf}</strong>
            <span className="arrow" aria-hidden>{arrow}</span>
          </div>
          <p className="encourage">{report.encouragement}</p>
        </div>
      </div>

      <div className="section-head">
        <h2>What you&rsquo;re doing well</h2>
      </div>
      <ul className="plainlist">
        {report.doingWell.map((item) => <li key={item}>{item}</li>)}
      </ul>

      <div className="section-head">
        <h2>What to work on next</h2>
      </div>
      <ul className="plainlist">
        {report.workOnNext.map((item) => <li key={item}>{item}</li>)}
      </ul>

      <button type="button" className="secondary" style={{ marginTop: 24 }} onClick={downloadPdf}>
        Download PDF
      </button>

      <style jsx>{`
        .examfeedback {
          display: flex; align-items: center; gap: 18px; margin: 18px 0 28px; flex-wrap: wrap;
        }
        .scorecard {
          flex: 1 1 240px; background: var(--surface); border: 1px solid var(--rule);
          border-radius: var(--radius); padding: 22px; box-shadow: var(--shadow-sm);
        }
        .scoreline { display: flex; align-items: baseline; gap: 10px; }
        .scoreline strong {
          font-size: 34px; font-family: var(--font-display), sans-serif; font-weight: 800;
          color: var(--brand-ink);
        }
        .arrow { font-size: 22px; color: var(--brand-green); }
        .encourage { margin: 8px 0 0; color: var(--ink-2); }
        .plainlist { padding-left: 20px; color: var(--ink-2); }
        .plainlist li { margin-bottom: 4px; }
      `}</style>
    </main>
  );
}
