"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Diagnosis } from "@/components/Diagnosis";
import { ScriptViewer } from "@/components/ScriptViewer";
import {
  api,
  type InterestReport,
  type IssuedReport,
  type SatPaper,
  type ScanDoc,
  type StudentDiagnosis,
} from "@/lib/api";
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
  const [noInterest, setNoInterest] = useState(false);
  const [papers, setPapers] = useState<SatPaper[]>([]);
  const [who, setWho] = useState<{ name: string; roll_no: string } | null>(null);
  const [paperId, setPaperId] = useState("");
  const [diagnosis, setDiagnosis] = useState<StudentDiagnosis | null>(null);
  const [ready, setReady] = useState(false);
  const [scripts, setScripts] = useState<ScanDoc[]>([]);
  const [issued, setIssued] = useState<IssuedReport[]>([]);
  const [issuing, setIssuing] = useState(false);
  const [issuedNote, setIssuedNote] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  // The two halves are independent. A student who sat a test but no interest inventory,
  // or the reverse, has a real record either way -- loading them together meant one
  // missing half took the whole page down and hid the other.
  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api.interestReport(key, studentId).then(setReport).catch(() => setNoInterest(true));
    api
      .studentPapers(key, studentId)
      .then((body) => {
        setWho(body.student);
        setPapers(body.assessments);
        if (body.assessments.length > 0) setPaperId(body.assessments[0].assessment_id);
      })
      .catch(() => undefined)
      .finally(() => setReady(true));
    api.studentDocuments(key, studentId).then((b) => setScripts(b.documents)).catch(() => undefined);
    api.issuedReports(key, studentId).then((b) => setIssued(b.reports)).catch(() => undefined);
  }, [studentId]);

  async function issue() {
    const key = getApiKey();
    if (!key || !paperId) return;
    const by = window.prompt("Your name, to go on the issued report:", "");
    if (by === null) return;
    setIssuing(true);
    try {
      const record = await api.issueReport(key, studentId, paperId, by);
      setIssued((all) => [record, ...all]);
      setIssuedNote(
        "Saved. This copy keeps the figures exactly as they read now, even if a mark is " +
          "corrected later.",
      );
    } catch {
      setIssuedNote("Could not save a copy. Nothing was stored.");
    } finally {
      setIssuing(false);
    }
  }

  async function downloadPdf(reportId: string) {
    const key = getApiKey();
    if (!key) return;
    setDownloadingId(reportId);
    try {
      const blob = await api.issuedReportPdf(key, reportId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `report-${who?.roll_no ?? studentId}-${reportId.slice(0, 8)}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setIssuedNote("Could not fetch the PDF. Try again.");
    } finally {
      setDownloadingId(null);
    }
  }

  useEffect(() => {
    const key = getApiKey();
    if (!key || !paperId) {
      setDiagnosis(null);
      return;
    }
    api.studentDiagnosis(key, studentId, paperId).then(setDiagnosis).catch(() => setDiagnosis(null));
  }, [studentId, paperId]);

  if (!ready) {
    return (
      <main className="content" style={{ maxWidth: 720 }}>
        <p className="muted">Loading…</p>
      </main>
    );
  }

  const lead = report?.holland_code?.[0];
  const streams = Object.entries(report?.stream_fit ?? {}).sort((a, b) => b[1] - a[1]);
  const name = report?.student.name ?? who?.name ?? "This student";
  const roll = report?.student.roll_no ?? who?.roll_no ?? "";

  return (
    <main className="content" style={{ maxWidth: 720 }}>
      <div className="noprint">
        <p className="eyebrow">
          <Link href="/admin" style={{ color: "inherit" }}>
            ← Dashboard
          </Link>
        </p>
        <h1 className="page-title" style={{ marginTop: 6 }}>{name}</h1>
        <p className="page-sub">{roll ? `Roll ${roll}` : "Student record"}</p>
      </div>

      <div className="section__head" style={{ marginTop: 24 }}>
        <h2 className="section-q">Test results</h2>
      </div>
      {papers.length === 0 ? (
        <p className="muted">
          No marks have been entered for this student yet. They are entered on the Answer
          sheet screen, against a paper that has been read and mapped to the book.
        </p>
      ) : (
        <>
          {papers.length > 1 && (
            <div className="card noprint field" style={{ marginBottom: 14 }}>
              <div className="card__body">
                <label htmlFor="paper" className="small">
                  Paper
                </label>
                <select
                  id="paper"
                  className="select"
                  value={paperId}
                  onChange={(e) => setPaperId(e.target.value)}
                  style={{ marginTop: 6, width: "100%" }}
                >
                  {papers.map((p) => (
                    <option key={p.assessment_id} value={p.assessment_id}>
                      {p.title} · {p.subject_label} · {p.questions_marked} marked
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}
          {diagnosis && who ? (
            <>
              <Diagnosis report={diagnosis} student={who} />
              <div className="noprint" style={{ marginTop: 14 }}>
                <button className="btn btn--ghost" onClick={issue} disabled={issuing}>
                  {issuing ? "Saving…" : "Save a copy of this report"}
                </button>
                {issuedNote && <p className="small muted">{issuedNote}</p>}
                {issued.length > 0 && (
                  <>
                    <p className="small muted">
                      {issued.length} cop{issued.length === 1 ? "y" : "ies"} saved. Latest by{" "}
                      {issued[0].issued_by || "someone unnamed"} on{" "}
                      {issued[0].issued_at?.slice(0, 10)}, {issued[0].earned} of{" "}
                      {issued[0].available}.
                    </p>
                    <button
                      className="btn btn--ghost btn--sm"
                      onClick={() => downloadPdf(issued[0].report_id)}
                      disabled={downloadingId === issued[0].report_id}
                      style={{ marginTop: 6 }}
                    >
                      {downloadingId === issued[0].report_id ? "Preparing…" : "Download as PDF"}
                    </button>
                  </>
                )}
              </div>
            </>
          ) : (
            <p className="muted">Loading the result…</p>
          )}
        </>
      )}

      {issued.length > 1 && (
        <>
          <div className="section__head noprint" style={{ marginTop: 24 }}>
            <div>
              <p className="eyebrow">Every issued report</p>
              <h2 className="section-q">Progress over time</h2>
            </div>
          </div>
          <ol className="noprint" style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
            {[...issued]
              .sort((a, b) => (a.issued_at ?? "").localeCompare(b.issued_at ?? ""))
              .map((r) => {
                const pct = r.available > 0 ? Math.round((r.earned / r.available) * 100) : 0;
                return (
                  <li key={r.report_id} className="bar-row" style={{ gridTemplateColumns: "200px 1fr 46px auto" }}>
                    <span className="bar-row__label">
                      {r.assessment_title ?? "Untitled paper"}
                      <span className="small muted"> · {r.issued_at?.slice(0, 10)}</span>
                    </span>
                    <span className="bar">
                      <span className="bar__fill" style={{ width: `${pct}%`, display: "block" }} />
                    </span>
                    <span className="bar-row__val">{pct}%</span>
                    <button
                      className="btn btn--ghost btn--sm"
                      onClick={() => downloadPdf(r.report_id)}
                      disabled={downloadingId === r.report_id}
                    >
                      {downloadingId === r.report_id ? "…" : "PDF"}
                    </button>
                  </li>
                );
              })}
          </ol>
        </>
      )}

      {scripts.length > 0 && (
        <>
          <div className="section__head" style={{ marginTop: 24 }}>
            <h2 className="section-q">Answer scripts</h2>
          </div>
          {scripts.map((doc) => (
            <div className="card" key={doc.document_id} style={{ marginBottom: 12 }}>
              <div className="card__body">
                <p className="small" style={{ marginTop: 0 }}>
                  <strong>{doc.assessment_title ?? "Paper"}</strong> ·{" "}
                  {doc.page_count} page{doc.page_count === 1 ? "" : "s"} · stored{" "}
                  {doc.uploaded_at?.slice(0, 10)}
                </p>
                <ScriptViewer doc={doc} />
                <p className="small muted" style={{ marginBottom: 0, marginTop: 10 }}>
                  The script the marks were read from.
                </p>
              </div>
            </div>
          ))}
        </>
      )}

      {noInterest && (
        <>
          <div className="section__head" style={{ marginTop: 24 }}>
            <h2 className="section-q">Interest profile</h2>
          </div>
          <p className="muted">This student has not completed the interest test yet.</p>
        </>
      )}

      {report && (
        <>
          {report.validity !== "valid" && (
            <div className="evidence evidence--gold" style={{ marginTop: 14 }}>
              <div>
                <strong>This session was flagged as {report.validity}.</strong>{" "}
                {report.validity_detail?.reasons?.join("; ")}. Treat the result with caution and
                consider a retest.
              </div>
            </div>
          )}

          {report.recommendation_withheld ? (
            <div className="evidence evidence--neutral" style={{ marginTop: 16 }}>
              <div>
                <strong>No stream is indicated.</strong> {report.withheld_reason}
              </div>
            </div>
          ) : (
            <div className="card" style={{ marginTop: 16, borderLeft: "3px solid var(--brand-teal)" }}>
              <div className="card__body">
                <p className="eyebrow">Holland code</p>
                <h2 className="mono" style={{ fontSize: 34, letterSpacing: "0.12em" }}>
                  {report.holland_code}
                </h2>
                <p className="muted small">
                  {report.holland_code
                    ?.split("")
                    .map((c) => SCALE_NAMES[c])
                    .join(" · ")}
                </p>
              </div>
            </div>
          )}

          <div className="section__head" style={{ marginTop: 24 }}>
            <h2 className="section-q">Interest profile</h2>
          </div>
          <div className="card">
            <div className="card__body">
              {report.scales.map((s) => (
                <div className="bar-row" key={s.scale}>
                  <span className="bar-row__label">{SCALE_NAMES[s.scale] ?? s.scale}</span>
                  <div className="bar" title={`95% interval ${s.ci[0]} to ${s.ci[1]}`}>
                    <div
                      className="bar__fill"
                      style={{
                        width: `${Math.max(2, s.percentile)}%`,
                        background: s.scale === lead ? "var(--brand-gold)" : undefined,
                      }}
                    />
                  </div>
                  <span className="bar-row__val">{Math.round(s.percentile)}</span>
                </div>
              ))}
              <p className="small muted" style={{ marginTop: 14, marginBottom: 0 }}>
                Percentile against the cohort, shrunk toward the prior while the cohort is small.
                Hover a bar for its 95% interval. They are wide on purpose at this sample size.
              </p>
            </div>
          </div>

          {!report.recommendation_withheld && streams.length > 0 && (
            <>
              <div className="section__head" style={{ marginTop: 24 }}>
                <h2 className="section-q">Stream fit</h2>
              </div>
              <div className="card">
                <div className="card__body">
                  {streams.map(([name, value], i) => (
                    <div className="bar-row" key={name}>
                      <span className="bar-row__label">{name}</span>
                      <div className="bar">
                        <div
                          className="bar__fill"
                          style={{
                            width: `${Math.max(2, value * 100)}%`,
                            background: i === 0 ? "var(--brand-gold)" : undefined,
                          }}
                        />
                      </div>
                      <span className="bar-row__val">{Math.round(value * 100)}</span>
                    </div>
                  ))}
                  <p className="small muted" style={{ marginTop: 14, marginBottom: 0 }}>
                    An indication for a counselling conversation, not a decision. Differentiation{" "}
                    {report.differentiation?.toFixed(2)} · consistency {report.consistency}/3.
                  </p>
                </div>
              </div>
            </>
          )}
        </>
      )}

      <style jsx>{`
        @media print {
          .noprint {
            display: none !important;
          }
        }
      `}</style>
    </main>
  );
}
