/**
 * AVAI, Mock data for a fully-mocked, backend-free UI build.
 *
 * Every page in the app should import from here. NOTHING in this project
 * should call fetch()/axios/etc. against a real server. When the real
 * backend exists later, these exports get replaced by real API calls with
 * the same shapes, that's the whole point of keeping this in one file.
 *
 * Shapes here follow avai-frontend-design-spec.md exactly (section refs in
 * comments). Where a shape represents something that doesn't exist in any
 * backend yet (🔧 BACKEND REQUIRED items), that's noted inline too.
 */

// ============================================================
// School / org context
// ============================================================

export const school = {
  id: "sch_001",
  name: "Bharat International Sr. Sec. School",
  board: "CBSE",
  state: "Tamil Nadu",
};

export const academicYear = "2026-27";

export const sections = ["X-A", "X-B"] as const;
/** Students per section, X-A and X-B are not the same size, the way a
 *  real school's sections rarely are. */
/** "X-A" -> "Class 10A", how staff name a section on screen. */
export function sectionLabel(section: string) {
  return `Class 10${section.split("-")[1] ?? section}`;
}
export const sectionSize: Record<string, number> = { "X-A": 45, "X-B": 53 };
export const subjects = [
  "Mathematics",
  "Science",
  "English",
  "Social Science",
] as const;

// ============================================================
// Auth / role mocks (§4 login flow, dev-only role switcher)
// 🔧 Teacher + Student are BACKEND REQUIRED (Index #1, #2), this is a
// stand-in for real sign-in until those exist.
// ============================================================

export type Role = "principal" | "teacher" | "student";

export const mockPrincipal = {
  id: "staff_principal_1",
  name: "Mrs. Kavitha Rajan",
  role: "principal" as const,
};

export type TeacherAssignment =
  | { type: "class"; section: string }
  | { type: "subject"; subject: string; sections: string[] };

export const mockTeachers: Array<{
  id: string;
  name: string;
  role: "teacher";
  assignments: TeacherAssignment[];
  /** An "exam cell" account: every subject, every section, question papers
   *  and marks only, no class-teacher view, no subject insights. AVAI
   *  issues this to the one staff member who runs the exam desk. */
  examsOnly?: boolean;
}> = [
  {
    id: "staff_teacher_1",
    name: "Mrs. Lakshmi",
    role: "teacher",
    assignments: [
      { type: "class", section: "X-A" },
      { type: "subject", subject: "Mathematics", sections: ["X-A", "X-B"] },
    ],
  },
  {
    id: "staff_teacher_2",
    name: "Mr. Ravi",
    role: "teacher",
    assignments: [
      { type: "subject", subject: "Science", sections: ["X-A", "X-B"] },
    ],
  },
  {
    id: "staff_teacher_3",
    name: "Mrs. Deepa Nair",
    role: "teacher",
    assignments: [
      { type: "class", section: "X-B" },
      { type: "subject", subject: "English", sections: ["X-A", "X-B"] },
    ],
  },
  {
    id: "staff_teacher_4",
    name: "Mr. Anand Kumar",
    role: "teacher",
    assignments: [{ type: "subject", subject: "Social Science", sections: ["X-A", "X-B"] }],
  },
  {
    id: "staff_teacher_examcell",
    name: "Mr. Vikram Iyer",
    role: "teacher",
    examsOnly: true,
    assignments: subjects.map((subject) => ({ type: "subject" as const, subject, sections: [...sections] })),
  },
];

export const mockStudentUser = {
  id: "student_aditi",
  name: "Aditi R.",
  rollNo: "01",
  section: "X-A",
};

// ============================================================
// The test calendar. Only tests marked "Analysed" have marks behind
// them; everything downstream (averages, reports, trend) derives from
// this list, so adding a test here lights it up across the app.
// ============================================================

export interface ConductedTest {
  key: string;
  name: string;
  date: string;
  status: "Analysed" | "Scheduled";
  /** Subjects this test covers; every subject when absent. */
  subjects?: string[];
}

export const testsConducted: ConductedTest[] = [
  { key: "unit_test_1", name: "Unit Test 1", date: "2026-06-02", status: "Analysed" },
  { key: "unit_test_2", name: "Unit Test 2", date: "2026-08-14", status: "Analysed" },
  { key: "quarterly", name: "Quarterly Exam", date: "2026-09-25", status: "Scheduled" },
  { key: "half_yearly", name: "Half Yearly Exam", date: "2026-11-10", status: "Scheduled" },
  { key: "pre_board_1", name: "Pre-Board 1", date: "2027-01-15", status: "Scheduled" },
  { key: "pre_board_2", name: "Pre-Board 2", date: "2027-02-10", status: "Scheduled" },
];

/** Analysed tests, oldest first, the spine of every derived number. */
export const analysedTests = testsConducted.filter((t) => t.status === "Analysed");
/** The most recent analysed test: what "current standing" means everywhere.
 *  `let` so it moves forward when a newly marked test completes; ES module
 *  bindings are live, so every importer sees the new value. */
export let latestTest = analysedTests[analysedTests.length - 1];

// ============================================================
// Chapter blueprint, what each subject's marks are made of, and how
// much each chapter is typically worth in the 80-mark Board paper.
// Chapter marks sum exactly to the subject's marks tested, so a
// student's real score can be split across chapters without inventing
// marks that don't exist.
// 🔧 BACKEND REQUIRED, the blueprint would come from paper mapping.
// ============================================================

export interface ChapterSpec {
  chapter: string;
  marks: number;
  /** How much harder than average this chapter is to score in (1.0 = par).
   *  Without this, marks are lost strictly in proportion to chapter size and
   *  the "biggest gap" is always just the biggest chapter. */
  difficulty: number;
  /** Marks this chapter typically carries in the 80-mark Board paper.
   *  null = this assessment didn't test it enough to say. */
  boardMarks: number | null;
}

export const subjectChapters: Record<string, ChapterSpec[]> = {
  Mathematics: [
    { chapter: "Quadratic Equations", marks: 7, boardMarks: 12, difficulty: 1.6 },
    { chapter: "Arithmetic Progressions", marks: 4, boardMarks: 8, difficulty: 0.85 },
    { chapter: "Trigonometry", marks: 3, boardMarks: 10, difficulty: 1.25 },
    { chapter: "Coordinate Geometry", marks: 3, boardMarks: null, difficulty: 0.7 },
  ],
  Science: [
    { chapter: "Electricity", marks: 6, boardMarks: 9, difficulty: 1.55 },
    { chapter: "Light", marks: 4, boardMarks: 7, difficulty: 1.0 },
    { chapter: "Carbon and its Compounds", marks: 5, boardMarks: 8, difficulty: 1.2 },
    { chapter: "Chemical Reactions & Equations", marks: 3, boardMarks: 6, difficulty: 0.9 },
    { chapter: "Periodic Classification", marks: 2, boardMarks: null, difficulty: 0.7 },
  ],
  English: [
    { chapter: "Unseen Passage", marks: 6, boardMarks: 10, difficulty: 1.35 },
    { chapter: "Writing Skills", marks: 5, boardMarks: 10, difficulty: 0.8 },
    { chapter: "Prose Literature", marks: 4, boardMarks: 8, difficulty: 0.85 },
  ],
  "Social Science": [
    { chapter: "Nationalism in India", marks: 6, boardMarks: 10, difficulty: 1.1 },
    { chapter: "Resources and Development", marks: 5, boardMarks: 8, difficulty: 0.8 },
    { chapter: "Power Sharing & Federalism", marks: 5, boardMarks: 8, difficulty: 0.95 },
    { chapter: "Map Work", marks: 4, boardMarks: 5, difficulty: 1.4 },
  ],
};

// Marks tested per subject, derived from the blueprint so the two can
// never drift apart: a chapter's marks always add up to its subject's total.
const subjectMaxMarks: Record<string, number> = Object.fromEntries(
  subjects.map((s) => [s, (subjectChapters[s] ?? []).reduce((sum, c) => sum + c.marks, 0)])
);


// ============================================================
// Full class rosters (2 sections, sized per sectionSize) with one set of
// per-subject scores per analysed test. Deterministically generated
// (seeded per section, never Math.random at render time) so the same
// names and numbers show up on every visit. This roster is the single
// source of truth: class averages, attention, reports and trend are
// all derived from it rather than stated separately.
// 🔧 BACKEND REQUIRED, the whole roster is dummy data.
// ============================================================

function mulberry32(seed: number) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function seedFromString(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (Math.imul(h, 31) + s.charCodeAt(i)) | 0;
  return h;
}

const firstNamePool = [
  "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna", "Ishaan", "Rohan",
  "Kabir", "Aryan", "Dhruv", "Karthik", "Rahul", "Nikhil", "Varun", "Yash", "Aniket", "Siddharth",
  "Aditi", "Ananya", "Diya", "Ishita", "Kavya", "Meera", "Priya", "Riya", "Sneha", "Tanvi",
  "Aarohi", "Anika", "Divya", "Gauri", "Isha", "Kritika", "Lavanya", "Nandini", "Pooja", "Shreya",
  "Manoj", "Sanjay", "Farhan", "Aisha", "Zara", "Vikram", "Naveen", "Ritika",
];
const lastInitialPool = ["R.", "K.", "S.", "M.", "P.", "N.", "V.", "T.", "G.", "D.", "B.", "J.", "A.", "L."];

const sectionMeanPct: Record<string, number> = { "X-A": 81, "X-B": 74 };

export interface TestScore {
  scored: number;
  outOf: number;
}
export interface FullRosterStudent {
  id: string;
  rollNo: string;
  name: string;
  section: string;
  scores: Record<string, Record<string, TestScore>>; // testKey -> subject -> score
}

export type Attention = "On Track" | "Watch" | "Intervention";

export function attentionFromPct(pct: number): Attention {
  if (pct >= 75) return "On Track";
  if (pct >= 55) return "Watch";
  return "Intervention";
}

/** Overall % for one student in one test, across all subjects. */
export function overallPctFor(student: FullRosterStudent, testKey: string): number {
  const row = student.scores[testKey];
  const present = row ? subjects.filter((s) => row[s]) : [];
  if (!present.length) return 0;
  return (present.reduce((sum, s) => sum + row[s].scored / row[s].outOf, 0) / present.length) * 100;
}

/** % for one student, one test, one subject (or overall when subject is "All"). */
export function pctFor(student: FullRosterStudent, testKey: string, subject: string): number {
  if (subject === "All") return overallPctFor(student, testKey);
  const s = student.scores[testKey]?.[subject];
  return s ? (s.scored / s.outOf) * 100 : 0;
}

/** Attention is always relative to the test being looked at, so the flag
 * never contradicts the percentage shown next to it. */
export function attentionFor(student: FullRosterStudent, testKey: string = latestTest.key): Attention {
  return attentionFromPct(overallPctFor(student, testKey));
}

