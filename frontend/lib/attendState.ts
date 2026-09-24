"use client";

import { useEffect, useSyncExternalStore } from "react";
import { assessmentContext, classRosterFull, findStudent, sections, type FullRosterStudent } from "./avai-mock-data";

/**
 * The onboarding assessment a school's students complete before any staff
 * member ever signs in. Module-level store + hook, same contract as
 * shareState.ts, with one difference: this run is mirrored to localStorage
 * so a teenager who reloads mid-test on a phone does not start over.
 * 🔧 BACKEND REQUIRED, nothing is submitted anywhere; "saved" means saved
 * in this browser.
 */

/** Everyone in the demo shares one password, printed on the slip. */
export const DEMO_PASSWORD = "avai@2026";

/** Fixed submission date, the app must not read the clock at render time. */
export const ONBOARDING_DATE = "22 Sep 2026";

/** Age as of the fixed "today" the whole app uses, never Date.now(). */
export function ageFrom(dob: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dob)) return null;
  const [by, bm, bd] = dob.split("-").map(Number);
  const [ty, tm, td] = assessmentContext.today.split("-").map(Number);
  let age = ty - by;
  if (tm < bm || (tm === bm && td < bd)) age -= 1;
  return age;
}

export interface AttendIdentity {
  studentId: string;
  loginId: string;
  name: string;
  section: string;
  rollNo: string;
}

export interface AttendDraft {
  identity: AttendIdentity | null;
  /** Highest step the student has reached, so a reload lands where they left. */
  step: number;
  // Basic information
  dob: string;
  gender: string;
  // Section 1, Your Background
  livesIn: string;
  decisionHelper: string;
  hasResponsibilities: string;
  // Section 2, Your Learning Profile
  favoriteSubject: string;
  comfortableSubject: string;
  learningType: string;
  // Section 3, Your Interests
  interests: string[];
  workInterest: string;
  newLearning: string;
  // Section 4, Your Future Plans
  futurePlan: string;
  futurePlanUnsure: boolean;
  class11Group: string;
  groupReasons: string[];
  groupConfidence: string;
  careersKnown: string[];
  futureConcerns: string[];
  submitted: boolean;
  /** Increments on every write, the autosave indicator watches it. */
  rev: number;
}

const STORAGE_KEY = "avai.attend.v1";

const EMPTY: AttendDraft = {
  identity: null,
  step: 0,
  dob: "",
  gender: "",
  livesIn: "",
  decisionHelper: "",
  hasResponsibilities: "",
  favoriteSubject: "",
  comfortableSubject: "",
  learningType: "",
  interests: [],
  workInterest: "",
  newLearning: "",
  futurePlan: "",
  futurePlanUnsure: false,
  class11Group: "",
  groupReasons: [],
  groupConfidence: "",
  careersKnown: [],
  futureConcerns: [],
  submitted: false,
  rev: 0,
};

let state: AttendDraft = EMPTY;
let hydrated = false;
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

function persist() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* private mode / blocked storage, the run still works, it just won't survive a reload */
  }
}

/** Reads the saved run once, on the client only, so the first client render
 * matches the server render and hydration stays quiet. */
function hydrate() {
  if (hydrated) return;
  hydrated = true;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw) as Partial<AttendDraft>;
    // A saved identity is only trusted if the student still exists in the roster.
    const identity = saved.identity && findStudent(saved.identity.studentId) ? saved.identity : null;
    state = { ...EMPTY, ...saved, identity };
    emit();
  } catch {
    /* unreadable or corrupt, start clean */
  }
}

export function patchAttend(patch: Partial<AttendDraft>) {
  state = { ...state, ...patch, rev: state.rev + 1 };
  persist();
  emit();
}

export function startAttend(identity: AttendIdentity) {
  state = { ...EMPTY, identity, rev: state.rev + 1 };
  persist();
  emit();
}

export function submitAttend() {
  patchAttend({ submitted: true });
}

export function resetAttend() {
  state = { ...EMPTY, rev: state.rev + 1 };
  persist();
  emit();
}

/** The whole run, reactively. */
export function useAttend(): AttendDraft {
  const draft = useSyncExternalStore(
    subscribe,
    () => state,
    () => EMPTY,
  );
  useEffect(hydrate, []);
  return draft;
}

// ------------------------------------------------------------
// Credentials, derived from the real roster, never stored
// ------------------------------------------------------------

/** "X-A" + "01" -> "AVAI-XA-01", the ID printed on the student's slip. */
export function loginIdFor(student: Pick<FullRosterStudent, "section" | "rollNo">): string {
  return `AVAI-${student.section.replace("-", "")}-${student.rollNo}`;
}

function normaliseId(raw: string): string {
  return raw.trim().toUpperCase().replace(/\s+/g, "");
}

export type AttendLoginResult =
  | { ok: true; identity: AttendIdentity }
  | { ok: false; field: "loginId" | "password"; message: string };

const sectionLetters = sections.map((s) => s.replace("-", "")).join("|");
const loginIdPattern = new RegExp(`^AVAI-(${sectionLetters})-(\\d{2})$`);

export function resolveAttendLogin(rawId: string, rawPassword: string): AttendLoginResult {
  const id = normaliseId(rawId);
  const match = loginIdPattern.exec(id);
  if (!match) {
    return {
      ok: false,
      field: "loginId",
      message: "IDs look like AVAI-XA-01. Check the slip your class teacher handed you.",
    };
  }
  const section = `${match[1][0]}-${match[1][1]}`;
  const student = (classRosterFull[section] ?? []).find((s) => s.rollNo === match[2]);
  if (!student) {
    return { ok: false, field: "loginId", message: `No student with roll ${match[2]} in ${section}.` };
  }
  if (rawPassword !== DEMO_PASSWORD) {
    return { ok: false, field: "password", message: "That password doesn't match this ID." };
  }
  return {
    ok: true,
    identity: {
      studentId: student.id,
      loginId: loginIdFor(student),
      name: student.name,
      section: student.section,
      rollNo: student.rollNo,
    },
  };
}

/** Two real, working logins to print on the entry screen. */
export const demoLogins = [
  { section: "X-A", rollNo: "01" },
  { section: "X-B", rollNo: "05" },
]
  .map(({ section, rollNo }) => (classRosterFull[section] ?? []).find((s) => s.rollNo === rollNo))
  .filter((s): s is FullRosterStudent => Boolean(s))
  .map((s) => ({ loginId: loginIdFor(s), name: s.name, section: s.section }));

/** Every student in the school can sign in, the entry screen says so. */
export const onboardingCohort = sections.reduce((n, s) => n + (classRosterFull[s]?.length ?? 0), 0);
