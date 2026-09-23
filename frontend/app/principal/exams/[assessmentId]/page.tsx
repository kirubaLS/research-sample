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
      <div className="hero row between" style={{ alignItems: "flex-end" }}>
        <div>
          <p className="eyebrow"><Link href="/principal/exams">Test</Link> &rsaquo; {data.assessment.title}</p>
          <h1 style={{ margin: 0 }}>{data.assessment.title}</h1>
          <p className="lede">{data.assessment.subject_label}</p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button type="button" className="secondary" disabled={!!downloading} onClick={() => download("xlsx")}>
            {downloading === "xlsx" ? "Preparing…" : "Download Excel"}
          </button>
          <button type="button" disabled={!!downloading} onClick={() => download("pdf")}>
            {downloading === "pdf" ? "Preparing…" : "Download PDF"}
          </button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <StatusOverviewBar counts={counts} title="Test Overview" />
      </div>

      <div className="tablewrap">
        <table>
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
                  <span className="row" style={{ gap: 10, flexWrap: "nowrap" }}>
                    <Avatar name={s.name} seed={s.student_id} size={30} />
                    {s.name}
                  </span>
                </td>
                <td className="num">{s.earned}/{s.available}{s.avg_score_pct != null ? ` (${s.avg_score_pct}%)` : ""}</td>
                <td><StatusBadge status={s.status} /></td>
                <td>
                  <Link href={`/principal/students/${s.student_id}`}>
                    <button type="button" className="secondary tiny">View</button>
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
    </main>
  );
}
