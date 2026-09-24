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
 * and "Share with student" per row -- so consolidating the nav loses none of it. All of
 * /teacher/classes/[id], /teacher/subjects/[code]/[id] and the earlier
 * /teacher/overview/[id] redirect here now.
 */

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { Avatar } from "@/components/academics/Avatar";
import { BarChartIcon, ClipboardIcon, PeopleIcon } from "@/components/academics/Icons";
import { ScoreDistribution } from "@/components/academics/ScoreDistribution";
import { StatTile, StatTileRow } from "@/components/academics/StatTile";
import { StatusBadge } from "@/components/academics/StatusBadge";
import { StatusOverviewBar } from "@/components/academics/StatusOverviewBar";
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

  if (error) return <p className="page-sub" style={{ color: "var(--risk)" }}>{error}</p>;
  if (!students || !section) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Mascot pose="loading" size={24} />
        <p className="muted" style={{ margin: 0 }}>Loading…</p>
      </div>
    );
  }

  // An Enter Marks link only makes sense once we know the exact subject to enter marks
  // for -- a class assignment covering several subjects has no single one to send the
  // link to, so it only shows for a subject-scoped view.
  const canEnterMarks = role?.can.enter_marks && subjectCode;

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16, flexWrap: "wrap" }}>
        <div>
          <p className="eyebrow">
            <Link href="/teacher/home">Home</Link> &rsaquo; {section.label}
          </p>
          <h1 className="page-title" style={{ marginTop: 4 }}>{section.label}</h1>
          <p className="page-sub">
            {subjectCode ? `${subjectCode} only` : "All subjects"} · {students.length} students
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {canEnterMarks && (
            <Link href={`/principal/enter-marks?assessment_subject=${subjectCode}&section_id=${sectionId}`} className="btn btn--ghost">
              Enter marks
            </Link>
          )}
          <button type="button" className="btn btn--ghost" disabled={downloading} onClick={downloadCsv}>
            {downloading ? "Preparing…" : "Download CSV"}
          </button>
        </div>
      </div>

      {(() => {
        const counts = students.reduce(
          (acc, s) => { acc[s.status] += 1; return acc; },
          { on_track: 0, needs_attention: 0, requires_review: 0, not_assessed: 0 },
        );
        const scored = students.filter((s) => s.avg_score_pct != null);
        const avg = scored.length
          ? Math.round(scored.reduce((sum, s) => sum + (s.avg_score_pct ?? 0), 0) / scored.length)
          : null;
        return (
          <div className="card" style={{ marginTop: 18, marginBottom: 20 }}>
            <div className="card__body classoverview-grid">
              <StatusOverviewBar counts={counts} title="Class Overview" />
              <div className="classoverview-stats">
                <StatTile icon={<PeopleIcon />} value={students.length} label="Students" tone="violet" />
                <StatTile icon={<ClipboardIcon />} value={students.reduce((s, r) => s + r.tests_taken, 0)} label="Tests Recorded" tone="info" />
                <StatTile icon={<BarChartIcon />} value={avg != null ? `${avg}%` : "N/A"} label="Class Avg. Score" tone="gold" />
              </div>
            </div>
            <style jsx>{`
              .classoverview-grid { display: flex; gap: 24px; flex-wrap: wrap; align-items: center; }
              .classoverview-grid > :global(.sob) { flex: 1 1 320px; min-width: 260px; }
              .classoverview-stats { display: flex; gap: 14px; flex-wrap: wrap; flex: 2 1 420px; }
              .classoverview-stats > :global(.stattile) { flex: 1 1 130px; border: none; box-shadow: none; padding: 4px 0; }
            `}</style>
          </div>
        );
      })()}

      <div className="tabs" style={{ marginBottom: 16 }}>
        {(["students", "cohort"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`tab${tab === t ? " tab--active" : ""}`}
          >
            {t === "students" ? "Students" : "Cohort snapshot"}
          </button>
        ))}
      </div>

      {tab === "students" && (
        <>
          <ScoreDistribution students={students} />

          <div className="filterbar">
            <div className="field">
              <label>Status</label>
              <select className="select" value={status} onChange={(e) => setStatus(e.target.value as AcademicStatus | "")}>
                <option value="">All statuses</option>
                <option value="on_track">On Track</option>
                <option value="needs_attention">Needs Attention</option>
                <option value="requires_review">Requires Review</option>
                <option value="not_assessed">Not Yet Assessed</option>
              </select>
            </div>
          </div>

          <div className="card">
            <div className="table-wrap">
              <table className="table">
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
                      <td className="strong">
                        <span style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "nowrap" }}>
                          <Avatar name={s.name} seed={s.student_id} size={30} />
                          {s.name}
                        </span>
                      </td>
                      <td><StatusBadge status={s.status} /></td>
                      <td className="num">{s.avg_score_pct != null ? `${s.avg_score_pct}%` : "N/A"}</td>
                      <td className="num">{s.tests_taken}</td>
                      <td>{s.top_improvement_area ? `${s.top_improvement_area.chapter} (${s.top_improvement_area.rate}%)` : "N/A"}</td>
                      <td>
                        <div style={{ display: "flex", gap: 6 }}>
                          <Link href={`/teacher/student/${s.student_id}`} className="btn btn--ghost btn--sm">View</Link>
                          <button
                            type="button"
                            className="btn btn--ghost btn--sm"
                            title="Report must be issued before it can be shared"
                            onClick={() => setShareFor({ studentId: s.student_id, name: s.name })}
                          >
                            Share ⋮
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {students.length === 0 && (
                    <tr><td colSpan={7} className="muted">No students match these filters.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {tab === "cohort" && (
        <div className="card">
          <div className="card__body">
            <p className="muted" style={{ marginTop: 0 }}>
              Cohort snapshot for {section.label}: Holland-code and stream-fit counts
              across the interest test, scoped to this section only.
            </p>
            {!cohort && <p className="muted">Loading…</p>}
            {cohort && cohort.counted === 0 && (
              <p className="muted">
                No student in this section has a countable interest profile yet
                {cohort.withheld > 0 && ` (${cohort.withheld} withheld as too undifferentiated to call)`}.
              </p>
            )}
            {cohort && cohort.counted > 0 && (
              <>
                <h3 style={{ marginTop: 4 }}>Where this class leans</h3>
                {Object.entries(cohort.streams)
                  .sort((a, b) => b[1] - a[1])
                  .map(([stream, n]) => (
                    <div className="bar-row" key={stream}>
                      <span className="bar-row__label">{stream}</span>
                      <div className="bar">
                        <div className="bar__fill" style={{ width: `${(n / cohort.counted) * 100}%` }} />
                      </div>
                      <span className="bar-row__val">{n}</span>
                    </div>
                  ))}

                <h3 style={{ marginTop: 18 }}>Holland codes</h3>
                {Object.entries(cohort.holland)
                  .sort((a, b) => b[1] - a[1])
                  .map(([code, n]) => (
                    <div className="bar-row" key={code}>
                      <span className="bar-row__label">{code}</span>
                      <div className="bar">
                        <div className="bar__fill" style={{ width: `${(n / cohort.counted) * 100}%` }} />
                      </div>
                      <span className="bar-row__val">{n}</span>
                    </div>
                  ))}

                <p className="small muted" style={{ marginTop: 12, marginBottom: 0 }}>
                  {cohort.counted} profile{cohort.counted === 1 ? "" : "s"} counted
                  {cohort.withheld > 0 && (
                    <> · {cohort.withheld} withheld as too undifferentiated to call</>
                  )}
                </p>
              </>
            )}
          </div>
        </div>
      )}

      {shareFor && (
        <ShareWithStudentModal
          studentId={shareFor.studentId}
          studentName={shareFor.name}
          onClose={() => setShareFor(null)}
        />
      )}
    </>
  );
}
