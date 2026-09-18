"use client";

/**
 * One student, one subject, for a teacher: the same chapter-wise marks and Remembering
 * & Understanding / Applying / Analysing-Evaluating-Creating tier breakdown, and the
 * same BoardX v2 one-pager, as the principal's own
 * app/admin/academics/students/[studentId]/subjects/[subjectCode]/page.tsx -- reusing
 * BoardXOnePager unchanged so the two surfaces can never visually drift apart.
 *
 * Scoped through GET /admin/teacher/academics/students/{id}/subjects/{code} and
 * GET /admin/teacher/academics/students/{id}/boardx -- the teacher-scoped siblings of
 * the principal's own routes, refused with 404 unless this teacher key holds a class
 * or subject assignment on the student's section covering this exact subject. The
 * principal-only GET /reports/student/{id}/boardx stays teacher-refused (its own
 * docstring explains why); this page never calls it.
 */

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { BoardXOnePager } from "@/components/academics/BoardXOnePager";
import { StatusBadge } from "@/components/academics/StatusBadge";
import { Mascot } from "@/components/Mascot";
import { api, type AcademicFinding, type BoardXReport, type StudentSubjectBreakdown } from "@/lib/api";
import { downloadBlob } from "@/lib/download";
import { getApiKey } from "@/lib/session";

export default function TeacherStudentSubjectPage({
  params,
}: {
  params: Promise<{ studentId: string; subjectCode: string }>;
}) {
  const { studentId, subjectCode } = use(params);
  const [data, setData] = useState<StudentSubjectBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [boardxAssessmentId, setBoardxAssessmentId] = useState("");
  const [boardx, setBoardx] = useState<BoardXReport | null>(null);
  const [boardxError, setBoardxError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherStudentSubjectBreakdown(key, studentId, subjectCode)
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
      .teacherStudentBoardX(key, studentId, boardxAssessmentId)
      .then(setBoardx)
      .catch(() => setBoardxError("Could not compose the BoardX report for this paper."));
  }, [studentId, boardxAssessmentId]);

  async function downloadCsv() {
    const key = getApiKey();
    if (!key) return;
    setDownloading(true);
    try {
      const blob = await api.teacherStudentSubjectCsv(key, studentId, subjectCode);
      downloadBlob(blob, `subject-breakdown.csv`);
    } catch {
      setError("Could not generate the CSV file.");
    } finally {
      setDownloading(false);
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
            <Link href={`/teacher/student/${studentId}`}>{data.student.name}</Link> &rsaquo; {data.subject.label}
          </p>
          <h1 style={{ margin: 0 }}>{data.subject.label}</h1>
          <p className="lede">{data.student.name} · Roll {data.student.roll_no}</p>
        </div>
        <button type="button" disabled={downloading} onClick={downloadCsv}>
          {downloading ? "Preparing…" : "Download CSV"}
        </button>
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

      {data.tests.length > 0 && (
        <>
          <div className="row between" style={{ alignItems: "flex-end", marginTop: 28, marginBottom: 8 }}>
            <div className="section-head" style={{ margin: 0 }}>
              <h2>One-Page BoardX Report</h2>
            </div>
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
