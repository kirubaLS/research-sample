"use client";

import { useSyncExternalStore } from "react";
import {
  adminSchools,
  removeConsoleSchool,
  schoolById,
  teacherRosterFor,
  TODAY,
  upsertSchoolFromDirectory,
  type Board,
} from "./avai-admin-data";
import { classRosterFull, mockPrincipal, mockTeachers, school as flagshipSchool, sections as flagshipSections, subjects, type TeacherAssignment } from "./avai-mock-data";
import { accessKeyFor } from "./adminState";

/**
 * Everything the ops console knows about the people in a school: details,
 * sections, principal, teachers with the exact subjects and sections they
 * can see, and every student with their parent's WhatsApp number.
 *
 * Seeded schools start from a directory derived from their existing data;
 * the first edit saves a full copy. Schools onboarded here exist only in
 * this store. Edits to the demo school (Bharat International) also update
 * the school app itself: teacher logins and parent numbers.
 * 🔧 BACKEND REQUIRED, saved in this browser only.
 */

export const TEACHER_ROLES = ["Subject teacher", "Exam cell"] as const;
export type TeacherRole = (typeof TEACHER_ROLES)[number];

export interface SubjectAccess {
  subject: string;
  sections: string[];
}

export interface OpsTeacher {
  id: string;
  name: string;
  phone: string;
  email: string;
  role: TeacherRole;
  access: SubjectAccess[];
  classTeacherOf: string | null;
  enabled: boolean;
  keyIssued: boolean;
  activated: boolean;
  keyRotation: number;
}

export interface OpsStudent {
  id: string;
  rollNo: string;
  name: string;
  section: string;
  parentName: string;
  whatsapp: string;
  /** Left the school: kept for the record, no longer on roll. */
  left?: boolean;
}

export interface OpsPrincipal {
  name: string;
  email: string;
  phone: string;
  keyRotation: number;
}

export interface SchoolDirectory {
  id: string;
  name: string;
  code: string;
  board: Board;
  city: string;
  state: string;
  address: string;
  academicYear: string;
  sections: string[];
  principal: OpsPrincipal;
  teachers: OpsTeacher[];
  students: OpsStudent[];
  createdAt: string;
  owner: string;
  /** True for schools created in the console. */
  isNew?: boolean;
}

export interface AuditEntry {
  at: string;
  schoolId: string;
  by: string;
  text: string;
}

interface OpsState {
  directories: Record<string, SchoolDirectory>;
  audit: AuditEntry[];
}

const STORAGE_KEY = "avai.ops.v1";
let state: OpsState = { directories: {}, audit: [] };
let version = 0;
const listeners = new Set<() => void>();

// ------------------------------------------------------------
// Deterministic helpers for directories derived from seed data
// ------------------------------------------------------------

function hash(s: string): number {
  let h = 7;
  for (let i = 0; i < s.length; i++) h = (Math.imul(h, 31) + s.charCodeAt(i)) >>> 0;
  return h;
}

const PARENT_FIRST = ["Suresh", "Lakshmi", "Ramesh", "Anitha", "Venkat", "Priya", "Mohan", "Kavitha", "Rajesh", "Deepa", "Srinivas", "Meena", "Ashok", "Revathi", "Ganesh", "Uma"];
const STUDENT_FIRST = ["Aarav", "Diya", "Ishaan", "Ananya", "Kabir", "Meera", "Rohan", "Kavya", "Arjun", "Sneha", "Vihaan", "Tanvi", "Aditya", "Riya", "Nikhil", "Pooja", "Siddharth", "Nandini", "Yash", "Gauri"];
const INITIALS = ["R.", "K.", "S.", "M.", "P.", "N.", "V.", "T.", "G.", "D."];

export function demoWhatsApp(id: string): string {
  const h = hash(id);
  return `9${String(h % 1000000000).padStart(9, "0")}`;
}

function parentFor(studentName: string, id: string): string {
  const surname = studentName.split(" ").slice(1).join(" ");
  return `${PARENT_FIRST[hash(`p|${id}`) % PARENT_FIRST.length]} ${surname}`.trim();
}

function teacherPhone(id: string) {
  return `9${String(hash(`t|${id}`) % 1000000000).padStart(9, "0")}`;
}

function emailFor(name: string, code: string) {
  const handle = name.replace(/^(Mrs?|Ms|Dr)\.\s*/i, "").toLowerCase().replace(/[^a-z]+/g, ".").replace(/^\.|\.$/g, "");
  return `${handle}@${code.toLowerCase().replace(/[^a-z]+/g, "")}.edu.in`;
}

