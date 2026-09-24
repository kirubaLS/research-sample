/**
 * AVAI, internal staff console mock data ("the book of business").
 *
 * This is the AVAI side of the product, not the school side: every account
 * we have sold, where each one sits in onboarding, and what ops has to chase
 * today. Bharat International (sch_001) is the live flagship and its numbers
 * are taken from avai-mock-data.ts so the two consoles never disagree.
 *
 * Deterministic throughout, seeded mulberry32, fixed TODAY, no Math.random
 * and no clock reads at render time.
 */

import {
  allStudents,
  analysedTests,
  classRosterFull,
  mockPrincipal,
  mockTeachers,
  school as flagshipSchool,
  sections as flagshipSections,
  subjects,
  type TeacherAssignment,
} from "./avai-mock-data";

// ============================================================
// Primitives
// ============================================================

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

/** The console's "now". Fixed so nothing in the UI reads the clock. */
export const TODAY = "2026-09-22";

const DAY = 86400000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function daysSince(iso: string): number {
  return Math.round((Date.parse(TODAY) - Date.parse(iso)) / DAY);
}

export function daysUntil(iso: string): number {
  return -daysSince(iso);
}

function shiftDays(iso: string, days: number): string {
  return new Date(Date.parse(iso) + days * DAY).toISOString().slice(0, 10);
}

