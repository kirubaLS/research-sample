// Baked in at BUILD time, not read at runtime: changing it on the host requires a fresh
// deploy, not a restart. The localhost fallback is right for a laptop and wrong for every
// deployment, which is why apiBaseIsDefault() exists -- an unset variable in production
// makes the browser ask the *visitor's* machine for the API, and the resulting failure
// looks like a dead backend rather than a missing setting.
import { getActiveSchool } from "@/lib/session";

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

export interface PaperSummary {
  id: string;
  title: string;
  subject_code: string;
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
  message: string | null;
  evidence: Proof[];
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
  created_at: string | null;
  questions_marked: number;
}

export interface DashboardPaper {
  id: string;
  title: string;
  subject_code: string;
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
  school: string;
};

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
  students: number;
  sections: PlatformSection[];
}

/** Only ever returned by create and rotate -- listing carries no key. */
export interface IssuedKey {
  api_key: string;
  api_key_notice: string;
}

export interface StaffKeySummary {
  id: string;
  /** null for an admin key: it belongs to no school, which is what lets it span them. */
  school_id: string | null;
  role: "principal" | "admin";
  label: string;
  created_at: string | null;
  revoked_at: string | null;
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
  next: string;
}

/** Multipart, so it cannot go through `request` -- setting Content-Type by hand drops the
 *  boundary the server needs to parse the body. The header name is a parameter because
 *  the operator surface and the school surface authenticate differently, and hard-coding
 *  one of them here would silently 404 every call from the other. */
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
  return (await res.json()) as T;
}

async function uploadMany<T>(
  path: string,
  key: string,
  files: File[],
  header: "X-Platform-Key" | "X-API-Key",
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
  return (await res.json()) as T;
}

export interface Subject {
  subject_code: string;
  label: string;
  grade: number;
  chapters: number;
  board_units: number;
  book_loaded: boolean;
  chunks: number;
  chunks_embedded: number;
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
  marks_missing: number;
  /** What was read, against what the paper says it is worth. */
  marks: { read: number; declared: number | null; short_by: number | null };
  questions: StagedQuestion[];
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
      role: "principal" | "admin";
      scope: "all_schools" | "one_school";
      can: {
        read_results: boolean;
        scan_papers: boolean;
        enter_marks: boolean;
        manage_roster: boolean;
        manage_schools: boolean;
      };
    }>("/admin/me", key),

  overview: (key: string) => authed<Overview>("/admin/overview", key),

  dashboard: (key: string) => authed<Dashboard>("/admin/dashboard", key),

  /** The subjects this deployment carries. Never a list written into a screen. */
  subjects: (key: string) => authed<{ subjects: Subject[] }>("/admin/subjects", key),

  roster: (key: string, sectionId: string) =>
    authed<{ section: { id: string; label: string; student_path: string }; students: RosterRow[] }>(
      `/admin/sections/${sectionId}/students`,
      key,
    ),

  cohort: (key: string, sectionId: string) =>
    authed<{ holland: Record<string, number>; streams: Record<string, number>; counted: number; withheld: number }>(
      `/admin/cohort/${sectionId}`,
      key,
    ),

  // --- operator console ---
  platformWhoami: (key: string) => operator<{ role: string }>("/platform/me", key),

  listSchools: (key: string) => operator<PlatformSchool[]>("/platform/schools", key),

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

  issueStaffKey: (key: string, schoolId: string, role: string, label: string) =>
    operator<StaffKeySummary & IssuedKey>(`/platform/schools/${schoolId}/keys`, key, {
      method: "POST",
      body: JSON.stringify({ role, label }),
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

  // --- knowledge base ---
  bookStatus: (key: string, subject: string) =>
    operator<BookStatus>(`/platform/books/${subject}`, key),

  setupCurriculum: (key: string, subject: string) =>
    operator<{ label: string; board_units: number; chapters: number; next: string }>(
      `/platform/books/${subject}/curriculum`, key, { method: "POST" },
    ),

  // --- question papers ---
  createAssessment: (key: string, body: Record<string, unknown>) =>
    authed<{ assessment_id: string; status: string }>("/assessments", key, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** One page or many, PDFs or photographs, in the order given. */
  scanPaper: (key: string, assessmentId: string, files: File[]) =>
    uploadMany<ScanResult>(`/assessments/${assessmentId}/scan`, key, files, "X-API-Key"),

  readScan: (key: string, assessmentId: string) =>
    authed<ScanReview>(`/assessments/${assessmentId}/scan`, key),

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

  uploadContents: (key: string, subject: string, file: File, edition: string) =>
    upload<{ chapters_expected: number; sections_expected: number; next: string }>(
      `/platform/books/${subject}/contents?edition=${encodeURIComponent(edition)}`, key, file,
    ),

  uploadChapter: (key: string, subject: string, file: File) =>
    upload<{ chapter: number; title: string; sections: number; chunks: number; board_unit_mapped: boolean }>(
      `/platform/books/${subject}/chapters`, key, file,
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

  studentDocuments: (key: string, studentId: string) =>
    authed<{ documents: ScanDoc[] }>(`/students/${studentId}/documents`, key),

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
};
