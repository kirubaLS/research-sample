"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type TeacherSectionSummary } from "@/lib/api";
import { getApiKey } from "@/lib/session";

export default function MyClasses() {
  const [sections, setSections] = useState<TeacherSectionSummary[] | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api.teacherSections(key).then((res) => setSections(res.sections));
  }, []);

  const classSections = (sections ?? []).filter((s) => s.can_read_all_subjects);

  return (
    <main className="narrow">
      <div className="hero">
        <h1>My Classes</h1>
      </div>
      <div className="stack" style={{ gap: 10 }}>
        {classSections.map((s) => (
          <Link key={s.section_id} href={`/teacher/classes/${s.section_id}`} className="card row between">
            <strong>{s.label ?? "Class"}</strong>
          </Link>
        ))}
        {sections && classSections.length === 0 && (
          <p className="muted">No classes assigned to this key yet.</p>
        )}
      </div>
    </main>
  );
}