function generateSectionRoster(section: string, count: number): FullRosterStudent[] {
  const rnd = mulberry32(seedFromString(section));
  const mean = sectionMeanPct[section] ?? 75;
  const used = new Set<string>();
  const students: FullRosterStudent[] = [];

  for (let i = 1; i <= count; i++) {
    const rollNo = String(i).padStart(2, "0");
    let name = "";
    do {
      const fn = firstNamePool[Math.floor(rnd() * firstNamePool.length)];
      const ln = lastInitialPool[Math.floor(rnd() * lastInitialPool.length)];
      name = `${fn} ${ln}`;
    } while (used.has(name));
    used.add(name);

    // Each student has their own skill level (wide spread around the
    // section mean) so overall attainment doesn't collapse toward the
    // mean the way averaging independently-random subjects would.
    const studentSkill = mean + (rnd() - 0.5) * 44;
    // How this student moved across the term. Mostly up, some flat, a few
    // down, a class where everyone gains the same amount reads as fake.
    const drift = -4 + rnd() * 12;

    const scores: FullRosterStudent["scores"] = {};
    for (const [testIndex, test] of analysedTests.entries()) {
      const testSkill = studentSkill - (analysedTests.length - 1 - testIndex) * drift;
      scores[test.key] = {};
      for (const subject of subjects) {
        const max = subjectMaxMarks[subject];
        const pct = Math.min(100, Math.max(20, testSkill + (rnd() - 0.5) * 16));
        scores[test.key][subject] = { scored: Math.max(0, Math.round((pct / 100) * max)), outOf: max };
      }
    }

    students.push({ id: `student_${section.replace("-", "")}_${rollNo}`, rollNo, name, section, scores });
  }
  return students;
}

export const classRosterFull: Record<string, FullRosterStudent[]> = Object.fromEntries(
  sections.map((s) => [s, generateSectionRoster(s, sectionSize[s])])
);

// Pin the named students the rest of the app refers to at their original
// roll numbers, so their links keep resolving inside the full roster.
function nameStudent(section: string, rollNo: string, id: string, name: string) {
  const roster = classRosterFull[section];
  const idx = roster.findIndex((s) => s.rollNo === rollNo);
  if (idx >= 0) roster[idx] = { ...roster[idx], id, name };
}
nameStudent("X-A", "01", "student_aditi", "Aditi R.");
nameStudent("X-B", "05", "student_riya", "Riya");
nameStudent("X-B", "14", "student_divya", "Divya");

export const allStudents: FullRosterStudent[] = sections.flatMap((s) => classRosterFull[s]);

/** testKey -> subject -> studentId -> mark per question (questionSets order).
 *  The single source of truth for marks: every subject score, chapter loss,
 *  band, rank and report is derived from these. Seeded at the bottom of
 *  this file for the analysed tests; answer cards saved in Enter Marks
 *  write here through setQuestionMarks(). */
export const questionMarks: Record<string, Record<string, Record<string, number[]>>> = {};

export function findStudent(id: string): FullRosterStudent | undefined {
  return allStudents.find((s) => s.id === id);
}

/** Class average % for a section in a test, the number every class-level
 * figure in the app is built from. */
export function classAveragePct(section: string, testKey: string): number {
  const roster = classRosterFull[section] ?? [];
  if (!roster.length) return 0;
  return roster.reduce((sum, s) => sum + overallPctFor(s, testKey), 0) / roster.length;
}

// ============================================================
// §5.2 Page header / assessment context
// ============================================================

export const assessmentContext = {
  /** "Now" for the whole mock build, every "x days ago" is measured from
   *  here, so the copy never drifts as real time passes. */
  today: "2026-09-19",
  assessmentName: latestTest.name,
  studentsAnalysed: allStudents.length,
  sectionsAnalysed: sections.length,
  subjectsAnalysed: subjects.length,
  boardBlueprintMapping: "Enabled",
  assessmentEvidence: `${analysedTests.length} Test${analysedTests.length === 1 ? "" : "s"}`,
  pilotStatusMessage: `Early Intelligence: this analysis is based on ${analysedTests.map((t) => t.name).join(" and ")}. Prediction confidence keeps improving as more assessments are analysed.`,
  assessmentOptions: testsConducted.map((t) => ({ label: t.name, selectable: t.status === "Analysed" })),
};

// ============================================================
// The reusable "finding" unit (§5.4), used across Marks Loss,
// Urgency vs Impact, Anomalies, and Interventions.
// confidence: ✅ exists at question level (QuestionTier.confidence) -
// aggregation to cohort level should be verified before real wiring.
// causeStatus "not_localized": 🔧 BACKEND REQUIRED (Index #3)
// ============================================================

export type Confidence = "HIGH" | "MEDIUM" | "EMERGING";
export type BoardUrgency = "VERY_HIGH" | "HIGH" | "MEDIUM" | "LOW";
export type CauseStatus = "localized" | "not_localized";

export interface Finding {
  id: string;
  subject: string;
  topic: string;
  subskill: string;
  studentsAffected: number;
  avgMarksLost: number;
  boardUrgency: BoardUrgency;
  boardRecurrence: string; // e.g. "4/4 recent Board years"
  confidence: Confidence;
  causeStatus: CauseStatus;
  observation: string;
  mostAffectedSections?: { section: string; pct: number }[];
  recommendedIntervention?: string[];
}

export const findings: Finding[] = [
  {
    id: "find_quadratics",
    subject: "Mathematics",
    topic: "Quadratic Equations",
    subskill: "Application Problems",
    studentsAffected: 60,
    avgMarksLost: 4.2,
    boardUrgency: "VERY_HIGH",
    boardRecurrence: "4/4 recent Board years",
    confidence: "HIGH",
    causeStatus: "localized",
    observation:
      "Most analysed students demonstrate the underlying concept but lose marks when the same concept appears in application-style questions.",
    mostAffectedSections: [
      { section: "X-B", pct: 66 },
      { section: "X-A", pct: 41 },
    ],
    recommendedIntervention: ["Application-focused revision", "Board-style question practice"],
  },
  {
    id: "find_electricity",
    subject: "Science",
    topic: "Electricity",
    subskill: "Numericals",
    studentsAffected: 50,
    avgMarksLost: 3.8,
    boardUrgency: "HIGH",
    boardRecurrence: "3/4 recent Board years",
    confidence: "HIGH",
    causeStatus: "localized",
    observation:
      "Students consistently lose marks converting the concept into a numerical answer, though the underlying law is generally understood.",
    recommendedIntervention: ["Numerical-practice drill sets", "Worked-example walkthroughs"],
  },
  {
    id: "find_light",
    subject: "Science",
    topic: "Light",
    subskill: undefined as unknown as string,
    studentsAffected: 34,
    avgMarksLost: 2.7,
    boardUrgency: "HIGH",
    boardRecurrence: "3/4 years",
    confidence: "HIGH", // confidence a problem exists, NOT confidence in a cause
    causeStatus: "not_localized", // 🔧 BACKEND REQUIRED (Index #3)
    observation:
      "Students are consistently losing marks across this chapter, but no single subtopic, competency or question pattern explains enough of the loss to identify a reliable cause.",
  },
  {
    id: "find_carbon",
    subject: "Science",
    topic: "Carbon and its Compounds",
    subskill: "Reasoning",
    studentsAffected: 29,
    avgMarksLost: 1.4,
    boardUrgency: "LOW",
    boardRecurrence: "1/4 years",
    confidence: "MEDIUM",
    causeStatus: "localized",
    observation:
      "A smaller, lower-urgency pattern, included to show contrast against high-urgency findings in the Urgency vs. Impact table.",
  },
];

// ============================================================
// §5.3 (10) Section Comparison, DERIVED from the roster, so a class's
// headline attainment always equals the average of the students shown
// in its own table (these used to be stated separately and disagreed).
// ============================================================

export const sectionComparison = buildSectionComparison();
function buildSectionComparison() {
  return sections.map((section) => {
  const roster = classRosterFull[section];
  const overallAttainment = Math.round(classAveragePct(section, latestTest.key));
  const needAttention = roster.filter((s) => attentionFor(s) !== "On Track").length;
  const critical = roster.filter((s) => attentionFor(s) === "Intervention").length;
  return {
    section,
    students: roster.length,
    overallAttainment,
    needAttention,
    critical,
    attention: overallAttainment >= 78 ? "Low" : overallAttainment >= 70 ? "Medium" : "High",
    /** Movement against the previous analysed test, in percentage points.
     *  null when this is the first analysed test. */
    delta:
      analysedTests.length > 1
        ? Math.round(classAveragePct(section, latestTest.key) - classAveragePct(section, analysedTests[analysedTests.length - 2].key))
        : null,
  };
  });
}

/** School-wide roll-up of the same numbers, so the Classes overview can
 *  say where the school stands before you pick a class. */
export const schoolSnapshot = buildSchoolSnapshot();
function buildSchoolSnapshot() {
  return {
  students: allStudents.length,
  sections: sections.length,
  overallAttainment: Math.round(allStudents.reduce((sum, s) => sum + overallPctFor(s, latestTest.key), 0) / allStudents.length),
  needAttention: allStudents.filter((s) => attentionFor(s) !== "On Track").length,
  critical: allStudents.filter((s) => attentionFor(s) === "Intervention").length,
  delta:
    analysedTests.length > 1
      ? Math.round(
          allStudents.reduce((sum, s) => sum + overallPctFor(s, latestTest.key), 0) / allStudents.length -
            allStudents.reduce((sum, s) => sum + overallPctFor(s, analysedTests[analysedTests.length - 2].key), 0) / allStudents.length
        )
      : null,
  };
}

// ============================================================
// §5.7 Empty / limited-evidence states, reusable copy
// ============================================================

export const emptyStates = {
  trendNotAvailable:
    "Trend and consistency insights require at least one additional analysed assessment.",
  trendTwoPoints:
    "Trend compares the two analysed assessments. Two points show direction, not a reliable trajectory.",
  earlySignal:
    "A possible pattern is visible, but there is not yet enough evidence for a strong conclusion.",
  causeNotLocalized:
    "Problem confirmed. Cause not localized. Manual review recommended.",
  paperUnderTests:
    "This assessment included too few application questions to confidently assess application readiness.",
};

// ============================================================
// §5.11 Manage Teachers screen, reuses mockTeachers above
// (🔧 BACKEND REQUIRED, Index #1)
// ============================================================

export const manageTeachersList = mockTeachers;

// ============================================================
// §7 Student-facing experience, 🔧 entire section BACKEND REQUIRED
// (Index #2). This is what the Student login/home/report screens render.
// ============================================================

// §7.3 One-page BoardX student report, mirrors the real
// "AVAI BoardX, Your One-Page Assessment Report" hand-off design:
// where you stand, how you handled questions, where marks went, and
// what to practise next. Evidence-first: nothing here invents a score
// or a pattern the underlying paper doesn't support.

export interface ReportStandingRow {
  chapter: string;
  scored: number;
  outOf: number;
  notScored: number;
  boardImportance: string; // e.g. "10 / 80" or "Not enough evidence"
}

export interface ReportMarksLostItem {
  chapter: string;
  scoreLabel: string; // "6 / 7"
  scored: number;
  outOf: number;
  subLabel: string; // "1 / 1 application mark not scored"
  insight: string;
}

export interface ReportActionGroup {
  heading: string;
  items: string[];
}

