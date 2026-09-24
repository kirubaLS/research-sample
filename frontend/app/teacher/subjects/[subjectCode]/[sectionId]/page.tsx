"use client";

/**
 * Subject view -- one subject, one section, matching the reference design's §6.3
 * SubjectView (src/app/teacher/subject/[subject]/[section]/page.tsx): an Insights tab
 * (real roster + score distribution, scoped to this subject via
 * GET /admin/teacher/academics/{sectionId}/students?subject_code=...) plus "Question
 * Paper" and "Enter Marks" tabs.
 *
 * The Paper/Marks tabs deep-link into the existing, fully working
 * /teacher/paper and /teacher/answers screens (scan/classify/mark-entry state machines
 * of ~1200 lines each) with ?subject=/&section= prefill, rather than re-implementing
 * that pipeline here -- see the prefill effects added to those two pages. Embedding
 * their full state machines inline would mean duplicating real, working scan/OCR/marks
 * logic; this keeps a single source of truth for it while still landing the teacher on
 * the right subject/paper without extra clicks, which is what the tab is for.
 */

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { FileText, ClipboardList } from "lucide-react";
import { Avatar } from "@/components/academics/Avatar";
import { BarChartIcon, ClipboardIcon, PeopleIcon } from "@/components/academics/Icons";
import { ScoreDistribution } from "@/components/academics/ScoreDistribution";
import { StatTile, StatTileRow } from "@/components/academics/StatTile";
import { StatusBadge } from "@/components/academics/StatusBadge";
import { Mascot } from "@/components/Mascot";
import { ShareWithStudentModal } from "@/components/teacher/ShareWithStudentModal";
import { api, type AcademicStatus, type ClassStudentRow } from "@/lib/api";
import { getApiKey, getRole } from "@/lib/session";

type Tab = "insights" | "paper" | "marks";

export default function SubjectSectionPage({
  params,
}: {
  params: Promise<{ subjectCode: string; sectionId: string }>;
}) {
  const { subjectCode, sectionId } = use(params);
  const role = getRole();
  const [tab, setTab] = useState<Tab>("insights");
  const [section, setSection] = useState<{ id: string; label: string } | null>(null);
  const [students, setStudents] = useState<ClassStudentRow[] | null>(null);
  const [status, setStatus] = useState<AcademicStatus | "">("");
  const [error, setError] = useState<string | null>(null);
  const [shareFor, setShareFor] = useState<{ studentId: string; name: string } | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherAcademicsStudents(key, sectionId, { subjectCode, status: status || undefined })
      .then((res) => {
        setSection(res.section);
        setStudents(res.students);
      })
      .catch(() => setError("Could not load this subject/class."));
  }, [sectionId, subjectCode, status]);

  if (error) return <p className="page-sub" style={{ color: "var(--risk)" }}>{error}</p>;
  if (!students || !section) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Mascot pose="loading" size={24} />
        <p className="muted" style={{ margin: 0 }}>Loading…</p>
      </div>
    );
  }

  const scored = students.filter((s) => s.avg_score_pct != null);
  const avg = scored.length
    ? Math.round(scored.reduce((sum, s) => sum + (s.avg_score_pct ?? 0), 0) / scored.length)
    : null;
  const testsRecorded = students.reduce((sum, s) => sum + s.tests_taken, 0);
  const canEnterMarks = role?.can.enter_marks;
  const canScanPapers = role?.can.scan_papers;

  return (
    <>
      <p className="eyebrow">
        <Link href="/teacher/home">Home</Link> &rsaquo;{" "}
        <Link href={`/teacher/home/${sectionId}`}>{section.label}</Link> &rsaquo; {subjectCode}
      </p>
      <h1 className="page-title" style={{ marginTop: 4 }}>
        {subjectCode} &middot; {section.label}
      </h1>
      <p className="muted small" style={{ marginTop: 4 }}>
        {students.length} students{avg != null ? ` · ${avg}% avg` : " · not yet assessed"}
      </p>

      <div className="tabs" role="tablist" style={{ marginTop: 18 }}>
        <button role="tab" aria-selected={tab === "insights"} className={`tab ${tab === "insights" ? "tab--active" : ""}`} onClick={() => setTab("insights")}>
          Insights
        </button>
        {canScanPapers && (
          <button role="tab" aria-selected={tab === "paper"} className={`tab ${tab === "paper" ? "tab--active" : ""}`} onClick={() => setTab("paper")}>
            <FileText size={13} style={{ verticalAlign: "-2px", marginRight: 5 }} /> Question paper
          </button>
        )}
        {canEnterMarks && (
          <button role="tab" aria-selected={tab === "marks"} className={`tab ${tab === "marks" ? "tab--active" : ""}`} onClick={() => setTab("marks")}>
            <ClipboardList size={13} style={{ verticalAlign: "-2px", marginRight: 5 }} /> Enter marks
          </button>
        )}
      </div>

      {tab === "insights" && (
        <>
          <div style={{ marginTop: 18 }}>
            <StatTileRow>
              <StatTile icon={<PeopleIcon />} value={students.length} label="Students" tone="violet" />
              <StatTile icon={<ClipboardIcon />} value={testsRecorded} label="Tests recorded" tone="info" />
              <StatTile icon={<BarChartIcon />} value={avg != null ? `${avg}%` : "N/A"} label="Avg score" tone="gold" />
            </StatTileRow>
          </div>

          <section className="section">
            <ScoreDistribution students={students} />
          </section>

          <section className="section">
            <div className="section__head">
              <h2 className="section-q">{section.label} students in {subjectCode}</h2>
              <div className="filter">
                <label htmlFor="roster-status">Status</label>
                <select id="roster-status" className="select" value={status} onChange={(e) => setStatus(e.target.value as AcademicStatus | "")}>
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
          </section>
        </>
      )}

      {tab === "paper" && canScanPapers && (
        <div className="card" style={{ marginTop: 18 }}>
          <div className="card__body">
            <p className="muted" style={{ marginTop: 0 }}>
              Scan, map and classify the {subjectCode} question paper -- the same real
              scan pipeline as the Papers screen, opened straight to this subject.
            </p>
            <Link href={`/teacher/paper?subject=${encodeURIComponent(subjectCode)}`} className="btn btn--primary">
              Open Question Paper for {subjectCode} <FileText size={14} style={{ marginLeft: 6 }} />
            </Link>
          </div>
        </div>
      )}

      {tab === "marks" && canEnterMarks && (
        <div className="card" style={{ marginTop: 18 }}>
          <div className="card__body">
            <p className="muted" style={{ marginTop: 0 }}>
              Enter or review marks for {section.label} in {subjectCode} -- the same real
              marks-entry screen as Enter Marks, opened straight to this subject and section.
            </p>
            <Link
              href={`/teacher/answers?subject=${encodeURIComponent(subjectCode)}&section=${encodeURIComponent(sectionId)}`}
              className="btn btn--primary"
            >
              Open Enter Marks for {subjectCode} <ClipboardList size={14} style={{ marginLeft: 6 }} />
            </Link>
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
