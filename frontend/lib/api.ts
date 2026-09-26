// Baked in at BUILD time, not read at runtime: changing it on the host requires a fresh
// deploy, not a restart. The localhost fallback is right for a laptop and wrong for every
// deployment, which is why apiBaseIsDefault() exists -- an unset variable in production
// makes the browser ask the *visitor's* machine for the API, and the resulting failure
// looks like a dead backend rather than a missing setting.
import { getActiveSchool, TeacherAssignment } from "@/lib/session";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function apiBase(): string {
  return BASE;
}

export function apiBaseIsDefault(): boolean {
  return !process.env.NEXT_PUBLIC_API_BASE;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Thrown when the request never reached the API at all -- DNS, CORS, or nothing there. */
export class ApiUnreachable extends Error {
  constructor(public base: string) {
    super(`Could not reach the API at ${base}`);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    // fetch rejects rather than returning a status when the origin is unreachable or the
    // browser blocked the response for CORS -- both are configuration, not a bad key
    throw new ApiUnreachable(BASE);
  }
  if (!res.ok) {
    const detail = await res.text();
    throw new ApiError(res.status, detail || res.statusText);
  }
  // A DELETE returns 204 with no body -- res.json() throws on empty input, which would
  // turn a successful deletion into a reported failure.
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/**
 * Which school this request is about. Sent on every authenticated call because an admin
 * key belongs to no school and the API refuses rather than guessing one. A principal's
 * key names its school and the API never reads this, so it is harmless to send.
 */
function scopeHeader(): Record<string, string> {
  const active = getActiveSchool();
  return active ? { "X-School-Id": active } : {};
}

function authed<T>(path: string, key: string, init?: RequestInit): Promise<T> {
  return request<T>(path, {
    ...init,
    headers: { "X-API-Key": key, ...scopeHeader(), ...(init?.headers ?? {}) },
  });
}

/**
 * The console takes two credentials -- the operator key that bootstraps a deployment, and
 * an admin key that names no school. They arrive on different headers, and which one is
 * held is not worth tracking separately, so the stored secret is offered as both: the
 * wrong one simply matches nothing.
 */
function operator<T>(path: string, key: string, init?: RequestInit): Promise<T> {
  return request<T>(path, {
    ...init,
    headers: { "X-Platform-Key": key, "X-API-Key": key, ...(init?.headers ?? {}) },
  });
}

async function authedBlob(path: string, key: string): Promise<Blob> {
  const res = await fetch(`${BASE}${path}`, { headers: { "X-API-Key": key, ...scopeHeader() } });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.blob();
}

function qs(params: Record<string, string | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (entries.length === 0) return "";
  return "?" + new URLSearchParams(entries as [string, string][]).toString();
}

function studentAuthed<T>(path: string, sessionToken: string, init?: RequestInit): Promise<T> {
  return request<T>(path, {
    ...init,
    headers: { "X-Student-Session": sessionToken, ...(init?.headers ?? {}) },
  });
}

// --- dashboard types ------------------------------------------------------------------
export interface SectionSummary {
  section_id: string;
  label: string;
  student_path: string;
  students: number;
  completed: number;
  flagged: number;
}

export interface Overview {
  school: { id: string; name: string; state: string | null };
  sections: SectionSummary[];
  totals: { students: number; completed: number; flagged: number };
  assessments: {
    id: string;
    title: string;
    paper_code: string | null;
    subject_code: string;
    status: string;
    total_marks: number | null;
    frozen: boolean;
  }[];
}

/** GET /admin/academics -- one row per class, a status bucket count per student derived
 * from real marks. No aspiration/action-plan/recheck fields -- this deployment has no
 * data model for those yet. */
export interface ClassAcademicSummary {
  section_id: string;
  label: string;
  grade: number;
  name: string;
  student_count: number;
  status_counts: {
    on_track: number;
    needs_attention: number;
    requires_review: number;
    not_assessed: number;
  };
  avg_score_pct: number | null;
  test_count: number;
}

export interface AcademicsOverview {
  school: { id: string; name: string };
  classes: ClassAcademicSummary[];
}

/** GET /admin/teacher/academics -- one row per class/subject this teacher key holds
 * (a class assignment reads every subject; a subject assignment reads only its own). */
export interface TeacherAcademicClassRow {
  section_id: string;
  label: string;
  subject_code: string | null;
  subject_label: string;
  student_count: number;
  status_counts: ClassAcademicSummary["status_counts"];
  avg_score_pct: number | null;
  /** Average marks earned / average marks possible per student, behind avg_score_pct
   *  -- both null together when nobody has a resolved mark yet. */
  avg_marks_earned: number | null;
  avg_marks_available: number | null;
  test_count: number;
}

export type AcademicStatus = "on_track" | "needs_attention" | "requires_review" | "not_assessed";

/** GET /admin/academics/{sectionId}/students -- one row per student in a class, plus
 * the real subject/test filter options that class actually has marks on. */
export interface ClassStudentRow {
  student_id: string;
  name: string;
  roll_no: string;
  status: AcademicStatus;
  avg_score_pct: number | null;
  tests_taken: number;
  top_improvement_area: { chapter: string; rate: number } | null;
  /** Score on the immediately preceding same-subject test, when the view is narrowed to
   *  one test and this student sat the earlier one too; otherwise null. */
  previous_score_pct: number | null;
  /** avg_score_pct minus previous_score_pct -- null when either side is missing. */
  delta_pct: number | null;
  parent_name: string | null;
  parent_whatsapp: string | null;
}

export interface ClassStudentsView {
  section: { id: string; label: string };
  previous_test: { assessment_id: string; title: string } | null;
  filters: {
    subjects: { subject_code: string; label: string }[];
    tests: { assessment_id: string; title: string }[];
  };
  students: ClassStudentRow[];
}

/** GET /admin/academics/students/{id} -- one student, every subject they have marks
 * in. */
export interface StudentSubjectRow {
  subject_code: string;
  label: string;
  avg_score_pct: number | null;
  tests_taken: number;
  status: AcademicStatus;
  strengths: string[];
  improve: string[];
}

export interface StudentAcademicsOverview {
  student: { id: string; name: string; roll_no: string; section_id: string; section_label: string | null };
  overall: {
    avg_score_pct: number | null; status: AcademicStatus; tests_taken: number;
    /** Every classmate's marks in the same section, rolled up the same way. */
    class_avg_score_pct: number | null;
    vs_class_pct: number | null;
  };
  subjects: StudentSubjectRow[];
}

/** GET /admin/academics/students/{id}/subjects/{code} -- chapter-wise and tier-wise
 * findings, the same evidence-floored shape a BoardX report uses. */
export interface AcademicFinding {
  key: string;
  label: string;
  earned: number;
  available: number;
  rate: number | null;
  questions: number;
  sufficient: boolean;
  message: string;
}

export interface StudentSubjectBreakdown {
  student: { id: string; name: string; roll_no: string };
  subject: { subject_code: string; label: string };
  overall: {
    earned: number; available: number; avg_score_pct: number | null;
    status: AcademicStatus; tests_taken: number;
  };
  by_chapter: AcademicFinding[];
  by_tier: AcademicFinding[];
  tests: { assessment_id: string; title: string }[];
}

/** GET /reports/student/{id}/boardx -- the BoardX v2 one-page report, composed from
 * frozen student-register sentences (app.analysis.boardx_report). Each line carries a
 * frozen-string id; only .text is ever shown. */
export interface BoardXLine {
  id: string;
  text: string;
}

export interface BoardXChapterRow {
  domain: string;
  domain_code: string;
  scored: number;
  available: number;
  not_scored: number;
  diagnosable: boolean;
  board_exposure: number | null;
  board_total: number | null;
  board_exposure_verified: boolean;
  estimated_board_impact: "NOT_CALIBRATED";
  lines: BoardXLine[];
}

export interface BoardXCard {
  domain: string;
  topic: string | null;
  lines: BoardXLine[];
  action: { remediation_ref: string; text: string } | null;
}

/** One skill x tier cell of section 2, keyed "skill|tier" by taxonomy code. */
export interface BoardXCrosstabRow {
  key: string;
  earned: number;
  available: number;
  questions: number;
  rate: number | null;
  sufficient: boolean;
  message: string;
  skill_label: string;
  tier: string | null;
  question_type: string | null;
}

export interface BoardXReport {
  assessment_id: string;
  assessment_title: string;
  subject_code: string;
  subject_label: string;
  student_id: string;
  student_name: string;
  assembly_band: "upper" | "lower";
  // section1's last entry carries only `lines` (the board-impact disclaimer), so a
  // chapter row is any entry that actually has a `domain`.
  section1: (BoardXChapterRow | { lines: BoardXLine[] })[];
  section2: { caption: BoardXLine; crosstab: BoardXCrosstabRow[] };
  section3: BoardXLine[];
  section4: BoardXCard[];
  section5: { actions: { remediation_ref: string; text: string; line: BoardXLine }[] };
  section6: BoardXLine[];
}

/** GET /admin/academics/tests -- every paper with at least one resolved mark. */
/** One scheduled exam day, as a principal or admin entered it (POST /admin/exams). */
export interface ExamSummary {
  id: string;
  name: string;
  /** ISO date (YYYY-MM-DD), exactly as entered. */
  scheduled_date: string;
  paper_count: number;
}

export interface ScheduledExam extends ExamSummary {
  status: string;
}

/** One section's average in one subject, over the real resolved marks of an exam. */
export interface ExamGridCell {
  section_id: string;
  section_label: string;
  grade: number;
  section_name: string;
  subject_code: string;
  subject_label: string;
  avg_score_pct: number;
  assessment_ids: string[];
}

export interface ConductedExam {
  /** "exam" for a grouped exam day; "paper" for a paper never attached to one. */
  kind: "exam" | "paper";
  id: string;
  name: string;
  /** The exam's scheduled date, or the paper's entry date for a standalone paper. */
  date: string | null;
  scheduled_date: string | null;
  paper_count: number;
  grid: ExamGridCell[];
  school_avg_pct: number | null;
  students_marked: number;
  subjects: string[];
  previous: { id: string; name: string } | null;
  delta_pct: number | null;
}

export interface ExamsOverview {
  today: string;
  upcoming: ScheduledExam[];
  awaiting_marks: ScheduledExam[];
  conducted: ConductedExam[];
  weakest_subject: { subject_code: string; label: string; avg_score_pct: number } | null;
}

export interface AcademicTestRow {
  assessment_id: string;
  title: string;
  subject_code: string;
  label: string;
  students_marked: number;
  avg_score_pct: number | null;
  /** This test's average score minus the immediately preceding test of the SAME
   *  subject's -- null when there is no earlier scored test of that subject to compare
   *  against, or this test itself has no score yet. Never a guess: both sides are real
   *  averages, or there is no number at all. */
  delta_pct: number | null;
}

/** GET /admin/teacher/academics/{section}/tests/{id}/marks-grid */
export interface MarksGridQuestion {
  address: string;
  label: string;
  max_marks: number;
  /** The question's real chapter (or, for a skill-anchored question with no chapter,
   *  its concept_family) label -- what a legend groups by. Never a fabricated name. */
  group: string;
}

export interface MarksGridRow {
  student_id: string;
  roll_no: string;
  name: string;
  /** address -> awarded mark, or null when nothing is resolved for that question yet. */
  marks: Record<string, number | null>;
  total: number;
}

export interface MarksGridReport {
  assessment: { id: string; title: string; subject_code: string; subject_label: string };
  section_id: string;
  questions: MarksGridQuestion[];
  total_marks: number;
  students: MarksGridRow[];
  fully_marked: boolean;
}

/** GET /admin/academics/tests/{id} -- one test's own student-by-student summary. */
export interface TestStudentRow {
  student_id: string;
  name: string;
  roll_no: string;
  earned: number;
  available: number;
  avg_score_pct: number | null;
  status: AcademicStatus;
}

export interface TestSummary {
  assessment: { id: string; title: string; subject_code: string; subject_label: string };
  status_counts: Record<AcademicStatus, number>;
  students: TestStudentRow[];
}

/** GET /admin/staff -- who holds a key for this school. Never carries the secret. */
export interface SchoolStaffRow {
  id: string;
  role: "principal" | "admin";
  label: string;
  created_at: string | null;
  revoked_at: string | null;
}

/** GET/POST /admin/teachers -- a teacher key, with its assignments. Never the secret. */
export interface TeacherAssignmentView {
  id: string;
  type: "class" | "subject";
  section_id: string;
  section_label: string | null;
  subject_code: string | null;
}

export interface TeacherKeyView {
  id: string;
  role: "teacher";
  label: string;
  /** A principal already has full authority over their own school's teacher keys. */
  api_key: string;
  created_at: string | null;
  revoked_at: string | null;
  assignments: TeacherAssignmentView[];
}

export interface TeacherAssignmentSpec {
  type: "class" | "subject";
  section_id: string;
  subject_code?: string | null;
}

export interface TeacherSectionSummary {
  section_id: string;
  can_read_all_subjects: boolean;
  subjects: string[];
  label: string | null;
  student_path: string | null;
}

/** GET /admin/teacher/students/{id}/reports -- every report issued for one student,
 * with whether it is currently shared with them. Never carries a PIN. */
export interface IssuedReportRow {
  report_id: string;
  assessment_id: string;
  student_id: string;
  issued_by: string;
  issued_at: string | null;
  earned: number;
  available: number;
  assessment_title: string | null;
  shared: boolean;
  shared_at: string | null;
  shared_by: string | null;
}

/** POST .../reports/{id}/share -- the PIN is carried once, on this response only. */
export interface SharedReportView extends IssuedReportRow {
  pin: string;
  class_code: string;
  roll_no: string;
  pin_notice: string;
}

/** POST /student/{classCode}/login */
export interface StudentLoginResult {
  session_token: string;
  student_name: string;
  expires_at: string;
}

/** GET /student/reports -- one row per report currently shared with the signed-in
 * student. */
export interface StudentReportRow {
  report_id: string;
  assessment_id: string;
  issued_at: string | null;
  earned: number;
  available: number;
  assessment_title: string | null;
  shared_at: string | null;
}

/** GET /student/reports/{id} -- the full payload behind one shared row. Same shape
 * `student_report`/`read_issued_report` return to staff -- the student portal is the
 * one that keeps its own rendering in plain language, not this response. */
export interface StudentReportDetail extends StudentReportRow {
  payload: Record<string, unknown>;
}

// --- class mark-entry sheet: one photograph, many students ----------------------------

export interface GridUploadResult {
  document_id: string;
  rows: number;
  clean: number;
  name_mismatch: number;
  unmatched: number;
  problems: string[];
  next: string;
}

export interface GridRowMark {
  address: string;
  marks: number | null;
  state: string;
  raw_value: string;
  problem: string | null;
}

export interface GridSheetRowView {
  row_id: string;
  roll_no: string;
  name_as_written: string;
  status: "unmatched" | "name_mismatch" | "clean";
  note: string | null;
  student: { id: string; name: string } | null;
  marks: GridRowMark[];
  can_confirm: boolean;
}

export interface GridSheetReview {
  document_id: string;
  assessment: { id: string; title: string };
  rows: GridSheetRowView[];
  ready_to_confirm: number;
}

export interface GridConfirmResult {
  confirmed: string[];
  skipped: { roll_no: string; reason: string }[];
  confirmed_by: string;
}

export interface PaperSummary {
  id: string;
  title: string;
  subject_code: string;
  subject_label: string;
  paper_code: string | null;
  total_marks: number | null;
  created_at: string | null;
  stage: "empty" | "scanned" | "confirmed" | "mapped";
  scanned_questions: number;
  questions: number;
  mapped_questions: number;
  students_with_marks: number;
  ready_for_answer_sheets: boolean;
}

export interface AnswerRow {
  address: string;
  section: string | null;
  question_no: string;
  sub_part: string | null;
  choice_alt: string | null;
  max_marks: number;
  stem_text: string | null;
  chapter: string | null;
  concept_family: string | null;
  marks: number | null;
  state: string | null;
  source: string | null;
}

export interface AnswerSheet {
  assessment: { id: string; title: string; subject_code: string; total_marks: number | null };
  student: { id: string; name: string; roll_no: string };
  questions: AnswerRow[];
  entered: number;
  remaining: number;
  scored: number;
  available: number;
}

export interface ConfirmAnswersResult {
  written: number;
  rejected: { address: string; reason: string }[];
  scored: number;
  available: number;
  remaining: number;
  complete: boolean;
}

export interface Proof {
  question_no: string;
  section: string | null;
  sub_part: string | null;
  choice_alt: string | null;
  question_type: string | null;
  stem_text: string | null;
  logical_page: number | null;
  curriculum_section: string | null;
  curriculum_section_title: string | null;
  concept_variant: string | null;
  mark_source: string | null;
  earned: number | null;
  max_marks: number | null;
  state: string | null;
  placement: {
    source: string | null;
    confidence: number | null;
    needs_review: boolean | null;
    book_evidence: string[];
    candidates: unknown[];
    chapter: string | null;
    concept_family: string | null;
    board_unit: string | null;
  } | null;
}

/** One reported figure, with the questions it was computed from. */
export interface Finding {
  kind: string;
  scope: string;
  /** The taxonomy code. Stable across cycles, and not for showing to anyone. */
  key: string;
  /** What the code is called in the book. Always prefer this on screen. */
  label: string;
  earned: number;
  available: number;
  questions: number;
  rate: number | null;
  ci: [number, number] | null;
  sufficient: boolean;
  /** HIGH / MEDIUM / EMERGING -- never derive this yourself from `sufficient`/`ci`,
   * the backend's confidence_tier is the one place that boundary is allowed to live. */
  confidence: "HIGH" | "MEDIUM" | "EMERGING";
  message: string | null;
  evidence: Proof[];
  /** Which chapter this topic/concept/sub-topic lives in, e.g. "Statistics" for "Finding
   *  the mean of ungrouped data" -- null only when the taxonomy has nothing above it
   *  (the finding is itself a chapter-level row). Always show this: a concept name on its
   *  own is unplaceable to a parent who has never seen the book's own chapter titles. */
  chapter: string | null;
  /** Only present on `focus`/`findings` entries -- how much this topic matters for the
   * Board, resolved through the question's own board unit. */
  board?: {
    board_unit: string | null;
    board_weight_pct: number | null;
    frequency_multiplier: number;
    urgency: number | null;
    /** VERY HIGH / HIGH / MEDIUM / LOW -- the badge a screen shows; `urgency` above is
     *  the raw score it was computed from, never itself a label to display. */
    urgency_tier: "VERY HIGH" | "HIGH" | "MEDIUM" | "LOW" | null;
    note: string | null;
  };
}

export interface BoardUrgencyRow {
  key: string;
  label: string;
  board_unit: string | null;
  board_weight_pct: number | null;
  frequency_multiplier: number;
  urgency: number | null;
  /** VERY HIGH / HIGH / MEDIUM / LOW -- null only when there are no eligible board
   * years to judge yet, which is a different state from LOW and should read that way. */
  urgency_tier: "VERY HIGH" | "HIGH" | "MEDIUM" | "LOW" | null;
  years_appeared: number | null;
  years_eligible: number | null;
  note: string | null;
}

export interface StudentDiagnosis {
  assessment_id: string;
  assessment_title: string;
  student_id: string;
  total: { earned: number; available: number; rate: number | null; questions: number };
  topic_axis: "concept_family" | "subtopic" | "chapter";
  topics: Finding[];
  strengths: Finding[];
  focus: Finding[];
  tier_summary: Finding[];
  findings: Finding[];
  all_crosstab: Finding[];
  board_urgency: BoardUrgencyRow[];
  board_weighted_indicators: {
    board_unit: string;
    label: string;
    /** Percentage points of the board's own weighting, already on a 0-100 scale. */
    board_weight: number;
    lost: number;
    available: number;
    weighted_loss: number;
  }[];
  coverage_gaps: {
    board_unit: string;
    label: string;
    board_weight: number;
    message: string;
  }[];
  not_offered: string[];
}

export interface PaperReport {
  assessment_id: string;
  students: number;
  items: {
    address: string;
    difficulty: number | null;
    discrimination: number | null;
    negative_discrimination: boolean;
    low_discrimination: boolean;
    no_variance: boolean;
    flag: boolean;
  }[];
  flagged_items: string[];
  cronbach_alpha: number | null;
  typology_alignment: {
    observed: Record<string, number>;
    target: Record<string, number>;
    chi_square: number;
    alignment_score: number;
    verdict: string;
  };
  /** STRONG / MODERATE / LIMITED -- read this and the verdict text together, never the
   * alignment_score alone: the spec is explicit that a bare percentage with no
   * interpretation is not the point. */
  diagnostic_strength: "STRONG" | "MODERATE" | "LIMITED";
  /** Share of this paper's marks that were Applying-tier / Analysing-Evaluating-Creating
   * tier -- null only when the paper carried no tier-tagged marks at all. */
  application_share: number | null;
  higher_order_share: number | null;
}

/** How the whole class did on one paper -- every field a real aggregation over every
 *  student's marks (see GET /reports/cohort/{id}'s own docstring), never an estimate. */
export interface CohortReport {
  assessment_id: string;
  assessment_title: string;
  students_analysed: number;
  band_counts: {
    full_mastery: number; band_80_89: number; band_60_79: number; below_60: number;
  };
  band_pct: {
    full_mastery: number; band_80_89: number; band_60_79: number; below_60: number;
  };
  section_bars: { section_id: string; label: string; pct: number; students: number }[];
  /** Each subject's own most recent graded assessment for the same section(s) -- see
   *  subject_bars_note; there is no shared "test occasion" across subjects in this schema. */
  subject_bars: {
    subject_code: string; subject_label: string; assessment_id: string; assessment_title: string; pct: number;
    band_counts: { full_mastery: number; band_80_89: number; band_60_79: number; below_60: number };
  }[];
  subject_bars_note: string;
  top_losses: {
    concept_family: string;
    label: string;
    students_affected: number;
    avg_marks_lost: number;
    board_urgency: string | null;
    confidence: "HIGH" | "MEDIUM" | "EMERGING";
  }[];
}

export interface ScanPageRef {
  index: number;
  content_type: string;
  byte_size: number;
  url: string;
}

export interface ScanDoc {
  document_id: string;
  kind: "question_paper" | "answer_sheet";
  assessment_id: string;
  assessment_title?: string | null;
  student_id: string | null;
  page_count: number;
  uploaded_at: string | null;
  confirmed_at: string | null;
  confirmed_by: string | null;
  pages: ScanPageRef[];
}

export interface IssuedReport {
  report_id: string;
  assessment_id: string;
  assessment_title: string | null;
  student_id: string;
  issued_by: string;
  issued_at: string | null;
  sha256: string;
  earned: number;
  available: number;
  payload?: StudentDiagnosis;
}

export interface ReadRow {
  address: string;
  section: string | null;
  question_no: string;
  choice_alt: string | null;
  max_marks: number;
  stem_text: string | null;
  read: boolean;
  marks: number | null;
  state: string | null;
  origin: string | null;
  raw_value: string | null;
  problem: string | null;
  edited_by: string | null;
  source_name: string | null;
}

export interface ReadingSheet {
  assessment: { id: string; title: string };
  student: { id: string; name: string; roll_no: string };
  questions: ReadRow[];
  read: number;
  missing: number;
  blocked: number;
  can_confirm: boolean;
}

export interface ReadResult {
  read: number;
  used_ocr: boolean;
  unmatched: { raw_address: string; raw_value: string; reason: string; origin: string }[];
  questions_on_paper: number;
  rolls_in_file: string[];
  problems: string[];
  source: string;
  note: string | null;
}

export interface SatPaper {
  assessment_id: string;
  title: string;
  subject_code: string;
  subject_label: string;
  created_at: string | null;
  questions_marked: number;
}

export interface DashboardPaper {
  id: string;
  title: string;
  subject_code: string;
  subject_label: string;
  created_at: string | null;
  questions: number;
  mapped: number;
  students_marked: number;
  paper_stored: boolean;
  stage: "empty" | "scanned" | "read" | "mapped";
}

export interface DashboardStudent {
  student_id: string;
  name: string;
  roll_no: string;
  papers_marked: number;
  scripts: number;
  reports: number;
}

export interface DashboardScript {
  document_id: string;
  student_id: string | null;
  student: string;
  roll_no: string;
  assessment_title: string | null;
  page_count: number;
  stored_at: string | null;
  first_page: string | null;
}

export interface Dashboard {
  school: { id: string; name: string; state: string | null };
  counts: {
    students: number;
    classes: number;
    papers: number;
    papers_read: number;
    question_papers_stored: number;
    scripts_stored: number;
    reports_issued: number;
    questions_total: number;
    questions_mapped: number;
  };
  papers: DashboardPaper[];
  students: DashboardStudent[];
  recent_scripts: DashboardScript[];
}

export interface RosterRow {
  student_id: string;
  name: string;
  roll_no: string;
  /** How many papers this student has marks on. Zero is a real answer, not a gap. */
  papers_marked: number;
  status: "not_started" | "in_progress" | "complete";
  validity: string | null;
  holland_code: string | null;
  withheld: boolean | null;
  top_stream: string | null;
}

export interface InterestReport {
  student: { id: string; name: string; roll_no: string };
  validity: string;
  validity_detail: { reasons?: string[] } | null;
  scales: { scale: string; raw: number; centered: number; percentile: number; ci: number[] }[];
  holland_code: string | null;
  differentiation: number | null;
  consistency: number | null;
  stream_fit: Record<string, number> | null;
  recommendation_withheld: boolean;
  withheld_reason: string | null;
}

export interface Screen {
  item_id: string;
  text: string;
  options: string[];
}

export interface SessionPayload {
  session_id: string;
  locale: string;
  total_items: number;
  screens: Screen[][];
}

export type ClassOption = {
  class_code: string;
  label: string;
  grade: number;
  section: string;
  school: string;
  board: string;
};

/** Everything the real 6-step /attend/onboarding wizard submits in one shot to
 * POST /t/{classCode}/onboard. Separate from the RIASEC start() payload above
 * -- this never creates a TestSession. */
export interface OnboardingIn {
  name: string;
  roll_no: string;
  age?: number;
  gender?: "female" | "male" | "other" | "prefer_not_to_say";
  dob?: string;
  board?: string;
  lives_in?: string;
  decision_helper?: string;
  responsibilities?: string;
  subject_enjoy?: string;
  subject_comfortable?: string;
  learning_type?: string;
  interests?: string[];
  work_interest?: string;
  new_learning_style?: string;
  future_career?: string;
  class11_group?: string;
  group_reason?: string[];
  confidence?: number;
  careers_known?: string[];
  future_concern?: string[];
}

export interface OnboardingOut {
  student_id: string;
  message: string;
}

// --- operator console types -----------------------------------------------------------
export interface PlatformSection {
  id: string;
  label: string;
  grade: number;
  name: string;
  student_path: string;
}

export interface PlatformSchool {
  id: string;
  name: string;
  board: string;
  state: string | null;
  training_consent: string;
  code: string | null;
  city: string | null;
  address: string | null;
  academic_year: string | null;
  students: number;
  sections: PlatformSection[];
  hidden_from_directory: boolean;
  created_at: string | null;
}

export interface SchoolPatch {
  name?: string;
  board?: string;
  state?: string;
  training_consent?: string;
  code?: string;
  city?: string;
  address?: string;
  academic_year?: string;
}

export interface TeacherAssignmentRow {
  id: string;
  staff_key_id: string;
  type: "class" | "subject";
  section_id: string;
  subject_code: string | null;
}

export interface TeacherAssignmentInput {
  type: "class" | "subject";
  section_id: string;
  subject_code?: string | null;
}

export interface PlatformStudentRow {
  id: string;
  name: string;
  roll_no: string;
  section_id: string;
  section_label: string | null;
  age: number | null;
  gender: string | null;
  dob: string | null;
  parent_name: string | null;
  parent_whatsapp: string | null;
}

export interface StudentBulkInput {
  name: string;
  roll_no: string;
  section_id: string;
  age?: number | null;
  gender?: string | null;
  dob?: string | null;
  parent_name?: string | null;
  parent_whatsapp?: string | null;
}

export interface AuditLogRow {
  id: string;
  action: string;
  detail: string | null;
  actor_role: string;
  actor_label: string;
  created_at: string | null;
}

/** Only ever returned by create and rotate -- listing carries no key. */
export interface IssuedKey {
  api_key: string;
  api_key_notice: string;
}

export interface PlatformOverviewRow {
  id: string;
  name: string;
  board: string;
  state: string | null;
  students: number;
  papers: number;
  answer_scripts: number;
  reports_issued: number;
  admin_keys: number;
  principal_keys: number;
}

export interface PlatformOverview {
  schools: PlatformOverviewRow[];
  totals: {
    schools: number;
    students: number;
    papers: number;
    answer_scripts: number;
    reports_issued: number;
  };
  cross_school_admin_keys: number;
}

export interface StaffKeySummary {
  id: string;
  /** null for an admin key: it belongs to no school, which is what lets it span them. */
  school_id: string | null;
  role: "principal" | "admin" | "teacher";
  label: string;
  name: string | null;
  email: string | null;
  phone: string | null;
  /** Only meaningful for role == "teacher": papers-and-marks rights across every
   * subject, no teaching assignment needed. */
  exam_cell: boolean;
  /** The operator is the top of the trust chain, so the listing carries the live key. */
  api_key: string;
  created_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
}

export interface FamilyProposal {
  code: string;
  label: string;
  chapter_code: string;
  chapter_label: string;
  /** The sections of the chapter this family draws on. Empty means it cannot be chosen
   *  by section afterwards, so it is worth knowing before creating it. */
  from_sections: string[];
  source: string;
  rationale: string | null;
  chunks: number;
  already_exists: boolean;
  /** Set when this proposal's label reads as the same idea as another proposal's, under
   *  the same chapter -- the code of that other proposal. Never auto-merged; a person
   *  picks which one to create. */
  similar_to?: string | null;
}

export interface UncoveredSections {
  chapter_code: string;
  /** Sections the book was actually loaded with that no family, existing or proposed,
   *  claims. A question landing in one of these has nothing to be mapped to, however
   *  thoroughly the family list below is reviewed -- create a family that names it. */
  sections: string[];
}

export interface FamilyProposals {
  subject: string;
  existing: number;
  proposed: number;
  without_a_section: number;
  possible_duplicates: number;
  uncovered_sections: UncoveredSections[];
  families: FamilyProposal[];
  note: string;
}

export interface AuditedFamily {
  code: string;
  label: string;
  chapter_code: string | null;
  questions: number;
  problem: string;
  /** Set on a duplicate entry only: the code of the family it should be merged into. */
  duplicate_of: string | null;
}

export interface FamilyAudit {
  subject: string;
  families: number;
  wrong_subject: AuditedFamily[];
  empty_code: AuditedFamily[];
  duplicates: AuditedFamily[];
  removable: number;
  kept_because_used: AuditedFamily[];
}

export interface ChapterCoverage {
  chapter_code: string;
  chapter: string;
  chunks: number;
  embedded: number;
  with_a_section: number;
}

export interface BookStatus {
  subject: string;
  curriculum_ready: boolean;
  contents_uploaded: boolean;
  edition?: string | null;
  expected_chapters: number;
  loaded_chapters: number;
  missing_chapters?: number[];
  chunks: number;
  embedded: number;
  embeddings_configured: boolean;
  /** Per chapter. A healthy whole-book total hides a chapter with nothing behind it. */
  coverage: ChapterCoverage[];
  chapters_with_nothing_behind_them: string[];
  /** filename -> what was loaded from it; the chapter number is what a bulk load reads
   *  to skip a file it already has */
  files?: Record<string, { chapter?: number; chunks?: number; loaded_at?: string }>;
  next: string;
}

/** Multipart, so it cannot go through `request` -- setting Content-Type by hand drops the
 *  boundary the server needs to parse the body. The header name is a parameter because
 *  the operator surface and the school surface authenticate differently, and hard-coding
 *  one of them here would silently 404 every call from the other. */
/**
 * A book upload the backend could not finish inside the request -- a Hindi subject's
 * text has to come from Gemini, tens of seconds for one call, and Render's own reverse
 * proxy enforces a request timeout no amount of backend-side retrying can get around. The
 * upload endpoint answers 202 with a job id instead of blocking, and this is what used to
 * be a bare fetch becomes: poll GET .../jobs/{id} until it resolves, then hand back
 * exactly what the synchronous endpoint (every other subject) returns directly, so
 * uploadContents/uploadChapter's own callers never have to know which happened.
 *
 * 2s between polls, 10 minutes before giving up -- long enough for a real chapter PDF, not
 * so long a genuinely stuck job hangs the page forever with no feedback.
 */
// Exported (not just used internally by upload()/uploadMany()) so a caller that already
// knows a job is in flight -- persisted from a previous onJobQueued callback -- can
// resume watching it directly, without re-uploading anything. Skipping straight to a
// poll here is what stops a lost connection from turning into a second, costly vision
// call for work the server already has queued or finished.
export async function pollJob<T>(
  jobsBase: string, key: string, jobId: string,
  header: "X-Platform-Key" | "X-API-Key",
): Promise<T> {
  const deadline = Date.now() + 10 * 60 * 1000;
  while (true) {
    let res: Response;
    try {
      res = await fetch(`${BASE}${jobsBase}/jobs/${jobId}`, {
        headers: { [header]: key, ...(header === "X-API-Key" ? scopeHeader() : {}) },
      });
    } catch {
      throw new ApiUnreachable(BASE);
    }
    if (!res.ok) {
      // the job failed -- the same status/detail a synchronous upload would have thrown
      throw new ApiError(res.status, await res.text());
    }
    const body = (await res.json()) as { status: string };
    if (body.status === "succeeded") return body as T;
    if (Date.now() > deadline) {
      throw new ApiError(504, `job ${jobId} did not finish within 10 minutes`);
    }
    await waitOrUntilVisible(2000);
  }
}

/**
 * The same 2s wait between polls, except it also resolves the instant the tab becomes
 * visible again -- switching back to a tab that was minimised or backgrounded shows the
 * result on the next tick rather than waiting out whatever was left of a throttled
 * background-tab interval, which browsers slow down (sometimes to once a minute or more).
 */
function waitOrUntilVisible(ms: number): Promise<void> {
  return new Promise((resolve) => {
    if (typeof document === "undefined") {
      setTimeout(resolve, ms);
      return;
    }
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
      resolve();
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") finish();
    };
    const timer = setTimeout(finish, ms);
    document.addEventListener("visibilitychange", onVisible);
  });
}

/**
 * A plain POST (no file body) that may answer 202 + job_id instead of the result
 * directly -- the placement endpoint's shape, distinct from upload()/uploadMany() only in
 * having nothing to attach as multipart form data.
 */
async function postAndPoll<T>(
  path: string, key: string, onJobQueued?: (jobId: string) => void,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "X-API-Key": key, ...scopeHeader() },
    });
  } catch {
    throw new ApiUnreachable(BASE);
  }
  if (!res.ok) throw new ApiError(res.status, await res.text());
  const data = (await res.json()) as Record<string, unknown>;
  if (data.status === "pending" && typeof data.job_id === "string") {
    onJobQueued?.(data.job_id);
    return pollJob<T>(path, key, data.job_id, "X-API-Key");
  }
  return data as T;
}