export interface BoardXStudentReport {
  subject: string;
  assessmentName: string; // "Unit Test 2"
  score: string; // "16 / 17", headline for the report list / hero
  trend: "up" | "down" | "flat"; // drives Improve/Achieve mascot pose
  encouragingLine: string;
  totalBoardMarks: number;
  boardExposureMarks: number;
  boardScoreImpact: "NOT_CALIBRATED" | string;
  standing: ReportStandingRow[];
  patternLabel: string;
  patternHeadline: string;
  patternBody: string;
  marksLost: ReportMarksLostItem[];
  noPatternNote: { chapter: string; scoreLabel: string; note: string } | null;
  actionPlan: ReportActionGroup[];
  practiceRule: string;
  takeaway: string;
  evidenceNote: string;
}

/** The one thing a chapter's lost marks usually mean, and the exact
 *  NCERT practice that addresses it. Curated per chapter, this is the
 *  pedagogy, not the arithmetic. */
export interface ChapterPattern {
  /** Short all-caps tag shown on the report, e.g. "MULTI-STEP APPLICATION". */
  label: string;
  /** Skill phrase used in headings / blocker labels, e.g. "Application". */
  lossKind: string;
  /** "You scored higher on questions asking you to X than …" */
  headline: string;
  /** One sentence naming the pattern in this chapter. */
  body: string;
  /** Sentence shown against the chapter's own lost marks. */
  insight: string;
  /** Exactly what to practise next. */
  practice: string[];
}

export const chapterPatterns: Record<string, ChapterPattern> = {
  "Quadratic Equations": {
    label: "MULTI-STEP APPLICATION",
    lossKind: "Application",
    headline: "You scored higher on questions asking you to state a rule than on questions asking you to apply it in a new situation.",
    body: "The clearest pattern here is on multi-step application questions in Quadratic Equations, the same pattern BoardX sees across Class X.",
    insight: "The marks lost are on questions that ask you to build the equation from a situation, not to solve one already given.",
    practice: ["Ex 4.3 Q7, word problem leading to a quadratic", "Ex 4.4 Q2, two-step \"nature of roots\" application", "Ex 4.4 Q5, forming the equation from a story sum"],
  },
  "Arithmetic Progressions": {
    label: "TERM SELECTION",
    lossKind: "Term selection",
    headline: "You scored higher on questions giving you the term to find than on questions where you had to work out which term is being asked for.",
    body: "The clearest pattern here is in choosing n before applying the formula in Arithmetic Progressions.",
    insight: "The formula is being applied correctly; the marks go on identifying which term the question is actually asking about.",
    practice: ["Ex 5.2 Q11, find n given the term value", "Ex 5.3 Q3, sum-to-n word problems", "Ex 5.3 Q10, AP formed from a real-world sequence"],
  },
  Trigonometry: {
    label: "IDENTITY CHOICE",
    lossKind: "Identity choice",
    headline: "You scored higher on direct ratio questions than on questions where you had to pick the identity to use first.",
    body: "The clearest pattern here is identity selection in Trigonometry, the step before the calculation.",
    insight: "The lost marks are on proofs where the first substitution decides whether the rest works out.",
    practice: ["Ex 8.4 Q5 (i-iii), prove using a chosen identity", "Ex 9.1 Q3, heights and distances, two-angle setup", "Ex 8.3 Q7, complementary-angle simplification"],
  },
  "Coordinate Geometry": {
    label: "FORMULA SETUP",
    lossKind: "Setup",
    headline: "You scored higher when the coordinates were given than when you had to derive them before substituting.",
    body: "The clearest pattern here is setting up the right formula in Coordinate Geometry.",
    insight: "The arithmetic is sound; the marks go on deciding which of section / distance / area applies.",
    practice: ["Ex 7.2 Q6, section formula with an unknown ratio", "Ex 7.1 Q8, distance with an unknown coordinate", "Ex 7.3 Q4, area of a triangle from vertices"],
  },
  Electricity: {
    label: "NUMERICAL CONVERSION",
    lossKind: "Numericals",
    headline: "You scored higher on questions asking you to state a law than on questions asking you to calculate a numerical answer.",
    body: "The clearest pattern here is on numerical questions in Electricity.",
    insight: "The lost marks are all on questions that ask you to calculate a value, not to state a rule.",
    practice: ["V = IR, single-step numericals, practice set A", "Power (P = VI), two-step problems", "Series + parallel combination circuits"],
  },
  Light: {
    label: "SIGN CONVENTION",
    lossKind: "Sign convention",
    headline: "You scored higher on ray-diagram questions than on questions needing the mirror or lens formula with signs.",
    body: "The clearest pattern here is sign convention in Light, Reflection and Refraction.",
    insight: "The method is right; the marks go on the sign of u, v or f before substituting.",
    practice: ["Mirror formula, 10 mixed concave/convex numericals", "Lens formula with magnification, both signs", "Draw-and-label: image position for each mirror case"],
  },
  "Carbon and its Compounds": {
    label: "REASONING",
    lossKind: "Reasoning",
    headline: "You scored higher on naming and structure questions than on questions asking why a reaction behaves the way it does.",
    body: "The clearest pattern here is reasoning questions in Carbon and its Compounds.",
    insight: "Structures are being drawn correctly; the marks go on explaining the behaviour behind them.",
    practice: ["Why soaps form micelles, write the full reason", "Addition vs substitution: give a reason for each", "Homologous series, explain the trend in properties"],
  },
  "Chemical Reactions & Equations": {
    label: "BALANCING",
    lossKind: "Balancing",
    headline: "You scored higher on identifying reaction types than on writing the balanced equation for them.",
    body: "The clearest pattern here is balancing and state symbols in Chemical Reactions & Equations.",
    insight: "The reaction is identified correctly; the marks go on balancing and state symbols.",
    practice: ["Balance 15 equations with state symbols", "Redox: mark what is oxidised and what is reduced", "Write equations from word descriptions"],
  },
  "Periodic Classification": {
    label: "TREND APPLICATION",
    lossKind: "Trends",
    headline: "You scored higher on recalling the position of an element than on using a trend to compare two of them.",
    body: "The clearest pattern here is applying periodic trends in Periodic Classification.",
    insight: "Positions are known; the marks go on using them to predict or compare a property.",
    practice: ["Compare atomic radius across a period, 8 pairs", "Predict valency from group number", "Explain metallic character down a group"],
  },
  "Unseen Passage": {
    label: "INFERENCE",
    lossKind: "Inference",
    headline: "You scored higher on questions whose answer is stated in the passage than on questions asking what the passage implies.",
    body: "The clearest pattern here is inference questions on the unseen passage.",
    insight: "Directly-stated answers are being found; the marks go on questions that need a conclusion drawn from the text.",
    practice: ["Two unseen passages, answer only the inference questions", "Underline the line your answer is built on, every time", "Vocabulary-in-context: 20 items"],
  },
  "Writing Skills": {
    label: "FORMAT",
    lossKind: "Format",
    headline: "You scored higher on the content of your writing than on the format marks around it.",
    body: "The clearest pattern here is format marks in letters and notices.",
    insight: "The content is there; the marks go on the fixed format, heading, address, closing, word limit.",
    practice: ["Three formal letters, format checklist marked first", "Two notices inside the word limit", "Rewrite one past answer, fixing format only"],
  },
  "Prose Literature": {
    label: "TEXTUAL EVIDENCE",
    lossKind: "Textual evidence",
    headline: "You scored higher on recall questions than on questions asking you to support an answer from the text.",
    body: "The clearest pattern here is supporting answers with textual evidence in the prose texts.",
    insight: "The answers are correct in substance; the marks go on quoting or referencing the text to back them.",
    practice: ["Answer 5 long questions with one quotation each", "Character sketch supported by three incidents", "Theme question: cite two moments from the text"],
  },
  "Nationalism in India": {
    label: "CAUSE AND EFFECT",
    lossKind: "Cause and effect",
    headline: "You scored higher on questions asking what happened than on questions asking why it happened.",
    body: "The clearest pattern here is cause-and-effect reasoning in Nationalism in India.",
    insight: "Events and dates are secure; the marks go on linking a cause to its consequence.",
    practice: ["Non-Cooperation: three causes, three effects", "Why Civil Disobedience was withdrawn, full answer", "Compare the two movements in a table"],
  },
  "Resources and Development": {
    label: "CLASSIFICATION",
    lossKind: "Classification",
    headline: "You scored higher on defining a resource than on classifying one correctly with a reason.",
    body: "The clearest pattern here is classification with justification in Resources and Development.",
    insight: "Definitions are known; the marks go on placing an example in the right category and saying why.",
    practice: ["Classify 20 resources on all four bases", "Soil types, one distinguishing feature each", "Land-use change: read and interpret the table"],
  },
  "Power Sharing & Federalism": {
    label: "EXAMPLE USE",
    lossKind: "Examples",
    headline: "You scored higher on stating a principle than on backing it with the right example.",
    body: "The clearest pattern here is using examples to support an argument in Power Sharing & Federalism.",
    insight: "The principle is stated correctly; the marks go on the supporting example the question asks for.",
    practice: ["Belgium vs Sri Lanka, two contrasts each", "List the three lists with two subjects each", "Decentralisation in India, one example per point"],
  },
  "Map Work": {
    label: "LOCATION ACCURACY",
    lossKind: "Location accuracy",
    headline: "You scored higher on naming a place than on locating it correctly on the map.",
    body: "The clearest pattern here is location accuracy in Map Work.",
    insight: "The places are identified; the marks go on marking them in the right position.",
    practice: ["Blank India map, 15 listed locations, twice", "Soil and mineral belts on one outline map", "Label the Congress-session sites in order"],
  },
};

// ============================================================
// Report engine, turns a student's real scores into the one-page
// BoardX report. Deterministic (seeded by student + test + subject)
// so the same student always gets the same breakdown, and the totals
// always reconcile with the marks shown everywhere else in the app.
// ============================================================

function fallbackPattern(chapter: string): ChapterPattern {
  return {
    label: "NOT LOCALIZED",
    lossKind: "Mixed",
    headline: "Marks were lost across more than one kind of question, so no single pattern can be issued yet.",
    body: `Loss in ${chapter} is spread across question types rather than concentrated in one.`,
    insight: emptyStates.causeNotLocalized,
    practice: [`Re-work every ${chapter} question from this paper`, "Mark the step where each answer went wrong", "Bring the two hardest ones to your teacher"],
  };
}

function patternFor(chapter: string): ChapterPattern {
  return chapterPatterns[chapter] ?? fallbackPattern(chapter);
}

/** A chapter's difficulty as taught in one section: the school-wide figure
 *  shifted ±35% per class, so different classes have genuinely different
 *  weak chapters the way different teachers and pacing produce. */
function sectionDifficulty(section: string, spec: ChapterSpec): number {
  const r = mulberry32(seedFromString(`${section}|${spec.chapter}`))();
  return spec.difficulty * (0.65 + r * 0.7);
}

/** Spread a subject's actual lost marks across its chapters, weighted by
 *  chapter size and a stable per-student difficulty draw. Largest-remainder
 *  allocation, capped so no chapter loses more marks than it carries. */
