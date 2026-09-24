"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, TrendingUp } from "lucide-react";
import {
  attentionFor,
  classRosterFull,
  lateBloomersForSubject,
  mainBlockerFor,
  pctFor,
  previousAnalysedTestKey,
} from "@/lib/avai-mock-data";
import { AttentionPill } from "@/components/Status";
import { EvidenceState } from "@/components/EvidenceState";
import { DeltaCell } from "@/components/StudentRosterTable";

type QuickFilter = "all" | "top" | "bloomers" | "critical";

const FILTER_LABEL: Record<QuickFilter, string> = {
  all: "All Students",
  top: "Top Performers",
  bloomers: "Late Bloomers",
  critical: "Critical",
};

/** A subject teacher's own roster table, one subject, one test at a time
 * (picked via `testKey`), with the same quick presets a class teacher
 * gets: top performers, students climbing since the last test, and
 * students needing urgent attention. Unlike StudentRosterTable (which is
 * principal-routed and subject-filterable), this one is locked to a
 * single subject and routes into the teacher's own student page. */
export function SubjectRoster({ subject, section, testKey }: { subject: string; section: string; testKey: string }) {
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("all");
  const roster = useMemo(() => classRosterFull[section] ?? [], [section]);
  const prevTestKey = previousAnalysedTestKey(testKey);

  const bloomerGains = useMemo(() => {
    const list = lateBloomersForSubject(subject, testKey, section);
    return new Map(list.map((b) => [b.student.id, b]));
  }, [subject, testKey, section]);

  const rows = useMemo(() => {
    const withScore = roster.map((s) => ({
      student: s,
      pct: Math.round(pctFor(s, testKey, subject)),
      delta: prevTestKey ? Math.round(pctFor(s, testKey, subject) - pctFor(s, prevTestKey, subject)) : null,
      attention: attentionFor(s, testKey),
      blocker: mainBlockerFor(s, testKey),
    }));

    let filtered = withScore;
    if (quickFilter === "bloomers") filtered = filtered.filter((r) => bloomerGains.has(r.student.id));
    if (quickFilter === "critical") filtered = filtered.filter((r) => r.attention === "Intervention");

    filtered = [...filtered].sort((a, b) => {
      if (quickFilter === "top") return b.pct - a.pct;
      if (quickFilter === "bloomers") return (bloomerGains.get(b.student.id)?.gain ?? 0) - (bloomerGains.get(a.student.id)?.gain ?? 0);
      if (quickFilter === "critical") return a.pct - b.pct;
      return Number(a.student.rollNo) - Number(b.student.rollNo);
    });
    if (quickFilter === "top") filtered = filtered.slice(0, 10);
    return filtered;
  }, [roster, testKey, subject, prevTestKey, quickFilter, bloomerGains]);

  return (
    <div className="card" style={{ marginTop: 14 }}>
      <div className="tabs" role="tablist" style={{ padding: "14px 18px 0" }}>
        {(["all", "top", "bloomers", "critical"] as QuickFilter[]).map((k) => (
          <button
            key={k}
            role="tab"
            aria-selected={quickFilter === k}
            className={`tab ${quickFilter === k ? "tab--active" : ""}`}
            onClick={() => setQuickFilter(k)}
            disabled={k === "bloomers" && !prevTestKey}
          >
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
                    {quickFilter === "bloomers" && !prevTestKey
                      ? "Needs a second analysed test to show movement."
                      : "No students match this filter."}
                  </EvidenceState>
                </td>
              </tr>
            )}
            {rows.map(({ student: s, pct, delta, attention, blocker }) => (
              <tr key={s.id}>
                <td className="muted">{s.rollNo}</td>
                <td className="strong">{s.name}</td>
                <td className="num">{pct}%</td>
                <td className="num">
                  {quickFilter === "bloomers" && bloomerGains.has(s.id) ? (
                    <span className="delta" data-dir="up">
                      <TrendingUp size={12} /> +{bloomerGains.get(s.id)!.gain}pt
                    </span>
                  ) : (
                    <DeltaCell delta={delta} />
                  )}
                </td>
                <td>{blocker}</td>
                <td>
                  <AttentionPill level={attention} />
                </td>
                <td style={{ textAlign: "right" }}>
                  <Link href={`/teacher/student/${s.id}`} className="btn btn--sm">
                    Report <ArrowRight size={12} />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card__foot small muted">
        {quickFilter === "top" ? `Top ${rows.length} of ${roster.length}` : `Showing ${rows.length} of ${roster.length} students.`}
      </div>
    </div>
  );
}