async function upload<T>(
  path: string,
  key: string,
  file: File,
  header: "X-Platform-Key" | "X-API-Key" = "X-Platform-Key",
): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { [header]: key, ...(header === "X-API-Key" ? scopeHeader() : {}) },
      body,
    });
  } catch {
    throw new ApiUnreachable(BASE);
  }
  if (!res.ok) throw new ApiError(res.status, await res.text());
  const data = (await res.json()) as Record<string, unknown>;
  if (data.status === "pending" && typeof data.job_id === "string") {
    const jobsBase = path.split("?")[0].replace(/\/(contents|chapters)$/, "");
    return pollJob<T>(jobsBase, key, data.job_id, header);
  }
  return data as T;
}

async function uploadMany<T>(
  path: string,
  key: string,
  files: File[],
  header: "X-Platform-Key" | "X-API-Key",
  // Set only by an endpoint that can answer with {status:"pending", job_id} because the
  // real work runs too long for one request (see GridSheetJob) -- everything else gets
  // its result directly and never looks at this.
  jobsBase?: string,
  // Fired the instant a job is queued (202 + job_id received), before polling starts --
  // a caller with somewhere durable to put it (see PendingSubmission) can persist the id
  // right away, so a connection lost partway through polling resumes by watching that
  // same job instead of resubmitting the files as a brand new one.
  onJobQueued?: (jobId: string) => void,
): Promise<T> {
  const body = new FormData();
  // The field name repeats rather than being indexed: that is what FastAPI reads as a
  // list, and the order of appends is the page order the server keeps.
  for (const file of files) body.append("files", file);
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { [header]: key, ...(header === "X-API-Key" ? scopeHeader() : {}) },
      body,
    });
  } catch {
    throw new ApiUnreachable(BASE);
  }
  if (!res.ok) throw new ApiError(res.status, await res.text());
  const data = (await res.json()) as Record<string, unknown>;
  if (jobsBase && data.status === "pending" && typeof data.job_id === "string") {
    onJobQueued?.(data.job_id);
    return pollJob<T>(jobsBase, key, data.job_id, header);
  }
  return data as T;
}

