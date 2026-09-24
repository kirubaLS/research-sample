"use client";

/**
 * Every paper with at least one resolved mark -- the Test tab's landing list. Tap a
 * test to see its own student-by-student summary, the same status bands every other
 * academics screen uses.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
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
        <>
          <TestsSummary tests={tests} />

          <section className="section">
            <div className="section__head">
              <div>
                <h2 className="section-q">Every test</h2>
                <p className="section__lead">Most recent first. Open one to see how each student did.</p>
              </div>
            </div>
            <div className="card">
              <div className="table-wrap">
                <table className="table table--hover">
                  <thead>
                    <tr>
                      <th>Test</th>
                      <th>Subject</th>
                      <th className="num">Students Marked</th>
                      <th className="num">Avg Score</th>
                      <th className="num">Movement</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {tests.map((t) => (
                      <tr key={t.assessment_id}>
                        <td className="strong">{t.title}</td>
                        <td>{t.label}</td>
                        <td className="num">{t.students_marked}</td>
                        <td className="num">
                          {t.avg_score_pct != null ? (
                            <span className="pillnum pillnum--solid" style={{ "--accent": scoreAccent(t.avg_score_pct) } as React.CSSProperties}>
                              {t.avg_score_pct}
                            </span>
                          ) : (
                            <span className="muted">N/A</span>
                          )}
                        </td>
                        <td className="num">
                          {t.delta_pct == null ? (
                            <span className="muted">&mdash;</span>
                          ) : (
                            <span className="delta" data-dir={t.delta_pct >= 0 ? "up" : "down"}>
                              {t.delta_pct >= 0 ? "▲" : "▼"} {Math.abs(t.delta_pct)}%
                            </span>
                          )}
                        </td>
                        <td style={{ textAlign: "right" }}>
                          <Link href={`/principal/exams/${t.assessment_id}`} className="btn btn--sm">
                            View <ArrowRight size={12} />
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function scoreAccent(pct: number): string {
  if (pct >= 78) return "var(--brand-green)";
  if (pct >= 60) return "var(--brand-gold)";
  return "var(--risk)";
}

/** A real, school-wide read on the same rows the table below lists one at a time:
 * the overall average across every test with marks, how many tests that spans, and
 * the single most-improved test -- nothing here is a second computation, every value
 * is derived directly from the `AcademicTestRow`s the API already returned. */
function TestsSummary({ tests }: { tests: AcademicTestRow[] }) {
  const scored = tests.filter((t) => t.avg_score_pct != null);
  const overallAvg = scored.length
    ? Math.round(scored.reduce((sum, t) => sum + (t.avg_score_pct ?? 0), 0) / scored.length)
    : null;
  const withDelta = tests.filter((t) => t.delta_pct != null);
  const biggestMover = withDelta.length
    ? withDelta.reduce((a, b) => (Math.abs(b.delta_pct ?? 0) > Math.abs(a.delta_pct ?? 0) ? b : a))
    : null;

  return (
    <div className="grid grid--3" style={{ marginTop: 20 }}>
      <div className="stat">
        <div className="stat__label">Average score across all tests</div>
        <div className="stat__value">{overallAvg != null ? `${overallAvg}%` : "N/A"}</div>
      </div>
      <div className="stat">
        <div className="stat__label">Tests with marks recorded</div>
        <div className="stat__value">{tests.length}</div>
      </div>
      <div className="stat">
        <div className="stat__label">Biggest movement</div>
        <div className="stat__value stat__value--sm">
          {biggestMover ? biggestMover.title : "-"}
          {biggestMover && biggestMover.delta_pct != null && (
            <span className="small muted" style={{ fontWeight: 400 }}>
              {" "}
              · <span className="delta" data-dir={biggestMover.delta_pct >= 0 ? "up" : "down"} style={{ fontSize: "inherit" }}>
                {biggestMover.delta_pct >= 0 ? "▲" : "▼"} {Math.abs(biggestMover.delta_pct)}%
              </span>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