/** "2026-09-21" -> "21 Sep 2026". Locale-free so it renders identically everywhere. */
export function formatDate(iso: string): string {
  const d = new Date(Date.parse(iso));
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function formatDayMonth(iso: string): string {
  const d = new Date(Date.parse(iso));
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

export function formatAgo(iso: string): string {
  const d = daysSince(iso);
  if (d <= 0) return "today";
  if (d === 1) return "yesterday";
  if (d < 21) return `${d} days ago`;
  if (d < 60) return `${Math.round(d / 7)} weeks ago`;
  return `${Math.round(d / 30)} months ago`;
}

/** Contract values read as Indian ops reads them: ₹6.4L, ₹12.0L. */
export function formatINR(value: number): string {
  if (value <= 0) return "-";
  if (value >= 100000) return `₹${(value / 100000).toFixed(1)}L`;
  return `₹${Math.round(value / 1000)}k`;
}

// ============================================================
// The AVAI team, who signs in to this console
// ============================================================

export interface StaffMember {
  id: string;
  name: string;
  role: string;
  email: string;
  region: string;
}

export const avaiStaff: StaffMember[] = [
  { id: "avai_1", name: "Nandita Rao", role: "Head of Onboarding", email: "nandita@avai.school", region: "South" },
  { id: "avai_2", name: "Imran Qureshi", role: "Onboarding Specialist", email: "imran@avai.school", region: "North" },
  { id: "avai_3", name: "Sneha Balan", role: "Account Manager", email: "sneha@avai.school", region: "South" },
  { id: "avai_4", name: "Rohit Deshpande", role: "Solutions Engineer", email: "rohit@avai.school", region: "West" },
];

export function staffById(id: string | null): StaffMember | null {
  return avaiStaff.find((s) => s.id === id) ?? null;
}

export function staffByEmail(email: string): StaffMember | null {
  const e = email.trim().toLowerCase();
  return avaiStaff.find((s) => s.email.toLowerCase() === e) ?? null;
}

export function staffInitials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

// ============================================================
// Account shapes
// ============================================================

export type Board = "CBSE" | "ICSE" | "State Board" | "IB";
export type Plan = "Pilot" | "Annual" | "Multi-year";
export type AccountStatus = "Live" | "Onboarding" | "Trial" | "At risk" | "Churned";

export const boards: Board[] = ["CBSE", "ICSE", "State Board", "IB"];
export const accountStatuses: AccountStatus[] = ["Live", "Onboarding", "Trial", "At risk", "Churned"];

export interface AdminContact {
  name: string;
  role: string;
  email: string;
  phone: string;
}

export type ChecklistState = "done" | "active" | "blocked" | "todo";

export interface ChecklistStep {
  key: string;
  label: string;
  detail: string;
  state: ChecklistState;
  date: string | null;
}

export type OnboardingStage = "Kick-off" | "Teacher setup" | "Student onboarding" | "Paper mapping" | "First analysis";

export const pipelineStages: OnboardingStage[] = [
  "Kick-off",
  "Teacher setup",
  "Student onboarding",
  "Paper mapping",
  "First analysis",
];

export interface SectionCoverage {
  section: string;
  total: number;
  onboarded: number;
}

export interface WeekPoint {
  /** Week-commencing label, e.g. "3 Aug". */
  label: string;
  weekStart: string;
  value: number;
  cumulative: number;
  /** Weeks that have not happened yet, drawn as pending, never as zero. */
  future: boolean;
}

export interface MonthPoint {
  label: string;
  value: number;
}

export interface AdminSchool {
  id: string;
  name: string;
  code: string;
  board: Board;
  city: string;
  state: string;
  plan: Plan;
  status: AccountStatus;
  contractValue: number;
  renewalDate: string;
  students: number;
  sections: number;
  teachersInvited: number;
  teachersActivated: number;
  studentsOnboarded: number;
  assessmentsAnalysed: number;
  analysedDates: string[];
  /** Tests created so far, may be ahead of assessmentsAnalysed when a
   *  test has been conducted but not every subject's paper is in yet. */
  testsConducted: number;
  papersUploaded: number;
  papersExpected: number;
  lastActivity: string;
  contact: AdminContact;
  note: string;
  owner: string;
  /** Completed onboarding steps, 0-8. Drives the checklist and the pipeline. */
  progress: number;
  stage: OnboardingStage | null;
  daysInStage: number;
  blocker: string | null;
  onboardingStart: string;
  checklist: ChecklistStep[];
  sectionCoverage: SectionCoverage[];
  onboardingSeries: WeekPoint[];
  analysedByMonth: MonthPoint[];
  onboardedThisWeek: number;
}

// ============================================================
// Seeds, the handwritten facts. Everything else is derived so the
// numbers can never contradict each other.
// ============================================================

interface SchoolSeed {
  id: string;
  name: string;
  code: string;
  board: Board;
  city: string;
  state: string;
  plan: Plan;
  status: AccountStatus;
  contractValue: number;
  renewalDate: string;
  students: number;
  sections: number;
  /** Class X teaching staff we expect to invite. */
  staffSize: number;
  analysedDates: string[];
  lastActivity: string;
  onboardingStart: string;
  progress: number;
  blocked?: boolean;
  daysInStage?: number;
  blocker?: string | null;
  owner: string;
  contact: AdminContact;
  note: string;
}

const seeds: SchoolSeed[] = [
  {
    id: flagshipSchool.id,
    name: flagshipSchool.name,
    code: "BISS-TN",
    board: "CBSE",
    city: "Coimbatore",
    state: flagshipSchool.state,
    plan: "Multi-year",
    status: "Live",
    contractValue: 640000,
    renewalDate: "2027-06-30",
    students: allStudents.length,
    sections: flagshipSections.length,
    staffSize: mockTeachers.length,
    analysedDates: analysedTests.map((t) => t.date),
    lastActivity: "2026-09-21",
    onboardingStart: "2026-05-04",
    progress: 8,
    owner: "Nandita Rao",
    contact: {
      name: mockPrincipal.name,
      role: "Principal",
      email: "k.rajan@bharatintl.edu.in",
      phone: "+91 98400 21877",
    },
    note: "Reference account. Quarterly paper is being mapped now; principal has asked for a board-projection view before Pre-Board 1.",
  },
  {
    id: "sch_002",
    name: "Sunrise Global Academy",
    code: "SGA-KA",
    board: "CBSE",
    city: "Bengaluru",
    state: "Karnataka",
    plan: "Annual",
    status: "Live",
    contractValue: 880000,
    renewalDate: "2027-04-15",
    students: 412,
    sections: 9,
    staffSize: 14,
    analysedDates: ["2026-06-08", "2026-07-21", "2026-09-03"],
    lastActivity: "2026-09-20",
    onboardingStart: "2026-04-27",
    progress: 8,
    owner: "Sneha Balan",
    contact: { name: "Dr. Anupama Shetty", role: "Principal", email: "principal@sunriseglobal.in", phone: "+91 98861 40233" },
    note: "Strongest weekly usage in the portfolio. Wants Class IX added next term.",
  },
  {
    id: "sch_003",
    name: "Vidya Niketan Public School",
    code: "VNP-MH",
    board: "CBSE",
    city: "Pune",
    state: "Maharashtra",
    plan: "Annual",
    status: "Live",
    contractValue: 520000,
    renewalDate: "2027-03-31",
    students: 318,
    sections: 7,
    staffSize: 11,
    analysedDates: ["2026-06-15", "2026-08-19"],
    lastActivity: "2026-09-18",
    onboardingStart: "2026-05-11",
    progress: 8,
    owner: "Rohit Deshpande",
    contact: { name: "Mr. Sandeep Kulkarni", role: "Vice Principal", email: "sandeep.k@vidyaniketan.edu.in", phone: "+91 98220 77104" },
    note: "Maths department is the heaviest user. Two teachers still share one login, flagged for cleanup.",
  },
  {
    id: "sch_004",
    name: "St. Aloysius High School",
    code: "SAH-KL",
    board: "ICSE",
    city: "Kochi",
    state: "Kerala",
    plan: "Pilot",
    status: "Live",
    contractValue: 145000,
    renewalDate: "2026-12-20",
    students: 186,
    sections: 4,
    staffSize: 8,
    analysedDates: ["2026-08-26"],
    lastActivity: "2026-09-16",
    onboardingStart: "2026-07-13",
    progress: 8,
    owner: "Sneha Balan",
    contact: { name: "Sr. Mary Thomas", role: "Principal", email: "office@staloysiuskochi.org", phone: "+91 94470 51288" },
    note: "Pilot converts or lapses in December. One analysed paper so far, needs a second before the renewal conversation.",
  },
  {
    id: "sch_005",
    name: "Greenwood Heights School",
    code: "GWH-DL",
    board: "CBSE",
    city: "New Delhi",
    state: "Delhi",
    plan: "Multi-year",
    status: "Live",
    contractValue: 1240000,
    renewalDate: "2028-05-31",
    students: 524,
    sections: 11,
    staffSize: 17,
    analysedDates: ["2026-05-29", "2026-07-02", "2026-08-11", "2026-09-09"],
    lastActivity: "2026-09-21",
    onboardingStart: "2026-04-13",
    progress: 8,
    owner: "Imran Qureshi",
    contact: { name: "Mrs. Radhika Malhotra", role: "Director, Academics", email: "radhika@greenwoodheights.edu.in", phone: "+91 98110 66421" },
    note: "Largest account. Board-projection reports go to the trust every month.",
  },
  {
    id: "sch_006",
    name: "Maharaja Agrasen Vidyalaya",
    code: "MAV-RJ",
    board: "CBSE",
    city: "Jaipur",
    state: "Rajasthan",
    plan: "Annual",
    status: "At risk",
    contractValue: 430000,
    renewalDate: "2026-11-30",
    students: 276,
    sections: 6,
    staffSize: 10,
    analysedDates: ["2026-06-22"],
    lastActivity: "2026-08-19",
    onboardingStart: "2026-05-18",
    progress: 8,
    owner: "Imran Qureshi",
    contact: { name: "Mr. Devendra Sharma", role: "Principal", email: "principal@mavjaipur.ac.in", phone: "+91 94140 30877" },
    note: "Quiet since August. Exam coordinator left; no one has uploaded the mid-term papers. Renewal is eight weeks out.",
  },
  {
    id: "sch_007",
    name: "Nalanda Model School",
    code: "NMS-BR",
    board: "State Board",
    city: "Patna",
    state: "Bihar",
    plan: "Pilot",
    status: "Trial",
    contractValue: 95000,
    renewalDate: "2026-12-05",
    students: 148,
    sections: 3,
    staffSize: 6,
    analysedDates: ["2026-09-04"],
    lastActivity: "2026-09-12",
    onboardingStart: "2026-08-03",
    progress: 7,
    owner: "Imran Qureshi",
    contact: { name: "Mr. Ajay Prasad", role: "Correspondent", email: "ajay@nalandamodel.in", phone: "+91 90310 44562" },
    note: "State-board blueprint differs from CBSE, mapping took two rounds. Reports not shared with parents yet.",
  },
  {
    id: "sch_008",
    name: "Oakridge International",
    code: "OKR-TS",
    board: "IB",
    city: "Hyderabad",
    state: "Telangana",
    plan: "Multi-year",
    status: "Onboarding",
    contractValue: 1080000,
    renewalDate: "2028-03-31",
    students: 460,
    sections: 10,
    staffSize: 15,
    analysedDates: [],
    lastActivity: "2026-09-19",
    onboardingStart: "2026-08-10",
    progress: 5,
    daysInStage: 6,
    blocker: "MYP grade descriptors need a custom blueprint before the first paper maps",
    owner: "Rohit Deshpande",
    contact: { name: "Ms. Leena George", role: "Head of School", email: "leena.george@oakridge-hyd.org", phone: "+91 90000 71255" },
    note: "Biggest new logo this quarter. Blueprint work is engineering-side, not the school's fault.",
  },
  {
    id: "sch_009",
    name: "Saraswati Vidya Mandir",
    code: "SVM-UP",
    board: "State Board",
    city: "Lucknow",
    state: "Uttar Pradesh",
    plan: "Pilot",
    status: "Onboarding",
    contractValue: 120000,
    renewalDate: "2027-01-31",
    students: 232,
    sections: 5,
    staffSize: 9,
    analysedDates: [],
    lastActivity: "2026-09-17",
    onboardingStart: "2026-08-24",
    progress: 4,
    daysInStage: 9,
    blocker: "Student ID slips printed but not handed out, only two sections have attended",
    owner: "Imran Qureshi",
    contact: { name: "Mr. Ramesh Tiwari", role: "Principal", email: "principal@svmlucknow.edu.in", phone: "+91 94150 88321" },
    note: "Needs a call with the class teachers, not the principal. Slips were printed on 29 Aug.",
  },
  {
    id: "sch_010",
    name: "Kalinga Public School",
    code: "KPS-OD",
    board: "CBSE",
    city: "Bhubaneswar",
    state: "Odisha",
    plan: "Annual",
    status: "Onboarding",
    contractValue: 395000,
    renewalDate: "2027-07-31",
    students: 298,
    sections: 6,
    staffSize: 11,
    analysedDates: [],
    lastActivity: "2026-09-20",
    onboardingStart: "2026-09-07",
    progress: 3,
    daysInStage: 4,
    blocker: null,
    owner: "Sneha Balan",
    contact: { name: "Mrs. Sujata Mishra", role: "Principal", email: "sujata@kalingapublic.edu.in", phone: "+91 94370 21904" },
    note: "Clean run so far. Keys go out this week, student onboarding is booked for the 28th.",
  },
  {
    id: "sch_011",
    name: "Little Flower Convent",
    code: "LFC-TN",
    board: "State Board",
    city: "Madurai",
    state: "Tamil Nadu",
    plan: "Pilot",
    status: "Onboarding",
    contractValue: 110000,
    renewalDate: "2027-02-28",
    students: 164,
    sections: 4,
    staffSize: 7,
    analysedDates: [],
    lastActivity: "2026-09-09",
    onboardingStart: "2026-08-17",
    progress: 2,
    blocked: true,
    daysInStage: 13,
    blocker: "Staff list still not shared by the correspondent, cannot invite teachers",
    owner: "Nandita Rao",
    contact: { name: "Sr. Josephine A.", role: "Correspondent", email: "lfcmadurai@gmail.com", phone: "+91 90031 66740" },
    note: "Third follow-up sent. Escalate to the management committee if nothing lands by the 25th.",
  },
  {
    id: "sch_012",
    name: "Himalaya Valley School",
    code: "HVS-HP",
    board: "CBSE",
    city: "Shimla",
    state: "Himachal Pradesh",
    plan: "Pilot",
    status: "Onboarding",
    contractValue: 105000,
    renewalDate: "2027-03-15",
    students: 122,
    sections: 3,
    staffSize: 6,
    analysedDates: [],
    lastActivity: "2026-09-21",
    onboardingStart: "2026-09-16",
    progress: 1,
    daysInStage: 3,
    blocker: null,
    owner: "Nandita Rao",
    contact: { name: "Mr. Tenzin Norbu", role: "Principal", email: "principal@himalayavalley.edu.in", phone: "+91 94180 33215" },
    note: "Signed last week. Kick-off call done; principal account created, teacher list expected on Thursday.",
  },
  {
    id: "sch_013",
    name: "Gyan Jyoti Academy",
    code: "GJA-MP",
    board: "CBSE",
    city: "Indore",
    state: "Madhya Pradesh",
    plan: "Annual",
    status: "Trial",
    contractValue: 165000,
    renewalDate: "2026-11-15",
    students: 204,
    sections: 5,
    staffSize: 8,
    analysedDates: ["2026-08-28"],
    lastActivity: "2026-09-15",
    onboardingStart: "2026-07-20",
    progress: 7,
    owner: "Rohit Deshpande",
    contact: { name: "Mr. Praveen Jain", role: "Academic Head", email: "praveen@gyanjyoti.ac.in", phone: "+91 99770 12048" },
    note: "One analysed paper, good teacher engagement. Trial ends 15 Nov, quote is drafted.",
  },
  {
    id: "sch_014",
    name: "Anand Niketan School",
    code: "ANS-GJ",
    board: "CBSE",
    city: "Ahmedabad",
    state: "Gujarat",
    plan: "Annual",
    status: "Onboarding",
    contractValue: 340000,
    renewalDate: "2027-06-15",
    students: 276,
    sections: 6,
    staffSize: 10,
    analysedDates: [],
    lastActivity: "2026-09-21",
    onboardingStart: "2026-08-06",
    progress: 6,
    daysInStage: 5,
    blocker: "First paper uploaded; three questions still unmapped in Social Science",
    owner: "Rohit Deshpande",
    contact: { name: "Mrs. Hetal Patel", role: "Principal", email: "hetal.patel@anandniketan.edu.in", phone: "+91 98250 60193" },
    note: "First analysis runs the moment mapping closes. Principal demo booked for 26 Sep.",
  },
  {
    id: "sch_015",
    name: "Riverdale Public School",
    code: "RPS-WB",
    board: "ICSE",
    city: "Kolkata",
    state: "West Bengal",
    plan: "Annual",
    status: "Churned",
    contractValue: 0,
    renewalDate: "2026-06-30",
    students: 240,
    sections: 5,
    staffSize: 9,
    analysedDates: ["2026-02-11", "2026-04-08"],
    lastActivity: "2026-06-27",
    onboardingStart: "2026-01-12",
    progress: 8,
    owner: "Sneha Balan",
    contact: { name: "Mr. Arindam Bose", role: "Principal", email: "arindam@riverdalekol.edu.in", phone: "+91 98300 44127" },
    note: "Did not renew after the pilot year, the principal who signed moved schools in May. Worth a re-approach in January.",
  },
];

// ============================================================
// Derivations
// ============================================================

const STEP_STUDENTS = 4;

const stepLabels = [
  "School created",
  "Principal invited",
  "Teachers invited",
  "Teacher keys generated",
  "Students onboarded",
  "First paper mapped",
  "First assessment analysed",
  "Reports shared",
];

const stepKeys = [
  "school_created",
  "principal_invited",
  "teachers_invited",
  "teacher_keys",
  "students_onboarded",
  "first_paper_mapped",
  "first_assessment",
  "reports_shared",
];

function invitedFor(seed: SchoolSeed, rnd: () => number): number {
  if (seed.progress >= 3) return seed.staffSize;
  // Mid-invite: part of the staff list is in. Blocked on the list itself: none.
  if (seed.progress === 2 && !seed.blocked) return Math.max(2, Math.round(seed.staffSize * (0.5 + rnd() * 0.2)));
  return 0;
}

function activatedFor(seed: SchoolSeed, invited: number, rnd: () => number): number {
  const ratio = seed.progress >= 6 ? 0.92 : seed.progress === 5 ? 0.84 : seed.progress === 4 ? 0.68 : seed.progress === 3 ? 0.25 : 0;
  if (ratio === 0) return 0;
  return Math.min(invited, Math.max(1, Math.round(invited * ratio * (0.92 + rnd() * 0.14))));
}

function sectionNamesFor(seed: SchoolSeed): string[] {
  if (seed.id === flagshipSchool.id) return [...flagshipSections];
  return Array.from({ length: seed.sections }, (_, i) => `X-${String.fromCharCode(65 + i)}`);
}

function coverageFor(seed: SchoolSeed, rnd: () => number): SectionCoverage[] {
  const names = sectionNamesFor(seed);
  // Section sizes must add up to the enrolled roll exactly.
  const base = Math.floor(seed.students / names.length);
  const totals = names.map((_, i) => base + (i < seed.students - base * names.length ? 1 : 0));
  const ratio =
    seed.progress > STEP_STUDENTS ? 0.94 : seed.progress === STEP_STUDENTS ? 0.42 : 0;

  return names.map((section, i) => {
    const total = seed.id === flagshipSchool.id ? (classRosterFull[section]?.length ?? totals[i]) : totals[i];
    if (ratio === 0) return { section, total, onboarded: 0 };
    // In-flight onboarding is lumpy: some sections have attended, some have not.
    const jitter = seed.progress === STEP_STUDENTS ? (rnd() < 0.45 ? 0.05 : 0.85 + rnd() * 0.15) : 0.93 + rnd() * 0.07;
    return { section, total, onboarded: Math.min(total, Math.round(total * (ratio === 0.42 ? jitter : jitter))) };
  });
}

function weeklySeries(seed: SchoolSeed, onboarded: number, rnd: () => number): WeekPoint[] {
  const buckets = 8;
  const starts = Array.from({ length: buckets }, (_, i) => shiftDays(seed.onboardingStart, i * 7));
  const past = starts.filter((s) => Date.parse(s) <= Date.parse(TODAY)).length || 1;

  // Front-loaded weights: most of a cohort attends in the first fortnight.
  const weights = Array.from({ length: past }, (_, i) => (1 + rnd() * 0.6) * Math.pow(0.78, i));
  const sum = weights.reduce((a, b) => a + b, 0);
  const raw = weights.map((w) => (w / sum) * onboarded);
  const values = raw.map((v) => Math.floor(v));
  let remainder = onboarded - values.reduce((a, b) => a + b, 0);
  const order = raw
    .map((v, i) => ({ i, frac: v - Math.floor(v) }))
    .sort((a, b) => b.frac - a.frac);
  for (const { i } of order) {
    if (remainder <= 0) break;
    values[i] += 1;
    remainder -= 1;
  }

  let running = 0;
  return starts.map((weekStart, i) => {
    const future = i >= past;
    const value = future ? 0 : values[i] ?? 0;
    running += value;
    return { label: formatDayMonth(weekStart), weekStart, value, cumulative: running, future };
  });
}

function monthSeries(dates: string[]): MonthPoint[] {
  const months = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"];
  return months.map((m) => ({
    label: MONTHS[Number(m.slice(5, 7)) - 1],
    value: dates.filter((d) => d.startsWith(m)).length,
  }));
}

function stageFor(progress: number): OnboardingStage {
  if (progress <= 1) return "Kick-off";
  if (progress <= 3) return "Teacher setup";
  if (progress === 4) return "Student onboarding";
  if (progress === 5) return "Paper mapping";
  return "First analysis";
}

function checklistFor(
  seed: SchoolSeed,
  invited: number,
  activated: number,
  onboarded: number,
  keysIssued: number,
): ChecklistStep[] {
  const details = [
    `${seed.code} · ${seed.board} · ${seed.city}`,
    `${seed.contact.name}, ${seed.contact.email}`,
    invited > 0 ? `${invited} of ${seed.staffSize} teachers invited` : `${seed.staffSize} teachers expected, none invited yet`,
    keysIssued > 0 ? `${keysIssued} access keys generated by AVAI` : "No keys generated yet",
    onboarded > 0 ? `${onboarded} of ${seed.students} students completed the onboarding test` : `0 of ${seed.students} students attended`,
    seed.progress > 5 ? "Blueprint mapped, every question tagged to a chapter" : "Question paper not mapped yet",
    seed.analysedDates.length > 0 ? `${seed.analysedDates.length} assessment${seed.analysedDates.length > 1 ? "s" : ""} analysed` : "No assessment analysed yet",
    seed.progress >= 8 ? "Principal and teacher reports live" : "Reports not shared",
  ];

  // Step dates walk forward from kick-off, except the last three, which are
  // pinned to the account's real first analysed paper so the timeline and the
  // usage chart can never tell different stories.
  const firstAnalysed = seed.analysedDates[0];
  const dateFor = (i: number) => {
    if (i === 4) return shiftDays(seed.onboardingStart, 18);
    if (firstAnalysed) {
      if (i === 5) return shiftDays(firstAnalysed, -7);
      if (i === 6) return firstAnalysed;
      if (i === 7) return shiftDays(firstAnalysed, 3);
    }
    return shiftDays(seed.onboardingStart, Math.round(i * 4.5) - 4);
  };

  return stepLabels.map((label, i) => {
    let state: ChecklistState = "todo";
    if (i < seed.progress) state = "done";
    else if (i === seed.progress) state = seed.blocked ? "blocked" : "active";
    const date = state === "done" ? dateFor(i) : null;
    return { key: stepKeys[i], label, detail: details[i], state, date };
  });
}

function buildSchool(seed: SchoolSeed): AdminSchool {
  const rnd = mulberry32(seedFromString(`school|${seed.id}`));
  const invited = invitedFor(seed, rnd);
  const activated = activatedFor(seed, invited, rnd);
  const keysIssued = seed.progress >= 4 ? invited : seed.progress === 3 ? Math.max(activated, Math.round(invited * 0.4)) : 0;
  const coverage = coverageFor(seed, rnd);
  const onboarded = coverage.reduce((n, c) => n + c.onboarded, 0);
  const series = weeklySeries(seed, onboarded, rnd);
  const current = series.find((w) => !w.future && Date.parse(w.weekStart) + 7 * DAY > Date.parse(TODAY));

  // A test that's been conducted but not fully analysed yet, on top of the
  // analysed ones, its papers are only partly uploaded.
  const pendingTest = seed.progress >= 5 && rnd() < 0.35 ? 1 : 0;
  const testsConducted = seed.analysedDates.length + pendingTest;
  const papersUploaded = seed.analysedDates.length * subjects.length + (pendingTest ? Math.round(rnd() * subjects.length) : 0);

  return {
    id: seed.id,
    name: seed.name,
    code: seed.code,
    board: seed.board,
    city: seed.city,
    state: seed.state,
    plan: seed.plan,
    status: seed.status,
    contractValue: seed.contractValue,
    renewalDate: seed.renewalDate,
    students: seed.students,
    sections: seed.sections,
    teachersInvited: invited,
    teachersActivated: activated,
    studentsOnboarded: onboarded,
    assessmentsAnalysed: seed.analysedDates.length,
    analysedDates: seed.analysedDates,
    testsConducted,
    papersUploaded,
    papersExpected: testsConducted * subjects.length,
    lastActivity: seed.lastActivity,
    contact: seed.contact,
    note: seed.note,
    owner: seed.owner,
    progress: seed.progress,
    stage: seed.status === "Onboarding" ? stageFor(seed.progress) : null,
    daysInStage: seed.daysInStage ?? 0,
    blocker: seed.blocker ?? null,
    onboardingStart: seed.onboardingStart,
    checklist: checklistFor(seed, invited, activated, onboarded, keysIssued),
    sectionCoverage: coverage,
    onboardingSeries: series,
    analysedByMonth: monthSeries(seed.analysedDates),
    onboardedThisWeek: current?.value ?? 0,
  };
}

export const adminSchools: AdminSchool[] = seeds.map(buildSchool);

export function schoolById(id: string): AdminSchool | undefined {
  return adminSchools.find((s) => s.id === id);
}

// ============================================================
// Teacher rosters
// ============================================================

export type InviteStatus = "Accepted" | "Sent" | "Not sent";
export type KeyStatus = "Active" | "Issued" | "Not issued";

export interface AdminTeacher {
  id: string;
  name: string;
  subjects: string[];
  classes: string[];
  invite: InviteStatus;
  keyStatus: KeyStatus;
  lastSeen: string | null;
}

const teacherFirstNames = [
  "Meenakshi", "Arun", "Shalini", "Prakash", "Vandana", "Joseph", "Rekha", "Naveen",
  "Sudha", "Mahesh", "Anjali", "Faisal", "Geeta", "Ramesh", "Neha", "Vikas", "Latha",
];
const teacherLastNames = ["Iyer", "Sharma", "Pillai", "Gupta", "Reddy", "Dsouza", "Bose", "Nair", "Verma", "Kulkarni", "Khan", "Joshi"];

function flagshipRoster(): AdminTeacher[] {
  return mockTeachers.map((t) => {
    const subjectList = t.assignments
      .filter((a): a is Extract<TeacherAssignment, { type: "subject" }> => a.type === "subject")
      .map((a) => a.subject);
    const classList = t.assignments.flatMap((a) => (a.type === "class" ? [a.section] : a.sections));
    return {
      id: t.id,
      name: t.name,
      subjects: subjectList,
      classes: Array.from(new Set(classList)).sort(),
      invite: "Sent" as InviteStatus,
      keyStatus: "Issued" as KeyStatus,
      lastSeen: null,
    };
  });
}

function genericRoster(s: AdminSchool): AdminTeacher[] {
  const rnd = mulberry32(seedFromString(`roster|${s.id}`));
  const seedRow = seeds.find((x) => x.id === s.id);
  const size = seedRow?.staffSize ?? s.teachersInvited;
  const sectionNames = s.sectionCoverage.map((c) => c.section);

  return Array.from({ length: size }, (_, i) => {
    const first = teacherFirstNames[Math.floor(rnd() * teacherFirstNames.length)];
    const last = teacherLastNames[Math.floor(rnd() * teacherLastNames.length)];
    const title = rnd() < 0.58 ? "Mrs." : "Mr.";
    const subjectCount = rnd() < 0.7 ? 1 : 2;
    const chosen: string[] = [];
    while (chosen.length < subjectCount) {
      const sub = subjects[Math.floor(rnd() * subjects.length)];
      if (!chosen.includes(sub)) chosen.push(sub);
    }
    const classCount = 1 + Math.floor(rnd() * Math.min(3, sectionNames.length));
    const classes: string[] = [];
    while (classes.length < classCount) {
      const sec = sectionNames[Math.floor(rnd() * sectionNames.length)];
      if (!classes.includes(sec)) classes.push(sec);
    }
    return {
      id: `${s.id}_t${i + 1}`,
      name: `${title} ${first} ${last}`,
      subjects: chosen,
      classes: classes.sort(),
      invite: "Not sent" as InviteStatus,
      keyStatus: "Not issued" as KeyStatus,
      lastSeen: null,
    };
  });
}

/** The roster, with invite/key/last-seen states that add up to the account's
 * invited and activated counts exactly. */
export function teacherRosterFor(schoolId: string): AdminTeacher[] {
  const s = schoolById(schoolId);
  if (!s) return [];
  // Before the staff list arrives there are no names to show, an empty
  // roster is the truth, not a list of invented teachers.
  if (s.teachersInvited === 0 && s.progress <= 2) return [];
  const rows = s.id === flagshipSchool.id ? flagshipRoster() : genericRoster(s);
  const rnd = mulberry32(seedFromString(`roster-state|${s.id}`));

  // Who is invited / activated is a seeded shuffle, so it is never simply
  // "the last teacher is always the laggard".
  const order = rows.map((_, i) => i).sort((a, b) => mulberry32(seedFromString(`${s.id}|${a}`))() - mulberry32(seedFromString(`${s.id}|${b}`))());
  const invitedSet = new Set(order.slice(0, s.teachersInvited));
  const activatedSet = new Set(order.slice(0, s.teachersActivated));
  const keysIssued = s.progress >= 4 ? s.teachersInvited : s.progress === 3 ? Math.max(s.teachersActivated, Math.round(s.teachersInvited * 0.4)) : 0;
  const keySet = new Set(order.slice(0, keysIssued));

  return rows.map((row, i) => {
    const invited = invitedSet.has(i);
    const activated = activatedSet.has(i);
    const hasKey = keySet.has(i);
    return {
      ...row,
      invite: activated ? "Accepted" : invited ? "Sent" : "Not sent",
      keyStatus: activated ? "Active" : hasKey ? "Issued" : "Not issued",
      lastSeen: activated ? shiftDays(s.lastActivity, -Math.floor(rnd() * 12)) : null,
    };
  });
}

// ============================================================
// Activity feed
// ============================================================

export type EventKind = "analysis" | "onboarding" | "teacher" | "account" | "support";

export interface AdminEvent {
  id: string;
  date: string;
  kind: EventKind;
  text: string;
  actor: string;
}

const accountEventPool = [
  (s: AdminSchool) => `Check-in call with ${s.contact.name}`,
  (s: AdminSchool) => `Usage summary emailed to ${s.contact.role.toLowerCase()}`,
  () => "Support ticket closed, marks upload from a scanned sheet",
  (s: AdminSchool) => `${s.plan} plan confirmed, invoice raised`,
  () => "Training session run for the class teachers",
  () => "Question paper re-uploaded after a scan quality issue",
];

export function activityFeedFor(schoolId: string): AdminEvent[] {
  const s = schoolById(schoolId);
  if (!s) return [];
  const rnd = mulberry32(seedFromString(`feed|${s.id}`));
  const events: AdminEvent[] = [];

  s.analysedDates.forEach((date, i) => {
    events.push({
      id: `${s.id}_an_${i}`,
      date,
      kind: "analysis",
      text: `Assessment analysed, ${s.sections} sections, ${s.students} papers`,
      actor: "AVAI engine",
    });
  });

  if (s.teachersInvited > 0) {
    events.push({
      id: `${s.id}_inv`,
      date: shiftDays(s.onboardingStart, 6),
      kind: "teacher",
      text: `${s.teachersInvited} teacher invites sent`,
      actor: s.owner,
    });
  }
  if (s.teachersActivated > 0) {
    events.push({
      id: `${s.id}_act`,
      date: shiftDays(s.onboardingStart, 12),
      kind: "teacher",
      text: `${s.teachersActivated} teachers activated their access key`,
      actor: "Self-serve",
    });
  }
  if (s.studentsOnboarded > 0) {
    events.push({
      id: `${s.id}_onb`,
      date: shiftDays(s.onboardingStart, 18),
      kind: "onboarding",
      text: `${s.studentsOnboarded} of ${s.students} students completed the onboarding test`,
      actor: "Student portal",
    });
  }
  if (s.blocker) {
    events.push({
      id: `${s.id}_blk`,
      date: shiftDays(s.lastActivity, -1),
      kind: "support",
      text: `Blocker logged, ${s.blocker}`,
      actor: s.owner,
    });
  }

  // Two seeded account-management events, walking back from last activity.
  let cursor = s.lastActivity;
  for (let i = 0; i < 3; i++) {
    const pick = accountEventPool[Math.floor(rnd() * accountEventPool.length)];
    events.push({ id: `${s.id}_ev_${i}`, date: cursor, kind: "account", text: pick(s), actor: s.owner });
    cursor = shiftDays(cursor, -(2 + Math.floor(rnd() * 9)));
  }

  return events
    .filter((e) => Date.parse(e.date) <= Date.parse(TODAY))
    .sort((a, b) => Date.parse(b.date) - Date.parse(a.date))
    .slice(0, 7);
}

// ============================================================
// Portfolio roll-ups
// ============================================================

export const portfolioKpis = buildPortfolioKpis();
function buildPortfolioKpis() {
  const active = () => adminSchools.filter((s) => s.status !== "Churned");
  return {
  schoolsLive: adminSchools.filter((s) => s.status === "Live").length,
  schoolsTotal: adminSchools.length,
  studentsUnderAnalysis: active().filter((s) => s.assessmentsAnalysed > 0).reduce((n, s) => n + s.students, 0),
  studentsOnPlatform: active().reduce((n, s) => n + s.studentsOnboarded, 0),
  teachersActivated: active().reduce((n, s) => n + s.teachersActivated, 0),
  teachersInvited: active().reduce((n, s) => n + s.teachersInvited, 0),
  assessmentsThisTerm: active().reduce(
    (n, s) => n + s.analysedDates.filter((d) => Date.parse(d) >= Date.parse("2026-04-01")).length,
    0,
  ),
  onboardedThisWeek: active().reduce((n, s) => n + s.onboardedThisWeek, 0),
  contractedValue: active().reduce((n, s) => n + s.contractValue, 0),
  onboardingCount: adminSchools.filter((s) => s.status === "Onboarding").length,
  };
}

export const statusMix = buildStatusMix();
function buildStatusMix() {
  return accountStatuses.map((status) => ({ status, count: adminSchools.filter((s) => s.status === status).length })).filter((r) => r.count > 0);
}

export interface AttentionItem {
  id: string;
  schoolId: string;
  schoolName: string;
  code: string;
  reason: string;
  metric: string;
  severity: "high" | "medium";
  owner: string;
}

function buildAttention(): AttentionItem[] {
  const items: AttentionItem[] = [];
  for (const s of adminSchools) {
    if (s.status === "Churned") continue;
    const quiet = daysSince(s.lastActivity);

    if (s.status === "At risk") {
      items.push({
        id: `${s.id}_risk`,
        schoolId: s.id,
        schoolName: s.name,
        code: s.code,
        reason: "No activity since the last analysed paper, renewal is close",
        metric: `${quiet} days quiet`,
        severity: "high",
        owner: s.owner,
      });
    }
    if (s.status === "Onboarding" && s.daysInStage >= 8) {
      items.push({
        id: `${s.id}_stall`,
        schoolId: s.id,
        schoolName: s.name,
        code: s.code,
        reason: s.blocker ?? `Stalled in ${s.stage}`,
        metric: `${s.daysInStage} days in ${s.stage}`,
        severity: s.daysInStage >= 12 ? "high" : "medium",
        owner: s.owner,
      });
    }
    if (s.status === "Live" && quiet > 14) {
      items.push({
        id: `${s.id}_quiet`,
        schoolId: s.id,
        schoolName: s.name,
        code: s.code,
        reason: "Live account has gone quiet, no uploads or report views",
        metric: `${quiet} days quiet`,
        severity: "medium",
        owner: s.owner,
      });
    }
    if (s.teachersInvited > 0 && s.teachersActivated / s.teachersInvited < 0.6 && s.progress >= 4) {
      items.push({
        id: `${s.id}_act`,
        schoolId: s.id,
        schoolName: s.name,
        code: s.code,
        reason: "Most invited teachers have never used their key",
        metric: `${s.teachersActivated} / ${s.teachersInvited} activated`,
        severity: "medium",
        owner: s.owner,
      });
    }
    const untilRenewal = daysUntil(s.renewalDate);
    if (untilRenewal > 0 && untilRenewal <= 60 && s.status !== "Onboarding") {
      items.push({
        id: `${s.id}_renew`,
        schoolId: s.id,
        schoolName: s.name,
        code: s.code,
        reason: `${s.plan} term ends soon, renewal conversation not started`,
        metric: `${untilRenewal} days to renewal`,
        severity: untilRenewal <= 45 ? "high" : "medium",
        owner: s.owner,
      });
    }
  }
  return items.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "high" ? -1 : 1));
}

