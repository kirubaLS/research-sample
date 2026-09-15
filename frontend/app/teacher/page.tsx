"use client";

// §6.1 -- teacher home: every section this teacher key holds, split into "My Classes"
// (class assignments) and "My Subjects" (subject assignments), from the real
// /admin/teacher/sections endpoint -- scoped to this key's own TeacherAssignment rows.

import Link from "next/link";
import { useEffect, useState } from "react";
import { Mascot } from "@/components/Mascot";
import { api, type TeacherSectionSummary } from "@/lib/api";
import { getApiKey } from "@/lib/session";

export default function TeacherHome() {
  const [sections, setSections] = useState<TeacherSectionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherSections(key)
      .then((res) => setSections(res.sections))
      .catch(() => setError("Could not load your classes. Try again in a minute."));
  }, []);

  const classSections = (sections ?? []).filter((s) => s.can_read_all_subjects);
  const subjectRows = (sections ?? []).flatMap((s) =>
    s.subjects.map((subject) => ({ section: s, subject })),
  );

  return (
    <main className="narrow">
      <div className="hero">
        <h1>Welcome back</h1>
      </div>

      {error && <p className="error">{error}</p>}
      {!sections && !error && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      )}

      {sections && classSections.length > 0 && (
        <>
          <div className="section-head">
            <p className="eyebrow">Class Teacher</p>
            <h2>My Classes</h2>
          </div>
          <div className="stack" style={{ gap: 10 }}>
            {classSections.map((s) => (
              <div className="card row between" key={s.section_id}>
                <div>
                  <strong>{s.label ?? "Class"}</strong>
                </div>
                <Link href={`/teacher/classes/${s.section_id}`}>
                  <button type="button" className="secondary">View class</button>
                </Link>
              </div>
            ))}
          </div>
        </>
      )}

      {sections && subjectRows.length > 0 && (
        <>
          <div className="section-head">
            <p className="eyebrow">Subject Teacher</p>
            <h2>My Subjects</h2>
          </div>
          <div className="stack" style={{ gap: 10 }}>
            {subjectRows.map(({ section, subject }) => (
              <div className="card row between" key={`${subject}-${section.section_id}`}>
                <div>
                  <strong>{subject} · {section.label ?? "Class"}</strong>
                </div>
                <Link href={`/teacher/subjects/${subject}/${section.section_id}`}>
                  <button type="button" className="secondary">Open</button>
                </Link>
              </div>
            ))}
          </div>
        </>
      )}

      {sections && classSections.length === 0 && subjectRows.length === 0 && (
        <p className="muted">No classes or subjects are assigned to this key yet. Ask your
          principal to add one.</p>
      )}
    </main>
  );
}