function chapterBreakdown(student: FullRosterStudent, testKey: string, subject: string): ReportStandingRow[] {
  const chapters = subjectChapters[subject] ?? [];
  const recorded = questionMarks[testKey]?.[subject]?.[student.id];
  if (recorded && chapters.length) {
    const qs = questionSets[subject] ?? [];
    return chapters.map((c) => {
      let scored = 0;
      qs.forEach((q, i) => {
        if (q.chapter === c.chapter) scored += recorded[i] ?? 0;
      });
      return {
        chapter: c.chapter,
        scored,
        outOf: c.marks,
        notScored: c.marks - scored,
        boardImportance: c.boardMarks === null ? "Not enough evidence" : `${c.boardMarks} / 80`,
      };
    });
  }
  return syntheticChapterBreakdown(student, testKey, subject);
}

/** The seed split of a subject score across chapters, used once to build
 *  the per-question marks of the demo's already-analysed tests. */
function syntheticChapterBreakdown(student: FullRosterStudent, testKey: string, subject: string): ReportStandingRow[] {
  const chapters = subjectChapters[subject] ?? [];
  const score = student.scores[testKey]?.[subject];
  if (!score || !chapters.length) return [];

  let remaining = score.outOf - score.scored;
  const rnd = mulberry32(seedFromString(`${student.id}|${testKey}|${subject}`));
  const weights = chapters.map((c) => c.marks * sectionDifficulty(student.section, c) * (0.6 + rnd() * 0.8));
  const totalWeight = weights.reduce((a, b) => a + b, 0) || 1;

  const ideal = chapters.map((c, i) => Math.min(c.marks, (weights[i] / totalWeight) * remaining));
  const lost = ideal.map((v) => Math.floor(v));
  remaining -= lost.reduce((a, b) => a + b, 0);

  // Hand out what rounding left over, biggest fractional part first.
  const order = chapters
    .map((_, i) => i)
    .sort((a, b) => ideal[b] - Math.floor(ideal[b]) - (ideal[a] - Math.floor(ideal[a])));
  while (remaining > 0) {
    const i = order.find((idx) => lost[idx] < chapters[idx].marks);
    if (i === undefined) break;
    lost[i] += 1;
    remaining -= 1;
    order.splice(order.indexOf(i), 1);
    order.push(i);
  }

  return chapters.map((c, i) => ({
    chapter: c.chapter,
    scored: c.marks - lost[i],
    outOf: c.marks,
    notScored: lost[i],
    boardImportance: c.boardMarks === null ? "Not enough evidence" : `${c.boardMarks} / 80`,
  }));
}

/** Previous analysed test, or null when this is the first one. */
function previousTestKey(testKey: string): string | null {
  const i = analysedTests.findIndex((t) => t.key === testKey);
  return i > 0 ? analysedTests[i - 1].key : null;
}

function trendFor(student: FullRosterStudent, testKey: string, subject: string): "up" | "down" | "flat" {
  const prevKey = previousTestKey(testKey);
  if (!prevKey) return "flat";
  const delta = pctFor(student, testKey, subject) - pctFor(student, prevKey, subject);
  if (delta >= 4) return "up";
  if (delta <= -4) return "down";
  return "flat";
}

function encouragementFor(pct: number, trend: "up" | "down" | "flat", prevExists: boolean): string {
  if (trend === "up") return "Up from your last assessment. Keep going, you're on the right path.";
  if (trend === "down" && prevExists) return "Down a little from last time. One focused chapter will turn this around.";
  if (pct >= 85) return "Strong, steady work. Hold this standard into the Board paper.";
  if (pct >= 70) return "Solid foundations, a bit more practice will help.";
  if (pct >= 55) return "The base is there. The chapter below is where the marks are waiting.";
  return "Start with one chapter, not five. The plan below is the shortest way up.";
}

/** The full one-page report for one student, one test, one subject.
 *  Every number here is derived from the student's actual scores. */
export function buildStudentReport(student: FullRosterStudent, testKey: string, subject: string): BoardXStudentReport | null {
  const score = student.scores[testKey]?.[subject];
  if (!score) return null;

  const test = testsConducted.find((t) => t.key === testKey);
  const standing = chapterBreakdown(student, testKey, subject);
  const pct = (score.scored / score.outOf) * 100;
  const trend = trendFor(student, testKey, subject);
  const prevKey = previousTestKey(testKey);

  const losses = standing.filter((r) => r.notScored > 0).sort((a, b) => b.notScored - a.notScored);
  const clean = standing.find((r) => r.notScored === 0) ?? null;
  const lead = losses[0] ?? null;
  const leadPattern = lead ? patternFor(lead.chapter) : null;

  const boardExposureMarks = standing.reduce((sum, r) => {
    const spec = (subjectChapters[subject] ?? []).find((c) => c.chapter === r.chapter);
    return sum + (spec?.boardMarks ?? 0);
  }, 0);

  const marksLost = losses.slice(0, 3).map((r) => {
    const p = patternFor(r.chapter);
    return {
      chapter: r.chapter,
      scoreLabel: `${r.scored} / ${r.outOf}`,
      scored: r.scored,
      outOf: r.outOf,
      subLabel: `${r.notScored} of ${r.outOf} mark${r.outOf === 1 ? "" : "s"} not scored, ${p.lossKind.toLowerCase()}`,
      insight: p.insight,
    };
  });

  const actionPlan = losses.slice(0, 2).map((r) => {
    const p = patternFor(r.chapter);
    return {
      heading: `${r === losses[0] ? "START WITH" : "THEN"}: ${r.chapter}, ${p.lossKind.toLowerCase()}`,
      items: p.practice,
    };
  });

  const prevName = prevKey ? testsConducted.find((t) => t.key === prevKey)?.name : null;
  const evidenceNote = prevName
    ? `Evidence note: this report covers ${test?.name ?? testKey} only; the trend compares it with ${prevName}. It does not predict your final Board score.`
    : "Evidence note: one assessment only; this does not predict your final Board score.";

  return {
    subject,
    assessmentName: test?.name ?? testKey,
    score: `${score.scored} / ${score.outOf}`,
    trend,
    encouragingLine: encouragementFor(pct, trend, Boolean(prevKey)),
    totalBoardMarks: 80,
    boardExposureMarks,
    boardScoreImpact: "NOT_CALIBRATED",
    standing,
    patternLabel: leadPattern ? leadPattern.label : "NO LOSS TO EXPLAIN",
    patternHeadline: leadPattern
      ? leadPattern.headline
      : "You scored every mark tested in this paper, so there is no loss pattern to show.",
    patternBody: leadPattern
      ? leadPattern.body
      : `Nothing in ${subject} was lost in this assessment. The next paper will test chapters this one didn't reach.`,
    marksLost,
    noPatternNote: clean
      ? {
          chapter: clean.chapter,
          scoreLabel: `${clean.scored} / ${clean.outOf}`,
          note: "Full marks here, there isn't a loss to explain, so no pattern is shown for this chapter.",
        }
      : null,
    actionPlan,
    practiceRule:
      "For every wrong answer, mark the error: reading the condition, choosing the method, setting up the steps, calculation, or the final answer.",
    takeaway: "See where the marks went, the pattern behind them, the Board importance, and the exact practice to do next.",
    evidenceNote,
  };
}

// ---- Report identity -------------------------------------------------
// A report id encodes who / which test / which subject, so any of the
// every student can be linked to directly.

export function reportId(studentId: string, testKey: string, subject: string): string {
  return `${studentId}~${testKey}~${subject}`;
}

export function parseReportId(id: string): { studentId: string; testKey: string; subject: string } | null {
  const [studentId, testKey, subject] = id.split("~");
  if (!studentId || !testKey || !subject) return null;
  return { studentId, testKey, subject };
}

/** Look a report up by id, the single entry point every report screen uses. */
export function getStudentReport(id: string): BoardXStudentReport | null {
  const parsed = parseReportId(id);
  if (!parsed) return null;
  const student = findStudent(parsed.studentId);
  if (!student) return null;
  return buildStudentReport(student, parsed.testKey, parsed.subject);
}

export interface ReportListing {
  id: string;
  subject: string;
  testKey: string;
  assessmentName: string;
  score: string;
  pct: number;
  trend: "up" | "down" | "flat";
  sharedAgo: string;
}

function sharedAgoFor(testKey: string): string {
  const test = testsConducted.find((t) => t.key === testKey);
  if (!test) return "recently";
  const days = Math.round((Date.parse(assessmentContext.today) - Date.parse(test.date)) / 86400000);
  if (days <= 1) return "today";
  if (days < 14) return `${days} days ago`;
  if (days < 60) return `${Math.round(days / 7)} weeks ago`;
  return `${Math.round(days / 30)} months ago`;
}

/** Every report available for a student, newest assessment first. */
export function reportsForStudent(studentId: string): ReportListing[] {
  const student = findStudent(studentId);
  if (!student) return [];
  return [...analysedTests]
    .reverse()
    .flatMap((test) =>
      subjects.map((subject) => {
        const s = student.scores[test.key][subject];
        return {
          id: reportId(student.id, test.key, subject),
          subject,
          testKey: test.key,
          assessmentName: test.name,
          score: `${s.scored} / ${s.outOf}`,
          pct: (s.scored / s.outOf) * 100,
          trend: trendFor(student, test.key, subject),
          sharedAgo: sharedAgoFor(test.key),
        };
      })
    );
}

// ---- Summary tier ----------------------------------------------------

export interface StudentSubjectGap {
  subject: string;
  lost: number;
  topic: string;
  subskill: string;
  boardUrgency: BoardUrgency;
  confidence: Confidence;
}

export interface StudentIntelligence {
  name: string;
  section: string;
  assessmentName: string;
  attainment: string;
  attainmentPct: number;
  marksLost: number;
  recoverableOpportunity: number;
  subjects: StudentSubjectGap[];
  boardXSummary: string;
}

function urgencyFromBoardMarks(boardMarks: number | null): BoardUrgency {
  if (boardMarks === null) return "LOW";
  if (boardMarks >= 12) return "VERY_HIGH";
  if (boardMarks >= 9) return "HIGH";
  if (boardMarks >= 6) return "MEDIUM";
  return "LOW";
}

function confidenceFromLoss(lost: number): Confidence {
  if (lost >= 3) return "HIGH";
  if (lost === 2) return "MEDIUM";
  return "EMERGING";
}