export const needsAttention: AttentionItem[] = buildAttention();

/** Distinct accounts behind the attention list, what the KPI counts. */
export const accountsNeedingAttention = new Set(needsAttention.map((i) => i.schoolId)).size;

export interface PipelineColumn {
  stage: OnboardingStage;
  schools: AdminSchool[];
  students: number;
}

export const pipelineBoard: PipelineColumn[] = buildPipeline();
function buildPipeline(): PipelineColumn[] {
  return pipelineStages.map((stage) => {
    const schools = adminSchools.filter((s) => s.status === "Onboarding" && s.stage === stage);
    return { stage, schools, students: schools.reduce((n, s) => n + s.students, 0) };
  });
}

/** What each stage actually means, shown under the column heading. */
export const stageHints: Record<OnboardingStage, string> = {
  "Kick-off": "Contract signed, principal account created",
  "Teacher setup": "Staff list collected, invites and keys issued by AVAI",
  "Student onboarding": "Students take the onboarding test with their slip",
  "Paper mapping": "First question paper uploaded and tagged to chapters",
  "First analysis": "Marks in, analysis running, reports about to go live",
};

// ============================================================
// Colour helpers, one place decides what a status looks like
// ============================================================

export function statusAccent(status: AccountStatus): string {
  switch (status) {
    case "Live":
      return "var(--brand-green)";
    case "Onboarding":
      return "var(--brand-blue)";
    case "Trial":
      return "var(--brand-gold)";
    case "At risk":
      return "var(--risk)";
    default:
      return "var(--muted)";
  }
}

