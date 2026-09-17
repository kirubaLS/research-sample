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
    <main className="wrap">
      <div className="hero row between" style={{ alignItems: "flex-end" }}>
        <div>
          <p className="eyebrow">Test</p>
          <h1 style={{ margin: 0 }}>Every Test</h1>
          <p className="lede">Every paper with marks recorded on it -- open one to see how the whole class did.</p>
        </div>
        {tests && tests.length > 0 && (
          <div className="row" style={{ gap: 8 }}>
            <button type="button" className="secondary" disabled={!!downloading} onClick={() => download("xlsx")}>
              {downloading === "xlsx" ? "Preparing…" : "Download Excel"}
            </button>
            <button type="button" disabled={!!downloading} onClick={() => download("pdf")}>
              {downloading === "pdf" ? "Preparing…" : "Download PDF"}
            </button>
          </div>
        )}
      </div>

      {error && <p className="error">{error}</p>}
      {!tests && !error && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      )}
      {tests && tests.length === 0 && <p className="muted">No test has any marks recorded yet.</p>}

      {tests && tests.length > 0 && (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Test</th>
                <th>Subject</th>
                <th>Students Marked</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {tests.map((t) => (
                <tr key={t.assessment_id}>
                  <td className="strong">{t.title}</td>
                  <td>{t.label}</td>
                  <td className="num">{t.students_marked}</td>
                  <td>
                    <Link href={`/admin/academics/tests/${t.assessment_id}`}>
                      <button type="button" className="secondary tiny">View</button>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
