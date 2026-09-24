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
 * /teacher/overview (the old flat version, and its own detail route) is retired: this
 * page and app/teacher/home/[sectionId] are its replacements, and /teacher/overview now
 * redirects here -- see app/teacher/overview/page.tsx and app/teacher/overview/[sectionId]/page.tsx.
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
    <>
      <p className="eyebrow">Teacher Home</p>
      <h1 className="page-title" style={{ marginTop: 4 }}>{name ? `Welcome, ${name}` : "My Subjects"}</h1>

      {error && <p className="page-sub" style={{ color: "var(--risk)" }}>{error}</p>}
      {!classes && !error && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 16 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      )}
      {classes && classes.length === 0 && (
        <p className="muted" style={{ marginTop: 16 }}>No classes or subjects are assigned to this key yet.</p>
      )}

      {classes && classes.length > 0 && <SubjectGroups classes={classes} />}
    </>
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
    <div className="section" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
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

/** The dominant status among a class's own status_counts -- the same four bands
 *  StatusOverviewBar/StatusBadge already use everywhere else, read here as one pill per
 *  row instead of a bar, since a row is one class/subject rather than many students. */
function dominantAttn(c: TeacherAcademicClassRow): { label: string; cls: string } | null {
  const counts = c.status_counts;
  const total = counts.on_track + counts.needs_attention + counts.requires_review + counts.not_assessed;
  if (total === 0 || total === counts.not_assessed) return null;
  if (counts.requires_review > 0) return { label: "Needs review", cls: "attn--high" };
  if (counts.needs_attention > 0) return { label: "Needs attention", cls: "attn--medium" };
  return { label: "On track", cls: "attn--low" };
}

function SubjectCard({ title, rows }: { title: string; rows: TeacherAcademicClassRow[] }) {
  return (
    <div className="card">
      <div className="card__head">
        <h3 style={{ fontSize: 18, margin: 0 }}>{title}</h3>
        <span className="small muted">{rows.length} class{rows.length === 1 ? "" : "es"}</span>
      </div>
      <div className="card__body">
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {rows.map((c) => {
            const attn = dominantAttn(c);
            return (
              <Link
                key={`${c.section_id}-${c.subject_code ?? "all"}`}
                href={`/teacher/home/${c.section_id}${c.subject_code ? `?subject=${c.subject_code}` : ""}`}
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
                {attn && <span className={`attn ${attn.cls}`}>{attn.label}</span>}
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
