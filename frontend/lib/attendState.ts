"use client";

import { useEffect, useSyncExternalStore } from "react";
import type { OnboardingIn } from "@/lib/api";

/**
 * The real 6-step /attend/onboarding wizard's draft, mirrored to sessionStorage
 * so a reload mid-wizard does not lose what a student already typed. One submit,
 * POST /t/{classCode}/onboard (see lib/api.ts's `onboard`), sends every step's
 * answers to StudentProfile at once -- there is no per-screen save the way the
 * old 36-item Likert flow had, because there is no per-item payload to save.
 *
 * The 36-item RIASEC instrument (TestSession/ItemResponse/scoring) still exists
 * in the backend, untouched, and is no longer wired into this onboarding flow.
 */

export type WizardAnswers = Partial<OnboardingIn>;

export interface AttendDraft {
  /** The class link this run belongs to, e.g. a Section id. */
  classCode: string | null;
  classLabel: string | null;
  schoolName: string | null;
  classBoard: string | null;
  classSection: string | null;
  classGrade: number | null;
  /** 0..5: which of the 6 steps is showing. Step 5 is the Done screen. */
  step: number;
  answers: WizardAnswers;
  /** Set once POST /t/{classCode}/onboard has answered. */
  studentId: string | null;
  submitted: boolean;
  /** Increments on every write, the autosave indicator watches it. */
  rev: number;
}

const STORAGE_KEY = "avai.attend.v2";

const EMPTY: AttendDraft = {
  classCode: null,
  classLabel: null,
  schoolName: null,
  classBoard: null,
  classSection: null,
  classGrade: null,
  step: 0,
  answers: {},
  studentId: null,
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
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
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
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw) as Partial<AttendDraft>;
    state = { ...EMPTY, ...saved };
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

export function patchAnswers(patch: WizardAnswers) {
  state = { ...state, answers: { ...state.answers, ...patch }, rev: state.rev + 1 };
  persist();
  emit();
}

export function pickClass(option: {
  class_code: string;
  label: string;
  school: string;
  board?: string;
  section?: string;
  grade?: number;
}) {
  state = {
    ...EMPTY,
    classCode: option.class_code,
    classLabel: option.label,
    schoolName: option.school,
    classBoard: option.board ?? null,
    classSection: option.section ?? null,
    classGrade: option.grade ?? null,
    rev: state.rev + 1,
  };
  persist();
  emit();
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