/** The subject-by-subject gap summary behind a student's headline number. */
export function studentIntelligenceFor(student: FullRosterStudent, testKey: string = latestTest.key): StudentIntelligence | null {
  const row = student.scores[testKey];
  if (!row) return null;

  const test = testsConducted.find((t) => t.key === testKey);
  const present = subjects.filter((s) => row[s]);
  const scored = present.reduce((sum, s) => sum + row[s].scored, 0);
  const outOf = present.reduce((sum, s) => sum + row[s].outOf, 0);

  const gaps: StudentSubjectGap[] = [];
  for (const subject of present) {
    const lead = chapterBreakdown(student, testKey, subject)
      .filter((r) => r.notScored > 0)
      .sort((a, b) => b.notScored / b.outOf - a.notScored / a.outOf || b.notScored - a.notScored)[0];
    if (!lead) continue;
    const spec = (subjectChapters[subject] ?? []).find((c) => c.chapter === lead.chapter);
    gaps.push({
      subject,
      lost: lead.notScored,
      topic: lead.chapter,
      subskill: patternFor(lead.chapter).lossKind,
      boardUrgency: urgencyFromBoardMarks(spec?.boardMarks ?? null),
      confidence: confidenceFromLoss(lead.notScored),
    });
  }
  gaps.sort((a, b) => b.lost - a.lost);


  const top = gaps[0];
  const urgent = gaps.find((g) => g.boardUrgency === "VERY_HIGH");
  const pct = overallPctFor(student, testKey);

  let summary: string;
  if (!top) {
    summary = `${student.name} scored every mark tested in ${test?.name ?? "this assessment"}. There is no gap to localize at this stage.`;
  } else {
    const first = `${student.name}'s loss is concentrated in ${top.subskill.toLowerCase()} in ${top.subject}, ${top.topic}.`;
    const second =
      urgent && urgent !== top
        ? ` The ${urgent.subject} gap in ${urgent.topic} is smaller but carries very high Board urgency, so both should be addressed together.`
        : top.boardUrgency === "VERY_HIGH"
        ? " This chapter carries very high Board urgency, so it is the right place to start."
        : gaps.length > 1
        ? ` ${gaps.length - 1} other subject${gaps.length === 2 ? "" : "s"} show smaller losses that do not yet form a pattern.`
        : " No other subject shows a loss large enough to call a pattern.";
    summary = first + second;
  }

  return {
    name: student.name,
    section: student.section,
    assessmentName: test?.name ?? testKey,
    attainment: `${scored} / ${outOf}`,
    attainmentPct: Math.round(pct),
    marksLost: outOf - scored,
    recoverableOpportunity: gaps.slice(0, 2).reduce((sum, g) => sum + g.lost, 0),
    subjects: gaps.slice(0, 3),
    boardXSummary: summary,
  };
}

/** The one chapter a student should fix first, shown in roster tables. */
export function mainBlockerFor(student: FullRosterStudent, testKey: string = latestTest.key): string {
  const intel = studentIntelligenceFor(student, testKey);
  const top = intel?.subjects[0];
  if (!top) return "-";
  return `${top.topic}, ${top.subskill}`;
}

// ============================================================
// §6.4 Student report page (Teacher-facing view of one student).
// Built from the same scores as the student's own report, so a teacher
// and a student never see different marks for the same paper.
// "issue" is ✅ a real shape; "share" is 🔧 BACKEND REQUIRED (Index #2).
// ============================================================

export interface TeacherSubjectReport {
  subject: string;
  assessment: string;
  score: string;
  strengths: string[];
  focusAreas: string[];
  issued: boolean;
  sharedWithStudent: boolean;
}

export function teacherReportFor(student: FullRosterStudent, testKey: string = latestTest.key) {
  const test = testsConducted.find((t) => t.key === testKey);
  const subjectReports: TeacherSubjectReport[] = subjects.map((subject, i) => {
    const score = student.scores[testKey]?.[subject];
    if (!score) {
      return { subject, assessment: test?.name ?? testKey, score: "- / -", strengths: [], focusAreas: [], issued: false, sharedWithStudent: false };
    }
    const rows = chapterBreakdown(student, testKey, subject);
    const clean = rows.filter((r) => r.notScored === 0).map((r) => r.chapter);
    const losses = rows.filter((r) => r.notScored > 0).sort((a, b) => b.notScored - a.notScored);
    return {
      subject,
      assessment: test?.name ?? testKey,
      score: `${score.scored}/${score.outOf}`,
      strengths: clean.length ? clean.slice(0, 2) : ["No chapter fully secured in this paper"],
      focusAreas: losses.slice(0, 2).map((r) => gapLabel(r.chapter)),
      issued: true,
      // Alternating share state keeps both "shared" and "not shared" UI
      // reachable without a backend to hold the real flag.
      sharedWithStudent: i % 2 === 0,
    };
  });
  return {
    studentName: student.name,
    rollNo: student.rollNo,
    section: student.section,
    subjectReports,
  };
}

// ============================================================
// ADDITIONS for the UI-only build (same shapes/style as above).
// Everything below is 🔧 BACKEND REQUIRED, no real endpoint yet.
// ============================================================

// §4 login form, dev-only switcher entries
export const devLoginOptions = [
  { key: "principal", label: "Sign in as Principal", sub: mockPrincipal.name, role: "principal" as Role, userId: mockPrincipal.id },
  { key: "teacher_1", label: "Sign in as Teacher", sub: "Mrs. Lakshmi · X-A class teacher · Maths X-A, X-B", role: "teacher" as Role, userId: "staff_teacher_1" },
  { key: "teacher_2", label: "Sign in as Teacher", sub: "Mr. Ravi · Science · X-A, X-B", role: "teacher" as Role, userId: "staff_teacher_2" },
  { key: "student", label: "Sign in as Student", sub: "Aditi R. · X-A · Roll 01", role: "student" as Role, userId: mockStudentUser.id },
];

// §6.2 / §6.3 Teacher class & subject views, roster per section
export interface RosterStudent {
  id: string;
  rollNo: string;
  name: string;
  section: string;
  attainment: Record<string, string>; // subject -> "x/y"
  attention: "On Track" | "Watch" | "Intervention";
  mainBlocker: string;
}

/** Roster rows for the teacher views, derived from the full roster so a
 *  teacher and the principal never see different numbers for the same
 *  student. `testKey` defaults to the latest analysed test. */
export function rosterFor(section: string, testKey: string = latestTest.key): RosterStudent[] {
  return (classRosterFull[section] ?? []).map((s) => {
    const row = s.scores[testKey];
    return {
      id: s.id,
      rollNo: s.rollNo,
      name: s.name,
      section: s.section,
      // A scheduled test has no scores yet, "-" rather than a crash.
      attainment: Object.fromEntries(subjects.map((sub) => [sub, row?.[sub] ? `${row[sub].scored}/${row[sub].outOf}` : "-"])),
      attention: attentionFor(s, testKey),
      mainBlocker: mainBlockerFor(s, testKey),
    };
  });
}

/** Every student in the school as a roster row (latest analysed test). */
export const classRoster: RosterStudent[] = sections.flatMap((s) => rosterFor(s));

// Class-level summary per section (teacher class view header)
export const classSummary: Record<string, { students: number; overallAttainment: number; attention: "Low" | "Medium" | "High"; topFinding: string }> = Object.fromEntries(
  sectionComparison.map((s) => [
    s.section,
    {
      students: s.students,
      overallAttainment: s.overallAttainment,
      attention: s.attention as "Low" | "Medium" | "High",
      topFinding: topGapFor(s.section, latestTest.key),
    },
  ])
);

// §6.3 Subject view, per-section subject snapshot, computed from the
// roster rather than stated, so a subject's average always matches the
// students listed underneath it.
export interface SubjectSnapshot {
  marksTested: number;
  avgAttainment: number;
  atExpectedLevelPct: number;
  topGap: string;
}

/** The chapter losing the most marks across a whole section. */
function topGapIn(section: string, testKey: string, subject: string): { chapter: string; lost: number; rate: number } | null {
  const roster = classRosterFull[section] ?? [];
  const lost = new Map<string, number>();
  const available = new Map<string, number>();
  for (const student of roster) {
    for (const row of chapterBreakdown(student, testKey, subject)) {
      lost.set(row.chapter, (lost.get(row.chapter) ?? 0) + row.notScored);
      available.set(row.chapter, (available.get(row.chapter) ?? 0) + row.outOf);
    }
  }
  const ranked = [...lost.entries()]
    .filter(([, n]) => n > 0)
    .map(([chapter, n]) => ({ chapter, lost: n, rate: n / (available.get(chapter) || 1) }))
    .sort((a, b) => b.rate - a.rate);
  return ranked[0] ?? null;
}

function gapLabel(chapter: string): string {
  return `${chapter}, ${patternFor(chapter).lossKind}`;
}

/** The section's single biggest gap across all subjects. */
export function topGapFor(section: string, testKey: string = latestTest.key): string {
  const candidates = subjects
    .map((subject) => topGapIn(section, testKey, subject))
    .filter((g): g is { chapter: string; lost: number; rate: number } => g !== null)
    .sort((a, b) => b.rate - a.rate);
  return candidates.length ? gapLabel(candidates[0].chapter) : "No gap localized";
}

export function subjectSnapshotFor(subject: string, section: string, testKey: string = latestTest.key): SubjectSnapshot {
  const roster = classRosterFull[section] ?? [];
  const outOf = subjectMaxMarks[subject] ?? 0;
  const scores = roster.map((s) => s.scores[testKey]?.[subject]).filter(Boolean) as TestScore[];
  const avg = scores.length ? scores.reduce((sum, s) => sum + s.scored, 0) / scores.length : 0;
  const atLevel = scores.filter((s) => s.scored / s.outOf >= 0.75).length;
  const gap = topGapIn(section, testKey, subject);
  return {
    marksTested: outOf,
    avgAttainment: Math.round(avg * 10) / 10,
    atExpectedLevelPct: scores.length ? Math.round((atLevel / scores.length) * 100) : 0,
    topGap: gap ? gapLabel(gap.chapter) : "No gap localized",
  };
}

// §5.9 Papers / §5.10 Enter marks / Help, page headers
export const pageHeaders = {
  papers: { title: "Question Papers", blurb: "Upload and map each subject's paper to the Board blueprint. Once a subject's paper is mapped, generate its answer card for marking." },
  enterMarks: { title: "Enter Marks", blurb: "Upload a filled answer card to read marks automatically, or enter them question-wise by hand. Teachers can also enter marks from their Subject view." },
  help: { title: "Help & Contact", blurb: "Something not working, or a number that looks wrong? Tell us and we'll take a look." },
};

// ============================================================
// §5.9 Question Papers, one paper per (test, subject). A test's papers
// are managed together, but each subject's paper is uploaded, mapped and
// turned into an answer card independently, that's how a real school
// runs it: different subject teachers hand theirs in on their own schedule.
// 🔧 BACKEND REQUIRED, upload / mapping / answer-card generation are all
// simulated with local state and timed status transitions; nothing here is
// actually parsed, scanned or stored.
// ============================================================

export type SubjectPaperStatus = "Not uploaded" | "Processing" | "Needs mapping" | "Mapped";

export interface SubjectPaper {
  testKey: string;
  subject: string;
  fileName: string | null;
  uploadedBy: string | null;
  uploadedAt: string | null;
  status: SubjectPaperStatus;
  /** Whether "Generate answer card" has been run for this paper, gates
   *  the answer-card upload flow in Enter Marks. */
  answerCardGenerated: boolean;
}

