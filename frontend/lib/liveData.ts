"use client";

import { useSyncExternalStore } from "react";
import {
  addConductedTest,
  initialSubjectPapers,
  refreshDerived,
  setQuestionMarks,
  type ConductedTest,
  type SubjectPaper,
} from "./avai-mock-data";
// Ops console edits to the demo school (teacher access, parent numbers)
// apply to the school app too, so load them wherever live data is used.
import "./opsDirectory";

/**
 * Everything staff change in this demo: tests created, question papers
 * uploaded and mapped, answer-card marks saved, and reports sent. Saved to
 * localStorage and applied to the shared mock data, so the principal's
 * figures move the moment a teacher saves marks (in this tab or another).
 * 🔧 BACKEND REQUIRED, all of this would live on the server.
 */

interface LiveState {
  tests: ConductedTest[];
  marks: Record<string, Record<string, Record<string, number[]>>>;
  papers: Record<string, Record<string, Partial<SubjectPaper>>>;
  /** `${section}~${testKey}` -> studentId -> ISO time sent */
  shareLog: Record<string, Record<string, string>>;
}

const STORAGE_KEY = "avai.live.v1";
let state: LiveState = { tests: [], marks: {}, papers: {}, shareLog: {} };
let version = 0;
let marksVersion = 0;
const listeners = new Set<() => void>();

function apply(next: LiveState) {
  state = next;
  for (const t of state.tests) addConductedTest({ ...t });
  for (const [testKey, bySubject] of Object.entries(state.marks)) {
    for (const [subject, rows] of Object.entries(bySubject)) setQuestionMarks(testKey, subject, rows);
  }
  refreshDerived();
}

function load() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) apply({ tests: [], marks: {}, papers: {}, shareLog: {}, ...(JSON.parse(raw) as Partial<LiveState>) });
  } catch {
    /* unreadable or blocked storage, start from the seed data */
  }
}

function persist() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* private mode: changes still apply for this session */
  }
}

function emit() {
  version++;
  for (const l of listeners) l();
}

// Staff pages only render after sign-in resolves on the client, so saved
// changes can be applied at import time without a hydration mismatch.
if (typeof window !== "undefined") {
  load();
  window.addEventListener("storage", (e) => {
    if (e.key !== STORAGE_KEY) return;
    load();
    marksVersion++;
    emit();
  });
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Changes whenever marks, papers, tests or the share log change. */
export function useLiveVersion(): number {
  return useSyncExternalStore(subscribe, () => version, () => 0);
}

/** Changes only when marks or tests change, the signal for recomputing figures. */
export function useMarksVersion(): number {
  return useSyncExternalStore(subscribe, () => marksVersion, () => 0);
}

export function saveMarks(testKey: string, subject: string, rows: Record<string, number[]>) {
  state.marks[testKey] ??= {};
  state.marks[testKey][subject] = { ...(state.marks[testKey][subject] ?? {}), ...rows };
  setQuestionMarks(testKey, subject, rows);
  refreshDerived();
  persist();
  marksVersion++;
  emit();
}

export function createTest(test: ConductedTest) {
  state.tests.push(test);
  addConductedTest({ ...test });
  refreshDerived();
  persist();
  marksVersion++;
  emit();
}

export function paperFor(testKey: string, subject: string): SubjectPaper {
  const base: SubjectPaper = initialSubjectPapers[testKey]?.[subject] ?? {
    testKey,
    subject,
    fileName: null,
    uploadedBy: null,
    uploadedAt: null,
    status: "Not uploaded",
    answerCardGenerated: false,
  };
  return { ...base, ...(state.papers[testKey]?.[subject] ?? {}) };
}

export function updatePaper(testKey: string, subject: string, patch: Partial<SubjectPaper>) {
  state.papers[testKey] ??= {};
  state.papers[testKey][subject] = { ...(state.papers[testKey][subject] ?? {}), ...patch };
  persist();
  emit();
}

export function sentLog(section: string, testKey: string): Record<string, string> {
  return state.shareLog[`${section}~${testKey}`] ?? {};
}

export function markSent(section: string, testKey: string, studentIds: string[], at: string) {
  const key = `${section}~${testKey}`;
  state.shareLog[key] = { ...(state.shareLog[key] ?? {}) };
  for (const id of studentIds) state.shareLog[key][id] = at;
  persist();
  emit();
}
