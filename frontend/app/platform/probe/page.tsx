"use client";

import { useState } from "react";
import { api, ApiError, ProbeResult } from "@/lib/api";
import { getPlatformKey } from "@/lib/session";
import { PAPER_30B } from "./questions";

/**
 * Does the knowledge base actually place a real question?
 *
 * The ingest summary cannot answer that: a book can load cleanly, agree with its contents
 * page, and still fail at the one thing it exists for.
 */
export default function ProbePage() {
  const [subject] = useState("X.MATH");
  const [text, setText] = useState(
    PAPER_30B.map((p) => `${p.q} | ${p.chapter} | ${p.stem}`).join("\n"),
  );
  const [result, setResult] = useState<ProbeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    const key = getPlatformKey();
    if (!key) return;
    const questions = text
      .split("\n")
      .map((line) => line.split("|").map((s) => s.trim()))
      .filter((parts) => parts.length >= 3 && parts[2])
      .map(([q, chapter, ...rest]) => ({ q, chapter, stem: rest.join(" | ") }));

    if (!questions.length) {
      setError("Each line needs: number | expected chapter | the question stem");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      setResult(await api.probe(key, subject, questions));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the API.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <div className="hero">
        <p className="eyebrow">Knowledge base</p>
        <h1>Probe with real questions</h1>
        <p className="lede">
          A book can load cleanly, agree with its own contents page, and still fail to place
          a real exam question. That is the only thing the knowledge base exists for, and
          nothing in the loading summary reveals it.
        </p>
      </div>

      <div className="card" style={{ marginTop: 22 }}>
        <div className="field">
          <label htmlFor="qs">
            Questions &mdash; one per line, as{" "}
            <span className="mono">number | expected chapter | stem</span>
          </label>
          <textarea
            id="qs"
            rows={12}
            value={text}
            onChange={(e) => setText(e.target.value)}
            style={{ fontFamily: "var(--mono)", fontSize: 13 }}
          />
          <p className="hint">
            Pre-filled with ten stems from the 30(B) paper. Replace them with your own to
            test a paper the knowledge base has never seen.
          </p>
        </div>
        {error && <p className="error">{error}</p>}
        <button onClick={run} disabled={busy}>
          {busy ? "Running…" : "Run the probe"}
        </button>
      </div>

      {result && (
        <>
          <div className="grid three" style={{ marginTop: 22 }}>
            <div className="stat">
              <span className="value">
                {result.hits}/{result.graded}
              </span>
              <span className="label">chapters resolved</span>
            </div>
            <div className="stat">
              <span className="value">{result.mode}</span>
              <span className="label">retrieval</span>
            </div>
            <div className="stat">
              <span className="value">
                {result.embedded}/{result.chunks}
              </span>
              <span className="label">chunks embedded</span>
            </div>
          </div>

          <div className="section-head">
            <h2>Results</h2>
          </div>
          <div className="card" style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid var(--rule)" }}>
                  <th style={{ padding: "8px 10px" }}>Q</th>
                  <th style={{ padding: "8px 10px" }}>Expected</th>
                  <th style={{ padding: "8px 10px" }}>Retrieved</th>
                  <th style={{ padding: "8px 10px" }}>Nearest</th>
                  <th style={{ padding: "8px 10px" }}>Sim.</th>
                  <th style={{ padding: "8px 10px" }}>Familiarity</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row) => (
                  <tr key={row.q} style={{ borderBottom: "1px solid var(--rule)" }}>
                    <td style={{ padding: "8px 10px" }} className="mono">
                      {row.q}
                    </td>
                    <td style={{ padding: "8px 10px" }}>{row.expected ?? "—"}</td>
                    <td
                      style={{
                        padding: "8px 10px",
                        color: row.hit === false ? "var(--mark)" : undefined,
                        fontWeight: row.hit === false ? 600 : undefined,
                      }}
                    >
                      {row.retrieved ?? "—"}
                    </td>
                    <td style={{ padding: "8px 10px" }} className="mono small">
                      {row.nearest ?? "—"}
                    </td>
                    <td style={{ padding: "8px 10px" }} className="mono">
                      {row.similarity.toFixed(2)}
                    </td>
                    <td style={{ padding: "8px 10px" }} className="mono small">
                      {row.familiarity ?? "abstained"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="notice" style={{ marginTop: 18 }}>{result.note}</div>

          {result.rows.some((r) => r.hit === false) && (
            <>
              <div className="section-head">
                <h2>What it got wrong</h2>
              </div>
              <div className="card">
                <p className="cardnote" style={{ marginBottom: 14 }}>
                  These are the useful rows. A miss usually means the question uses a method
                  the book teaches in vocabulary the book never uses &mdash; which is exactly
                  the ADAPTED case, and a real limit rather than a tuning problem.
                </p>
                {result.rows
                  .filter((r) => r.hit === false)
                  .map((r) => (
                    <div key={r.q} style={{ marginBottom: 14 }}>
                      <p className="small">
                        <strong>Q{r.q}</strong> &mdash; expected {r.expected}, got{" "}
                        {r.retrieved} ({r.nearest}, {r.similarity.toFixed(2)})
                      </p>
                      <p className="small muted mono">
                        runners-up:{" "}
                        {r.runners_up
                          .map((u) => `${u.chapter} ${u.similarity.toFixed(2)}`)
                          .join(" · ") || "none"}
                      </p>
                    </div>
                  ))}
              </div>
            </>
          )}
        </>
      )}
    </main>
  );
}
