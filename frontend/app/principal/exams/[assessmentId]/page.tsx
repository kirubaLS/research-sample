"use client";

/**
 * One test, every student who has a mark on it -- the same status bands the rest of
 * the academics screens use, computed from this one paper alone.
 */

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Avatar } from "@/components/academics/Avatar";
import { StatusBadge } from "@/components/academics/StatusBadge";
import { StatusOverviewBar } from "@/components/academics/StatusOverviewBar";
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

      <div className="card" style={{ margin: "20px 0" }}>
        <div className="card__body">
          <StatusOverviewBar counts={counts} title="Test Overview" />
        </div>
      </div>

      <div className="table-wrap">
        <table className="table table--hover">
          <thead>
            <tr>
              <th>Roll</th>
              <th>Name</th>
              <th>Score</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.students.map((s) => (
              <tr key={s.student_id}>
                <td>{s.roll_no}</td>
                <td className="strong">
                  <span style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "nowrap" }}>
                    <Avatar name={s.name} seed={s.student_id} size={30} />
                    {s.name}
                  </span>
                </td>
                <td className="num">{s.earned}/{s.available}{s.avg_score_pct != null ? ` (${s.avg_score_pct}%)` : ""}</td>
                <td><StatusBadge status={s.status} /></td>
                <td>
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
  );
}
