"use client";

/**
 * One student, one subject: chapter-wise marks and the Remembering & Understanding /
 * Applying / Analysing-Evaluating-Creating tier breakdown, from the same
 * evidence-floored findings machinery a BoardX report uses -- never a number this
 * paper's own marks cannot support.
 */

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { BoardXOnePager } from "@/components/academics/BoardXOnePager";
import { BarChartIcon, ClipboardIcon, TargetIcon } from "@/components/academics/Icons";
import { StatTile, StatTileRow } from "@/components/academics/StatTile";
import { StatusBadge } from "@/components/academics/StatusBadge";
import { Mascot } from "@/components/Mascot";
import { api, type AcademicFinding, type BoardXReport, type StudentSubjectBreakdown } from "@/lib/api";
import { downloadBlob } from "@/lib/download";
import { getApiKey } from "@/lib/session";

const STATUS_TONE = { on_track: "verify", needs_attention: "warn", requires_review: "risk", not_assessed: "neutral" } as const;

export default function StudentSubjectPage({
  params,
}: {
  params: Promise<{ studentId: string; subjectCode: string }>;
}) {
  const { studentId, subjectCode } = use(params);
  const [data, setData] = useState<StudentSubjectBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"pdf" | "xlsx" | null>(null);
  const [boardxAssessmentId, setBoardxAssessmentId] = useState("");
  const [boardx, setBoardx] = useState<BoardXReport | null>(null);
  const [boardxError, setBoardxError] = useState<string | null>(null);
  const [boardxDownloading, setBoardxDownloading] = useState(false);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .studentSubjectBreakdown(key, studentId, subjectCode)
      .then((res) => {
        setData(res);
        if (res.tests.length > 0) setBoardxAssessmentId(res.tests[0].assessment_id);
      })
      .catch(() => setError("Could not load this subject -- there may be no marks recorded for it."));
  }, [studentId, subjectCode]);

  useEffect(() => {
    const key = getApiKey();
    if (!key || !boardxAssessmentId) return;
    setBoardx(null);
    setBoardxError(null);
    api
      .studentBoardX(key, studentId, boardxAssessmentId)
      .then(setBoardx)
      .catch(() => setBoardxError("Could not compose the BoardX report for this paper."));
  }, [studentId, boardxAssessmentId]);

  async function downloadBoardX() {
    const key = getApiKey();
    if (!key || !boardxAssessmentId) return;
    setBoardxDownloading(true);
    try {
      const blob = await api.studentBoardXPdf(key, studentId, boardxAssessmentId);
      downloadBlob(blob, `boardx-report.pdf`);
    } catch {
      setBoardxError("Could not generate the BoardX PDF.");
    } finally {
      setBoardxDownloading(false);
    }
  }

  async function download(kind: "pdf" | "xlsx") {
    const key = getApiKey();
    if (!key) return;
    setDownloading(kind);
    try {
      const blob = kind === "pdf"
        ? await api.studentSubjectPdf(key, studentId, subjectCode)
        : await api.studentSubjectXlsx(key, studentId, subjectCode);
      downloadBlob(blob, `subject-breakdown.${kind}`);
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

  return (
    <main className="wrap">
      <div className="hero row between" style={{ alignItems: "flex-end" }}>
        <div>
          <p className="eyebrow">
            <Link href={`/admin/academics/students/${studentId}`}>{data.student.name}</Link> &rsaquo; {data.subject.label}
          </p>
          <h1 style={{ margin: 0 }}>{data.subject.label}</h1>
          <p className="lede">{data.student.name} · Roll {data.student.roll_no}</p>
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

      <StatTileRow>
        <StatTile
          icon={<BarChartIcon />}
          value={data.overall.avg_score_pct != null ? `${data.overall.avg_score_pct}%` : "N/A"}
          label="Score"
          tone="gold"
        />
        <StatTile icon={<ClipboardIcon />} value={`${data.overall.earned} / ${data.overall.available}`} label="Marks" tone="info" />
        <StatTile icon={<ClipboardIcon />} value={data.overall.tests_taken} label="Tests" tone="violet" />
        <StatTile
          icon={<TargetIcon />}
          value={<StatusBadge status={data.overall.status} />}
          label="Status"
          tone={STATUS_TONE[data.overall.status]}
        />
      </StatTileRow>

      <div className="section-head"><h2>By Chapter</h2></div>
      <FindingsTable findings={data.by_chapter} emptyText="No chapter-tagged questions yet." />

      <div className="section-head" style={{ marginTop: 24 }}><h2>By Category (Remembering, Applying, Analysing)</h2></div>
      <FindingsTable findings={data.by_tier} emptyText="No category-classified questions yet." />

      {data.tests.length > 0 && (
        <>
          <div className="row between" style={{ alignItems: "flex-end", marginTop: 28, marginBottom: 8 }}>
            <div className="section-head" style={{ margin: 0 }}>
              <h2>One-Page BoardX Report</h2>
            </div>
            <div className="row" style={{ gap: 10 }}>
              {data.tests.length > 1 && (
                <div className="field" style={{ marginBottom: 0, minWidth: 200 }}>
                  <label>Paper</label>
                  <select value={boardxAssessmentId} onChange={(e) => setBoardxAssessmentId(e.target.value)}>
                    {data.tests.map((t) => (
                      <option key={t.assessment_id} value={t.assessment_id}>{t.title}</option>
                    ))}
                  </select>
                </div>
              )}
              <button
                type="button" className="secondary" disabled={!boardx || boardxDownloading}
                onClick={downloadBoardX}
                style={{ alignSelf: "flex-end" }}
              >
                {boardxDownloading ? "Preparing…" : "Download PDF"}
              </button>
            </div>
          </div>
          {boardxError && <p className="error">{boardxError}</p>}
          {!boardx && !boardxError && (
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Mascot pose="loading" size={20} />
              <p className="muted" style={{ margin: 0 }}>Composing…</p>
            </div>
          )}
          {boardx && <BoardXOnePager report={boardx} rollNo={data.student.roll_no} />}
        </>
      )}
    </main>
  );
}

function FindingsTable({ findings, emptyText }: { findings: AcademicFinding[]; emptyText: string }) {
  if (findings.length === 0) return <p className="muted">{emptyText}</p>;
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Score</th>
            <th>Questions</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f) => {
            const pct = f.sufficient && f.rate != null ? Math.round(f.rate * 100) : null;
            const tone = pct == null ? "" : pct >= 75 ? "verify" : pct >= 50 ? "" : "warn";
            return (
              <tr key={f.key}>
                <td className="strong">{f.label}</td>
                <td className="num" style={{ minWidth: 160 }}>
                  {pct != null ? (
                    <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
                      <div className={`progress${tone ? ` ${tone}` : ""}`} style={{ flex: 1 }}>
                        <div style={{ width: `${pct}%` }} />
                      </div>
                      <span style={{ whiteSpace: "nowrap" }}>{f.earned}/{f.available} ({pct}%)</span>
                    </div>
                  ) : (
                    "N/A"
                  )}
                </td>
                <td className="num">{f.questions}</td>
                <td className="small muted">{f.message}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
