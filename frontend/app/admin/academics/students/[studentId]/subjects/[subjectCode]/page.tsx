"use client";

/**
 * One student, one subject: chapter-wise marks and the Remembering & Understanding /
 * Applying / Analysing-Evaluating-Creating tier breakdown, from the same
 * evidence-floored findings machinery a BoardX report uses -- never a number this
 * paper's own marks cannot support.
 */

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { StatusBadge } from "@/components/academics/StatusBadge";
import { Mascot } from "@/components/Mascot";
import { api, type AcademicFinding, type StudentSubjectBreakdown } from "@/lib/api";
import { downloadBlob } from "@/lib/download";
import { getApiKey } from "@/lib/session";

export default function StudentSubjectPage({
  params,
}: {
  params: Promise<{ studentId: string; subjectCode: string }>;
}) {
  const { studentId, subjectCode } = use(params);
  const [data, setData] = useState<StudentSubjectBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"pdf" | "xlsx" | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .studentSubjectBreakdown(key, studentId, subjectCode)
      .then(setData)
      .catch(() => setError("Could not load this subject -- there may be no marks recorded for it."));
  }, [studentId, subjectCode]);

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

      <div className="tiles" style={{ marginBottom: 24 }}>
        <div className="tile">
          <span className="tile-n">{data.overall.avg_score_pct != null ? `${data.overall.avg_score_pct}%` : "—"}</span>
          <span className="tile-l">Score</span>
        </div>
        <div className="tile">
          <span className="tile-n">{data.overall.earned} / {data.overall.available}</span>
          <span className="tile-l">Marks</span>
        </div>
        <div className="tile">
          <span className="tile-n">{data.overall.tests_taken}</span>
          <span className="tile-l">Tests</span>
        </div>
        <div className="tile">
          <StatusBadge status={data.overall.status} />
          <span className="tile-l" style={{ marginTop: 6 }}>Status</span>
        </div>
      </div>

      <div className="section-head"><h2>By Chapter</h2></div>
      <FindingsTable findings={data.by_chapter} emptyText="No chapter-tagged questions yet." />

      <div className="section-head" style={{ marginTop: 24 }}><h2>By Category (Remembering, Applying, Analysing)</h2></div>
      <FindingsTable findings={data.by_tier} emptyText="No category-classified questions yet." />
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
          {findings.map((f) => (
            <tr key={f.key}>
              <td className="strong">{f.label}</td>
              <td className="num">
                {f.sufficient && f.rate != null
                  ? `${f.earned}/${f.available} (${Math.round(f.rate * 100)}%)`
                  : "—"}
              </td>
              <td className="num">{f.questions}</td>
              <td className="small muted">{f.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