// Chapters in the Board blueprint that a subject's papers in this build
// don't reach. Coverage is measured against the whole blueprint, not
// against any one paper, so it's a property of the subject, not the test.
const blueprintExtras: Record<string, string[]> = {
  Mathematics: ["Real Numbers", "Polynomials", "Pair of Linear Equations", "Triangles", "Circles", "Statistics", "Probability"],
  Science: ["Magnetic Effects of Current", "Sources of Energy", "Acids, Bases and Salts", "Metals and Non-metals"],
  English: ["Grammar", "Poetry", "Supplementary Reader"],
  "Social Science": ["The Making of a Global World", "Agriculture", "Political Parties", "Money and Credit"],
};

/** Split a chapter's marks into whole questions (5 / 3 / 2 marks), never
 *  leaving a 1-mark stub. The split always sums back to the chapter total. */
function splitIntoQuestions(marks: number): number[] {
  const out: number[] = [];
  let left = marks;
  while (left > 0) {
    if (left >= 5 && left - 5 !== 1) out.push(5);
    else if (left >= 3 && left - 3 !== 1) out.push(3);
    else if (left >= 2) out.push(2);
    else out.push(left);
    left -= out[out.length - 1];
  }
  return out;
}

/** The questions in a subject's paper, derived from the same chapter
 *  blueprint the student reports are built on, so "View mapping", the
 *  answer card and a student's report all describe the same paper. */
function questionsForSubjects(paperSubjects: string[]): PaperQuestion[] {
  const questions: PaperQuestion[] = [];
  let n = 1;
  for (const subject of paperSubjects) {
    for (const spec of subjectChapters[subject] ?? []) {
      for (const marks of splitIntoQuestions(spec.marks)) {
        questions.push({ no: `Q${n++}`, chapter: spec.chapter, marks });
      }
    }
  }
  return questions;
}

function mappingForSubjects(paperSubjects: string[]): { chapter: string; covered: boolean; questionsMapped: number }[] {
  const questions = questionsForSubjects(paperSubjects);
  const covered = paperSubjects.flatMap((subject) =>
    (subjectChapters[subject] ?? []).map((spec) => ({
      chapter: spec.chapter,
      covered: true,
      questionsMapped: questions.filter((q) => q.chapter === spec.chapter).length,
    }))
  );
  const missing = paperSubjects.flatMap((subject) => (blueprintExtras[subject] ?? []).map((chapter) => ({ chapter, covered: false, questionsMapped: 0 })));
  return [...covered, ...missing];
}

export interface PaperQuestion {
  no: string;
  chapter: string;
  marks: number;
}

/** Chapter-by-chapter blueprint mapping, keyed by subject, every analysed
 *  test's paper for a subject is assumed to test the same chapter set (the
 *  same assumption the report engine makes via `subjectChapters`), so
 *  coverage is a property of the subject rather than of one test's file. */
export const paperChapterMapping: Record<string, { chapter: string; covered: boolean; questionsMapped: number }[]> = Object.fromEntries(
  subjects.map((s) => [s, mappingForSubjects([s])])
);

/** Question-by-question breakdown behind each chapter's questionsMapped
 *  count, shown when a subject's paper is opened. */
export const paperQuestions: Record<string, PaperQuestion[]> = Object.fromEntries(subjects.map((s) => [s, questionsForSubjects([s])]));

/** Coverage of the Board blueprint by a subject's paper, derived from its
 *  own mapping so the card and the drawer can never disagree. */
export function paperCoverage(subject: string) {
  const rows = paperChapterMapping[subject];
  if (!rows) return null;
  const covered = rows.filter((r) => r.covered).length;
  return { covered, total: rows.length, pct: Math.round((covered / rows.length) * 100) };
}

/** Question-wise entry grid per subject, derived from the same blueprint -
 *  the columns a teacher types (or an answer card fills) into are the
 *  questions the paper actually contains. */
/** One question per mark, a real paper's marking scheme is far more
 *  granular than the chapter-level split used for blueprint mapping
 *  (`paperQuestions`), and Enter Marks is where that granularity actually
 *  matters: a teacher is transcribing individual question scores off a
 *  scanned answer card, not chapter totals. Still sums to the same
 *  subject total, so a grid entry always reconciles with the score shown
 *  everywhere else. */
function subPartsForSubject(subject: string): QuestionSpec[] {
  const out: QuestionSpec[] = [];
  let n = 1;
  for (const spec of subjectChapters[subject] ?? []) {
    for (let i = 0; i < spec.marks; i++) {
      out.push({ key: `q${n}`, label: `Q${n}`, maxMarks: 1, chapter: spec.chapter });
      n++;
    }
  }
  return out;
}

export const questionSets: Record<string, QuestionSpec[]> = Object.fromEntries(subjects.map((subject) => [subject, subPartsForSubject(subject)]));

export interface QuestionSpec {
  key: string;
  label: string;
  maxMarks: number;
  /** Which chapter this question came from, the same blueprint the paper
   *  mapping and the student reports use. */
  chapter: string;
}

/** First teacher assigned to a subject, used as the default uploader on a
 *  seeded paper record. */
function teacherForSubject(subject: string): string {
  const t = mockTeachers.find((t) => t.assignments.some((a) => a.type === "subject" && a.subject === subject));
  return t?.name ?? mockPrincipal.name;
}

function seedPaper(testKey: string, subject: string, status: SubjectPaperStatus): SubjectPaper {
  const test = testsConducted.find((t) => t.key === testKey)!;
  const uploaded = status !== "Not uploaded";
  return {
    testKey,
    subject,
    fileName: uploaded ? `${testKey}-${subject.toLowerCase().replace(/[^a-z]+/g, "-")}.pdf` : null,
    uploadedBy: uploaded ? teacherForSubject(subject) : null,
    uploadedAt: uploaded ? test.date : null,
    status,
    answerCardGenerated: status === "Mapped",
  };
}

/** testKey -> subject -> paper. The two analysed tests already have every
 *  subject mapped (marks couldn't exist otherwise); the Quarterly Exam has
 *  a Science paper mid-review; every other combination starts "Not
 *  uploaded", what a school's paper tracker actually looks like mid-term. */
export const initialSubjectPapers: Record<string, Record<string, SubjectPaper>> = Object.fromEntries(
  testsConducted.map((t) => [
    t.key,
    Object.fromEntries(
      subjects.map((s) => {
        if (t.status === "Analysed") return [s, seedPaper(t.key, s, "Mapped")];
        if (t.key === "quarterly" && s === "Science") return [s, seedPaper(t.key, s, "Needs mapping")];
        return [s, seedPaper(t.key, s, "Not uploaded")];
      })
    ),
  ])
);

/** Simulated OCR read of a scanned answer card: splits a student's real
 *  subject score across that subject's questions (largest-remainder,
 *  weighted by question marks and a stable per-student draw), so an
 *  uploaded answer card reconciles with the score already on record.
 *  Only meaningful for an analysed test, a scheduled one has no marks to
 *  read yet, so callers should gate the upload flow on that. */
export function ocrMarksFor(studentId: string, testKey: string, subject: string): Record<string, number> | null {
  const recorded = questionMarks[testKey]?.[subject]?.[studentId];
  if (recorded) return Object.fromEntries((questionSets[subject] ?? []).map((q, i) => [q.key, recorded[i] ?? 0]));
  const student = findStudent(studentId);
  const score = student?.scores[testKey]?.[subject];
  const qs = questionSets[subject];
  if (!student || !score || !qs?.length) return null;

  const rnd = mulberry32(seedFromString(`ocr|${studentId}|${testKey}|${subject}`));
  const weights = qs.map((q) => q.maxMarks * (0.5 + rnd()));
  const totalWeight = weights.reduce((a, b) => a + b, 0) || 1;
  const ideal = qs.map((q, i) => Math.min(q.maxMarks, (weights[i] / totalWeight) * score.scored));
  const floorVals = ideal.map((v) => Math.floor(v));
  let remaining = score.scored - floorVals.reduce((a, b) => a + b, 0);
  const order = qs.map((_, i) => i).sort((a, b) => ideal[b] - Math.floor(ideal[b]) - (ideal[a] - Math.floor(ideal[a])));
  while (remaining > 0) {
    const i = order.find((idx) => floorVals[idx] < qs[idx].maxMarks);
    if (i === undefined) break;
    floorVals[i] += 1;
    remaining -= 1;
    order.splice(order.indexOf(i), 1);
    order.push(i);
  }
  return Object.fromEntries(qs.map((q, i) => [q.key, floorVals[i]]));
}

// ============================================================
// Help & Contact, replaces the old Settings screen. A mock-only build
// has nothing to configure; what a principal actually needs is a way to
// reach AVAI when something looks wrong.
// ============================================================

export const helpContact = {
  supportEmail: "support@avai.school",
  supportPhone: "+91 44 4567 8900",
  hours: "Mon-Sat, 9:00 AM - 6:00 PM IST",
  faqs: [
    { q: "A student's marks look wrong, what do I do?", a: "Open Enter Marks for that assessment and correct the question-wise score; every report and KPI that depends on it updates immediately." },
    { q: "Why does a chapter say \"Not enough evidence\"?", a: "That chapter wasn't tested enough in the mapped papers to say anything reliable about it yet, map a paper against it to change that." },
    { q: "Can I undo sending a report to students?", a: "Not from here, check the test before sending. Message us below if a report needs to be recalled." },
  ],
};

// ============================================================
// Principal → Classes (classwise drill-down: Overview → Class →
// Student, with a test-wise report picker on the student page).
// Reuses sectionComparison / classRoster / studentReportDetail -
// no new cohort-level numbers are invented here.
// ============================================================

/** Every report id available for a student, one per analysed test per
 *  subject, so every student drills down to a real report. */
export function studentReportIds(studentId: string): string[] {
  return reportsForStudent(studentId).map((r) => r.id);
}

/** Section -> class teacher's display name, derived from mockTeachers' assignments. */
export const classTeacherBySection: Record<string, string> = Object.fromEntries(
  mockTeachers.flatMap((t) => t.assignments.filter((a) => a.type === "class").map((a) => [(a as { section: string }).section, t.name]))
);

// ============================================================
// Principal home, "Class X" grade dashboard: Board-mark-band tables,
// section/subject pies, and the intelligence layer (toppers, late
// bloomers, weakest class/subject, anomalies).
//
// A student's assessment % is projected onto a 100-mark Board scale per
// subject (and summed for the 500-mark total) so the bands read the way
// a principal actually thinks about Board marks. This is a projection
// from internal assessments, not a calibrated Board-score prediction -
// every screen that uses it says "projected" for that reason.
// 🔧 BACKEND REQUIRED, real Board-mark projection is a modelling
// problem; this mock scales the analysed-assessment % directly.
// ============================================================

/** One subject's assessment % projected onto a 100-mark Board scale. */
export function projectedSubjectMarks(student: FullRosterStudent, testKey: string, subject: string): number {
  return Math.round(pctFor(student, testKey, subject));
}

/** Sum of all 5 subjects' projected marks, a 500-mark Board-scale total. */
export function projectedTotalMarks(student: FullRosterStudent, testKey: string): number {
  const row = student.scores[testKey] ?? {};
  // A test that covered only some subjects projects its overall % onto 500.
  if (!subjects.every((s) => row[s])) return Math.round(overallPctFor(student, testKey) * 5);
  return subjects.reduce((sum, s) => sum + projectedSubjectMarks(student, testKey, s), 0);
}

