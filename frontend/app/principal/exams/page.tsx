"use client";

/**
 * Every paper with at least one resolved mark -- the Test tab's landing list. Tap a
 * test to see its own student-by-student summary, the same status bands every other
 * academics screen uses.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { Mascot } from "@/components/Mascot";
import { api, type AcademicTestRow } from "@/lib/api";
import { downloadBlob } from "@/lib/download";
import { getApiKey } from "@/lib/session";

export default function TestsTabPage() {
  const [tests, setTests] = useState<AcademicTestRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"pdf" | "xlsx" | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .academicsTests(key)
      .then((res) => setTests(res.tests))
      .catch(() => setError("Could not load tests."));
  }, []);

  async function download(kind: "pdf" | "xlsx") {
    const key = getApiKey();
    if (!key) return;
    setDownloading(kind);
    try {
      const blob = kind === "pdf" ? await api.academicsTestsPdf(key) : await api.academicsTestsXlsx(key);
      downloadBlob(blob, `tests.${kind}`);
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
          <p className="eyebrow">Test</p>
          <h1 className="page-title">Every Test</h1>
          <p className="page-sub">Every paper with marks recorded on it -- open one to see how the whole class did.</p>
        </div>
        {tests && tests.length > 0 && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" className="btn btn--ghost" disabled={!!downloading} onClick={() => download("xlsx")}>
              {downloading === "xlsx" ? "Preparing…" : "Download Excel"}
            </button>
            <button type="button" className="btn btn--primary" disabled={!!downloading} onClick={() => download("pdf")}>
              {downloading === "pdf" ? "Preparing…" : "Download PDF"}
            </button>
          </div>
        )}
      </div>

      {error && <p style={{ color: "var(--risk)", fontSize: 13.5, marginTop: 12 }}>{error}</p>}
      {!tests && !error && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 20 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      )}
      {tests && tests.length === 0 && <p className="muted" style={{ marginTop: 20 }}>No test has any marks recorded yet.</p>}

      {tests && tests.length > 0 && (
        <div className="table-wrap" style={{ marginTop: 20 }}>
          <table className="table table--hover">
            <thead>
              <tr>
                <th>Test</th>
                <th>Subject</th>
                <th>Students Marked</th>
                <th>Avg Score</th>
                <th>Movement</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {tests.map((t) => (
                <tr key={t.assessment_id}>
                  <td className="strong">{t.title}</td>
                  <td>{t.label}</td>
                  <td className="num">{t.students_marked}</td>
                  <td className="num">{t.avg_score_pct != null ? `${t.avg_score_pct}%` : "N/A"}</td>
                  <td className="num">
                    {t.delta_pct == null ? (
                      <span className="muted">&mdash;</span>
                    ) : (
                      <span className="delta" data-dir={t.delta_pct >= 0 ? "up" : "down"}>
                        {t.delta_pct >= 0 ? "▲" : "▼"} {Math.abs(t.delta_pct)}%
                      </span>
                    )}
                  </td>
                  <td>
                    <Link href={`/principal/exams/${t.assessment_id}`}>
                      <button type="button" className="btn btn--ghost btn--sm">View</button>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
