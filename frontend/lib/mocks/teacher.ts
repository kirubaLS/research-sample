/**
 * Mocked teacher-role fixture data.
 *
 * TODO(backend): Dependency Index #1 -- the backend has no `teacher` StaffKey role and no
 * `teacher_assignment` table today (only `principal`/`admin`). Everything in this file
 * stands in for what `GET /admin/me` would return once that role/assignment model exists,
 * and for the roster/marks rows a real scoped endpoint would return. None of it is wired
 * to a real endpoint -- every call site that reads from here carries its own
 * `// TODO(backend): Dependency Index #1` comment as well.
 */

export type TeacherAssignment =
  | { type: "class"; sectionId: string; sectionLabel: string; students: number }
  | {
      type: "subject";
      subjectCode: string;
      subjectLabel: string;
      sectionId: string;
      sectionLabel: string;
      students: number;
    };

export interface MockTeacher {
  name: string;
  assignments: TeacherAssignment[];
}

// The fixture the spec itself suggests: one Class Teacher assignment, one Subject
// Teacher assignment, so both "My Classes" and "My Subjects" render on home (§6.1).
export const MOCK_TEACHER: MockTeacher = {
  name: "Mrs. Lakshmi",
  assignments: [
    { type: "class", sectionId: "10-A", sectionLabel: "10-A", students: 32 },
    {
      type: "subject",
      subjectCode: "MATH",
      subjectLabel: "Maths",
      sectionId: "10-A",
      sectionLabel: "10-A",
      students: 32,
    },
    {
      type: "subject",
      subjectCode: "MATH",
      subjectLabel: "Maths",
      sectionId: "10-B",
      sectionLabel: "10-B",
      students: 30,
    },
  ],
};

export interface MockRosterRow {
  studentId: string;
  roll: string;
  name: string;
  scores: Record<string, number | null>; // subjectCode -> marks out of 80
  conceptGap?: string;
}

const SUBJECTS: { code: string; label: string }[] = [
  { code: "MATH", label: "Maths" },
  { code: "SCI", label: "Science" },
  { code: "SOC", label: "Social" },
];

function rosterFor(sectionId: string, count: number): MockRosterRow[] {
  const rows: MockRosterRow[] = [];
  const names = [
    "Aditi R.", "Bala S.", "Chitra M.", "Dinesh K.", "Elango V.", "Farida N.",
    "Gowri P.", "Harish T.", "Ishwarya D.", "Jeevan A.",
  ];
  for (let i = 0; i < count; i++) {
    const roll = String(i + 1).padStart(2, "0");
    const seed = sectionId.charCodeAt(sectionId.length - 1) + i;
    rows.push({
      studentId: `${sectionId}-${roll}`,
      roll,
      name: `${names[i % names.length]}`,
      scores: {
        MATH: 40 + ((seed * 7) % 40),
        SCI: 38 + ((seed * 11) % 42),
        SOC: 45 + ((seed * 5) % 35),
      },
      conceptGap: seed % 3 === 0 ? "Applying-tier ↓" : seed % 3 === 1 ? "Cross-subject ⚠" : undefined,
    });
  }
  return rows;
}

// TODO(backend): Dependency Index #1 -- a real Class view roster would come from a
// section-scoped roster/cohort endpoint once teacher assignment scoping exists.
export const MOCK_CLASS_ROSTERS: Record<string, MockRosterRow[]> = {
  "10-A": rosterFor("10-A", 32),
  "10-B": rosterFor("10-B", 30),
};

export const MOCK_SUBJECTS = SUBJECTS;

export function subjectLabel(code: string): string {
  return SUBJECTS.find((s) => s.code === code)?.label ?? code;
}

export interface MockPaper {
  title: string;
  subjectCode: string;
}

// TODO(backend): Dependency Index #1 -- "papers this term" per section is illustrative
// only; a real Class/Subject view would read this from the existing assessments endpoints
// once scoped by teacher assignment.
export const MOCK_PAPERS_THIS_TERM: Record<string, MockPaper[]> = {
  "10-A": [
    { title: "Unit Test 2", subjectCode: "MATH" },
    { title: "Unit Test 2", subjectCode: "SCI" },
    { title: "Unit Test 2", subjectCode: "SOC" },
  ],
  "10-B": [{ title: "Unit Test 2", subjectCode: "MATH" }],
};

// TODO(backend): Dependency Index #1 -- Manage Teachers (spec §5.11) has no backend
// storage yet; this in-memory list is a placeholder for `teacher_assignment` rows,
// reset on reload. It exists so the screen has something to render and edit against.
export interface MockManagedTeacher {
  id: string;
  name: string;
  assignments: TeacherAssignment[];
  keyIssuedAt: string;
  revoked: boolean;
}

export const MOCK_MANAGED_TEACHERS: MockManagedTeacher[] = [
  {
    id: "t1",
    name: "Mrs. Lakshmi",
    assignments: MOCK_TEACHER.assignments,
    keyIssuedAt: "2026-06-02",
    revoked: false,
  },
  {
    id: "t2",
    name: "Mr. Ravi",
    assignments: [
      { type: "subject", subjectCode: "SCI", subjectLabel: "Science", sectionId: "10-A", sectionLabel: "10-A", students: 32 },
      { type: "subject", subjectCode: "SCI", subjectLabel: "Science", sectionId: "10-C", sectionLabel: "10-C", students: 29 },
    ],
    keyIssuedAt: "2026-05-14",
    revoked: false,
  },
];

export function assignmentLabel(a: TeacherAssignment): string {
  return a.type === "class"
    ? `Class Teacher · ${a.sectionLabel}`
    : `Subject Teacher · ${a.subjectLabel} · ${a.sectionLabel}`;
}

/** A short, clearly-fake sign-in key -- never a real StaffKey, never sent anywhere. */
export function mockGenerateKey(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let out = "";
  for (let i = 0; i < 24; i++) out += chars[Math.floor(Math.random() * chars.length)];
  return out;
}
