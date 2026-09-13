"use client";

// §6.1 -- teacher home. Both assignment-type sections stack vertically when the teacher
// holds both kinds; only the relevant section renders otherwise.
// TODO(backend): Dependency Index #1 -- all class/subject/student-count/paper-count
// figures below come from MOCK_TEACHER / MOCK_PAPERS_THIS_TERM, not a real
// teacher_assignment-scoped endpoint.

import Link from "next/link";
import { MOCK_PAPERS_THIS_TERM, MOCK_TEACHER, subjectLabel } from "@/lib/mocks/teacher";

export default function TeacherHome() {
  const classAssignments = MOCK_TEACHER.assignments.filter((a) => a.type === "class");
  const subjectAssignments = MOCK_TEACHER.assignments.filter((a) => a.type === "subject");

  return (
    <main className="narrow">
      <div className="hero">
        <h1>Welcome back, {MOCK_TEACHER.name}</h1>
      </div>

      {classAssignments.length > 0 && (
        <>
          <div className="section-head">
            <p className="eyebrow">Class Teacher</p>
            <h2>My Classes</h2>
          </div>
          <div className="stack" style={{ gap: 10 }}>
            {classAssignments.map((a) =>
              a.type === "class" ? (
                <div className="card row between" key={a.sectionId}>
                  <div>
                    <strong>{a.sectionLabel}</strong>
                    <p className="cardnote">
                      {a.students} students ·{" "}
                      {(MOCK_PAPERS_THIS_TERM[a.sectionId] ?? []).length} papers this term
                    </p>
                  </div>
                  <Link href={`/teacher/classes/${a.sectionId}`}>
                    <button type="button" className="secondary">View class</button>
                  </Link>
                </div>
              ) : null,
            )}
          </div>
        </>
      )}

      {subjectAssignments.length > 0 && (
        <>
          <div className="section-head">
            <p className="eyebrow">Subject Teacher</p>
            <h2>My Subjects</h2>
          </div>
          <div className="stack" style={{ gap: 10 }}>
            {subjectAssignments.map((a) =>
              a.type === "subject" ? (
                <div className="card row between" key={`${a.subjectCode}-${a.sectionId}`}>
                  <div>
                    <strong>{subjectLabel(a.subjectCode)} · {a.sectionLabel}</strong>
                    <p className="cardnote">{a.students} students</p>
                  </div>
                  <Link href={`/teacher/subjects/${a.subjectCode}/${a.sectionId}`}>
                    <button type="button" className="secondary">Open</button>
                  </Link>
                </div>
              ) : null,
            )}
          </div>
        </>
      )}
    </main>
  );
}
