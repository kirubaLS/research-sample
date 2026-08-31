"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { api, type InterestReport } from "@/lib/api";
import { getApiKey } from "@/lib/session";

const SCALE_NAMES: Record<string, string> = {
  R: "Realistic",
  I: "Investigative",
  A: "Artistic",
  S: "Social",
  E: "Enterprising",
  C: "Conventional",
};

export default function StudentReport({ params }: { params: Promise<{ studentId: string }> }) {
  const { studentId } = use(params);
  const [report, setReport] = useState<InterestReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .interestReport(key, studentId)
      .then(setReport)
      .catch(() => setError("No completed test for this student yet."));
  }, [studentId]);

  if (error) {
    return (
      <main className="narrow">
        <p className="error">{error}</p>
      </main>
    );
  }
  if (!report) {
    return (
      <main className="narrow">
        <p className="muted">Loading…</p>
      </main>
    );
  }

  const lead = report.holland_code?.[0];
  const streams = Object.entries(report.stream_fit ?? {}).sort((a, b) => b[1] - a[1]);

  return (
    <main className="narrow">
      <div className="hero">
        <p className="eyebrow">
          <Link href="/admin" style={{ color: "inherit" }}>
            ← Dashboard
          </Link>
        </p>
        <h1>{report.student.name}</h1>
        <p className="lede">
          Roll {report.student.roll_no} · interest profile
        </p>
      </div>

      {report.validity !== "valid" && (
        <div className="notice warn" style={{ marginTop: 14 }}>
          <strong>This session was flagged as {report.validity}.</strong>{" "}
          {report.validity_detail?.reasons?.join("; ")}. Treat the result with caution and
          consider a retest.
        </div>
      )}

      {report.recommendation_withheld ? (
        <div className="notice mark" style={{ marginTop: 16 }}>
          <strong>No stream is indicated.</strong> {report.withheld_reason}
        </div>
      ) : (
        <div className="card accentbar" style={{ marginTop: 16 }}>
          <p className="eyebrow">Holland code</p>
          <h2 className="mono" style={{ fontSize: 34, letterSpacing: "0.12em" }}>
            {report.holland_code}
          </h2>
          <p className="cardnote">
            {report.holland_code
              ?.split("")
              .map((c) => SCALE_NAMES[c])
              .join(" · ")}
          </p>
        </div>
      )}

      <div className="section-head">
        <h2>Interest profile</h2>
      </div>
      <div className="card">
        {report.scales.map((s) => (
          <div className="scalerow" key={s.scale}>
            <span className="nm">{SCALE_NAMES[s.scale] ?? s.scale}</span>
            <div className="scaletrack" title={`95% interval ${s.ci[0]} to ${s.ci[1]}`}>
              <div
                className={`scalefill ${s.scale === lead ? "lead" : ""}`}
                style={{ width: `${Math.max(2, s.percentile)}%` }}
              />
            </div>
            <span className="pct">{Math.round(s.percentile)}</span>
          </div>
        ))}
        <p className="small muted" style={{ marginTop: 14, marginBottom: 0 }}>
          Percentile against the cohort, shrunk toward the prior while the cohort is small.
          Hover a bar for its 95% interval. They are wide on purpose at this sample size.
        </p>
      </div>

      {!report.recommendation_withheld && streams.length > 0 && (
        <>
          <div className="section-head">
            <h2>Stream fit</h2>
          </div>
          <div className="card">
            {streams.map(([name, value], i) => (
              <div className="scalerow" key={name}>
                <span className="nm">{name}</span>
                <div className="scaletrack">
                  <div
                    className={`scalefill ${i === 0 ? "lead" : ""}`}
                    style={{ width: `${Math.max(2, value * 100)}%` }}
                  />
                </div>
                <span className="pct">{Math.round(value * 100)}</span>
              </div>
            ))}
            <p className="small muted" style={{ marginTop: 14, marginBottom: 0 }}>
              An indication for a counselling conversation, not a decision. Differentiation{" "}
              {report.differentiation?.toFixed(2)} · consistency {report.consistency}/3.
            </p>
          </div>
        </>
      )}
    </main>
  );
}
