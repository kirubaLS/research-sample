"use client";

/**
 * One test, every student who has a mark on it within this teacher key's own scope --
 * the same status bands the rest of the academics screens use. Real data only:
 * GET /admin/teacher/academics/tests/{assessmentId}.
 */

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { StatusBadge } from "@/components/academics/StatusBadge";
import { Mascot } from "@/components/Mascot";
import { api, type TestSummary } from "@/lib/api";
import { getApiKey } from "@/lib/session";

export default function TeacherTestSummaryPage({ params }: { params: Promise<{ assessmentId: string }> }) {
  const { assessmentId } = use(params);
  const [data, setData] = useState<TestSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherAcademicsTestSummary(key, assessmentId)
      .then(setData)
      .catch(() => setError("Could not load this test."));
  }, [assessmentId]);

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

  const counts = data.status_counts;

  return (
    <main className="wrap">
      <div className="hero">
        <p className="eyebrow"><Link href="/teacher/tests">Test</Link> &rsaquo; {data.assessment.title}</p>
        <h1 style={{ margin: 0 }}>{data.assessment.title}</h1>
        <p className="lede">{data.assessment.subject_label}</p>
      </div>

      <div className="tiles" style={{ marginBottom: 20 }}>
        <div className="tile tile-good"><span className="tile-n">{counts.on_track}</span><span className="tile-l">On Track</span></div>
        <div className="tile tile-warn"><span className="tile-n">{counts.needs_attention}</span><span className="tile-l">Needs Attention</span></div>
        <div className="tile tile-warn"><span className="tile-n">{counts.requires_review}</span><span className="tile-l">Requires Review</span></div>
        <div className="tile"><span className="tile-n">{counts.not_assessed}</span><span className="tile-l">Not Yet Assessed</span></div>
      </div>

      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Roll</th>
              <th>Name</th>
              <th>Score</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {data.students.map((s) => (
              <tr key={s.student_id}>
                <td>{s.roll_no}</td>
                <td className="strong">{s.name}</td>
                <td className="num">{s.earned}/{s.available}{s.avg_score_pct != null ? ` (${s.avg_score_pct}%)` : ""}</td>
                <td><StatusBadge status={s.status} /></td>
              </tr>
            ))}
            {data.students.length === 0 && (
              <tr><td colSpan={4} className="muted">No marks recorded for this test yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
