"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Download } from "lucide-react";
import { api, type StudentAcademicsOverview, type StudentSubjectBreakdown } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { usePageHeader } from "@/lib/pageHeader";
import { AttentionPill } from "@/components/Status";
import { EvidenceState } from "@/components/EvidenceState";
import { STATUS_LABEL, STATUS_PILL_KEY } from "@/lib/statusLabels";

/** Principal → Classes → section → student. Real data end to end: GET
 * /admin/academics/students/{id} for the overall/subject summary, and GET
 * /admin/academics/students/{id}/subjects/{code} for the chapter-wise breakdown
 * of the subject currently selected. The full narrative BoardX one-pager (the
 * reference's fake `report`) has no line-for-line real equivalent here -- the
 * real one-page report exists only as a PDF (GET /reports/student/{id}/boardx.pdf),
 * so it is offered as a download instead of re-rendered inline. */
export default function PrincipalStudentPage() {
  const { section, studentId } = useParams<{ section: string; studentId: string }>();
  const key = getApiKey() ?? "";

  const [overview, setOverview] = useState<StudentAcademicsOverview | null>(null);
  const [subjectCode, setSubjectCode] = useState<string>("");
  const [breakdown, setBreakdown] = useState<StudentSubjectBreakdown | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);

  usePageHeader({ title: overview?.student.name ?? studentId, backHref: `/principal/classes/${section}` });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const ov = await api.studentAcademics(key, studentId);
        if (cancelled) return;
        setOverview(ov);
        if (ov.subjects.length) setSubjectCode((prev) => prev || ov.subjects[0].subject_code);
      } catch {
        if (!cancelled) setOverview(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studentId]);

  useEffect(() => {
    if (!subjectCode) return;
    let cancelled = false;
    (async () => {
      try {
        const b = await api.studentSubjectBreakdown(key, studentId, subjectCode);
        if (!cancelled) setBreakdown(b);
      } catch {
        if (!cancelled) setBreakdown(null);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studentId, subjectCode]);

  async function downloadBoardX() {
    const latestTest = breakdown?.tests[breakdown.tests.length - 1];
    if (!latestTest) return;
    setDownloading(true);
    try {
      const blob = await api.studentBoardXPdf(key, studentId, latestTest.assessment_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${overview?.student.name ?? studentId}-${subjectCode}-boardx.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }

  if (loading) return <p className="muted">Loading…</p>;
  if (!overview) return <EvidenceState kind="early">No academic record found for this student.</EvidenceState>;

  const { student, overall, subjects } = overview;

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16 }}>
        <p className="page-sub" style={{ marginTop: 0 }}>
          {student.section_label ?? section} · Roll {student.roll_no}
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button className="btn btn--sm" disabled={downloading || !breakdown?.tests.length} onClick={downloadBoardX}>
            <Download size={13} /> {downloading ? "Preparing…" : "Download report"}
          </button>
          <AttentionPill level={STATUS_PILL_KEY[overall.status]} label={STATUS_LABEL[overall.status]} />
        </div>
      </div>

      <div className="filterbar" style={{ marginTop: 20 }}>
        <div className="filter">
          <label htmlFor="subject-picker">Subject report</label>
          <select id="subject-picker" className="select" value={subjectCode} onChange={(e) => setSubjectCode(e.target.value)}>
            {subjects.map((s) => (
              <option key={s.subject_code} value={s.subject_code}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid--3" style={{ marginTop: 16 }}>
        <div className="stat">
          <div className="stat__label">Overall</div>
          <div className="stat__value stat__value--sm">{overall.avg_score_pct === null ? "-" : `${Math.round(overall.avg_score_pct)}%`}</div>
        </div>
        <div className="stat">
          <div className="stat__label">Tests taken</div>
          <div className="stat__value stat__value--sm">{overall.tests_taken}</div>
        </div>
        <div className="stat">
          <div className="stat__label">Subjects with marks</div>
          <div className="stat__value stat__value--sm">{subjects.length}</div>
        </div>
      </div>

      <section className="section">
        <h2 className="section-q">Every subject</h2>
        <div className="card card--flat" style={{ marginTop: 12 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Subject</th>
                <th className="num">Score</th>
                <th className="num">Tests</th>
                <th>Status</th>
                <th>Strengths</th>
                <th>Needs improvement</th>
              </tr>
            </thead>
            <tbody>
              {subjects.map((s) => (
                <tr key={s.subject_code}>
                  <td className="strong">{s.label}</td>
                  <td className="num">{s.avg_score_pct === null ? "-" : `${Math.round(s.avg_score_pct)}%`}</td>
                  <td className="num">{s.tests_taken}</td>
                  <td>
                    <AttentionPill level={STATUS_PILL_KEY[s.status]} label={STATUS_LABEL[s.status]} />
                  </td>
                  <td className="small">{s.strengths.join(", ") || "-"}</td>
                  <td className="small">{s.improve.join(", ") || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {breakdown && (
        <section className="section">
          <h2 className="section-q">{breakdown.subject.label}, where marks were lost</h2>
          <div className="card card--flat" style={{ marginTop: 12 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Chapter</th>
                  <th className="num">Earned</th>
                  <th className="num">Available</th>
                  <th className="num">Rate</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {breakdown.by_chapter.map((c) => (
                  <tr key={c.key}>
                    <td className="strong">{c.label}</td>
                    <td className="num">{c.earned}</td>
                    <td className="num">{c.available}</td>
                    <td className="num">{c.rate === null ? "-" : `${Math.round(c.rate * 100)}%`}</td>
                    <td className="small muted">{c.sufficient ? "" : c.message}</td>
                  </tr>
                ))}
                {breakdown.by_chapter.length === 0 && (
                  <tr>
                    <td colSpan={5}>
                      <EvidenceState kind="early" compact>
                        No chapter-wise findings for this subject yet.
                      </EvidenceState>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