export interface MarkBand {
  label: string;
  min: number;
  max: number;
}

/** Bands over the 500-mark projected total. */
export const totalMarkBands: MarkBand[] = [
  { label: "450 - 500", min: 450, max: 500 },
  { label: "400 - 449", min: 400, max: 449 },
  { label: "350 - 399", min: 350, max: 399 },
  { label: "Below 350", min: 0, max: 349 },
];

/** Bands over one subject's 100-mark projected score. */
export const subjectMarkBands: MarkBand[] = [
  { label: "90 - 100", min: 90, max: 100 },
  { label: "80 - 89", min: 80, max: 89 },
  { label: "70 - 79", min: 70, max: 79 },
  { label: "60 - 69", min: 60, max: 69 },
  { label: "Below 60", min: 0, max: 59 },
];

/** Students in `section` (or every section when "All") whose projected
 *  total falls in `band`, highest total first. */
export function studentsInTotalBand(section: string | "All", testKey: string, band: MarkBand): FullRosterStudent[] {
  const roster = section === "All" ? allStudents : (classRosterFull[section] ?? []);
  return roster
    .filter((s) => {
      const total = projectedTotalMarks(s, testKey);
      return total >= band.min && total <= band.max;
    })
    .sort((a, b) => projectedTotalMarks(b, testKey) - projectedTotalMarks(a, testKey));
}

/** Same, for one subject's projected marks. */
export function studentsInSubjectBand(section: string | "All", testKey: string, subject: string, band: MarkBand): FullRosterStudent[] {
  const roster = section === "All" ? allStudents : (classRosterFull[section] ?? []);
  return roster
    .filter((s) => {
      const m = projectedSubjectMarks(s, testKey, subject);
      return m >= band.min && m <= band.max;
    })
    .sort((a, b) => projectedSubjectMarks(b, testKey, subject) - projectedSubjectMarks(a, testKey, subject));
}

/** How many students in `section` (or "All") fall in each band, in band order. */
export function totalBandCounts(section: string | "All", testKey: string): { band: MarkBand; count: number }[] {
  return totalMarkBands.map((band) => ({ band, count: studentsInTotalBand(section, testKey, band).length }));
}

export function subjectBandCounts(section: string | "All", testKey: string, subject: string): { band: MarkBand; count: number }[] {
  return subjectMarkBands.map((band) => ({ band, count: studentsInSubjectBand(section, testKey, subject, band).length }));
}

/** A student's 1-based rank within their own section, by overall % (or by
 *  one subject's %). Ties keep the roster's roll-number order. */
export function overallRankFor(student: FullRosterStudent, testKey: string): number {
  const roster = classRosterFull[student.section] ?? [];
  const ranked = [...roster].sort((a, b) => overallPctFor(b, testKey) - overallPctFor(a, testKey) || Number(a.rollNo) - Number(b.rollNo));
  return ranked.findIndex((s) => s.id === student.id) + 1;
}

export function subjectRankFor(student: FullRosterStudent, testKey: string, subject: string): number {
  const roster = classRosterFull[student.section] ?? [];
  const ranked = [...roster].sort((a, b) => pctFor(b, testKey, subject) - pctFor(a, testKey, subject) || Number(a.rollNo) - Number(b.rollNo));
  return ranked.findIndex((s) => s.id === student.id) + 1;
}

/** Top N students school-wide, or within one section, by overall %. */
export function topStudents(n: number, testKey: string = latestTest.key, section: string | "All" = "All"): FullRosterStudent[] {
  const roster = section === "All" ? allStudents : (classRosterFull[section] ?? []);
  return [...roster].sort((a, b) => overallPctFor(b, testKey) - overallPctFor(a, testKey)).slice(0, n);
}

export interface LateBloomer {
  student: FullRosterStudent;
  prevPct: number;
  nowPct: number;
  gain: number;
}

/** The analysed test before `testKey`, or null when it's the first one. */
export function previousAnalysedTestKey(testKey: string): string | null {
  const i = analysedTests.findIndex((t) => t.key === testKey);
  return i > 0 ? analysedTests[i - 1].key : null;
}

/** Students who moved up the most between `testKey` and the analysed test
 *  before it, "late bloomers" rather than the (usually already-strong)
 *  toppers. Empty when `testKey` is the first analysed test. */
export function lateBloomersFor(n: number, testKey: string = latestTest.key, section: string | "All" = "All"): LateBloomer[] {
  const prevKey = previousAnalysedTestKey(testKey);
  if (!prevKey) return [];
  const roster = section === "All" ? allStudents : (classRosterFull[section] ?? []);
  return roster
    .map((student) => {
      const prevPct = overallPctFor(student, prevKey);
      const nowPct = overallPctFor(student, testKey);
      return { student, prevPct: Math.round(prevPct), nowPct: Math.round(nowPct), gain: Math.round(nowPct - prevPct) };
    })
    .filter((r) => r.gain > 0)
    .sort((a, b) => b.gain - a.gain)
    .slice(0, n);
}

/** Same as lateBloomersFor, but the gain is measured in one subject only -
 *  for a subject teacher's own view, where "late bloomer" should mean
 *  rising in their subject, not overall. */
export function lateBloomersForSubject(subject: string, testKey: string, section: string | "All" = "All"): LateBloomer[] {
  const prevKey = previousAnalysedTestKey(testKey);
  if (!prevKey) return [];
  const roster = section === "All" ? allStudents : (classRosterFull[section] ?? []);
  return roster
    .map((student) => {
      const prevPct = pctFor(student, prevKey, subject);
      const nowPct = pctFor(student, testKey, subject);
      return { student, prevPct: Math.round(prevPct), nowPct: Math.round(nowPct), gain: Math.round(nowPct - prevPct) };
    })
    .filter((r) => r.gain > 0)
    .sort((a, b) => b.gain - a.gain);
}

/** Late bloomers against the latest analysed test. */
export function lateBloomers(n: number, section: string | "All" = "All"): LateBloomer[] {
  return lateBloomersFor(n, latestTest.key, section);
}

export interface SubjectStanding {
  subject: string;
  avgPct: number;
}

/** School-wide average % per subject, weakest first. */
export function subjectsByAverage(testKey: string = latestTest.key): SubjectStanding[] {
  return subjects
    .map((subject) => ({
      subject,
      avgPct: Math.round((allStudents.reduce((sum, s) => sum + pctFor(s, testKey, subject), 0) / allStudents.length) * 10) / 10,
    }))
    .sort((a, b) => a.avgPct - b.avgPct);
}

export interface AnomalyInsight {
  id: string;
  kind: "hidden-strength" | "all-rounder" | "section-subject-slump";
  headline: string;
  detail: string;
  numbers: { label: string; value: string }[];
  section?: string;
  subject?: string;
  studentId?: string;
}

/** Strips whatever extra sort key a candidate list was carrying (e.g.
 *  `spread`, `gap`) once it's been sorted and sliced, leaving a plain
 *  AnomalyInsight to push. */
function dropSortKey<T extends AnomalyInsight>(candidate: T): AnomalyInsight {
  const { id, kind, headline, detail, numbers, section, subject, studentId } = candidate;
  return { id, kind, headline, detail, numbers, section, subject, studentId };
}

/** Real, numbers-backed surprises, never a bare claim. Computed once from
 *  the same roster every other KPI reads, so nothing here can disagree
 *  with the table underneath it. Thresholds below are tuned against this
 *  build's actual seeded data (checked by hand), not picked blind, a
 *  student's subjects move together enough that "ranked #1 overall and
 *  in the bottom third" essentially never happens, so "hidden strength"
 *  is framed as relative over-performance instead of an absolute rank. */
function computeAnomalies(testKey: string): AnomalyInsight[] {
  const insights: AnomalyInsight[] = [];
  const schoolSubjectAvg = Object.fromEntries(subjectsByAverage(testKey).map((s) => [s.subject, s.avgPct]));

  // 1. Hidden strength: below their own section's overall average, but
  // with one subject at least 10pt above their own overall %, a real
  // strength the overall number buries.
  const hiddenStrength: (AnomalyInsight & { spread: number })[] = [];
  for (const section of sections) {
    const roster = classRosterFull[section];
    const sectionAvg = classAveragePct(section, testKey);
    for (const student of roster) {
      const overall = overallPctFor(student, testKey);
      if (overall >= sectionAvg) continue;
      let best: { subject: string; pct: number } | null = null;
      for (const subject of subjects) {
        const pct = pctFor(student, testKey, subject);
        if (!best || pct > best.pct) best = { subject, pct };
      }
      if (!best) continue;
      const spread = best.pct - overall;
      if (spread < 10) continue;
      hiddenStrength.push({
        id: `hidden_${student.id}`,
        kind: "hidden-strength",
        headline: `${student.name} is well below ${section}'s average overall, but shines in ${best.subject}`,
        detail: `Overall ${Math.round(overall)}% against ${section}'s ${Math.round(sectionAvg)}% average, yet ${Math.round(best.pct)}% in ${best.subject}, ${Math.round(spread)}pt above their own overall score.`,
        numbers: [
          { label: "Overall", value: `${Math.round(overall)}%` },
          { label: `${best.subject}`, value: `${Math.round(best.pct)}%` },
          { label: `${section} average`, value: `${Math.round(sectionAvg)}%` },
        ],
        section,
        subject: best.subject,
        studentId: student.id,
        spread,
      });
    }
  }
  insights.push(...hiddenStrength.sort((a, b) => b.spread - a.spread).slice(0, 3).map(dropSortKey));

  // 2. Near-all-rounder: ranked in the top 2 of their section in at least
  // 4 of the 5 subjects tested, genuinely rare, so shown as found.
  for (const section of sections) {
    const roster = classRosterFull[section];
    for (const student of roster) {
      const ranks = subjects.map((subject) => ({ subject, rank: subjectRankFor(student, testKey, subject) }));
      const top2Count = ranks.filter((r) => r.rank <= 2).length;
      if (top2Count < 4) continue;
      insights.push({
        id: `allrounder_${student.id}`,
        kind: "all-rounder",
        headline: `${student.name} ranks in the top 2 of ${section} in ${top2Count} of ${subjects.length} subjects`,
        detail: `${ranks.filter((r) => r.rank <= 2).map((r) => `#${r.rank} in ${r.subject}`).join(", ")}, consistently near the top across the board, not just one strong subject.`,
        numbers: ranks.map((r) => ({ label: r.subject, value: `#${r.rank}` })),
        section,
        studentId: student.id,
      });
    }
  }

  // 3. Section-subject slump: the subject(s) where a section trails the
  // school average by the widest margin, school-wide, not just one
  // section's overall weakness restated five times.
  const slumps: (AnomalyInsight & { gap: number })[] = [];
  for (const section of sections) {
    const roster = classRosterFull[section];
    for (const subject of subjects) {
      const sectionAvg = roster.reduce((sum, s) => sum + pctFor(s, testKey, subject), 0) / roster.length;
      const gap = schoolSubjectAvg[subject] - sectionAvg;
      if (gap < 6) continue;
      const belowSchoolAvg = roster.filter((s) => pctFor(s, testKey, subject) < schoolSubjectAvg[subject]).length;
      slumps.push({
        id: `slump_${section}_${subject}`,
        kind: "section-subject-slump",
        headline: `${section} trails the school in ${subject} by ${Math.round(gap)}pt`,
        detail: `${section}'s ${subject} average is ${Math.round(sectionAvg)}% against a school average of ${Math.round(schoolSubjectAvg[subject])}%, ${belowSchoolAvg} of ${roster.length} students in ${section} score below the school average in ${subject}.`,
        numbers: [
          { label: `${section} average`, value: `${Math.round(sectionAvg)}%` },
          { label: "School average", value: `${Math.round(schoolSubjectAvg[subject])}%` },
          { label: "Below school average", value: `${belowSchoolAvg} of ${roster.length}` },
        ],
        section,
        subject,
        gap,
      });
    }
  }
  insights.push(...slumps.sort((a, b) => b.gap - a.gap).slice(0, 3).map(dropSortKey));

  return insights;
}