/** One physical book (e.g. First Flight) inside a subject group. */
export interface SubjectBook {
  subject_code: string;
  label: string;
  grade: number;
  chapters: number;
  board_units: number;
  book_loaded: boolean;
  chunks: number;
  chunks_embedded: number;
}

/** A real single-paper subject: one book for most subjects, several for English/Hindi.
 * `group_code`/`group_label` are always present; `subject_code`/`label` mirror them
 * (back-compat for a one-book group, where group and book are the same thing). Submit
 * `group_code` as an Assessment's subject_code -- /place resolves it back to every book. */
export interface Subject extends SubjectBook {
  group_code: string;
  group_label: string;
  books: SubjectBook[];
}

export interface ScanResult {
  route: "text" | "vision";
  pages: number;
  questions: number;
  sub_parts: number;
  choice_alternatives: number;
  context_stems: number;
  total_marks: number;
  staged: number;
  already_promoted: number;
  declared: {
    questions: number | null;
    sections: Record<string, number> | null;
    total_marks: number | null;
  };
  problems: string[];
}

export interface MappedTo {
  chapter: string | null;
  curriculum_section: string | null;
  /** The book's own heading for that section. */
  topic: string | null;
  concept_family: string | null;
  board_unit: string | null;
  /** 'R&U' | 'AP' | 'AEC', or null when nothing has worked it out yet. */
  tier: string | null;
  tier_label: string | null;
  /** The latest placement's own verdict on itself -- a family the reading could not
   *  settle, or a chapter move that left the family unable to place it. */
  needs_review: boolean;
  review_reason: string | null;
}

