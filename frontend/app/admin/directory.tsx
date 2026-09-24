"use client";

/**
 * Shared bits for the operator console's forms.
 *
 * The reference design's directory.tsx also carried AccessMatrix, TeacherModal
 * and StudentsEditor -- a full "which subjects/sections can this teacher see"
 * matrix and a paste-from-spreadsheet student roster editor. Neither has a
 * real backend counterpart: /platform has no bulk teacher/student import and
 * no per-teacher subject/section access grant (a school's own principal key
 * manages its teachers' section/subject assignments from inside /admin, via
 * api.createTeacher/addTeacherAssignment -- a different, already-real screen
 * outside this task's scope). Dropped here rather than wired to nothing;
 * see the gap note in the wiring report.
 */

export function FieldError({ children }: { children?: React.ReactNode }) {
  if (!children) return null;
  return <span className="ops-err">{children}</span>;
}
