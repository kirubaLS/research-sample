"use client";

/**
 * Teacher Home, subject-first -- the new design's §6.1 grouping. The data underneath is
 * identical to /teacher/overview (GET /admin/teacher/academics: one row per class/subject
 * this teacher key holds), only regrouped for display: a teacher thinks "my Maths classes"
 * and "my Chemistry classes" before "my classes," and a subject card with two section rows
 * says that more directly than a flat list of class/subject rows ever could.
 *
 * A row with no subject_code (a class-teacher assignment, which reads every subject for
 * that section rather than one) cannot join a subject group honestly -- it is not about
 * one subject -- so those are kept in their own "Your Classes" group instead of forced
 * into whichever subject happened to be scored first.
 *
 * /teacher/overview (the flat version) is left exactly as it was: nothing here replaces
 * it yet, this is the first page of an in-progress redesign and the old route is the
 * fallback until every page it links to has its own redesigned counterpart.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { Mascot } from "@/components/Mascot";
import { api, type TeacherAcademicClassRow } from "@/lib/api";
import { getApiKey, getSchoolName } from "@/lib/session";

export default function TeacherHomePage() {
  const [classes, setClasses] = useState<TeacherAcademicClassRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const name = getSchoolName();

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
        <p className="eyebrow">Teacher Home</p>
        <h1 style={{ margin: 0 }}>{name ? `Welcome, ${name}` : "My Subjects"}</h1>
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

      {classes && classes.length > 0 && <SubjectGroups classes={classes} />}
    </main>
  );
}

function SubjectGroups({ classes }: { classes: TeacherAcademicClassRow[] }) {
  // subject_code null => a class-teacher assignment (every subject of that section, not
  // one) -- kept apart rather than mixed into a subject group it does not belong to.
  const bySubject = new Map<string, { label: string; rows: TeacherAcademicClassRow[] }>();
  const wholeClass: TeacherAcademicClassRow[] = [];
  for (const row of classes) {
    if (!row.subject_code) {
      wholeClass.push(row);
      continue;
    }
    const group = bySubject.get(row.subject_code) ?? { label: row.subject_label, rows: [] };
    group.rows.push(row);
    bySubject.set(row.subject_code, group);
  }

  return (
    <div className="stack" style={{ gap: 20 }}>
      {wholeClass.length > 0 && (
        <SubjectCard title="Your Classes" rows={wholeClass} />
      )}
      {[...bySubject.entries()]
        .sort((a, b) => a[1].label.localeCompare(b[1].label))
        .map(([code, group]) => (
          <SubjectCard key={code} title={group.label} rows={group.rows} />
        ))}
    </div>
  );
}

function SubjectCard({ title, rows }: { title: string; rows: TeacherAcademicClassRow[] }) {
  return (
    <div className="card">
      <div className="card__body">
        <h3 style={{ fontSize: 18, margin: "0 0 12px" }}>{title}</h3>
        <div className="stack" style={{ gap: 8 }}>
          {rows.map((c) => (
            <Link
              key={`${c.section_id}-${c.subject_code ?? "all"}`}
              href={`/teacher/overview/${c.section_id}${c.subject_code ? `?subject=${c.subject_code}` : ""}`}
              className="subject-row"
            >
              <div>
                <div className="strong">{c.label}</div>
                <div className="small muted">
                  {c.student_count} students
                  {c.avg_score_pct != null ? ` · ${c.avg_score_pct}% avg` : " · not yet assessed"}
                  {c.test_count > 0 ? ` · ${c.test_count} paper${c.test_count === 1 ? "" : "s"}` : ""}
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>

      <style jsx>{`
        .card__body { padding: 4px 4px 8px; }
        .subject-row {
          display: flex; align-items: center; justify-content: space-between;
          padding: 10px 12px; border: 1px solid var(--rule); border-radius: var(--radius-sm, 10px);
          text-decoration: none; color: inherit; transition: border-color 0.15s ease;
        }
        .subject-row:hover { border-color: var(--brand-teal); }
      `}</style>
    </div>
  );
}
