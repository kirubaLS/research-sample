/** The dashboard's sign-in: an API key held in the browser, sent as X-API-Key. */

const KEY = "yaadhum:apiKey";
const SCHOOL = "yaadhum:school";

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
