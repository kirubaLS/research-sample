"use client";

import { useEffect, useSyncExternalStore } from "react";
import type { SessionPayload } from "@/lib/api";

/**
 * The real interest-test run a student takes before any staff member ever
 * signs in -- POST /t/{classCode}/start, then a batch of PATCH-like saves per
 * screen (POST /t/session/{id}/responses) and a final POST .../complete (see
 * lib/api.ts's classes/startSession/saveResponses/complete). Mirrored to
 * sessionStorage only, matching what the previously-real /t/[classCode]/test
 * flow did (see git history), so a reload mid-test does not lose the session
 * id or the answers already typed -- but nothing here is ever read back by a
 * teacher or principal; the payload itself is real, this file just holds it
 * client-side long enough to submit it.
 *
 * The reference design's AttendDraft (a five-section personality/background/
 * future-plans profile, ID+password login, DEMO_PASSWORD) has no backend
 * counterpart at all: the real endpoint takes a name/roll_no/age/gender/
 * section/locale profile and returns 36 Likert items, nothing else. That
 * richer shape is not reproduced here rather than faked.
 */

export interface AttendProfile {
  name: string;
  roll_no: string;
  age?: number;
  gender?: "female" | "male" | "other" | "prefer_not_to_say";
  section: string;
  locale: "en" | "ta" | "hi";
}

export interface AttendAnswer {
  value: number;
  shownAt: number;
  answeredAt: number;
}

export interface AttendDraft {
  /** The class link this run belongs to, e.g. a Section id. */
  classCode: string | null;
  /** What the school (a real one, from GET /t/classes) called this class. */
  classLabel: string | null;
  schoolName: string | null;
  profile: AttendProfile | null;
  /** Set once POST /t/{classCode}/start has answered. */
  sessionId: string | null;
  payload: SessionPayload | null;
  /** -1 = instructions, then an index into payload.screens. */
  screenIndex: number;
  answers: Record<string, AttendAnswer>;
  submitted: boolean;
  /** Increments on every write, the autosave indicator watches it. */
  rev: number;
}

const STORAGE_KEY = "avai.attend.v1";

const EMPTY: AttendDraft = {
  classCode: null,
  classLabel: null,
  schoolName: null,
  profile: null,
  sessionId: null,
  payload: null,
  screenIndex: -1,
  answers: {},
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

export function pickClass(classCode: string, classLabel: string, schoolName: string) {
  state = { ...EMPTY, classCode, classLabel, schoolName, rev: state.rev + 1 };
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