function deriveDirectory(schoolId: string): SchoolDirectory | null {
  const s = schoolById(schoolId);
  if (!s) return null;
  const isFlagship = schoolId === flagshipSchool.id;
  const sections = s.sectionCoverage.map((c) => c.section);
  const roster = teacherRosterFor(schoolId);

  const teachers: OpsTeacher[] = isFlagship
    ? mockTeachers.map((t) => {
        const r = roster.find((x) => x.id === t.id);
        return {
          id: t.id,
          name: t.name,
          phone: teacherPhone(t.id),
          email: emailFor(t.name, s.code),
          role: t.examsOnly ? "Exam cell" : "Subject teacher",
          access: t.examsOnly
            ? []
            : t.assignments.filter((a): a is Extract<TeacherAssignment, { type: "subject" }> => a.type === "subject").map((a) => ({ subject: a.subject, sections: [...a.sections] })),
          classTeacherOf: t.assignments.find((a) => a.type === "class")?.section ?? null,
          enabled: true,
          keyIssued: true,
          activated: r?.keyStatus === "Active",
          keyRotation: 0,
        };
      })
    : roster.map((t) => ({
        id: t.id,
        name: t.name,
        phone: teacherPhone(t.id),
        email: emailFor(t.name, s.code),
        role: "Subject teacher" as TeacherRole,
        access: t.subjects.map((subject) => ({ subject, sections: [...t.classes] })),
        classTeacherOf: null,
        enabled: true,
        keyIssued: t.keyStatus !== "Not issued",
        activated: t.keyStatus === "Active",
        keyRotation: 0,
      }));

  const students: OpsStudent[] = isFlagship
    ? flagshipSections.flatMap((sec) =>
        (classRosterFull[sec] ?? []).map((st) => ({
          id: st.id,
          rollNo: st.rollNo,
          name: st.name,
          section: sec,
          parentName: parentFor(st.name, st.id),
          whatsapp: demoWhatsApp(st.id),
        })),
      )
    : s.sectionCoverage.flatMap((c) =>
        Array.from({ length: c.total }, (_, i) => {
          const id = `${schoolId}_${c.section}_${i + 1}`;
          const name = `${STUDENT_FIRST[hash(`n|${id}`) % STUDENT_FIRST.length]} ${INITIALS[hash(`i|${id}`) % INITIALS.length]}`;
          return { id, rollNo: String(i + 1).padStart(2, "0"), name, section: c.section, parentName: parentFor(name, id), whatsapp: demoWhatsApp(id) };
        }),
      );

  return {
    id: s.id,
    name: s.name,
    code: s.code,
    board: s.board,
    city: s.city,
    state: s.state,
    address: `${s.city}, ${s.state}`,
    academicYear: "2026-27",
    sections,
    principal: {
      name: isFlagship ? mockPrincipal.name : s.contact.name,
      email: s.contact.email,
      phone: s.contact.phone.replace(/\D/g, "").slice(-10),
      keyRotation: 0,
    },
    teachers,
    students,
    createdAt: s.onboardingStart,
    owner: s.owner,
  };
}

// ------------------------------------------------------------
// Applying a directory to the rest of the app
// ------------------------------------------------------------

function summarise(d: SchoolDirectory) {
  const onRoll = d.students.filter((s) => !s.left);
  const enabled = d.teachers.filter((t) => t.enabled);
  upsertSchoolFromDirectory({
    id: d.id,
    name: d.name,
    code: d.code,
    board: d.board,
    city: d.city,
    state: d.state,
    contact: { name: d.principal.name, role: "Principal", email: d.principal.email, phone: formatPhone(d.principal.phone) },
    owner: d.owner,
    createdAt: d.createdAt,
    sectionSizes: Object.fromEntries(d.sections.map((sec) => [sec, onRoll.filter((s) => s.section === sec).length])),
    teachers: enabled.length,
    teachersWithKeys: enabled.filter((t) => t.keyIssued).length,
    teachersActive: enabled.filter((t) => t.activated).length,
    principalKey: true,
  });
}

/** The demo school's teacher logins follow its directory. */
function syncFlagship(d: SchoolDirectory) {
  const next = d.teachers
    .filter((t) => t.enabled)
    .map((t) => {
      const assignments: TeacherAssignment[] = [];
      if (t.classTeacherOf) assignments.push({ type: "class", section: t.classTeacherOf });
      if (t.role === "Exam cell") for (const subject of subjects) assignments.push({ type: "subject", subject, sections: [...flagshipSections] });
      else for (const a of t.access) if (a.sections.length) assignments.push({ type: "subject", subject: a.subject, sections: [...a.sections] });
      return { id: t.id, name: t.name, role: "teacher" as const, assignments, examsOnly: t.role === "Exam cell" || undefined };
    });
  mockTeachers.splice(0, mockTeachers.length, ...next);
  for (const st of d.students) {
    const rosterStudent = (classRosterFull[st.section] ?? []).find((r) => r.id === st.id);
    if (rosterStudent) rosterStudent.name = st.name;
  }
}

