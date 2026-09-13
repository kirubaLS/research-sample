"use client";

/**
 * §6.4 -- Teacher-facing student report page. One shared component in spirit with the
 * principal's Individual Student Intelligence (§5.6) and the real
 * frontend/app/admin/students/[studentId]/page.tsx, but lighter: leads with
 * Issue/Share actions instead of the board-urgency-ranked narrative summary, and a
 * Subject Teacher only ever sees their own subject's row (never Science/Social in
 * passing) while a Class Teacher sees every subject stacked.
 *
 * TODO(backend): Dependency Index #1 -- student/roster/score/strengths/focus data below
 * is mocked (MOCK_CLASS_ROSTERS has no real per-subject diagnosis attached); a real
 * version reads the same StudentDiagnosis object admin/students/[studentId] already
 * renders via <Diagnosis/>, scoped by a real teacher_assignment.
 *
 * [Issue this report] is wired to the REAL `POST /reports/student/{id}/issue` via
 * api.issueReport -- ✅ buildable now per the spec. It is called with this mocked
 * studentId/assessmentId, so on a real backend without a matching record it will
 * correctly fail rather than fake a success; only the teacher-scoping context around it
 * is mocked.
 */

import { Suspense, use, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { MOCK_CLASS_ROSTERS, MOCK_SUBJECTS, MOCK_TEACHER, subjectLabel } from "@/lib/mocks/teacher";
import { ShareWithStudentModal } from "@/components/teacher/ShareWithStudentModal";

// TODO(backend): Dependency Index #1 -- illustrative strengths/focus text per subject,
// standing in for the real Finding[] a StudentDiagnosis would carry.
function mockNotes(subjectCode: string, score: number) {
  const strong = score >= 65;
  return {
    strengths: strong ? ["Recall", "Algebra basics"] : ["Recall-based questions"],
    focus: strong
      ? ["Applying-tier — Quadratic Equations"]
      : [`${subjectLabel(subjectCode)} — application-style questions`],
  };
}

export default function TeacherStudentReport({
  params,
}: {
  params: Promise<{ studentId: string }>;
}) {
  return (
    <Suspense fallback={null}>
      <TeacherStudentReportInner params={params} />
    </Suspense>
  );
}

function TeacherStudentReportInner({
  params,
}: {
  params: Promise<{ studentId: string }>;
}) {
  const { studentId } = use(params);
  const search = useSearchParams();
  const scopedSubject = search.get("subject");
  const [issuing, setIssuing] = useState(false);
  const [issueNote, setIssueNote] = useState<string | null>(null);
  const [shareOpen, setShareOpen] = useState(false);

  const sectionId = studentId.split("-").slice(0, -1).join("-");
  const roster = MOCK_CLASS_ROSTERS[sectionId] ?? [];
  const student = roster.find((r) => r.studentId === studentId);

  const isClassTeacher = MOCK_TEACHER.assignments.some(
    (a) => a.type === "class" && a.sectionId === sectionId,
  );
  const subjectsToShow = scopedSubject
    ? [scopedSubject]
    : isClassTeacher
      ? MOCK_SUBJECTS.map((s) => s.code)
      : MOCK_SUBJECTS.filter((s) =>
          MOCK_TEACHER.assignments.some(
            (a) => a.type === "subject" && a.subjectCode === s.code && a.sectionId === sectionId,
          ),
        ).map((s) => s.code);

  if (!student) {
    return (
      <main className="narrow">
        <p className="muted">This demo student was not found in the mocked roster.</p>
      </main>
    );
  }

  async function issue(subjectCode: string) {
    const key = getApiKey();
    setIssuing(true);
    setIssueNote(null);
    try {
      if (!key) throw new Error("no key");
      await api.issueReport(key, studentId, `${subjectCode}-unit-test-2`, MOCK_TEACHER.name);
      setIssueNote("Issued.");
    } catch (err) {
      setIssueNote(
        err instanceof ApiError
          ? "Could not issue: this demo student isn't backed by a real record."
          : "Issuing requires a real signed-in staff session (this is a demo student).",
      );
    } finally {
      setIssuing(false);
    }
  }

  return (
    <main className="narrow">
      <div className="hero">
        <h1>{student.name} · Roll {student.roll} · {sectionId}</h1>
      </div>

      {subjectsToShow.map((code) => {
        const score = student.scores[code];
        if (score == null) return null;
        const notes = mockNotes(code, score);
        return (
          <div className="card" key={code} style={{ marginBottom: 14 }}>
            <div className="row between">
              <strong>{subjectLabel(code)} — Term 2 Assessment</strong>
              <strong>{score}/80</strong>
            </div>
            <p className="cardnote">Strengths: {notes.strengths.join(", ")}</p>
            <p className="cardnote">Focus areas: {notes.focus.join(", ")}</p>
            <div className="row" style={{ gap: 8, marginTop: 10 }}>
              <button type="button" disabled={issuing} onClick={() => issue(code)}>
                {issuing ? "Issuing…" : "Issue this report"}
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => setShareOpen(true)}
                title="Share with student"
              >
                Share with student
              </button>
            </div>
          </div>
        );
      })}

      {issueNote && <p className="small muted">{issueNote}</p>}

      {shareOpen && (
        <ShareWithStudentModal studentName={student.name} onClose={() => setShareOpen(false)} />
      )}
    </main>
  );
}
