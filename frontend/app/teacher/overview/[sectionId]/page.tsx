"use client";

/**
 * One class as this teacher key is scoped to see it -- every subject for a class
 * assignment, or just the one subject a subject assignment names (the backend always
 * runs it as that subject, regardless of what's in the URL). Real data only:
 * GET /admin/teacher/academics/{sectionId}/students.
 *
 * Also carries what the old /teacher/classes/[sectionId] and
 * /teacher/subjects/[code]/[sectionId] detail routes offered that this screen didn't
 * on its own -- a cohort snapshot tab (Holland-code/stream-fit counts, teacher-scoped
 * GET /admin/teacher/cohort/{id}), an Enter Marks link for a subject-assigned teacher,
 * and "Share with student" per row -- so consolidating the nav loses none of it. Both
 * old routes now redirect here.
 */

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/academics/StatusBadge";
import { Mascot } from "@/components/Mascot";
import { ShareWithStudentModal } from "@/components/teacher/ShareWithStudentModal";
import { api, type AcademicStatus, type ClassStudentRow } from "@/lib/api";
import { downloadBlob } from "@/lib/download";
import { getApiKey, getRole } from "@/lib/session";

type Tab = "students" | "cohort";
type Cohort = { holland: Record<string, number>; streams: Record<string, number>; counted: number; withheld: number };

export default function TeacherClassPage({ params }: { params: Promise<{ sectionId: string }> }) {
  const { sectionId } = use(params);
  const role = getRole();
  const [tab, setTab] = useState<Tab>("students");
  const [section, setSection] = useState<{ id: string; label: string } | null>(null);
  const [subjectCode, setSubjectCode] = useState<string | null>(null);
  const [students, setStudents] = useState<ClassStudentRow[] | null>(null);
  const [status, setStatus] = useState<AcademicStatus | "">("");
  const [error, setError] = useState<string | null>(null);
  const [cohort, setCohort] = useState<Cohort | null>(null);
  const [shareFor, setShareFor] = useState<{ studentId: string; name: string } | null>(null);
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherAcademicsStudents(key, sectionId, { status: status || undefined })
      .then((res) => {
        setSection(res.section);
        setSubjectCode(res.subject_code);
        setStudents(res.students);
      })
      .catch(() => setError("Could not load this class."));
  }, [sectionId, status]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (tab !== "cohort") return;
    const key = getApiKey();
    if (!key) return;
    api.teacherCohort(key, sectionId).then(setCohort);
  }, [tab, sectionId]);

  async function downloadCsv() {
    const key = getApiKey();
    if (!key) return;
    setDownloading(true);
    try {
      const blob = await api.teacherAcademicsStudentsCsv(key, sectionId, { status: status || undefined });
      downloadBlob(blob, `${section?.label ?? "class"}-students.csv`);
    } catch {
      setError("Could not generate the CSV file.");
    } finally {
      setDownloading(false);
    }
  }

  if (error) return <main className="wrap"><p className="error">{error}</p></main>;
  if (!students || !section) {
    return (
      <main className="wrap">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      </main>
    );
  }

  // An Enter Marks link only makes sense once we know the exact subject to enter marks
  // for -- a class assignment covering several subjects has no single one to send the
  // link to, so it only shows for a subject-scoped view.
  const canEnterMarks = role?.can.enter_marks && subjectCode;

  return (
    <main className="wrap">
      <div className="hero row between" style={{ alignItems: "flex-end" }}>
        <div>
          <p className="eyebrow">
            <Link href="/teacher/overview">Overview</Link> &rsaquo; {section.label}
          </p>
          <h1 style={{ margin: 0 }}>{section.label}</h1>
          <p className="lede">
            {subjectCode ? `${subjectCode} only` : "All subjects"} · {students.length} students
          </p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          {canEnterMarks && (
            <Link href={`/admin/answers?assessment_subject=${subjectCode}&section_id=${sectionId}`}>
              <button type="button" className="secondary">Enter marks</button>
            </Link>
          )}
          <button type="button" className="secondary" disabled={downloading} onClick={downloadCsv}>
            {downloading ? "Preparing…" : "Download CSV"}
          </button>
        </div>
      </div>

      <div className="subtabbar" style={{ display: "flex", gap: 4, marginBottom: 16, borderBottom: "1px solid var(--rule)" }}>
        {(["students", "cohort"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`subtab-btn${tab === t ? " on" : ""}`}
            style={{
              border: 0, background: "transparent", padding: "8px 4px", marginRight: 14,
              fontSize: 13.5, fontWeight: 600, cursor: "pointer",
              color: tab === t ? "var(--brand-ink)" : "var(--ink-3)",
              borderBottom: tab === t ? "2px solid var(--brand-ink)" : "2px solid transparent",
            }}
          >
            {t === "students" ? "Students" : "Cohort snapshot"}
          </button>
        ))}
      </div>

      {tab === "students" && (
        <>
          <div className="row" style={{ gap: 10, flexWrap: "wrap", marginBottom: 18 }}>
            <div className="field" style={{ marginBottom: 0, minWidth: 170 }}>
              <label>Status</label>
              <select value={status} onChange={(e) => setStatus(e.target.value as AcademicStatus | "")}>
                <option value="">All statuses</option>
                <option value="on_track">On Track</option>
                <option value="needs_attention">Needs Attention</option>
                <option value="requires_review">Requires Review</option>
                <option value="not_assessed">Not Yet Assessed</option>
              </select>
            </div>
          </div>

          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Roll</th>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Avg Score</th>
                  <th>Tests Taken</th>
                  <th>Top Area to Improve</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.student_id}>
                    <td>{s.roll_no}</td>
                    <td className="strong">{s.name}</td>
                    <td><StatusBadge status={s.status} /></td>
                    <td className="num">{s.avg_score_pct != null ? `${s.avg_score_pct}%` : "—"}</td>
                    <td className="num">{s.tests_taken}</td>
                    <td>{s.top_improvement_area ? `${s.top_improvement_area.chapter} (${s.top_improvement_area.rate}%)` : "—"}</td>
                    <td className="row" style={{ gap: 6 }}>
                      <Link href={`/teacher/student/${s.student_id}`}>
                        <button type="button" className="secondary tiny">View</button>
                      </Link>
                      <button
                        type="button"
                        className="secondary tiny"
                        title="Report must be issued before it can be shared"
                        onClick={() => setShareFor({ studentId: s.student_id, name: s.name })}
                      >
                        Share ⋮
                      </button>
                    </td>
                  </tr>
                ))}
                {students.length === 0 && (
                  <tr><td colSpan={7} className="muted">No students match these filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === "cohort" && (
        <div className="card">
          <p className="cardnote" style={{ marginTop: 0 }}>
            Cohort snapshot for {section.label} — Holland-code and stream-fit counts
            across the interest test, scoped to this section only.
          </p>
          {cohort ? (
            <>
              <p><strong>Counted:</strong> {cohort.counted} &nbsp; <strong>Withheld:</strong> {cohort.withheld}</p>
              <p className="cardnote">Holland: {JSON.stringify(cohort.holland)}</p>
              <p className="cardnote">Streams: {JSON.stringify(cohort.streams)}</p>
            </>
          ) : (
            <p className="muted">Loading…</p>
          )}
        </div>
      )}

      {shareFor && (
        <ShareWithStudentModal
          studentId={shareFor.studentId}
          studentName={shareFor.name}
          onClose={() => setShareFor(null)}
        />
      )}
    </main>
  );
}
