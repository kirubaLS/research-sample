/**
 * The id of a background job (a vision scan, a placement run, a grid-sheet read) that the
 * server has already queued -- kept in localStorage, the same place session.ts keeps
 * everything else this app needs back after a reload, so a tab switch, a minimised
 * browser or a full page reload never loses track of work the backend is already doing.
 *
 * Deliberately narrow: only the job id and what it belongs to. Everything else (subject,
 * title, captured pages) that a *pre-queue* failure needs to retry from lives in
 * pageStore's IndexedDB PendingSubmission instead -- this is only for "the server already
 * has it, keep watching."
 */

const PREFIX = "yaadhum:job:";

export type JobKind = "paper-scan" | "paper-place" | "gridsheet";

function storageKey(kind: JobKind, scopeKey: string): string {
  return `${PREFIX}${kind}:${scopeKey}`;
}

export function setJob(kind: JobKind, scopeKey: string, jobId: string): void {
  try {
    window.localStorage.setItem(storageKey(kind, scopeKey), jobId);
  } catch {
    /* private browsing, storage disabled, or a full quota -- the job still runs
       server-side, this only loses the convenience of resuming it automatically */
  }
}

export function getJob(kind: JobKind, scopeKey: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(storageKey(kind, scopeKey));
  } catch {
    return null;
  }
}

export function clearJob(kind: JobKind, scopeKey: string): void {
  try {
    window.localStorage.removeItem(storageKey(kind, scopeKey));
  } catch {
    /* nothing to clean up if storage never worked */
  }
}
