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
    <main className="content">
      <p className="eyebrow">Knowledge base</p>
      <h1 className="page-title" style={{ marginTop: 6 }}>Probe with real questions</h1>
      <p className="page-sub">
        A book can load cleanly, agree with its own contents page, and still fail to place
        a real exam question. That is the only thing the knowledge base exists for, and
        nothing in the loading summary reveals it.
      </p>

      <div className="card" style={{ marginTop: 22 }}>
        <div className="card__body">
          <div className="field">
            <label htmlFor="qs">
              Questions, one per line, as{" "}
              <span className="mono">number | expected chapter | stem</span>
            </label>
            <textarea
              id="qs"
              className="input"
              rows={12}
              value={text}
              onChange={(e) => setText(e.target.value)}
              style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 13 }}
            />
            <p className="muted small">
              Pre-filled with ten stems from the 30(B) paper. Replace them with your own to
              test a paper the knowledge base has never seen.
            </p>
          </div>
          {error && <div className="evidence evidence--gold" style={{ marginTop: 10 }}><div>{error}</div></div>}
          <button className="btn btn--primary" onClick={run} disabled={busy} style={{ marginTop: 10 }}>
            {busy ? "Running…" : "Run the probe"}
          </button>
        </div>
      </div>

      {result && (
        <>
          <div className="grid grid--3" style={{ marginTop: 22 }}>
            <div className="stat">
              <span className="stat__value">
                {result.hits}/{result.graded}
              </span>
              <span className="stat__label">chapters resolved</span>
            </div>
            <div className="stat">
              <span className="stat__value">{result.confident}/{result.rows.length}</span>
              <span className="stat__label">confident enough to act on</span>
            </div>
            <div className="stat">
              <span className="stat__value">
                {result.embedded}/{result.chunks}
              </span>
              <span className="stat__label">chunks embedded</span>
            </div>
          </div>

          <div className="section__head" style={{ marginTop: 24 }}>
            <h2 className="section-q">Results</h2>
          </div>
          <div className="card">
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Q</th>
                    <th>Expected</th>
                    <th>Retrieved</th>
                    <th>Nearest</th>
                    <th>Sim.</th>
                    <th>Familiarity</th>
                    <th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row) => (
                    <tr key={row.q}>
                      <td className="mono">
                        {row.q}
                      </td>
                      <td>{row.expected ?? "none given"}</td>
                      <td
                        style={{
                          color: row.hit === false ? "var(--risk)" : undefined,
                          fontWeight: row.hit === false ? 600 : undefined,
                        }}
                      >
                        {row.retrieved ?? "nothing"}
                      </td>
                      <td className="mono small">
                        {row.nearest ?? "nothing"}
                      </td>
                      <td className="mono">
                        {row.similarity.toFixed(2)}
                      </td>
                      <td className="mono small">
                        {row.familiarity ?? "abstained"}
                      </td>
                      <td className="mono small">
                        {row.confident ? "confident" : "ask a human"}
                        {!row.agreed && " · split"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="evidence evidence--neutral" style={{ marginTop: 18 }}><div>{result.note}</div></div>

          <div className="evidence evidence--neutral" style={{ marginTop: 12 }}>
            <div>
              Retrieval is <strong>{result.mode}</strong>. A row is confident only when both
              retrievers picked the same chapter <em>and</em> it beat the runner-up by a real
              margin. On the paper this was built against, the one wrong answer had the
              smallest margin of any row, so the rows marked{" "}
              <span className="mono">ask a human</span> are where to spend attention, and
              where 100&nbsp;% actually comes from.
            </div>
          </div>

          {result.rows.some((r) => r.hit === false) && (
            <>
              <div className="section__head" style={{ marginTop: 24 }}>
                <h2 className="section-q">What it got wrong</h2>
              </div>
              <div className="card">
                <div className="card__body">
                  <p className="muted small" style={{ marginBottom: 14 }}>
                    These are the useful rows. A miss usually means the question uses a method
                    the book teaches in vocabulary the book never uses, which is exactly
                    the ADAPTED case, and a real limit rather than a tuning problem.
                  </p>
                  {result.rows
                    .filter((r) => r.hit === false)
                    .map((r) => (
                      <div key={r.q} style={{ marginBottom: 14 }}>
                        <p className="small">
                          <strong>Q{r.q}</strong>: expected {r.expected}, got{" "}
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
              </div>
            </>
          )}
        </>
      )}
    </main>
  );
}
