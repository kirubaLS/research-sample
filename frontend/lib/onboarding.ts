/**
 * The rules the onboarding wizard applies: where Tamil Nadu's districts are, how a school code is
 * made, which academic years to offer, how a class is typed, and what a valid name, number and
 * email look like. Pure functions, so every rule is tested without a browser and the wizard
 * only has to call them.
 */

// --- districts ---------------------------------------------------------------------------------

/** Tamil Nadu's 38 districts, each with a two-letter code that no other district shares. */
export const TN_DISTRICTS: { name: string; code: string }[] = [
  { name: "Ariyalur", code: "AR" }, { name: "Chengalpattu", code: "CG" }, { name: "Chennai", code: "CH" },
  { name: "Coimbatore", code: "CB" }, { name: "Cuddalore", code: "CU" }, { name: "Dharmapuri", code: "DH" },
  { name: "Dindigul", code: "DI" }, { name: "Erode", code: "ER" }, { name: "Kallakurichi", code: "KL" },
  { name: "Kancheepuram", code: "KA" }, { name: "Kanniyakumari", code: "KY" }, { name: "Karur", code: "KU" },
  { name: "Krishnagiri", code: "KR" }, { name: "Madurai", code: "MD" }, { name: "Mayiladuthurai", code: "MY" },
  { name: "Nagapattinam", code: "NG" }, { name: "Namakkal", code: "NM" }, { name: "Nilgiris", code: "NL" },
  { name: "Perambalur", code: "PE" }, { name: "Pudukkottai", code: "PU" }, { name: "Ramanathapuram", code: "RA" },
  { name: "Ranipet", code: "RN" }, { name: "Salem", code: "SL" }, { name: "Sivaganga", code: "SV" },
  { name: "Tenkasi", code: "TK" }, { name: "Thanjavur", code: "TJ" }, { name: "Theni", code: "TH" },
  { name: "Thoothukudi", code: "TU" }, { name: "Tiruchirappalli", code: "TR" }, { name: "Tirunelveli", code: "TV" },
  { name: "Tirupathur", code: "TT" }, { name: "Tiruppur", code: "TI" }, { name: "Tiruvallur", code: "TL" },
  { name: "Tiruvannamalai", code: "TM" }, { name: "Tiruvarur", code: "TA" }, { name: "Vellore", code: "VE" },
  { name: "Viluppuram", code: "VI" }, { name: "Virudhunagar", code: "VR" },
];

export const DEFAULT_STATE = "Tamil Nadu";

/** Tamil Nadu first, because it is where schools are onboarded; the rest alphabetically. */
export const INDIAN_STATES: string[] = [
  DEFAULT_STATE,
  ...[
    "Andhra Pradesh", "Delhi", "Goa", "Gujarat", "Haryana", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra",
    "Odisha", "Puducherry", "Punjab", "Rajasthan", "Telangana", "Uttar Pradesh", "West Bengal",
  ].sort(),
];

export function districtCode(district: string): string | null {
  return TN_DISTRICTS.find((d) => d.name.toLowerCase() === district.trim().toLowerCase())?.code ?? null;
}

// --- school code -------------------------------------------------------------------------------

/** Words that say what kind of school it is, or honour a saint, but not which school: leaving
 * them in would give "Sri Vidya School" and "Sri Ram School" the same prefix. */
const NOISE = new Set([
  "SCHOOL", "SCHOOLS", "SENIOR", "SECONDARY", "SEC", "HIGHER", "HIGH", "HR", "MATRICULATION", "MATRIC", "MAT",
  "PUBLIC", "INTERNATIONAL", "INTL", "RESIDENTIAL", "CBSE", "ICSE", "THE", "OF", "AND", "A", "AN", "GOVT",
  "GOVERNMENT", "PRIVATE", "ENGLISH", "MEDIUM", "SRI", "SHRI", "SREE", "SRIMATHI", "SMT", "ST", "SAINT",
  "MR", "DR", "NURSERY", "PRIMARY", "MIDDLE", "ELEMENTARY", "VIDYALAYA", "VIDYALAYAM",
]);

