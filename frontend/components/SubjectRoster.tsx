"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { ClassStudentRow } from "@/lib/api";
import { AttentionPill } from "@/components/Status";
import { EvidenceState } from "@/components/EvidenceState";

type QuickFilter = "all" | "top" | "critical";

const FILTER_LABEL: Record<QuickFilter, string> = {
  all: "All Students",
  top: "Top Performers",
  critical: "Critical",
};

const STATUS_LABEL: Record<string, string> = {
  on_track: "On Track",
  needs_attention: "Needs Attention",
  requires_review: "Requires Review",
  not_assessed: "Not assessed",
};

/** A subject teacher's own roster table, backed by the real, subject-scoped student rows
 * GET /admin/teacher/academics/{section}/students already returned to the page around it
 * (no re-fetch here, so the insights tab and this table can never disagree). */
export function SubjectRoster({ subject, section, students }: { subject: string; section: string; students: ClassStudentRow[] }) {
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("all");

  const rows = useMemo(() => {
    let filtered = students;
    if (quickFilter === "critical") filtered = filtered.filter((r) => r.status === "requires_review" || r.status === "needs_attention");
    filtered = [...filtered].sort((a, b) => {
      if (quickFilter === "top") return (b.avg_score_pct ?? -1) - (a.avg_score_pct ?? -1);
      if (quickFilter === "critical") return (a.avg_score_pct ?? 101) - (b.avg_score_pct ?? 101);
      return a.roll_no.localeCompare(b.roll_no, undefined, { numeric: true });
    });
    if (quickFilter === "top") filtered = filtered.slice(0, 10);
    return filtered;
  }, [students, quickFilter]);

  return (
    <div className="card" style={{ marginTop: 14 }}>
      <div className="tabs" role="tablist" style={{ padding: "14px 18px 0" }}>
        {(["all", "top", "critical"] as QuickFilter[]).map((k) => (
          <button key={k} role="tab" aria-selected={quickFilter === k} className={`tab ${quickFilter === k ? "tab--active" : ""}`} onClick={() => setQuickFilter(k)}>
            {FILTER_LABEL[k]}
          </button>
        ))}
      </div>
      <div className="table-wrap table-wrap--scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Roll</th>
              <th>Student</th>
              <th className="num">{subject}</th>
              <th>Top improvement area</th>
              <th>Attention</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={6}>
                  <EvidenceState kind="early" compact>No students match this filter.</EvidenceState>
                </td>
              </tr>
            )}
            {rows.map((s) => (
              <tr key={s.student_id}>
                <td className="muted">{s.roll_no}</td>
                <td className="strong">{s.name}</td>
                <td className="num">{s.avg_score_pct != null ? `${Math.round(s.avg_score_pct)}%` : "—"}</td>
                <td>{s.top_improvement_area ? `${s.top_improvement_area.chapter} (${Math.round(s.top_improvement_area.rate * 100)}%)` : "—"}</td>
                <td>
                  <AttentionPill level={STATUS_LABEL[s.status] ?? s.status} />
                </td>
                <td style={{ textAlign: "right" }}>
                  <Link href={`/teacher/student/${s.student_id}`} className="btn btn--sm">
                    Report <ArrowRight size={12} />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card__foot small muted">
        {quickFilter === "top" ? `Top ${rows.length} of ${students.length}` : `Showing ${rows.length} of ${students.length} students.`}
      </div>
    </div>
  );
}
