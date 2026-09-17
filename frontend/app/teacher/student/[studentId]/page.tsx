"use client";

/**
 * §6.4 -- Teacher-facing student page.
 *
 * Real data only: the student's row from this teacher's own section roster
 * (GET /admin/teacher/sections/{id}/students), scoped exactly like every other teacher
 * read. Issuing a report and viewing per-subject findings both go through
 * /reports/student/{id}, which is require_reader-gated and, in this pass, deliberately
 * not opened to a teacher key (see backend/app/api/deps.py's require_reader docstring) --
 * so those actions are not offered here yet rather than shown broken. "Share with
 * student" issues a real PIN for a report already issued elsewhere (a principal, from
 * the student's admin page) -- see ShareWithStudentModal.
 */

import { use, useEffect, useState } from "react";
import { api, type RosterRow } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { ShareWithStudentModal } from "@/components/teacher/ShareWithStudentModal";

export default function TeacherStudentPage({
  params,
}: {
  params: Promise<{ studentId: string }>;
}) {
  const { studentId } = use(params);
  const [student, setStudent] = useState<RosterRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shareOpen, setShareOpen] = useState(false);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherSections(key)
      .then(async (res) => {
        for (const s of res.sections) {
          const roster = await api.teacherRoster(key, s.section_id);
          const found = roster.students.find((r) => r.student_id === studentId);
          if (found) {
            setStudent(found);
            return;
          }
        }
        setError("This student is not in one of your assigned classes.");
      })
      .catch(() => setError("Could not load this student."));
  }, [studentId]);

  if (error) {
    return (
      <main className="narrow">
        <p className="error">{error}</p>
      </main>
    );
  }
  if (!student) {
    return (
      <main className="narrow">
        <p className="muted">Loading…</p>
      </main>
    );
  }

  return (
    <main className="narrow">
      <div className="hero">
        <h1>{student.name} · Roll {student.roll_no}</h1>
      </div>
      <div className="card">
        <p className="cardnote" style={{ marginTop: 0 }}>Status: {student.status.replace("_", " ")}</p>
        <p className="cardnote">Papers marked: {student.papers_marked}</p>
        <div className="row" style={{ gap: 8, marginTop: 10 }}>
          <button type="button" className="secondary" onClick={() => setShareOpen(true)}>
            Share with student
          </button>
        </div>
      </div>

      {shareOpen && (
        <ShareWithStudentModal
          studentId={student.student_id}
          studentName={student.name}
          onClose={() => setShareOpen(false)}
        />
      )}
    </main>
  );
}
