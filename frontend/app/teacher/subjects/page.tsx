"use client";

import Link from "next/link";
import { MOCK_TEACHER, subjectLabel } from "@/lib/mocks/teacher";

export default function MySubjects() {
  const subjectAssignments = MOCK_TEACHER.assignments.filter((a) => a.type === "subject");
  return (
    <main className="narrow">
      <div className="hero">
        <h1>My Subjects</h1>
      </div>
      <div className="stack" style={{ gap: 10 }}>
        {subjectAssignments.map((a) =>
          a.type === "subject" ? (
            <Link
              key={`${a.subjectCode}-${a.sectionId}`}
              href={`/teacher/subjects/${a.subjectCode}/${a.sectionId}`}
              className="card row between"
            >
              <strong>{subjectLabel(a.subjectCode)} · {a.sectionLabel}</strong>
              <span className="cardnote">{a.students} students</span>
            </Link>
          ) : null,
        )}
      </div>
    </main>
  );
}
