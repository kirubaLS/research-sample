/** The dashboard's sign-in: an API key held in the browser, sent as X-API-Key. */

const KEY = "yaadhum:apiKey";
const SCHOOL = "yaadhum:school";
const ROLE = "yaadhum:role";
const ACTIVE = "yaadhum:activeSchool";

/**
 * The school an admin key is acting on. A principal never has one -- their key names its
 * school and the API resolves it without consulting the request, so setting this could
 * not move them even if something tried.
 */
export function getActiveSchool(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACTIVE);
}

export function setActiveSchool(schoolId: string): void {
  window.localStorage.setItem(ACTIVE, schoolId);
}

export function clearActiveSchool(): void {
  if (typeof window !== "undefined") window.localStorage.removeItem(ACTIVE);
}

/** One class or subject a teacher key may touch. Mirrors GET /admin/me's `assignments`. */
export interface TeacherAssignment {
  type: "class" | "subject";
  section_id: string;
  section_label: string | null;
  subject_code: string | null;
}

/** What a signed-in staff key may do. Mirrors /admin/me; the server is the authority. */
export interface StaffRole {
  role: "principal" | "admin" | "teacher";
  /** "all_schools" for an admin key, which belongs to none and must pick one. */
  scope: "all_schools" | "one_school";
  can: {
    read_results: boolean;
    scan_papers: boolean;
    enter_marks: boolean;
    manage_roster: boolean;
    manage_schools: boolean;
  };
  /** Only present for a teacher key -- which sections/subjects it may touch. */
  assignments?: TeacherAssignment[];
  /** Set only for a teacher key: the exam cell, papers-and-marks rights across every
   * subject, no assignments of their own. The server's own fact, not something the
   * client infers from assignments/can. */
  exam_cell?: boolean;
}

/**
 * Cached only so the navigation can render without a round trip. Every screen that acts
 * on it re-reads /admin/me, and the API refuses anything this does not cover regardless
 * of what the browser believes -- a hidden button is a courtesy, never the control.
 */
export function getRole(): StaffRole | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(ROLE);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StaffRole;
  } catch {
    return null;
  }
}

export function setRole(role: StaffRole): void {
  window.localStorage.setItem(ROLE, JSON.stringify(role));
}

export function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(KEY);
}

export function setApiKey(key: string, schoolName: string): void {
  window.localStorage.setItem(KEY, key);
  window.localStorage.setItem(SCHOOL, schoolName);
}

export function getSchoolName(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(SCHOOL);
}

export function signOut(): void {
  window.localStorage.removeItem(KEY);
  window.localStorage.removeItem(SCHOOL);
  window.localStorage.removeItem(ROLE);
  window.localStorage.removeItem(ACTIVE);
}

// --- operator console -----------------------------------------------------------------
// A separate credential from the school key above, kept under a separate storage key so
// signing out of one never silently leaves the other behind.

const PLATFORM = "yaadhum:platformKey";

export function getPlatformKey(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(PLATFORM);
}

export function setPlatformKey(key: string): void {
  window.localStorage.setItem(PLATFORM, key);
}

export function signOutPlatform(): void {
  window.localStorage.removeItem(PLATFORM);
}

// --- student session ---------------------------------------------------------------
// A student session is its own credential (a StudentSession token from POST
// /student/{classCode}/login, see app/api/student.py), deliberately separate from the
// staff api-key storage above -- it carries no role, opens no staff route, and grants
// nothing beyond whatever GET /student/reports itself returns. Never read by AdminGate,
// the teacher shell, or any code path that also holds a real StaffKey/api key.

const STUDENT_SESSION = "yaadhum:studentSession";
const STUDENT_NAME = "yaadhum:studentName";

export function setStudentSession(token: string, name: string): void {
  window.localStorage.setItem(STUDENT_SESSION, token);
  window.localStorage.setItem(STUDENT_NAME, name);
}

export function getStudentSession(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STUDENT_SESSION);
}

export function getStudentName(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(STUDENT_NAME) ?? "";
}

export function clearStudentSession(): void {
  window.localStorage.removeItem(STUDENT_SESSION);
  window.localStorage.removeItem(STUDENT_NAME);
}
