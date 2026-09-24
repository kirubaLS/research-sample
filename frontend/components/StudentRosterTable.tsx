"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Search, TrendingDown, TrendingUp, X } from "lucide-react";
import { analysedTests, attentionFor, mainBlockerFor, pctFor, subjects, type FullRosterStudent } from "@/lib/avai-mock-data";
import { AttentionPill } from "@/components/Status";
import { EvidenceState } from "@/components/EvidenceState";

/** Movement against the previous analysed test. `null` means there is no
 * earlier test to compare with, shown as an em dash, never as "0". */
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

/** The student roster table shared by Class detail and the per-test class
 * page: subject filter, quick presets (All / Top 10 / Need Attention /
 * Critical), and a fixed-height, sticky-header, internally-scrolling table
 * of the full roster (not a sample, not paginated). */
export function StudentRosterTable({
  roster,
  testKey,
  section,
  testStatus,
  testName,
  fillHeight = false,
  leadingFilters,
  heading,
}: {
  roster: FullRosterStudent[];
  testKey: string;
  section: string;
  testStatus: "Analysed" | "Scheduled";
  testName?: string;
  /** Extra controls rendered in the same filter row (the class page puts
   * its Test picker here so both selects sit on one line). */
  leadingFilters?: React.ReactNode;
  /** Card + table grow to fill the parent's remaining height (for the
   * single-screen test-sheet page) instead of capping at a fixed height. */
  fillHeight?: boolean;
  /** Rendered above the filters, inside the same frozen block (e.g. the
   * "Students in X-A" heading), so it freezes with the filters and tabs
   * rather than scrolling away above them. Ignored in fillHeight mode,
   * where the page itself never scrolls. */
  heading?: React.ReactNode;
}) {
  const router = useRouter();
  const [subjectFilter, setSubjectFilter] = useState("All");
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("all");
  const [query, setQuery] = useState("");

  // The frozen heading + filters + tabs block's own height, measured so the
  // table's <thead> can stick right below it (rather than at the very top,
  // which would tuck it under the frozen block once both are stuck). Only
  // needed outside fillHeight mode, that one has no page-level scroll to
  // freeze against in the first place.
  const stickyRef = useRef<HTMLDivElement>(null);
  const [stickyHeight, setStickyHeight] = useState(0);
  useEffect(() => {
    if (fillHeight || !stickyRef.current) return;
    const el = stickyRef.current;
    const measure = () => setStickyHeight(el.offsetHeight);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [fillHeight]);

  // The test before this one, so the table can show movement rather than
  // a standing figure with no context.
  const prevTestKey = useMemo(() => {
    const i = analysedTests.findIndex((t) => t.key === testKey);
    return i > 0 ? analysedTests[i - 1].key : null;
  }, [testKey]);

  const rows = useMemo(() => {
    if (testStatus !== "Analysed") return [];
    const withScore = roster.map((s) => ({
      student: s,
      pct: Math.round(pctFor(s, testKey, subjectFilter)),
      delta: prevTestKey ? Math.round(pctFor(s, testKey, subjectFilter) - pctFor(s, prevTestKey, subjectFilter)) : null,
      attention: attentionFor(s, testKey),
      blocker: mainBlockerFor(s, testKey),
    }));

    let filtered = withScore;
    // Match from the start of the first name or surname, so "a" lists every
    // A-name and "ar" narrows it to Arjun, Aryan and so on as you type.
    const q = query.trim().toLowerCase();
    if (q) filtered = filtered.filter((r) => r.student.name.toLowerCase().split(/\s+/).some((w) => w.startsWith(q)) || r.student.name.toLowerCase().startsWith(q));
    if (quickFilter === "attention") filtered = filtered.filter((r) => r.attention !== "On Track");
    if (quickFilter === "critical") filtered = filtered.filter((r) => r.attention === "Intervention");

    // Top 10 is best-first; the two risk presets are worst-first, because
    // that's the order you'd actually work down the list in.
    filtered = [...filtered].sort((a, b) => {
      if (quickFilter === "top10") return b.pct - a.pct;
      if (quickFilter === "attention" || quickFilter === "critical") return a.pct - b.pct;
      return Number(a.student.rollNo) - Number(b.student.rollNo);
    });
    if (quickFilter === "top10") filtered = filtered.slice(0, 10);
    return filtered;
  }, [roster, testKey, prevTestKey, testStatus, subjectFilter, quickFilter, query]);

  return (
    <div style={fillHeight ? { display: "flex", flexDirection: "column", flex: 1, minHeight: 0 } : undefined}>
      <div ref={stickyRef} className={fillHeight ? undefined : "roster-sticky"} style={{ flex: "0 0 auto" }}>
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
          <div className="filter">
            <label htmlFor="subject-filter">Subject</label>
            <select id="subject-filter" className="select" value={subjectFilter} onChange={(e) => setSubjectFilter(e.target.value)}>
              <option value="All">All subjects</option>
              {subjects.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </div>
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
        {testStatus !== "Analysed" ? (
          <div className="placeholder">
            <p>{testName ?? "This test"} hasn&apos;t been conducted yet, no marks to show.</p>
          </div>
        ) : (
          <div
            className={`table-wrap ${fillHeight ? "table-wrap--flex" : "table-wrap--stack"}`}
            style={fillHeight ? undefined : ({ "--sticky-offset": `${stickyHeight}px` } as React.CSSProperties)}
          >
            <table className="table table--hover table--roster">
              <thead>
                <tr>
                  <th>Roll</th>
                  <th>Student</th>
                  <th className="num">{subjectFilter === "All" ? "Overall" : subjectFilter}</th>
                  <th className="num">vs last</th>
                  <th>Main blocker</th>
                  <th>Attention</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={7}>
                      <EvidenceState kind="early" compact>
                        No students match this filter.
                      </EvidenceState>
                    </td>
                  </tr>
                )}
                {rows.map(({ student: s, pct, delta, attention, blocker }) => (
                  <tr key={s.id} onClick={() => router.push(`/principal/classes/${section}/${s.id}`)}>
                    <td className="muted">{s.rollNo}</td>
                    <td className="strong">{s.name}</td>
                    <td className="num">{pct}%</td>
                    <td className="num">
                      <DeltaCell delta={delta} />
                    </td>
                    <td>{blocker}</td>
                    <td>
                      <AttentionPill level={attention} />
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <Link href={`/principal/classes/${section}/${s.id}`} className="btn btn--sm" onClick={(e) => e.stopPropagation()}>
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
          {quickFilter === "top10" ? `Top ${rows.length} of ${roster.length}` : `Showing ${rows.length} of ${roster.length} students.`}
        </div>
      </div>
    </div>
  );
}
