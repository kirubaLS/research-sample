/**
 * Mocked student-auth + student-report fixture data.
 *
 * TODO(backend): Dependency Index #2 -- students never authenticate today (roll no +
 * school code + PIN does not exist as a backend auth path), and there is no
 * `shared_with_student` flag on `student_report`. Everything here stands in for what a
 * real student-auth + share flow would return. None of it is wired to a real endpoint --
 * any PIN "unlocks" this fixed set of mock reports for the demo only.
 */

export interface MockStudentReport {
  reportId: string;
  subjectLabel: string;
  term: string;
  score: number;
  outOf: number;
  previousScore: number | null; // for trend arrow / mascot pose
  sharedAt: string; // human-readable relative-ish string for the list
  doingWell: string[];
  workOnNext: string[];
  encouragement: string;
}

// TODO(backend): Dependency Index #2 -- a real student home would read from
// `GET /students/me/reports` (or similar) filtered to `shared_with_student: true`.
export const MOCK_STUDENT_REPORTS: MockStudentReport[] = [
  {
    reportId: "demo-report-maths-t2",
    subjectLabel: "Maths",
    term: "Term 2",
    score: 78,
    outOf: 80,
    previousScore: 65,
    sharedAt: "3 days ago",
    doingWell: ["Recall-based questions", "Basic algebra"],
    workOnNext: ["Quadratic equations — application-style questions"],
    encouragement: "Keep going. You're on the right path.",
  },
  {
    reportId: "demo-report-science-t1",
    subjectLabel: "Science",
    term: "Term 1",
    score: 65,
    outOf: 80,
    previousScore: 65,
    sharedAt: "2 months ago",
    doingWell: ["Life processes", "Diagrams and labelling"],
    workOnNext: ["Numerical problems in electricity"],
    encouragement: "Solid, steady work. A little more practice on numericals will help.",
  },
];

export function mockStudentReport(reportId: string): MockStudentReport | null {
  return MOCK_STUDENT_REPORTS.find((r) => r.reportId === reportId) ?? null;
}

/** Trend: "improve" if this attempt beats the last one on file for this subject, "achieve"
 *  for a standout result (90%+ and improving), otherwise neutral (no pose). Mirrors §7.3's
 *  mascot rule, applied to the mock trend numbers above -- this is presentation logic
 *  only, not a new backend computation. */
export function mockTrendPose(r: MockStudentReport): "achieve" | "improve" | null {
  const pct = r.score / r.outOf;
  const prevPct = r.previousScore != null ? r.previousScore / r.outOf : null;
  const improving = prevPct != null && r.score > r.previousScore!;
  if (improving && pct >= 0.9) return "achieve";
  if (improving) return "improve";
  return null;
}

export interface MockStudentIdentity {
  name: string;
  rollNo: string;
  schoolCode: string;
}

// TODO(backend): Dependency Index #2 -- there is no student-auth endpoint yet. Any
// non-empty roll number + school code + PIN "signs in" here and returns this fixed
// identity + report set, purely for demoing the flow end to end.
export const MOCK_STUDENT_IDENTITY: MockStudentIdentity = {
  name: "Aditi",
  rollNo: "01",
  schoolCode: "DEMO01",
};
