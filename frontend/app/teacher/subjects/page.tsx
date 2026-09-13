"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type TeacherSectionSummary } from "@/lib/api";
import { getApiKey } from "@/lib/session";

export default function MySubjects() {
  const [sections, setSections] = useState<TeacherSectionSummary[] | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api.teacherSections(key).then((res) => setSections(res.sections));
  }, []);

  const rows = (sections ?? []).flatMap((s) => s.subjects.map((subject) => ({ section: s, subject })));

  return (
    <main className="narrow">
      <div className="hero">
        <h1>My Subjects</h1>
      </div>
      <div className="stack" style={{ gap: 10 }}>
        {rows.map(({ section, subject }) => (
          <Link
            key={`${subject}-${section.section_id}`}
            href={`/teacher/subjects/${subject}/${section.section_id}`}
            className="card row between"
          >
            <strong>{subject} · {section.label ?? "Class"}</strong>
          </Link>
        ))}
        {sections && rows.length === 0 && (
          <p className="muted">No subjects assigned to this key yet.</p>
        )}
      </div>
    </main>
  );
}