/** The two letters a school's name contributes: the first two letters of its first word that
 * says which school it is ("Bharathi Vidyalaya" and "Bharat Matric" both give BH). */
export function namePrefix(name: string): string {
  const words = name
    .toUpperCase()
    .replace(/[^A-Z0-9\s]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
  const first = words.find((w) => !NOISE.has(w) && /[A-Z]/.test(w)) ?? words.find((w) => /[A-Z]/.test(w)) ?? "";
  const letters = first.replace(/[^A-Z]/g, "");
  return (letters + "XX").slice(0, 2);
}

/**
 * KR-BH-01: district code, name prefix, and a running number. Two schools in one district whose
 * names begin alike share the first two parts, so the number is what tells them apart: it is one
 * more than the highest already used for that pair, never a gap that could be filled twice.
 * ``existing`` is every school code already issued.
 */
export function generateSchoolCode(district: string, schoolName: string, existing: Iterable<string>): string {
  const d = districtCode(district);
  if (!d || !schoolName.trim()) return "";
  const base = `${d}-${namePrefix(schoolName)}`;
  const taken = new RegExp(`^${base}-(\\d+)$`, "i");
  let highest = 0;
  for (const code of existing) {
    const m = taken.exec((code ?? "").trim());
    if (m) highest = Math.max(highest, Number(m[1]));
  }
  return `${base}-${String(highest + 1).padStart(2, "0")}`;
}

// --- academic year -----------------------------------------------------------------------------

/** The Indian academic year begins in June. */
export function academicYearStart(now: Date = new Date()): number {
  return now.getMonth() >= 5 ? now.getFullYear() : now.getFullYear() - 1;
}

/** The years to offer, from the current academic year on: value "2026-27", label "2026 to 2027". */
export function academicYearOptions(now: Date = new Date(), count = 6): { value: string; label: string }[] {
  const start = academicYearStart(now);
  return Array.from({ length: count }, (_, i) => {
    const y = start + i;
    return { value: `${y}-${String((y + 1) % 100).padStart(2, "0")}`, label: `${y} to ${y + 1}` };
  });
}

// --- classes -----------------------------------------------------------------------------------

export type ClassSpec = { grade: number; name: string };

export function classLabel(c: ClassSpec): string {
  return `${c.grade}${c.name}`;
}

/** "10C", "10-C", "10 c" -> 10 / C. Null when it is not a class. */
export function parseClass(raw: string): ClassSpec | null {
  const m = /^\s*(\d{1,2})\s*[-\s]?\s*([A-Za-z0-9]{1,3})\s*$/.exec(raw);
  if (!m || !/[A-Za-z]/.test(m[2])) return null;
  const grade = Number(m[1]);
  if (grade < 1 || grade > 12) return null;
  return { grade, name: m[2].toUpperCase() };
}

const SECTION_LETTERS = ["A", "B", "C", "D", "E", "F"];

/**
 * What to offer while someone types a class: "10" -> 10A..10F, "10c" -> 10C, "1" -> 1A..1F then
 * 10A..10F. Anything already added is left out. Empty input offers nothing.
 */
export function classSuggestions(query: string, existing: ClassSpec[], limit = 18): ClassSpec[] {
  const q = query.trim().toUpperCase().replace(/[-\s]/g, "");
  const m = /^(\d{1,2})([A-Z0-9]{0,3})$/.exec(q);
  if (!m) return [];
  const have = new Set(existing.map(classLabel));
  const typedGrade = m[1];
  const typedName = m[2];
  const grades = Array.from({ length: 12 }, (_, i) => i + 1).filter((g) => String(g).startsWith(typedGrade));
  // the grade exactly as typed comes first ("1" before "10")
  grades.sort((a, b) => Number(String(b) === typedGrade) - Number(String(a) === typedGrade) || a - b);
  const out: ClassSpec[] = [];
  for (const grade of grades) {
    const names = typedName
      ? [typedName, ...SECTION_LETTERS.filter((l) => l.startsWith(typedName) && l !== typedName)]
      : SECTION_LETTERS;
    for (const name of names) {
      if (!name.startsWith(typedName)) continue;
      const spec = { grade, name };
      if (!have.has(classLabel(spec)) && !out.some((o) => classLabel(o) === classLabel(spec))) out.push(spec);
    }
  }
  return out.slice(0, limit);
}

// --- field rules -------------------------------------------------------------------------------

const PERSON = /^[A-Za-z][A-Za-z .'-]*$/;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/** Digits only, as the backend stores it: +91 and a leading 0 before a mobile number are dropped. */
export function normalisePhone(raw: string): string {
  let d = (raw ?? "").replace(/\D/g, "");
  if (d.length === 12 && d.startsWith("91")) d = d.slice(2);
  if (d.length === 11 && d.startsWith("0") && "6789".includes(d[1])) d = d.slice(1);
  return d;
}

/** What a phone box lets through while typing: digits and the usual separators, never letters. */
export function phoneInput(raw: string): string {
  return raw.replace(/[^\d+\-\s()]/g, "").slice(0, 20);
}

export const isMobile = (raw: string) => /^[6-9]\d{9}$/.test(normalisePhone(raw));
export const isLandline = (raw: string) => /^0\d{9,10}$/.test(normalisePhone(raw));

/** Each rule returns the message to show, or null when the value is fine. */
export const rules = {
  schoolName(v: string): string | null {
    const s = v.trim();
    if (!s) return "Enter the school's name.";
    if (s.length < 3) return "The school's name is too short.";
    if (!/[A-Za-z]{2}/.test(s)) return "The name must contain letters.";
    if (!/^[A-Za-z0-9 .,'&()/-]+$/.test(s)) return "The name has a character that cannot be used (letters, digits and . , ' & ( ) / - only).";
    if (s.length > 200) return "The name is too long.";
    return null;
  },
  district(v: string, mustBeListed: boolean): string | null {
    if (!v.trim()) return "Choose the district.";
    if (mustBeListed && districtCode(v) === null) return "Choose the district from the list.";
    return null;
  },
  /** The school office: a mobile, or a landline with its STD code. */
  contactNumber(v: string): string | null {
    if (!v.trim()) return "Enter the school's contact number.";
    if (/[A-Za-z]/.test(v)) return "A contact number is digits only.";
    if (!isMobile(v) && !isLandline(v)) {
      return "Enter a 10-digit mobile number, or a landline with its STD code (e.g. 04343 222333).";
    }
    return null;
  },
  /** A person's mobile: ten digits, starting 6 to 9. */
  mobile(v: string, required: boolean): string | null {
    if (!v.trim()) return required ? "Enter a mobile number." : null;
    if (/[A-Za-z]/.test(v)) return "A mobile number is digits only.";
    return isMobile(v) ? null : "Enter a 10-digit mobile number starting with 6, 7, 8 or 9.";
  },
  email(v: string, required: boolean): string | null {
    const s = v.trim();
    if (!s) return required ? "Enter an email address." : null;
    if (s.length > 200 || !EMAIL.test(s)) return "That is not a valid email address.";
    return null;
  },
  personName(v: string, required = true): string | null {
    const s = v.trim();
    if (!s) return required ? "Enter the name." : null;
    if (s.length < 3) return "The name is too short.";
    if (!PERSON.test(s)) return "A name has letters only (spaces, . ' - are fine), no digits.";
    return null;
  },
  address(v: string): string | null {
    const s = v.trim();
    if (!s) return null;
    if (s.length < 5) return "The address is too short.";
    return s.length > 500 ? "The address is too long." : null;
  },
  academicYear(v: string, options: { value: string }[]): string | null {
    return options.some((o) => o.value === v) ? null : "Choose the academic year.";
  },
  classes(list: ClassSpec[]): string | null {
    return list.length === 0 ? "Add at least one class." : null;
  },
  rollNo(v: string): string | null {
    const s = v.trim();
    if (!s) return "Roll number needed.";
    return /^[A-Za-z0-9/-]{1,12}$/.test(s) ? null : "Roll number: letters and digits only.";
  },
};

/** The first message for each field that fails, empty when everything is valid. */
export function firstErrors(checks: Record<string, string | null>): Record<string, string> {
  return Object.fromEntries(Object.entries(checks).filter(([, v]) => v !== null)) as Record<string, string>;
}
