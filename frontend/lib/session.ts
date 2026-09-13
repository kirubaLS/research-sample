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

/** What a signed-in staff key may do. Mirrors /admin/me; the server is the authority. */
export interface StaffRole {
  role: "principal" | "admin";
  /** "all_schools" for an admin key, which belongs to none and must pick one. */
  scope: "all_schools" | "one_school";
  can: {
    read_results: boolean;
    scan_papers: boolean;
    enter_marks: boolean;
    manage_roster: boolean;
    manage_schools: boolean;
  };
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

// --- mocked teacher / student sessions ------------------------------------------------
// TODO(backend): Dependency Index #1 (teacher) / #2 (student) -- `GET /admin/me` never
// returns `role: "teacher"` today, and there is no student-auth endpoint at all. These two
// helpers hold a purely local, clearly-labeled demo session so the mocked Teacher and
// Student shells (frontend/app/teacher, frontend/app/student) have something to read
// without pretending either round-tripped through a real backend. Never read by AdminGate
// or by any code path that also holds a real StaffKey/api key.

const MOCK_TEACHER = "yaadhum:mockTeacher";
const MOCK_STUDENT = "yaadhum:mockStudent";

/** Marks that the current browser is previewing the mocked Teacher shell (demo data). */
export function enterMockTeacherPreview(): void {
  window.localStorage.setItem(MOCK_TEACHER, "1");
}

export function isMockTeacherPreview(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(MOCK_TEACHER) === "1";
}

export function exitMockTeacherPreview(): void {
  window.localStorage.removeItem(MOCK_TEACHER);
}

/** Marks that the current browser "signed in" via the mocked student roll-no/PIN form. */
export function enterMockStudentSession(): void {
  window.localStorage.setItem(MOCK_STUDENT, "1");
}

export function isMockStudentSession(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(MOCK_STUDENT) === "1";
}

export function exitMockStudentSession(): void {
  window.localStorage.removeItem(MOCK_STUDENT);
}
