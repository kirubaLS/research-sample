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
    <main>
      <div className="hero">
        <h1>Hi {getStudentName()}</h1>
      </div>

      {error && <p className="error">{error}</p>}

      {!reports && !error && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      )}

      {reports && reports.length === 0 && (
        <div style={{ textAlign: "center", padding: "40px 0" }}>
          <Mascot pose="hello" size={72} />
          <p className="lede" style={{ marginTop: 14 }}>
            Nothing shared with you yet. Your teacher will let you know when a report is
            ready.
          </p>
        </div>
      )}

      {reports && reports.length > 0 && (
        <>
          <div className="section-head">
            <h2>Your reports</h2>
          </div>
          <div className="stack" style={{ gap: 10 }}>
            {reports.map((r) => (
              <div className="card row between" key={r.report_id}>
                <div>
                  <strong>{r.assessment_title ?? "Report"}</strong>
                  <p className="cardnote">
                    {r.earned} / {r.available} marks
                    {r.shared_at && ` · shared ${new Date(r.shared_at).toLocaleDateString()}`}
                  </p>
                </div>
                <Link href={`/student/report/${r.report_id}`}>
                  <button type="button">Open</button>
                </Link>
              </div>
            ))}
          </div>
        </>
      )}
    </main>
  );
}