export interface StagedQuestion {
  address: string;
  edited_by?: string | null;
  section: string | null;
  question_no: string;
  sub_part: string | null;
  choice_alt: string | null;
  max_marks: number | null;
  /** The shared stem of a question whose sub-parts carry the marks. Worth nothing itself. */
  is_context: boolean;
  stem_text: string | null;
  page: number | null;
  mapped_to: MappedTo | null;
  blocked_reason: string | null;
}

export interface ScanReview {
  assessment_id: string;
  route: string;
  staged: number;
  confirmed_at: string | null;
  confirmed_by: string | null;
  edited: number;
  mapped: number;
  /** A classify pass has actually run on this paper -- true even if every question came
   *  back abstained, so it tells "never classified" apart from "classified, nothing
   *  settled" without re-running anything to find out. */
  classified: boolean;
  marks_missing: number;
  /** What was read, against what the paper says it is worth. */
  marks: { read: number; declared: number | null; short_by: number | null };
  /** What the paper's own cover/instructions page states about itself, read once at scan
   *  time and stored on the assessment -- so reopening a paper can show these again. */
  declared: {
    questions: number | null;
    sections: Record<string, number> | null;
    total_marks: number | null;
  };
  questions: StagedQuestion[];
}

export interface ReviewChapterOption {
  code: string;
  label: string;
}

export interface ReviewQuestion {
  question_id: string;
  address: string;
  question_no: string;
  marks: number;
  stem: string;
  proposed_chapter: string | null;
  proposed_chapter_code: string | null;
  curriculum_section: string | null;
  /** 'R&U' | 'AP' | 'AEC', or null when nothing settled it. */
  tier: string | null;
  tier_label: string | null;
  confidence: number;
  source: string;
  reasoning: string | null;
  evidence: string[];
}

export interface ReviewQueue {
  assessment_id: string;
  total_placed: number;
  pending: number;
  questions: ReviewQuestion[];
  /** This paper's own subject chapters -- what a settled question can be filed under. */
  chapters: ReviewChapterOption[];
}

export interface DocumentSummary {
  document_id: string;
  kind: "question_paper" | "answer_sheet" | "mark_grid";
  assessment_id: string;
  student_id: string | null;
  page_count: number;
  sha256: string;
  uploaded_by: string;
  uploaded_at: string | null;
  confirmed_at: string | null;
  confirmed_by: string | null;
  pages: { index: number; content_type: string; byte_size: number; url: string }[];
}

export interface ConfirmResult {
  confirmed_at: string;
  confirmed_by: string;
  questions: number;
  edited: number;
  total_marks: number;
}

export interface MapResult {
  retrieval: string;
  mapped: number;
  blocked: number;
  blocked_addresses: string[];
  needs_review: number;
  with_topic: number;
  context_stems: number;
}

export interface Spend {
  model: string;
  effort: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  passages_shown: number;
  chapters_shown: number;
}

