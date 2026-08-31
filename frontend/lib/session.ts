/** The dashboard's sign-in: an API key held in the browser, sent as X-API-Key. */

const KEY = "yaadhum:apiKey";
const SCHOOL = "yaadhum:school";
const ROLE = "yaadhum:role";

/** What a signed-in staff key may do. Mirrors /admin/me; the server is the authority. */
export interface StaffRole {
  role: "principal" | "admin";
  can: {
    read_results: boolean;
    scan_papers: boolean;
    enter_marks: boolean;
    manage_roster: boolean;
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