function applyAll() {
  for (const d of Object.values(state.directories)) {
    summarise(d);
    if (d.id === flagshipSchool.id) syncFlagship(d);
  }
}

function load() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) state = { directories: {}, audit: [], ...(JSON.parse(raw) as Partial<OpsState>) };
  } catch {
    /* start from the seed data */
  }
  applyAll();
}

function persist() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* blocked storage: changes last for this session */
  }
}

function emit() {
  version++;
  for (const l of listeners) l();
}

if (typeof window !== "undefined") {
  load();
  window.addEventListener("storage", (e) => {
    if (e.key !== STORAGE_KEY) return;
    load();
    emit();
  });
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function useOpsVersion(): number {
  return useSyncExternalStore(subscribe, () => version, () => 0);
}

// ------------------------------------------------------------
// Reads
// ------------------------------------------------------------

const derivedCache = new Map<string, SchoolDirectory>();

export function directoryFor(schoolId: string): SchoolDirectory | null {
  const saved = state.directories[schoolId];
  if (saved) return saved;
  if (!derivedCache.has(schoolId)) {
    const d = deriveDirectory(schoolId);
    if (!d) return null;
    derivedCache.set(schoolId, d);
  }
  return derivedCache.get(schoolId)!;
}

export function auditFor(schoolId: string): AuditEntry[] {
  return state.audit.filter((a) => a.schoolId === schoolId).slice(0, 40);
}

/** Parent WhatsApp number for a demo-school student, as held by AVAI ops. */
export function parentWhatsAppFor(studentId: string): string | null {
  const d = directoryFor(flagshipSchool.id);
  return d?.students.find((s) => s.id === studentId)?.whatsapp ?? null;
}

export function teacherKey(schoolId: string, t: OpsTeacher): string {
  return accessKeyFor(schoolId, t.id, t.keyRotation);
}

export function principalKey(d: SchoolDirectory): string {
  return accessKeyFor(d.id, "principal", d.principal.keyRotation);
}

// ------------------------------------------------------------
// Writes
// ------------------------------------------------------------

function nowIso() {
  return new Date().toISOString();
}

/** Save a full directory (create or edit) and log what changed. */
export function saveDirectory(d: SchoolDirectory, by: string, note: string) {
  state.directories[d.id] = structuredClone(d);
  state.audit.unshift({ at: nowIso(), schoolId: d.id, by, text: note });
  state.audit = state.audit.slice(0, 400);
  derivedCache.delete(d.id);
  summarise(d);
  if (d.id === flagshipSchool.id) syncFlagship(d);
  persist();
  emit();
}

/** Apply a change to a school's directory, starting from its current state. */
export function updateDirectory(schoolId: string, by: string, note: string, change: (d: SchoolDirectory) => void) {
  const current = directoryFor(schoolId);
  if (!current) return;
  const next = structuredClone(current);
  change(next);
  saveDirectory(next, by, note);
}

export function deleteConsoleSchool(schoolId: string) {
  delete state.directories[schoolId];
  state.audit = state.audit.filter((a) => a.schoolId !== schoolId);
  removeConsoleSchool(schoolId);
  persist();
  emit();
}

// ------------------------------------------------------------
// Validation + formatting shared by the wizard and the editor
// ------------------------------------------------------------

export function cleanPhone(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  return digits.length > 10 ? digits.slice(-10) : digits;
}

export function isValidPhone(raw: string): boolean {
  return /^[6-9]\d{9}$/.test(cleanPhone(raw));
}

export function isValidEmail(raw: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(raw.trim());
}

export function formatPhone(raw: string): string {
  const d = cleanPhone(raw);
  return d.length === 10 ? `+91 ${d.slice(0, 5)} ${d.slice(5)}` : raw;
}

/** "Sri Vidya Mandir School" + "Chennai" -> "SVM-CHE", unique across the portfolio. */
export function suggestSchoolCode(name: string, city: string): string {
  const letters = name
    .replace(/\b(school|the|of|and|sr|sec|senior|secondary|higher)\b\.?/gi, "")
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0]!.toUpperCase())
    .join("")
    .slice(0, 4) || "SCH";
  const base = `${letters}-${city.replace(/[^a-z]/gi, "").slice(0, 3).toUpperCase() || "IN"}`;
  let code = base;
  let n = 2;
  while (adminSchools.some((s) => s.code === code)) code = `${base}${n++}`;
  return code;
}

export function newId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;
}

export const TODAY_ISO = TODAY;
