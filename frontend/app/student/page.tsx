"use client";

// §7.2 -- Student home, "My Reports". Flat list, most recent first, no filters/search.
// Real data: GET /student/reports, gated by the StudentSession token the layout above
// already validated on mount.

import Link from "next/link";
import { useEffect, useState } from "react";
import { Mascot } from "@/components/Mascot";
import { api, type StudentReportRow } from "@/lib/api";
import { getStudentName, getStudentSession } from "@/lib/session";

export default function StudentHome() {
  const [reports, setReports] = useState<StudentReportRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getStudentSession();
    if (!token) return;
    api
      .studentReports(token)
      .then((res) => setReports(res.reports))
      .catch(() => setError("Could not load your reports. Try again in a minute."));
  }, []);

  return (
    <main className="content" style={{ maxWidth: 720 }}>
      <h1 className="page-title" style={{ marginBottom: 16 }}>Hi {getStudentName()}</h1>

      {error && (
        <div className="evidence evidence--gold">
          <div>{error}</div>
        </div>
      )}

      {!reports && !error && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      )}

      {reports && reports.length === 0 && (
        <div className="empty-hero">
          <Mascot pose="hello" size={72} />
          <p>
            Nothing shared with you yet. Your teacher will let you know when a report is
            ready.
          </p>
        </div>
      )}

      {reports && reports.length > 0 && (
        <>
          <div className="section__head">
            <h2 className="section-q">Your reports</h2>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {reports.map((r) => (
              <div className="report-card" key={r.report_id}>
                <div>
                  <strong className="report-card__subj">{r.assessment_title ?? "Report"}</strong>
                  <p className="muted small" style={{ margin: "2px 0 0" }}>
                    {r.earned} / {r.available} marks
                    {r.shared_at && ` · shared ${new Date(r.shared_at).toLocaleDateString()}`}
                  </p>
                </div>
                <Link href={`/student/report/${r.report_id}`}>
                  <button type="button" className="btn btn--primary btn--sm">Open</button>
                </Link>
              </div>
            ))}
          </div>
        </>
      )}
    </main>
  );
}