/** computeAnomalies walks every student against every subject rank, so the
 *  per-test result is cached, switching the assessment on the Class X
 *  dashboard re-reads it rather than recomputing. */
const anomalyCache = new Map<string, AnomalyInsight[]>();

/** Anomalies for any analysed test. */
export function anomaliesFor(testKey: string): AnomalyInsight[] {
  const cached = anomalyCache.get(testKey);
  if (cached) return cached;
  const computed = computeAnomalies(testKey);
  anomalyCache.set(testKey, computed);
  return computed;
}

export let anomalyInsights: AnomalyInsight[] = anomaliesFor(latestTest.key);

// ============================================================
// Class X overview roll-ups, attention tiers, per-test section
// standings, and share rounding. All derived from the same roster as
// everything above, so nothing on the overview can disagree with a
// class or student page.
// ============================================================

export interface AttentionBreakdown {
  total: number;
  onTrack: number;
  watch: number;
  intervention: number;
}

/** How a cohort splits across the three attention tiers in one test. */
export function attentionBreakdown(testKey: string = latestTest.key, section: string | "All" = "All"): AttentionBreakdown {
  const roster = section === "All" ? allStudents : (classRosterFull[section] ?? []);
  const tiers = roster.map((s) => attentionFor(s, testKey));
  return {
    total: roster.length,
    onTrack: tiers.filter((t) => t === "On Track").length,
    watch: tiers.filter((t) => t === "Watch").length,
    intervention: tiers.filter((t) => t === "Intervention").length,
  };
}

export interface SectionStanding {
  section: string;
  students: number;
  overallAttainment: number;
  needAttention: number;
  critical: number;
  /** Movement against the previous analysed test, in points. null if none. */
  delta: number | null;
}

/** sectionComparison, but for any analysed test rather than only the
 *  latest, so a dashboard with an assessment picker never shows last
 *  test's standings next to this test's numbers. */
export function sectionStandings(testKey: string = latestTest.key): SectionStanding[] {
  const prevKey = previousAnalysedTestKey(testKey);
  return sections.map((section) => {
    const roster = classRosterFull[section] ?? [];
    const overallAttainment = Math.round(classAveragePct(section, testKey));
    return {
      section,
      students: roster.length,
      overallAttainment,
      needAttention: roster.filter((s) => attentionFor(s, testKey) !== "On Track").length,
      critical: roster.filter((s) => attentionFor(s, testKey) === "Intervention").length,
      delta: prevKey ? Math.round(classAveragePct(section, testKey) - classAveragePct(section, prevKey)) : null,
    };
  });
}

/** Rounds a set of counts to whole percentages that still add up to 100
 *  (largest-remainder), so a distribution's shares never read as 99% or
 *  101% next to the counts they describe. */
export function percentShares(counts: number[]): number[] {
  const total = counts.reduce((sum, c) => sum + c, 0);
  if (total <= 0) return counts.map(() => 0);
  const exact = counts.map((c) => (c / total) * 100);
  const floors = exact.map((v) => Math.floor(v));
  let remainder = 100 - floors.reduce((sum, v) => sum + v, 0);
  const order = exact
    .map((v, i) => ({ i, frac: v - Math.floor(v) }))
    .sort((a, b) => b.frac - a.frac || a.i - b.i);
  const shares = [...floors];
  for (const { i } of order) {
    if (remainder <= 0) break;
    shares[i] += 1;
    remainder -= 1;
  }
  return shares;
}


// ============================================================
// Live marks. Per-question marks drive everything above; saving an
// answer card rewrites them and refreshDerived() rolls the change
// through every cached headline figure.
// ============================================================

/** Split a chapter's scored marks across that chapter's 1-mark questions,
 *  deterministically, so the seeded analysed tests have real answer cards. */
function seedQuestionMarks(student: FullRosterStudent, testKey: string, subject: string): number[] {
  const qs = questionSets[subject] ?? [];
  const out = qs.map(() => 0);
  const rnd = mulberry32(seedFromString(`qm|${student.id}|${testKey}|${subject}`));
  for (const row of syntheticChapterBreakdown(student, testKey, subject)) {
    const idx = qs.map((q, i) => (q.chapter === row.chapter ? i : -1)).filter((i) => i >= 0);
    const order = idx.map((i) => ({ i, r: rnd() })).sort((a, b) => a.r - b.r);
    let left = row.scored;
    for (const { i } of order) {
      if (left <= 0) break;
      const give = Math.min(qs[i].maxMarks, left);
      out[i] = give;
      left -= give;
    }
  }
  return out;
}

for (const test of analysedTests) {
  questionMarks[test.key] = {};
  for (const subject of subjects) {
    questionMarks[test.key][subject] = {};
    for (const student of allStudents) questionMarks[test.key][subject][student.id] = seedQuestionMarks(student, test.key, subject);
  }
}

/** Recorded marks for one answer card, or null if none recorded yet. */
export function questionMarksFor(testKey: string, subject: string, studentId: string): number[] | null {
  return questionMarks[testKey]?.[subject]?.[studentId] ?? null;
}

/** Whether every student has recorded marks for this test, subject and section. */
export function isSubjectMarked(testKey: string, subject: string, section: string): boolean {
  const roster = classRosterFull[section] ?? [];
  return roster.length > 0 && roster.every((s) => !!questionMarks[testKey]?.[subject]?.[s.id]);
}

/** Marking progress for a test across every subject and section. */
export function testSubjects(testKey: string): string[] {
  return testsConducted.find((t) => t.key === testKey)?.subjects ?? [...subjects];
}

export function markingProgress(testKey: string): { done: number; total: number } {
  const list = testSubjects(testKey);
  let done = 0;
  for (const subject of list) for (const section of sections) if (isSubjectMarked(testKey, subject, section)) done++;
  return { done, total: list.length * sections.length };
}

/** Write one section's answer-card marks. Updates the students' subject
 *  scores in place; a test with every subject marked becomes analysed. */
export function setQuestionMarks(testKey: string, subject: string, marks: Record<string, number[]>) {
  const qs = questionSets[subject] ?? [];
  const outOf = qs.reduce((sum, q) => sum + q.maxMarks, 0);
  questionMarks[testKey] ??= {};
  questionMarks[testKey][subject] ??= {};
  for (const [studentId, row] of Object.entries(marks)) {
    questionMarks[testKey][subject][studentId] = row;
    const student = findStudent(studentId);
    if (!student) continue;
    student.scores[testKey] ??= {};
    student.scores[testKey][subject] = { scored: row.reduce((a, b) => a + b, 0), outOf };
  }
  const test = testsConducted.find((t) => t.key === testKey);
  if (test && test.status !== "Analysed" && markingProgress(testKey).done === markingProgress(testKey).total) {
    test.status = "Analysed";
  }
}

/** Add a test created from the question-paper screen. */
export function addConductedTest(test: ConductedTest) {
  if (testsConducted.some((t) => t.key === test.key)) return;
  testsConducted.push(test);
  testsConducted.sort((a, b) => a.date.localeCompare(b.date));
}

/** What a phone photo of an answer card reads for a test with nothing on
 *  record yet: each student performs near their latest level in the
 *  subject, question by question, adjusted for chapter difficulty. */
export function simulatedCardRead(studentId: string, testKey: string, subject: string): number[] {
  const student = findStudent(studentId);
  const qs = questionSets[subject] ?? [];
  const base = student ? pctFor(student, latestTest.key, subject) / 100 : 0.7;
  const rnd = mulberry32(seedFromString(`card|${studentId}|${testKey}|${subject}`));
  const shift = (rnd() - 0.45) * 0.16;
  return qs.map((q) => {
    const spec = (subjectChapters[subject] ?? []).find((c) => c.chapter === q.chapter);
    const p = Math.min(0.97, Math.max(0.08, base + shift - ((spec?.difficulty ?? 1) - 1) * 0.18));
    return rnd() < p ? q.maxMarks : 0;
  });
}

function refreshFindings() {
  for (const f of findings) {
    const spec = (subjectChapters[f.subject] ?? []).find((c) => c.chapter === f.topic);
    if (!spec) continue;
    const perSection: { section: string; pct: number }[] = [];
    let affected = 0;
    let lostSum = 0;
    for (const section of sections) {
      let n = 0;
      for (const student of classRosterFull[section] ?? []) {
        const row = chapterBreakdown(student, latestTest.key, f.subject).find((r) => r.chapter === f.topic);
        if (row && row.notScored / row.outOf >= 1 / 3) {
          n++;
          lostSum += row.notScored;
        }
      }
      affected += n;
      perSection.push({ section, pct: Math.round((n / Math.max(1, (classRosterFull[section] ?? []).length)) * 100) });
    }
    f.studentsAffected = affected;
    f.avgMarksLost = affected ? Math.round((lostSum / affected) * 10) / 10 : 0;
    if (f.mostAffectedSections) f.mostAffectedSections = perSection.sort((a, b) => b.pct - a.pct);
  }
}

/** Recompute every figure cached at module load after marks change. */
export function refreshDerived() {
  const analysed = testsConducted.filter((t) => t.status === "Analysed");
  analysedTests.splice(0, analysedTests.length, ...analysed);
  latestTest = analysedTests[analysedTests.length - 1];
  anomalyCache.clear();
  anomalyInsights = anomaliesFor(latestTest.key);
  refreshFindings();
  sectionComparison.splice(0, sectionComparison.length, ...buildSectionComparison());
  Object.assign(schoolSnapshot, buildSchoolSnapshot());
  Object.assign(assessmentContext, {
    assessmentName: latestTest.name,
    assessmentEvidence: `${analysedTests.length} Test${analysedTests.length === 1 ? "" : "s"}`,
    pilotStatusMessage: `Early Intelligence: this analysis is based on ${analysedTests.map((t) => t.name).join(" and ")}. Prediction confidence keeps improving as more assessments are analysed.`,
    assessmentOptions: testsConducted.map((t) => ({ label: t.name, selectable: t.status === "Analysed" })),
  });
}

refreshDerived();