export function checklistAccent(state: ChecklistState): string {
  switch (state) {
    case "done":
      return "var(--brand-green)";
    case "active":
      return "var(--brand-blue)";
    case "blocked":
      return "var(--risk)";
    default:
      return "var(--line-strong)";
  }
}

export function eventAccent(kind: EventKind): string {
  switch (kind) {
    case "analysis":
      return "var(--brand-teal)";
    case "onboarding":
      return "var(--brand-blue)";
    case "teacher":
      return "var(--brand-gold)";
    case "support":
      return "var(--risk)";
    default:
      return "var(--muted)";
  }
}

/** Onboarding completeness as a percentage of the eight-step checklist. */
export function onboardingPct(s: AdminSchool): number {
  return Math.round((s.progress / stepLabels.length) * 100);
}

export const checklistLength = stepLabels.length;


// ============================================================
// Schools edited or onboarded from the console. The directory (people,
// sections, students) lives in src/lib/opsDirectory.ts; these write its
// headline numbers back into the portfolio so every list agrees.
// ============================================================

export interface DirectorySummary {
  id: string;
  name: string;
  code: string;
  board: Board;
  city: string;
  state: string;
  contact: AdminContact;
  owner: string;
  createdAt: string;
  /** Section name -> students on roll. */
  sectionSizes: Record<string, number>;
  teachers: number;
  teachersWithKeys: number;
  teachersActive: number;
  principalKey: boolean;
}

