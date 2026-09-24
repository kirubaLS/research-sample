"use client";

import { useEffect, useSyncExternalStore } from "react";
import { avaiStaff, staffById, staffByEmail, type StaffMember } from "./avai-admin-data";

/**
 * AVAI staff session for the internal console, plus the small amount of
 * state an ops person can actually change in a demo: access keys they have
 * generated and reminders they have sent.
 *
 * Deliberately separate from src/lib/auth.tsx, a school principal signing
 * in must never land in here, and an AVAI staff session must survive a
 * principal signing out. Module-level store + useSyncExternalStore, the
 * same contract as attendState.ts.
 * 🔧 BACKEND REQUIRED, nothing is verified; any listed email signs in.
 */

const STORAGE_KEY = "avai.admin.v1";

export interface AdminState {
  staffId: string | null;
  /** `${schoolId}:${teacherId}` -> generated access key. */
  keys: Record<string, string>;
  /** `${schoolId}:${teacherId}` -> how many times the key has been changed. */
  rotations: Record<string, number>;
  /** School ids an ops person has nudged this session. */
  reminded: string[];
  /** True once localStorage has been read on the client. */
  ready: boolean;
}

const EMPTY: AdminState = { staffId: null, keys: {}, rotations: {}, reminded: [], ready: false };

let state: AdminState = EMPTY;
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
    const { staffId, keys, rotations, reminded } = state;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ staffId, keys, rotations, reminded }));
  } catch {
    /* blocked storage, the console still works, it just won't survive a reload */
  }
}

/** Client-only read, so the first client render matches the server render. */
function hydrate() {
  if (hydrated) return;
  hydrated = true;
  let saved: Partial<AdminState> = {};
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) saved = JSON.parse(raw) as Partial<AdminState>;
  } catch {
    /* unreadable, start clean */
  }
  const staffId = saved.staffId && staffById(saved.staffId) ? saved.staffId : null;
  state = { ...EMPTY, ...saved, staffId, ready: true };
  emit();
}

export function useAdminState(): AdminState {
  const snapshot = useSyncExternalStore(
    subscribe,
    () => state,
    () => EMPTY,
  );
  useEffect(hydrate, []);
  return snapshot;
}

/** The signed-in AVAI staff member, plus whether the session has loaded. */
export function useStaffSession(): { staff: StaffMember | null; ready: boolean } {
  const { staffId, ready } = useAdminState();
  return { staff: staffById(staffId), ready };
}

export type StaffSignInResult =
  | { ok: true; staff: StaffMember }
  | { ok: false; field: "email" | "password"; message: string };

export function signInStaff(email: string, password: string): StaffSignInResult {
  const staff = staffByEmail(email);
  if (!staff) {
    return { ok: false, field: "email", message: "No AVAI staff account with that email. Use one of the demo accounts below." };
  }
  if (password.trim().length === 0) {
    return { ok: false, field: "password", message: "Enter any password, this build does not check it." };
  }
  state = { ...state, staffId: staff.id, ready: true };
  persist();
  emit();
  return { ok: true, staff };
}

export function signOutStaff() {
  state = { ...state, staffId: null };
  persist();
  emit();
}

// ------------------------------------------------------------
// Access keys, AVAI generates these, not the school
// ------------------------------------------------------------

const KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

function mulberry32(seed: number) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function seedFromString(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (Math.imul(h, 31) + s.charCodeAt(i)) | 0;
  return h;
}

/** Deterministic for a given rotation, so the same teacher at the same
 *  rotation always gets the same key back, but a new rotation produces a
 *  genuinely different one, for "change key". */
export function accessKeyFor(schoolId: string, teacherId: string, rotation = 0): string {
  const rnd = mulberry32(seedFromString(`key|${schoolId}|${teacherId}|${rotation}`));
  const block = () =>
    Array.from({ length: 4 }, () => KEY_ALPHABET[Math.floor(rnd() * KEY_ALPHABET.length)]).join("");
  return `AVAI-${block()}-${block()}`;
}

export function keyIdFor(schoolId: string, teacherId: string): string {
  return `${schoolId}:${teacherId}`;
}

/** Generates (or re-reads) a teacher's key and records it in the session. */
export function issueKey(schoolId: string, teacherId: string): string {
  const id = keyIdFor(schoolId, teacherId);
  const existing = state.keys[id];
  if (existing) return existing;
  const key = accessKeyFor(schoolId, teacherId, state.rotations[id] ?? 0);
  state = { ...state, keys: { ...state.keys, [id]: key } };
  persist();
  emit();
  return key;
}

/** Invalidates a teacher's current key and issues a new one in its place. */
export function regenerateKey(schoolId: string, teacherId: string): string {
  const id = keyIdFor(schoolId, teacherId);
  const rotation = (state.rotations[id] ?? 0) + 1;
  const key = accessKeyFor(schoolId, teacherId, rotation);
  state = { ...state, keys: { ...state.keys, [id]: key }, rotations: { ...state.rotations, [id]: rotation } };
  persist();
  emit();
  return key;
}

export function markReminded(schoolId: string) {
  if (state.reminded.includes(schoolId)) return;
  state = { ...state, reminded: [...state.reminded, schoolId] };
  persist();
  emit();
}

/** Demo accounts printed on the sign-in screen. */
export const demoStaffLogins = avaiStaff.map((s) => ({ email: s.email, name: s.name, role: s.role }));

/** Everyone shares one password in the demo; it is shown on screen. */
export const DEMO_STAFF_PASSWORD = "avai-ops";