export interface PlaceResult {
  placed: number;
  /** Questions whose chapter, topic and sub-topic the judge settled on the question. */
  labelled: number;
  unsettled_family: number;
  family_refused: number;
  /** How many came back with a category. The rest abstained. */
  tiers: number;
  needs_review: number;
  note: string | null;
  grounding_violations: { question: string; problems: string[] }[];
  /** What the run actually spent, read back off the responses rather than estimated. */
  spend: Spend;
}

export interface ProbeRow {
  q: string;
  expected: string | null;
  retrieved: string | null;
  hit: boolean | null;
  nearest: string | null;
  similarity: number;
  familiarity: string | null;
  why: string;
  margin: number;
  agreed: boolean;
  confident: boolean;
  runners_up: { reference: string; chapter: string; similarity: number }[];
}

export interface ProbeResult {
  mode: string;
  confident: number;
  chunks: number;
  embedded: number;
  graded: number;
  hits: number;
  rows: ProbeRow[];
  note: string;
}

export const api = {
  classes: () => request<ClassOption[]>("/t/classes"),

  onboard: (classCode: string, body: OnboardingIn) =>
    request<OnboardingOut>(`/t/${classCode}/onboard`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  startSession: (classCode: string, body: Record<string, unknown>) =>
    request<SessionPayload>(`/t/${classCode}/start`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  saveResponses: (
    sessionId: string,
    responses: { item_id: string; value: number; shown_at: number; answered_at: number }[],
  ) =>
    request<{ saved: number; answered: number; total_items: number }>(
      `/t/session/${sessionId}/responses`,
      { method: "POST", body: JSON.stringify({ responses }) },
    ),

  complete: (sessionId: string) =>
    request<{ message: string; submitted: number }>(`/t/session/${sessionId}/complete`, {
      method: "POST",
    }),

  // --- dashboard ---
  whoami: (key: string) =>
    authed<{
      name: string;
      state: string | null;
      school_id: string;
      role: "principal" | "admin" | "teacher";
      scope: "all_schools" | "one_school";
      can: {
        read_results: boolean;
        scan_papers: boolean;
        enter_marks: boolean;
        manage_roster: boolean;
        manage_schools: boolean;
      };
      /** Only present for a teacher key. */
      assignments?: TeacherAssignment[];
      /** Only present for a teacher key: the exam cell, the server's own fact. */
      exam_cell?: boolean;
    }>("/admin/me", key),

  overview: (key: string) => authed<Overview>("/admin/overview", key),

  dashboard: (key: string) => authed<Dashboard>("/admin/dashboard", key),

  /** Every class, its status split and its average score -- derived from real marks. */
  academicsOverview: (key: string) => authed<AcademicsOverview>("/admin/academics", key),

  /** The same overview table as a real .xlsx file, principal/admin only. */
  academicsOverviewXlsx: (key: string) => authedBlob("/admin/academics/overview.xlsx", key),

  /** The same overview table as a real PDF file. */
  academicsOverviewPdf: (key: string) => authedBlob("/admin/academics/overview.pdf", key),

  /** Every student in one class -- status, avg score, weakest chapter -- optionally
   * narrowed to one subject, one test, one status band, or the top N scorers. `top` is
   * applied server-side so a screen and its downloads can never disagree about which
   * students "top scorers" means. */
  classStudents: (
    key: string, sectionId: string,
    filters?: { subjectCode?: string; assessmentId?: string; status?: AcademicStatus; top?: number },
  ) =>
    authed<ClassStudentsView>(
      `/admin/academics/${sectionId}/students${qs({
        subject_code: filters?.subjectCode, assessment_id: filters?.assessmentId, status: filters?.status,
        top: filters?.top?.toString(),
      })}`,
      key,
    ),

  classStudentsXlsx: (
    key: string, sectionId: string,
    filters?: { subjectCode?: string; assessmentId?: string; status?: AcademicStatus; top?: number },
  ) =>
    authedBlob(
      `/admin/academics/${sectionId}/students.xlsx${qs({
        subject_code: filters?.subjectCode, assessment_id: filters?.assessmentId, status: filters?.status,
        top: filters?.top?.toString(),
      })}`,
      key,
    ),

  classStudentsPdf: (
    key: string, sectionId: string,
    filters?: { subjectCode?: string; assessmentId?: string; status?: AcademicStatus; top?: number },
  ) =>
    authedBlob(
      `/admin/academics/${sectionId}/students.pdf${qs({
        subject_code: filters?.subjectCode, assessment_id: filters?.assessmentId, status: filters?.status,
        top: filters?.top?.toString(),
      })}`,
      key,
    ),

  /** One student, every subject they have marks in. */
  studentAcademics: (key: string, studentId: string) =>
    authed<StudentAcademicsOverview>(`/admin/academics/students/${studentId}`, key),

  studentAcademicsXlsx: (key: string, studentId: string, subjectCode?: string) =>
    authedBlob(`/admin/academics/students/${studentId}.xlsx${qs({ subject_code: subjectCode })}`, key),

  studentAcademicsPdf: (key: string, studentId: string, subjectCode?: string) =>
    authedBlob(`/admin/academics/students/${studentId}.pdf${qs({ subject_code: subjectCode })}`, key),

  /** One student, one subject: chapter-wise and tier-wise findings. */
  studentSubjectBreakdown: (key: string, studentId: string, subjectCode: string) =>
    authed<StudentSubjectBreakdown>(`/admin/academics/students/${studentId}/subjects/${subjectCode}`, key),

  studentSubjectXlsx: (key: string, studentId: string, subjectCode: string) =>
    authedBlob(`/admin/academics/students/${studentId}/subjects/${subjectCode}.xlsx`, key),

  studentSubjectPdf: (key: string, studentId: string, subjectCode: string) =>
    authedBlob(`/admin/academics/students/${studentId}/subjects/${subjectCode}.pdf`, key),

  /** The BoardX v2 one-page report for one student, one paper. */
  studentBoardX: (key: string, studentId: string, assessmentId: string) =>
    authed<BoardXReport>(`/reports/student/${studentId}/boardx${qs({ assessment_id: assessmentId })}`, key),

  studentBoardXPdf: (key: string, studentId: string, assessmentId: string) =>
    authedBlob(`/reports/student/${studentId}/boardx.pdf${qs({ assessment_id: assessmentId })}`, key),

  /** Every paper with at least one resolved mark -- the Test tab's own list. */
  academicsTests: (key: string) => authed<{ tests: AcademicTestRow[] }>("/admin/academics/tests", key),

  /** Upcoming, awaiting-marks and conducted exam days. */
  exams: (key: string) => authed<ExamsOverview>("/admin/exams", key),

  /** Schedule an exam day for a real date; papers are attached to it later. */
  createExam: (key: string, body: { name: string; scheduled_date: string }) =>
    authed<ExamSummary>("/admin/exams", key, { method: "POST", body: JSON.stringify(body) }),

  attachExamPaper: (key: string, examId: string, assessmentId: string) =>
    authed<ExamSummary>(`/admin/exams/${examId}/papers`, key, {
      method: "POST",
      body: JSON.stringify({ assessment_id: assessmentId }),
    }),

  academicsTestsXlsx: (key: string) => authedBlob("/admin/academics/tests.xlsx", key),

  academicsTestsPdf: (key: string) => authedBlob("/admin/academics/tests.pdf", key),

  /** One test's own student-by-student summary. */
  testSummary: (key: string, assessmentId: string) =>
    authed<TestSummary>(`/admin/academics/tests/${assessmentId}`, key),

  testSummaryXlsx: (key: string, assessmentId: string) =>
    authedBlob(`/admin/academics/tests/${assessmentId}.xlsx`, key),

  testSummaryPdf: (key: string, assessmentId: string) =>
    authedBlob(`/admin/academics/tests/${assessmentId}.pdf`, key),

  /** The subjects this deployment carries. Never a list written into a screen. */
  subjects: (key: string) => authed<{ subjects: Subject[] }>("/admin/subjects", key),

  roster: (key: string, sectionId: string) =>
    authed<{ section: { id: string; label: string; student_path: string }; students: RosterRow[] }>(
      `/admin/sections/${sectionId}/students`,
      key,
    ),

  /** Who else can act on this school -- read-only, never the key secret itself. */
  listStaff: (key: string) => authed<SchoolStaffRow[]>("/admin/staff", key),

  cohort: (key: string, sectionId: string) =>
    authed<{ holland: Record<string, number>; streams: Record<string, number>; counted: number; withheld: number }>(
      `/admin/cohort/${sectionId}`,
      key,
    ),

  /** Add a student to the roster by hand -- self-registration via the class link is
   * still the normal path; this is for a correction or a student who has not sat it. */
  createStudent: (
    key: string,
    sectionId: string,
    body: { name: string; roll_no: string; age?: number; gender?: string; dob?: string },
  ) =>
    authed<{ student_id: string; name: string; roll_no: string }>(
      `/admin/sections/${sectionId}/students`, key, { method: "POST", body: JSON.stringify(body) },
    ),

  /** Every field optional -- send only what changed. */
  updateStudent: (
    key: string,
    studentId: string,
    body: { name?: string; roll_no?: string; age?: number; gender?: string; dob?: string },
  ) =>
    authed<{ student_id: string; changed: string[] }>(`/admin/students/${studentId}`, key, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  /** Hard delete: the student and every test session, mark and script that names them. */
  deleteStudent: (key: string, studentId: string) =>
    authed<void>(`/admin/students/${studentId}`, key, { method: "DELETE" }),

  // --- teachers (principal-scoped management; teacher-scoped reads) ---

  /** Every teacher key issued for this school, with their assignments. Principal/admin. */
  listTeachers: (key: string) => authed<TeacherKeyView[]>("/admin/teachers", key),

  /** Issue a teacher key -- the raw key comes back once, same as every other credential
   * this deployment issues. */
  createTeacher: (
    key: string,
    body: { label: string; assignments: TeacherAssignmentSpec[] },
  ) =>
    authed<TeacherKeyView & IssuedKey>("/admin/teachers", key, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  addTeacherAssignment: (key: string, teacherKeyId: string, spec: TeacherAssignmentSpec) =>
    authed<TeacherKeyView>(`/admin/teachers/${teacherKeyId}/assignments`, key, {
      method: "POST",
      body: JSON.stringify(spec),
    }),

  removeTeacherAssignment: (key: string, teacherKeyId: string, assignmentId: string) =>
    authed<void>(`/admin/teachers/${teacherKeyId}/assignments/${assignmentId}`, key, {
      method: "DELETE",
    }),

  revokeTeacher: (key: string, teacherKeyId: string) =>
    authed<TeacherKeyView>(`/admin/teachers/${teacherKeyId}/revoke`, key, { method: "POST" }),

  /** Rename a teacher. Touches only the label -- their key and assignments are untouched. */
  renameTeacher: (key: string, teacherKeyId: string, label: string) =>
    authed<TeacherKeyView>(`/admin/teachers/${teacherKeyId}`, key, {
      method: "PATCH",
      body: JSON.stringify({ label }),
    }),

  /** Replace a teacher's key with a fresh one, keeping their assignments. The old key
   * stops working the instant this returns; the new raw key comes back once, same as
   * createTeacher. Refused for an already-revoked key. */
  reissueTeacherKey: (key: string, teacherKeyId: string) =>
    authed<TeacherKeyView & IssuedKey>(`/admin/teachers/${teacherKeyId}/reissue`, key, {
      method: "POST",
    }),

  /** Every section a teacher key may open, with what it may do there. */
  teacherSections: (key: string) =>
    authed<{ sections: TeacherSectionSummary[] }>("/admin/teacher/sections", key),

  /** The roster for one class -- refused with 404 unless this teacher key holds a class
   * or subject assignment there, same shape as `roster` above. */
  teacherRoster: (key: string, sectionId: string) =>
    authed<{ section: { id: string; label: string; student_path: string }; students: RosterRow[] }>(
      `/admin/teacher/sections/${sectionId}/students`,
      key,
    ),

  teacherCohort: (key: string, sectionId: string) =>
    authed<{ holland: Record<string, number>; streams: Record<string, number>; counted: number; withheld: number }>(
      `/admin/teacher/cohort/${sectionId}`,
      key,
    ),

  // --- teacher-scoped academics: the same Overview/Test drill-down a principal gets,
  // narrowed to exactly this key's own class/subject assignments ---

  teacherAcademicsOverview: (key: string) =>
    authed<{ classes: TeacherAcademicClassRow[] }>("/admin/teacher/academics", key),

  teacherAcademicsStudents: (key: string, sectionId: string, filters?: { subjectCode?: string; assessmentId?: string; status?: AcademicStatus }) =>
    authed<{
      section: { id: string; label: string };
      subject_code: string | null;
      previous_test: { assessment_id: string; title: string } | null;
      students: ClassStudentRow[];
    }>(
      `/admin/teacher/academics/${sectionId}/students${qs({
        subject_code: filters?.subjectCode, assessment_id: filters?.assessmentId, status: filters?.status,
      })}`,
      key,
    ),

  teacherAcademicsStudentsCsv: (key: string, sectionId: string, filters?: { subjectCode?: string; assessmentId?: string; status?: AcademicStatus }) =>
    authedBlob(
      `/admin/teacher/academics/${sectionId}/students.csv${qs({
        subject_code: filters?.subjectCode, assessment_id: filters?.assessmentId, status: filters?.status,
      })}`,
      key,
    ),

  teacherAcademicsTests: (key: string) =>
    authed<{ tests: AcademicTestRow[] }>("/admin/teacher/academics/tests", key),

  teacherAcademicsTestSummary: (key: string, assessmentId: string) =>
    authed<TestSummary>(`/admin/teacher/academics/tests/${assessmentId}`, key),

  teacherAcademicsTestSummaryCsv: (key: string, assessmentId: string) =>
    authedBlob(`/admin/teacher/academics/tests/${assessmentId}.csv`, key),

  /** The already-graded, read-only per-question marks grid for one section on one
   *  paper -- real awarded marks, real chapter/concept_family names for a legend,
   *  and a real total. `fully_marked` says whether every student has every question
   *  resolved, the signal a caller uses to decide whether to show this grid at all. */
  teacherMarksGrid: (key: string, sectionId: string, assessmentId: string) =>
    authed<MarksGridReport>(`/admin/teacher/academics/${sectionId}/tests/${assessmentId}/marks-grid`, key),

  // --- teacher-scoped student detail + BoardX drill-down: the same cross-subject
  // overview, chapter/tier breakdown and BoardX one-pager a principal gets, narrowed
  // to exactly the subjects this teacher key's own assignments cover ---

  teacherStudentAcademics: (key: string, studentId: string, subjectCode?: string) =>
    authed<StudentAcademicsOverview>(
      `/admin/teacher/academics/students/${studentId}${qs({ subject_code: subjectCode })}`, key,
    ),

  teacherStudentAcademicsCsv: (key: string, studentId: string, subjectCode?: string) =>
    authedBlob(
      `/admin/teacher/academics/students/${studentId}.csv${qs({ subject_code: subjectCode })}`, key,
    ),

  teacherStudentSubjectBreakdown: (key: string, studentId: string, subjectCode: string) =>
    authed<StudentSubjectBreakdown>(
      `/admin/teacher/academics/students/${studentId}/subjects/${subjectCode}`, key,
    ),

  teacherStudentSubjectCsv: (key: string, studentId: string, subjectCode: string) =>
    authedBlob(`/admin/teacher/academics/students/${studentId}/subjects/${subjectCode}.csv`, key),

  teacherStudentBoardX: (key: string, studentId: string, assessmentId: string) =>
    authed<BoardXReport>(
      `/admin/teacher/academics/students/${studentId}/boardx${qs({ assessment_id: assessmentId })}`, key,
    ),

  /** Every paper this teacher key may author -- narrowed to the subjects it holds a
   *  subject assignment for. Same row shape as listPapers(); every mutation on one of
   *  these papers (create/scan/map/etc) goes through the same /assessments/... routes
   *  listPapers' own results point at -- the scoping is enforced server-side on those
   *  routes, not by this list being narrower. */
  teacherPapers: (key: string) =>
    authed<{ assessments: PaperSummary[] }>("/admin/teacher/papers", key),

  // --- sharing a report with the student it belongs to ---

  /** Every report issued for a student -- the list a "Share" picker is built from. */
  studentIssuedReports: (key: string, studentId: string) =>
    authed<{ reports: IssuedReportRow[] }>(`/admin/teacher/students/${studentId}/reports`, key),

  /** Issue a fresh PIN for one report and mark it shared -- the PIN, class code and
   * roll number are all shown once, on this response only. Re-sharing an already-shared
   * report replaces its PIN rather than failing. */
  shareReport: (key: string, reportId: string, by: string) =>
    authed<SharedReportView>(`/admin/teacher/reports/${reportId}/share`, key, {
      method: "POST",
      body: JSON.stringify({ by }),
    }),

  /** Take a report back. The PIN already handed out stops working immediately. */
  unshareReport: (key: string, reportId: string) =>
    authed<IssuedReportRow>(`/admin/teacher/reports/${reportId}/unshare`, key, { method: "POST" }),

  // --- the student portal itself (no staff key; a session token instead) ---

  /** Roll number + PIN, traded for a session token. `classCode` is the same code the
   * interest-test class picker uses (a Section's id). */
  studentLogin: (classCode: string, rollNo: string, pin: string) =>
    request<StudentLoginResult>(`/student/${classCode}/login`, {
      method: "POST",
      body: JSON.stringify({ roll_no: rollNo, pin }),
    }),

  /** Every report currently shared with the signed-in student. */
  studentReports: (sessionToken: string) =>
    studentAuthed<{ student_name: string; reports: StudentReportRow[] }>("/student/reports", sessionToken),

  /** One shared report's full payload. */
  studentReport: (sessionToken: string, reportId: string) =>
    studentAuthed<StudentReportDetail>(`/student/reports/${reportId}`, sessionToken),

  studentLogout: (sessionToken: string) =>
    studentAuthed<{ ok: boolean }>("/student/logout", sessionToken, { method: "POST" }),

  // --- operator console ---
  platformWhoami: (key: string) => operator<{ role: string }>("/platform/me", key),

  listSchools: (key: string) => operator<PlatformSchool[]>("/platform/schools", key),

  /** Every school's counts on one screen -- students, papers, answer scripts, issued
   * reports and active staff keys, summed and broken down per school. */
  platformOverview: (key: string) => operator<PlatformOverview>("/platform/overview", key),

  createSchool: (
    key: string,
    body: {
      name: string;
      board: string;
      state: string;
      training_consent: string;
      sections: { grade: number; name: string }[];
    },
  ) =>
    operator<PlatformSchool & IssuedKey>("/platform/schools", key, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Show or hide a school's classes on the public /t/classes directory. */
  setDirectoryVisibility: (key: string, schoolId: string, hidden: boolean) =>
    operator<PlatformSchool>(`/platform/schools/${schoolId}/directory-visibility`, key, {
      method: "PATCH",
      body: JSON.stringify({ hidden }),
    }),

  addSection: (key: string, schoolId: string, section: { grade: number; name: string }) =>
    operator<PlatformSection>(`/platform/schools/${schoolId}/sections`, key, {
      method: "POST",
      body: JSON.stringify(section),
    }),

  listAdminKeys: (key: string) => operator<StaffKeySummary[]>("/platform/keys", key),

  issueAdminKey: (key: string, label: string) =>
    operator<StaffKeySummary & IssuedKey>("/platform/keys", key, {
      method: "POST",
      body: JSON.stringify({ role: "admin", label }),
    }),

  revokeAdminKey: (key: string, keyId: string) =>
    operator<StaffKeySummary>(`/platform/keys/${keyId}/revoke`, key, { method: "POST" }),

  listStaffKeys: (key: string, schoolId: string) =>
    operator<StaffKeySummary[]>(`/platform/schools/${schoolId}/keys`, key),

  issueStaffKey: (key: string, schoolId: string, role: string, label: string, examCell = false) =>
    operator<StaffKeySummary & IssuedKey>(`/platform/schools/${schoolId}/keys`, key, {
      method: "POST",
      body: JSON.stringify({ role, label, exam_cell: examCell }),
    }),

  revokeStaffKey: (key: string, schoolId: string, keyId: string) =>
    operator<{ id: string; revoked_at: string }>(
      `/platform/schools/${schoolId}/keys/${keyId}/revoke`, key, { method: "POST" },
    ),

  rotateKey: (key: string, schoolId: string) =>
    operator<IssuedKey & { school_id: string; name: string }>(
      `/platform/schools/${schoolId}/rotate-key`,
      key,
      { method: "POST" },
    ),

  /** One school's full detail view -- School details / Overview tabs. */
  getSchool: (key: string, schoolId: string) =>
    operator<PlatformSchool>(`/platform/schools/${schoolId}`, key),

  /** The School details tab's save action. Only the fields present are changed. */
  patchSchool: (key: string, schoolId: string, patch: SchoolPatch) =>
    operator<PlatformSchool>(`/platform/schools/${schoolId}`, key, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  /** Contact-detail edit for a principal or teacher key -- Principal/Teachers tabs. */
  patchStaffKey: (
    key: string,
    schoolId: string,
    keyId: string,
    patch: { name?: string; email?: string; phone?: string; label?: string },
  ) =>
    operator<StaffKeySummary>(`/platform/schools/${schoolId}/keys/${keyId}`, key, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  /** A teacher key's class/subject assignments. */
  listAssignments: (key: string, schoolId: string, keyId: string) =>
    operator<TeacherAssignmentRow[]>(
      `/platform/schools/${schoolId}/keys/${keyId}/assignments`, key,
    ),

  /** Replaces a teacher key's full assignment set with exactly the list given. */
  setAssignments: (
    key: string, schoolId: string, keyId: string, assignments: TeacherAssignmentInput[],
  ) =>
    operator<TeacherAssignmentRow[]>(
      `/platform/schools/${schoolId}/keys/${keyId}/assignments`, key,
      { method: "PATCH", body: JSON.stringify({ assignments }) },
    ),

  /** The full student roster across every section -- the Students tab. */
  listPlatformStudents: (key: string, schoolId: string) =>
    operator<PlatformStudentRow[]>(`/platform/schools/${schoolId}/students`, key),

  /** Add several students at once. */
  bulkAddStudents: (key: string, schoolId: string, students: StudentBulkInput[]) =>
    operator<PlatformStudentRow[]>(`/platform/schools/${schoolId}/students/bulk`, key, {
      method: "POST",
      body: JSON.stringify({ students }),
    }),

  /** Recent actions taken on this school through the ops console -- the Activity tab. */
  listActivity: (key: string, schoolId: string) =>
    operator<AuditLogRow[]>(`/platform/schools/${schoolId}/activity`, key),

  // --- knowledge base ---
  /** The subjects this deployment carries -- platform-scoped, so a bare operator key
   * with no school yet created can still populate this screen's own dropdown. Not
   * `admin.subjects`: that route needs `current_staff` (a real school's key), which a
   * platform key was quietly locked out of by an unrelated fix, breaking that route for
   * this exact screen. */
  platformSubjects: (key: string) =>
    operator<{ subjects: Subject[] }>("/platform/books", key),

  bookStatus: (key: string, subject: string) =>
    operator<BookStatus>(`/platform/books/${subject}`, key),

  /** What families the loaded book's own section headings suggest. */
  proposeFamilies: (key: string, subject: string) =>
    operator<FamilyProposals>(`/platform/books/${subject}/concept-families`, key),

  /** One paid read of every loaded chapter, proposing its families. 409 when a run is
   *  already stored -- read those instead of paying again. */
  proposeFamiliesWithModel: (key: string, subject: string) =>
    operator<{ proposed: number; chapters_read: number; failed: { chapter: string; error: string }[]; warning?: string | null }>(
      `/platform/books/${subject}/concept-families/propose-llm`, key, { method: "POST" },
    ),

  createFamilies: (key: string, subject: string, families: FamilyProposal[]) =>
    operator<{
      created: number;
      already_existed: number;
      unknown_chapters: string[];
      wrong_subject: string[];
    }>(
      `/platform/books/${subject}/concept-families`,
      key,
      { method: "POST", body: JSON.stringify({ families }) },
    ),

  setupCurriculum: (key: string, subject: string) =>
    operator<{ label: string; board_units: number; chapters: number; next: string }>(
      `/platform/books/${subject}/curriculum`, key, { method: "POST" },
    ),

  /** Families under this subject that should not be there: filed under the wrong chapter,
   *  a Hindi/Tamil label with no slug, or -- the "Trigonometry" / "Trig" / "Trigo" case --
   *  two families under one chapter that are the same idea by two different names. Read-only. */
  auditFamilies: (key: string, subject: string) =>
    operator<FamilyAudit>(`/platform/books/${subject}/concept-families/audit`, key),

  /** Removes the wrong-subject and empty-code families the audit found (never a
   *  duplicate -- which one survives a duplicate pair is a person's call, made with
   *  mergeFamilies instead). */
  applyFamilyAudit: (key: string, subject: string) =>
    operator<{ subject: string; removed: number; duplicates_left_for_review: number; next: string }>(
      `/platform/books/${subject}/concept-families/audit/apply`, key, { method: "POST" },
    ),

  /** Folds `remove` into `keep`: every question, placement and proposal on a removed
   *  family is re-pointed at `keep` before it is deleted, so no mark is lost. */
  mergeFamilies: (key: string, subject: string, keep: string, remove: string[]) =>
    operator<{ kept: string; removed: string[]; questions_moved: number; placements_moved: number; next: string }>(
      `/platform/books/${subject}/concept-families/merge`,
      key,
      { method: "POST", body: JSON.stringify({ keep, remove }) },
    ),

  // --- question papers ---
  createAssessment: (key: string, body: Record<string, unknown>) =>
    authed<{ assessment_id: string; status: string }>("/assessments", key, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Rename a paper, or correct its code / total marks. Refused once its scan is confirmed. */
  editAssessment: (
    key: string,
    assessmentId: string,
    body: { title?: string; paper_code?: string; total_marks?: number },
  ) =>
    authed<{ assessment_id: string; changed: string[] }>(`/assessments/${assessmentId}`, key, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  /** Removes the paper and everything staged, scanned, mapped or marked under it. */
  deleteAssessment: (key: string, assessmentId: string) =>
    authed<void>(`/assessments/${assessmentId}`, key, { method: "DELETE" }),

  /** Removes one scanned document -- a question paper or an answer script -- and its pages. */
  deleteDocument: (key: string, documentId: string) =>
    authed<void>(`/documents/${documentId}`, key, { method: "DELETE" }),

  /** Every scanned document kept for this paper (its own upload, plus every student's
   * answer script if student_id is left off) -- one document per (assessment, kind,
   * student) at most, since a re-upload replaces rather than adds. */
  listDocuments: (key: string, assessmentId: string, studentId?: string) =>
    authed<{ documents: DocumentSummary[] }>(
      `/assessments/${assessmentId}/documents${studentId ? `?student_id=${studentId}` : ""}`,
      key,
    ),

  /** One page or many, PDFs or photographs, in the order given. onJobQueued fires the
   * instant a vision read is queued (202 + job_id) -- pass it to persist the id
   * somewhere durable before polling starts, so a lost connection can resume watching
   * that job instead of resubmitting the pages as a second, separately-billed read. */
  scanPaper: (key: string, assessmentId: string, files: File[], onJobQueued?: (jobId: string) => void) =>
    uploadMany<ScanResult>(
      `/assessments/${assessmentId}/scan`, key, files, "X-API-Key",
      // A scanned/photographed paper (no text layer) needs a vision call and can run
      // past Render's request timeout, so that case answers 202 with a job to poll --
      // a text-layer PDF still returns its result directly, no polling.
      `/assessments/${assessmentId}/scan`,
      onJobQueued,
    ),

  /** Resume watching a scan job already queued on the server -- no files to send, it
   * already has them. Use this instead of scanPaper() whenever a job_id from an earlier
   * onJobQueued is on hand: re-uploading would queue a second, wasted vision read for
   * work the server is already doing or has already finished. */
  resumeScanJob: (key: string, assessmentId: string, jobId: string) =>
    pollJob<ScanResult>(`/assessments/${assessmentId}/scan`, key, jobId, "X-API-Key"),

  readScan: (key: string, assessmentId: string) =>
    authed<ScanReview>(`/assessments/${assessmentId}/scan`, key),

  /** The questions a person still has to settle, with what the machine had to go on --
   *  and the real chapters (code + label) of this paper's own subject, to settle one
   *  into. */
  reviewQueue: (key: string, assessmentId: string) =>
    authed<ReviewQueue>(`/assessments/${assessmentId}/review`, key),

  /** A person settles one question's chapter/section/tier. Recorded as a new placement,
   *  never an edit -- the machine's attempt stays in the history. */
  settleReview: (
    key: string,
    assessmentId: string,
    questionId: string,
    body: { chapter_code: string; curriculum_section?: string | null; tier?: string | null; reviewed_by: string },
  ) =>
    authed<{ question_id: string; chapter: string; remaining: number }>(
      `/assessments/${assessmentId}/review/${questionId}`,
      key,
      { method: "POST", body: JSON.stringify(body) },
    ),

  editScanned: (
    key: string,
    assessmentId: string,
    address: string,
    body: Record<string, unknown>,
  ) =>
    authed<{ address: string; changed?: string[]; removed?: boolean }>(
      `/assessments/${assessmentId}/scan/${encodeURIComponent(address)}`,
      key,
      { method: "PATCH", body: JSON.stringify(body) },
    ),

  confirmScan: (key: string, assessmentId: string, by: string) =>
    authed<ConfirmResult>(`/assessments/${assessmentId}/scan/confirm`, key, {
      method: "POST",
      body: JSON.stringify({ by }),
    }),

  mapPaper: (key: string, assessmentId: string) =>
    authed<MapResult>(`/assessments/${assessmentId}/map`, key, { method: "POST" }),

  /** The judge reads the passages retrieval found and settles chapter, topic, sub-topic
   *  and the cognitive category. Needs the classifier key on the API service.
   *
   *  A call per question -- around forty for an ordinary paper -- so this always answers
   *  202 with a job to poll rather than the result directly: the sum of those calls runs
   *  past a reverse proxy's request timeout long before the model itself is done, the same
   *  reason scanPaper() and uploadGridSheet() poll instead of blocking. onJobQueued fires
   *  the instant it's queued, for the same reason scanPaper's does: so a lost connection
   *  resumes watching the job already running server-side, rather than reclassifying the
   *  whole paper a second time. */
  placePaper: (key: string, assessmentId: string, onJobQueued?: (jobId: string) => void) =>
    postAndPoll<PlaceResult>(`/assessments/${assessmentId}/place`, key, onJobQueued),

  /** Resume watching a placement job already queued on the server -- see resumeScanJob. */
  resumePlacementJob: (key: string, assessmentId: string, jobId: string) =>
    pollJob<PlaceResult>(`/assessments/${assessmentId}/place`, key, jobId, "X-API-Key"),

  uploadContents: (key: string, subject: string, file: File, edition: string) =>
    upload<{ chapters_expected: number; sections_expected: number; next: string }>(
      `/platform/books/${subject}/contents?edition=${encodeURIComponent(edition)}`, key, file,
    ),

  uploadChapter: (key: string, subject: string, file: File, locateKnownSections = false) =>
    upload<{ chapter: number; title: string; sections: number; chunks: number; board_unit_mapped: boolean }>(
      `/platform/books/${subject}/chapters` + (locateKnownSections ? "?locate_known_sections=true" : ""),
      key, file,
    ),

  embedBatch: (key: string, subject: string) =>
    operator<{ embedded: number; remaining: number; done: boolean }>(
      `/platform/books/${subject}/embed`, key, { method: "POST" },
    ),

  probe: (
    key: string,
    subject: string,
    questions: { q: string; stem: string; chapter?: string }[],
  ) =>
    operator<ProbeResult>(`/platform/books/${subject}/probe`, key, {
      method: "POST",
      body: JSON.stringify({ questions }),
    }),

  listPapers: (key: string) =>
    authed<{ assessments: PaperSummary[] }>("/assessments", key),

  answerSheet: (key: string, assessmentId: string, studentId: string) =>
    authed<AnswerSheet>(`/assessments/${assessmentId}/answers/${studentId}`, key),

  confirmAnswers: (
    key: string,
    assessmentId: string,
    studentId: string,
    answers: { address: string; marks?: number | null; state?: string }[],
    by: string,
  ) =>
    authed<ConfirmAnswersResult>(
      `/assessments/${assessmentId}/answers/${studentId}/confirm`,
      key,
      { method: "POST", body: JSON.stringify({ answers, by }) },
    ),

  readMarksFile: async (
    key: string, assessmentId: string, studentId: string, files: File[],
  ) => {
    const body = new FormData();
    // The field name repeats rather than being indexed: that is what FastAPI reads as a
    // list, and the order of appends is the page order the server keeps.
    for (const file of files) body.append("files", file);
    const res = await fetch(
      `${BASE}/assessments/${assessmentId}/answers/${studentId}/read`,
      { method: "POST", headers: { "X-API-Key": key, ...scopeHeader() }, body },
    );
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return (await res.json()) as ReadResult;
  },

  reading: (key: string, assessmentId: string, studentId: string) =>
    authed<ReadingSheet>(`/assessments/${assessmentId}/answers/${studentId}/reading`, key),

  editReading: (
    key: string, assessmentId: string, studentId: string, address: string,
    body: { marks: number | null; state: string; by: string },
  ) =>
    authed<ReadingSheet>(
      `/assessments/${assessmentId}/answers/${studentId}/reading/${address}`,
      key,
      { method: "PATCH", body: JSON.stringify(body) },
    ),

  confirmReading: (key: string, assessmentId: string, studentId: string, by: string) =>
    authed<{ written: number; confirmed_by: string }>(
      `/assessments/${assessmentId}/answers/${studentId}/reading/confirm`,
      key,
      { method: "POST", body: JSON.stringify({ by }) },
    ),

  confirmClassReading: (key: string, assessmentId: string, sectionId: string, by: string) =>
    authed<{
      confirmed: { student_id: string; name: string }[];
      skipped: { student_id: string; name: string; reason: string }[];
      confirmed_by: string;
    }>(
      `/assessments/${assessmentId}/sections/${sectionId}/reading/confirm-class`,
      key,
      { method: "POST", body: JSON.stringify({ by }) },
    ),

  uploadAnswerPages: (key: string, assessmentId: string, studentId: string, files: File[]) =>
    uploadMany<ScanDoc>(
      `/assessments/${assessmentId}/answers/${studentId}/pages`, key, files, "X-API-Key",
    ),

  /**
   * One stored page, as a blob.
   *
   * Fetched rather than linked: the page endpoint needs the school key, and an <img src>
   * or a plain link sends no headers, so a link would have been an affordance that shows
   * nothing. The caller revokes the object URL when it is done with it.
   */
  pageBlob: async (key: string, url: string): Promise<string> => {
    const res = await fetch(`${BASE}${url}`, { headers: { "X-API-Key": key, ...scopeHeader() } });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return URL.createObjectURL(await res.blob());
  },

  /** An issued report, rendered server-side as an actual PDF file -- something a
   * principal can hand a parent or keep on file. Fetched as a blob, like a page image,
   * because the download needs the school's key on the request. */
  issuedReportPdf: async (key: string, reportId: string): Promise<Blob> => {
    const res = await fetch(`${BASE}/reports/issued/${reportId}/pdf`, {
      headers: { "X-API-Key": key, ...scopeHeader() },
    });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.blob();
  },

  studentDocuments: (key: string, studentId: string) =>
    authed<{ documents: ScanDoc[] }>(`/students/${studentId}/documents`, key),

  uploadGridSheet: (
    key: string, assessmentId: string, sectionId: string, files: File[],
    onJobQueued?: (jobId: string) => void,
  ) =>
    uploadMany<GridUploadResult>(
      `/assessments/${assessmentId}/sections/${sectionId}/gridsheet`, key, files, "X-API-Key",
      // Reading a photo calls a vision model and can run past Render's request timeout,
      // so this endpoint always answers 202 with a job to poll -- never the result directly.
      `/assessments/${assessmentId}/gridsheet`,
      onJobQueued,
    ),

  uploadSingleScript: (
    key: string, assessmentId: string, sectionId: string, files: File[],
    onJobQueued?: (jobId: string) => void,
  ) =>
    uploadMany<GridUploadResult>(
      `/assessments/${assessmentId}/sections/${sectionId}/script`, key, files, "X-API-Key",
      // Same reason as the class photo: a vision call can run past Render's request
      // timeout, so this always answers 202 with a job to poll.
      `/assessments/${assessmentId}/gridsheet`,
      onJobQueued,
    ),

  /** Resume watching a grid-sheet read already queued on the server (GET
   *  .../gridsheet/jobs/{job_id}, the same route uploadGridSheet/uploadSingleScript already
   *  poll internally) -- for a page reload or a lost connection partway through polling,
   *  so it watches the job already running server-side instead of re-uploading the photo
   *  as a second, separately-billed vision read. */
  resumeGridSheetJob: (key: string, assessmentId: string, jobId: string) =>
    pollJob<GridUploadResult>(`/assessments/${assessmentId}/gridsheet`, key, jobId, "X-API-Key"),

  uploadGridSheetFile: (key: string, assessmentId: string, sectionId: string, files: File[]) =>
    uploadMany<GridUploadResult>(
      `/assessments/${assessmentId}/sections/${sectionId}/gridsheet/file`, key, files, "X-API-Key",
      // No vision call for a spreadsheet or a text-layer PDF -- fast enough to answer
      // directly, no job to poll.
    ),

  /** A blank, printable mark-entry sheet for one section of one paper -- built from the
   *  paper's own confirmed questions and the section's own roster, so it can never offer
   *  a column or row this paper/class doesn't really have. Hand it out, collect it filled
   *  in, and read it back with uploadGridSheet/uploadGridSheetFile: the printed column
   *  headers are the same labels that upload already knows how to parse. */
  answerCardPdf: (key: string, assessmentId: string, sectionId: string) =>
    authedBlob(`/assessments/${assessmentId}/sections/${sectionId}/answer-card.pdf`, key),

  gridSheet: (key: string, assessmentId: string, documentId: string) =>
    authed<GridSheetReview>(`/assessments/${assessmentId}/gridsheet/${documentId}`, key),

  resolveGridRow: (
    key: string, assessmentId: string, documentId: string, rowId: string,
    body:
      | { student_id: string }
      | { create: { name: string; roll_no: string; age?: number | null; gender?: string | null; dob?: string | null } },
  ) =>
    authed<{ row_id: string; student_id: string; status: string }>(
      `/assessments/${assessmentId}/gridsheet/${documentId}/rows/${rowId}/resolve`,
      key, { method: "POST", body: JSON.stringify(body) },
    ),

  confirmGridSheet: (key: string, assessmentId: string, documentId: string, by: string) =>
    authed<GridConfirmResult>(
      `/assessments/${assessmentId}/gridsheet/${documentId}/confirm`, key,
      { method: "POST", body: JSON.stringify({ by }) },
    ),

  issueReport: (key: string, studentId: string, assessmentId: string, by: string) =>
    authed<IssuedReport>(`/reports/student/${studentId}/issue`, key, {
      method: "POST",
      body: JSON.stringify({ assessment_id: assessmentId, by }),
    }),

  issuedReports: (key: string, studentId: string) =>
    authed<{ reports: IssuedReport[] }>(`/reports/student/${studentId}/issued`, key),

  studentPapers: (key: string, studentId: string) =>
    authed<{ student: { id: string; name: string; roll_no: string }; assessments: SatPaper[] }>(
      `/reports/student/${studentId}/assessments`,
      key,
    ),

  studentDiagnosis: (key: string, studentId: string, assessmentId: string) =>
    authed<StudentDiagnosis>(
      `/reports/student/${studentId}?assessment_id=${encodeURIComponent(assessmentId)}`,
      key,
    ),

  interestReport: (key: string, studentId: string) =>
    authed<InterestReport>(`/reports/interest/${studentId}`, key),

  // --- board intelligence ---

  paperReport: (key: string, assessmentId: string) =>
    authed<PaperReport>(`/reports/paper/${assessmentId}`, key),

  /** `sectionId` narrows every figure to one class's own students, same real
   *  aggregation as the whole-school read -- see reports.py's own note on cohort_report. */
  cohortReport: (key: string, assessmentId: string, sectionId?: string) =>
    authed<CohortReport>(`/reports/cohort/${assessmentId}${qs({ section_id: sectionId })}`, key),

  /** The same real findings, scoped to one teacher key's own section -- /reports/cohort
   *  refuses every teacher key outright (it has no section/subject filter of its own).
   *  section_id is required here, unlike the principal route's optional one: a teacher's
   *  read is always scoped to one class they actually hold. */
  teacherCohortReport: (key: string, assessmentId: string, sectionId: string) =>
    authed<CohortReport>(`/reports/teacher/cohort/${assessmentId}${qs({ section_id: sectionId })}`, key),

  /** Every concept family's board multiplier/urgency for one subject -- GET /board-frequency.
   *  Used by BoardX to enrich a cohort finding with "X/4 recent years" (years_appeared /
   *  years_eligible), which GET /reports/cohort/{id} itself does not carry per family.
   *  Best-effort: a school whose curriculum_version/stream differ from the defaults below
   *  simply gets no match, and callers fall back to showing the urgency tier alone. */
  boardFrequency: (key: string, subjectCode: string) =>
    authed<{ families: BoardFrequencyRow[] }>(
      `/board-frequency?subject_code=${encodeURIComponent(subjectCode)}`,
      key,
    )
      .then((r) => r.families)
      .catch(() => [] as BoardFrequencyRow[]),
};

export interface BoardFrequencyRow {
  concept_family: string;
  label: string;
  chapter: string | null;
  board_unit: string | null;
  board_weight_pct: number | null;
  multiplier: number;
  urgency: number | null;
  urgency_tier: "VERY HIGH" | "HIGH" | "MEDIUM" | "LOW" | null;
  years_appeared: number;
  years_eligible: number;
  note: string | null;
}
