// Baked in at BUILD time, not read at runtime: changing it on the host requires a fresh
// deploy, not a restart. The localhost fallback is right for a laptop and wrong for every
// deployment, which is why apiBaseIsDefault() exists -- an unset variable in production
// makes the browser ask the *visitor's* machine for the API, and the resulting failure
// looks like a dead backend rather than a missing setting.
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

function authed<T>(path: string, key: string, init?: RequestInit): Promise<T> {
  return request<T>(path, { ...init, headers: { "X-API-Key": key, ...(init?.headers ?? {}) } });
}

function operator<T>(path: string, key: string, init?: RequestInit): Promise<T> {
  return request<T>(path, { ...init, headers: { "X-Platform-Key": key, ...(init?.headers ?? {}) } });
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

export interface RosterRow {
  student_id: string;
  name: string;
  roll_no: string;
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
 *  boundary the server needs to parse the body. */
async function upload<T>(path: string, key: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { method: "POST", headers: { "X-Platform-Key": key }, body });
  } catch {
    throw new ApiUnreachable(BASE);
  }
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return (await res.json()) as T;
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
  runners_up: { reference: string; chapter: string; similarity: number }[];
}

export interface ProbeResult {
  mode: string;
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
  whoami: (key: string) => authed<{ name: string; state: string | null }>("/admin/me", key),

  overview: (key: string) => authed<Overview>("/admin/overview", key),

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

  interestReport: (key: string, studentId: string) =>
    authed<InterestReport>(`/reports/interest/${studentId}`, key),
};
