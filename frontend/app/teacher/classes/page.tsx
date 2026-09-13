"use client";

import Link from "next/link";
import { MOCK_TEACHER } from "@/lib/mocks/teacher";

export default function MyClasses() {
  const classAssignments = MOCK_TEACHER.assignments.filter((a) => a.type === "class");
  return (
    <main className="narrow">
      <div className="hero">
        <h1>My Classes</h1>
      </div>
      <div className="stack" style={{ gap: 10 }}>
        {classAssignments.map((a) =>
          a.type === "class" ? (
            <Link key={a.sectionId} href={`/teacher/classes/${a.sectionId}`} className="card row between">
              <strong>{a.sectionLabel}</strong>
              <span className="cardnote">{a.students} students</span>
            </Link>
          ) : null,
        )}
      </div>
    </main>
  );
}
