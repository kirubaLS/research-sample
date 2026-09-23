"use client";

/**
 * §7.3 -- Student report detail, the "Exam Feedback" brand card. Deliberately narrower
 * than any staff view: no comparison to classmates, no percentile, no board urgency
 * ranking, plain language only (no "R&U/AP/AEC tier" jargon), no share/compare/class-
 * average affordance anywhere on this screen.
 *
 * Real data: GET /student/reports/{id}, the same payload `student_report` computes for
 * staff (see app/api/reports.py), re-read here into plain language -- a frontend-layer
 * translation, not a second backend computation. No trend/previous-score line: nothing
 * in that payload names a prior report to compare against, so this shows the one score
 * honestly rather than inventing a comparison. No PDF download either, for the same
 * reason -- the existing PDF export is staff-only (require_reader); a student-scoped
 * one does not exist yet.
 */

import { notFound, useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { Mascot } from "@/components/Mascot";
import { api, type StudentReportDetail } from "@/lib/api";
import { getStudentSession } from "@/lib/session";

interface NamedFinding {
  label?: string;
}

export default function StudentReportDetail({
  params,
}: {
  params: Promise<{ reportId: string }>;
}) {
  const { reportId } = use(params);
  const router = useRouter();
  const [report, setReport] = useState<StudentReportDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getStudentSession();
    if (!token) return;
    api
      .studentReport(token, reportId)
      .then(setReport)
      .catch(() => setError("not-found"));
  }, [reportId]);

  if (error) return notFound();
  if (!report) {
    return (
      <main>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      </main>
    );
  }

  const payload = report.payload as {
    strengths?: NamedFinding[];
    focus?: NamedFinding[];
  };
  const doingWell = (payload.strengths ?? []).map((f) => f.label).filter(Boolean) as string[];
  const workOnNext = (payload.focus ?? []).map((f) => f.label).filter(Boolean) as string[];
  const rate = report.available > 0 ? report.earned / report.available : null;
  const pose = rate == null ? "hello" : rate >= 0.75 ? "achieve" : rate >= 0.4 ? "improve" : "practice";

  return (
    <main>
      <button type="button" className="btn--ghost btn--sm" onClick={() => router.push("/student")} style={{ marginBottom: 14 }}>
        ← Your reports
      </button>

      <h1 style={{ marginBottom: 18 }}>{report.assessment_title ?? "Report"}</h1>

      <div className="examfeedback">
        <Mascot pose={pose} size={64} />
        <div className="scorecard">
          <div className="scoreline">
            <strong>{report.earned} / {report.available}</strong>
          </div>
        </div>
      </div>

      {doingWell.length > 0 && (
        <>
          <div className="section-head">
            <h2>What you&rsquo;re doing well</h2>
          </div>
          <ul className="plainlist">
            {doingWell.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </>
      )}

      {workOnNext.length > 0 && (
        <>
          <div className="section-head">
            <h2>What to work on next</h2>
          </div>
          <ul className="plainlist">
            {workOnNext.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </>
      )}

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
