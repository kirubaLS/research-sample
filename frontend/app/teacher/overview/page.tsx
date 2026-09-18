"use client";

/**
 * The same Overview a principal opens, narrowed to exactly this teacher key's own
 * class/subject assignments -- a class assignment shows every subject for that
 * section; a subject assignment shows only its own subject's marks. Real data only:
 * GET /admin/teacher/academics.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { Mascot } from "@/components/Mascot";
import { api, type TeacherAcademicClassRow } from "@/lib/api";
import { getApiKey } from "@/lib/session";

export default function TeacherOverviewPage() {
  const [classes, setClasses] = useState<TeacherAcademicClassRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherAcademicsOverview(key)
      .then((res) => setClasses(res.classes))
      .catch(() => setError("Could not load your classes."));
  }, []);

  return (
    <main className="narrow">
      <div className="hero">
        <p className="eyebrow">Overview</p>
        <h1 style={{ margin: 0 }}>Your Classes</h1>
      </div>

      {error && <p className="error">{error}</p>}
      {!classes && !error && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      )}
      {classes && classes.length === 0 && (
        <p className="muted">No classes or subjects are assigned to this key yet.</p>
      )}

      {classes && classes.length > 0 && (
        <div className="stack" style={{ gap: 12 }}>
          {classes.map((c) => {
            const counts = c.status_counts;
            const total = c.student_count || 1;
            const segments = [
              { n: counts.on_track, color: "var(--verify)" },
              { n: counts.needs_attention, color: "var(--warn)" },
              { n: counts.requires_review, color: "var(--risk)" },
              { n: counts.not_assessed, color: "var(--rule-2)" },
            ];
            return (
              <Link
                key={`${c.section_id}-${c.subject_code ?? "all"}`}
                href={`/teacher/overview/${c.section_id}${c.subject_code ? `?subject=${c.subject_code}` : ""}`}
                style={{ textDecoration: "none", color: "inherit" }}
              >
                <div className="card">
                  <div className="row between" style={{ alignItems: "flex-start" }}>
                    <div>
                      <strong>{c.label}</strong>
                      <p className="cardnote" style={{ margin: "2px 0 0" }}>
                        {c.subject_label} · {c.student_count} students
                      </p>
                    </div>
                    {c.avg_score_pct != null && <span className="badge blue">{c.avg_score_pct}% avg</span>}
                  </div>
                  <div
                    style={{
                      display: "flex", height: 8, borderRadius: 999, overflow: "hidden",
                      background: "var(--rule)", marginTop: 12,
                    }}
                  >
                    {segments.map((s, i) => s.n > 0 && (
                      <div key={i} style={{ width: `${(s.n / total) * 100}%`, background: s.color }} />
                    ))}
                  </div>
                  <p className="small muted" style={{ marginTop: 8, marginBottom: 0 }}>
                    {c.test_count} paper{c.test_count === 1 ? "" : "s"} with marks recorded
                  </p>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </main>
  );
}