function freshChecklist(d: DirectorySummary, progress: number, students: number): ChecklistStep[] {
  const details = [
    `${d.code} · ${d.board} · ${d.city}`,
    `${d.contact.name}, ${d.contact.email}`,
    d.teachers ? `${d.teachers} teachers added` : "No teachers added yet",
    d.teachersWithKeys ? `${d.teachersWithKeys} access keys generated by AVAI` : "No keys generated yet",
    `0 of ${students} students completed the onboarding test`,
    "Question paper not mapped yet",
    "No assessment analysed yet",
    "Reports not shared",
  ];
  return stepLabels.map((label, i) => ({
    key: stepKeys[i],
    label,
    detail: details[i],
    state: i < progress ? "done" : i === progress ? "active" : "todo",
    date: i < progress ? d.createdAt : null,
  }));
}

/** Create or update a school's portfolio row from its directory. */
export function upsertSchoolFromDirectory(d: DirectorySummary) {
  const students = Object.values(d.sectionSizes).reduce((a, b) => a + b, 0);
  const existing = adminSchools.find((s) => s.id === d.id);
  if (existing) {
    const onboardedBy = new Map(existing.sectionCoverage.map((c) => [c.section, c.onboarded]));
    Object.assign(existing, {
      name: d.name,
      code: d.code,
      board: d.board,
      city: d.city,
      state: d.state,
      contact: d.contact,
      students,
      sections: Object.keys(d.sectionSizes).length,
      teachersInvited: d.teachers,
      teachersActivated: Math.min(d.teachers, d.teachersActive),
      sectionCoverage: Object.entries(d.sectionSizes).map(([section, total]) => ({ section, total, onboarded: Math.min(total, onboardedBy.get(section) ?? 0) })),
    });
    existing.studentsOnboarded = existing.sectionCoverage.reduce((n, c) => n + c.onboarded, 0);
  } else {
    const progress = 1 + (d.contact.name ? 1 : 0) + (d.teachers ? 1 : 0) + (d.teachers && d.teachersWithKeys === d.teachers ? 1 : 0);
    adminSchools.push({
      id: d.id,
      name: d.name,
      code: d.code,
      board: d.board,
      city: d.city,
      state: d.state,
      plan: "Pilot",
      status: "Onboarding",
      contractValue: 0,
      renewalDate: shiftDays(d.createdAt, 365),
      students,
      sections: Object.keys(d.sectionSizes).length,
      teachersInvited: d.teachers,
      teachersActivated: d.teachersActive,
      studentsOnboarded: 0,
      assessmentsAnalysed: 0,
      analysedDates: [],
      testsConducted: 0,
      papersUploaded: 0,
      papersExpected: 0,
      lastActivity: d.createdAt,
      contact: d.contact,
      note: "Onboarded from the ops console.",
      owner: d.owner,
      progress,
      stage: stageFor(progress),
      daysInStage: 0,
      blocker: null,
      onboardingStart: d.createdAt,
      checklist: freshChecklist(d, progress, students),
      sectionCoverage: Object.entries(d.sectionSizes).map(([section, total]) => ({ section, total, onboarded: 0 })),
      onboardingSeries: [],
      analysedByMonth: monthSeries([]),
      onboardedThisWeek: 0,
    });
  }
  Object.assign(portfolioKpis, buildPortfolioKpis());
  statusMix.splice(0, statusMix.length, ...buildStatusMix());
  pipelineBoard.splice(0, pipelineBoard.length, ...buildPipeline());
}

/** Remove a school added from the console. */
export function removeConsoleSchool(id: string) {
  const i = adminSchools.findIndex((s) => s.id === id);
  if (i >= 0) adminSchools.splice(i, 1);
  Object.assign(portfolioKpis, buildPortfolioKpis());
  statusMix.splice(0, statusMix.length, ...buildStatusMix());
  pipelineBoard.splice(0, pipelineBoard.length, ...buildPipeline());
}
