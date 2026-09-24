"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Search, TrendingDown, TrendingUp, X } from "lucide-react";
import type { ClassStudentRow } from "@/lib/api";
import { AttentionPill } from "@/components/Status";
import { EvidenceState } from "@/components/EvidenceState";
import { STATUS_LABEL, STATUS_PILL_KEY } from "@/lib/statusLabels";

/** Movement against a previous figure. `null` means there is nothing real to compare
 * against, shown as an em dash, never as "0". Still used by teacher-facing pages this
 * task did not touch. */
export function DeltaCell({ delta, suffix = "pt" }: { delta: number | null; suffix?: string }) {
  if (delta === null) return <span className="muted">-</span>;
  if (delta === 0) return <span className="muted">no change</span>;
  const up = delta > 0;
  return (
    <span className="delta" data-dir={up ? "up" : "down"}>
      {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
      {up ? "+" : "−"}
      {Math.abs(delta)}
      {suffix}
    </span>
  );
}

type QuickFilter = "all" | "top10" | "attention" | "critical";

const quickFilterLabel: Record<QuickFilter, string> = {
  all: "All Students",
  top10: "Top 10",
  attention: "Need Attention",
  critical: "Critical",
};

/** The student roster table shared by Class detail and the per-test class page: quick
 * presets (All / Top 10 / Need Attention / Critical) plus a search box, over a real
 * GET /admin/academics/{sectionId}/students result. The subject/test filter lives on
 * the parent page (it drives a refetch), this component only searches and re-orders
 * whatever rows it is handed. */
export function StudentRosterTable({
  rows,
  sectionId,
  loading,
  fillHeight = false,
  leadingFilters,
  heading,
}: {
  rows: ClassStudentRow[];
  sectionId: string;
  loading?: boolean;
  /** Extra controls rendered in the same filter row (e.g. a subject/test picker). */
  leadingFilters?: React.ReactNode;
  /** Card + table grow to fill the parent's remaining height instead of capping at a
   * fixed height. */
  fillHeight?: boolean;
  /** Rendered above the filters (e.g. the "Students in X-A" heading). */
  heading?: React.ReactNode;
}) {
  const router = useRouter();
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("all");
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    let list = rows;
    const q = query.trim().toLowerCase();
    if (q) list = list.filter((r) => r.name.toLowerCase().split(/\s+/).some((w) => w.startsWith(q)) || r.name.toLowerCase().startsWith(q));
    if (quickFilter === "attention") list = list.filter((r) => r.status !== "on_track");
    if (quickFilter === "critical") list = list.filter((r) => r.status === "requires_review");

    const score = (r: ClassStudentRow) => r.avg_score_pct ?? -1;
    list = [...list].sort((a, b) => {
      if (quickFilter === "top10") return score(b) - score(a);
      if (quickFilter === "attention" || quickFilter === "critical") return score(a) - score(b);
      return a.roll_no.localeCompare(b.roll_no, undefined, { numeric: true });
    });
    if (quickFilter === "top10") list = list.slice(0, 10);
    return list;
  }, [rows, quickFilter, query]);

  return (
    <div style={fillHeight ? { display: "flex", flexDirection: "column", flex: 1, minHeight: 0 } : undefined}>
      <div style={{ flex: "0 0 auto" }}>
        {!fillHeight && heading}
        <div className="filterbar" style={{ marginBottom: 0 }}>
          <div className="filter roster-search">
            <label htmlFor="roster-search">Search student</label>
            <div className="searchbox">
              <Search size={15} aria-hidden="true" />
              <input
                id="roster-search"
                className="input"
                type="search"
                placeholder="Type a name"
                autoComplete="off"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              {query && (
                <button type="button" className="iconbtn" aria-label="Clear search" onClick={() => setQuery("")}>
                  <X size={14} />
                </button>
              )}
            </div>
          </div>
          {leadingFilters}
        </div>

        <div className="tabs" role="tablist" style={{ marginTop: 14 }}>
          {(["all", "top10", "attention", "critical"] as QuickFilter[]).map((k) => (
            <button key={k} role="tab" aria-selected={quickFilter === k} className={`tab ${quickFilter === k ? "tab--active" : ""}`} onClick={() => setQuickFilter(k)}>
              {quickFilterLabel[k]}
            </button>
          ))}
        </div>
      </div>

      <div className="card" style={fillHeight ? { marginTop: 14, flex: 1, minHeight: 0, display: "flex", flexDirection: "column" } : { marginTop: 14 }}>
        {loading ? (
          <div className="placeholder">
            <p>Loading roster…</p>
          </div>
        ) : (
          <div className={`table-wrap ${fillHeight ? "table-wrap--flex" : "table-wrap--stack"}`}>
            <table className="table table--hover table--roster">
              <thead>
                <tr>
                  <th>Roll</th>
                  <th>Student</th>
                  <th className="num">Score</th>
                  <th className="num">Tests taken</th>
                  <th>Top improvement area</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={7}>
                      <EvidenceState kind="early" compact>
                        No students match this filter.
                      </EvidenceState>
                    </td>
                  </tr>
                )}
                {filtered.map((s) => (
                  <tr key={s.student_id} onClick={() => router.push(`/principal/classes/${sectionId}/${s.student_id}`)}>
                    <td className="muted">{s.roll_no}</td>
                    <td className="strong">{s.name}</td>
                    <td className="num">{s.avg_score_pct === null ? "-" : `${Math.round(s.avg_score_pct)}%`}</td>
                    <td className="num">{s.tests_taken}</td>
                    <td>{s.top_improvement_area ? s.top_improvement_area.chapter : "-"}</td>
                    <td>
                      <AttentionPill level={STATUS_PILL_KEY[s.status]} label={STATUS_LABEL[s.status]} />
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <Link href={`/principal/classes/${sectionId}/${s.student_id}`} className="btn btn--sm" onClick={(e) => e.stopPropagation()}>
                        Report <ArrowRight size={12} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="card__foot small muted" style={{ flex: "0 0 auto" }}>
          {quickFilter === "top10" ? `Top ${filtered.length} of ${rows.length}` : `Showing ${filtered.length} of ${rows.length} students.`}
        </div>
      </div>
    </div>
  );
}
