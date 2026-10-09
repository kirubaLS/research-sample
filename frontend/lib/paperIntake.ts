/**
 * What the Question papers screen does with a paper's heading: pick the subject it names from
 * the school's subjects, find the exam card it belongs to (so a Mathematics paper and a Science
 * paper of the same "Unit Test 1" share one card), and fill in what the heading left out.
 * Pure functions, tested without a browser.
 */

export type Detected = {
  subject: string | null;
  class: string | null;
  title: string | null;
  date: string | null;
  total_marks: number | null;
  duration: string | null;
};

const ALIASES: Record<string, string> = {
  maths: "mathematics", math: "mathematics", mathematic: "mathematics",
  sst: "social science", "social studies": "social science", "social sciences": "social science",
  sci: "science", eng: "english", hin: "hindi", tam: "tamil",
};

/** "Class X Mathematics (Paper 1)" -> "mathematics". */
export function normaliseSubject(raw: string): string {
  let s = raw.toLowerCase()
    .replace(/\b(class|std|standard|grade)\s*[ivx0-9]+\b/g, " ")
    .replace(/\(.*?\)/g, " ")
    .replace(/\b(paper|question|subject|cbse|icse)\b/g, " ")
    .replace(/[^a-z\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (ALIASES[s]) s = ALIASES[s];
  return s;
}

type SubjectLike = { subject_code: string; label: string; group_label?: string };

/** The school's subject this heading names, or null when none clearly does. */
export function matchSubject(detected: string | null, subjects: SubjectLike[]): string | null {
  if (!detected) return null;
  const want = normaliseSubject(detected);
  if (!want) return null;
  const names = (s: SubjectLike) => [s.label, s.group_label ?? ""].map(normaliseSubject).filter(Boolean);
  const exact = subjects.filter((s) => names(s).includes(want));
  if (exact.length === 1) return exact[0].subject_code;
  if (exact.length > 1) return null;
  const loose = subjects.filter((s) => names(s).some((n) => n.includes(want) || want.includes(n)));
  return loose.length === 1 ? loose[0].subject_code : null;
}

const tidy = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

/** The exam card with this name, so a second paper joins it instead of making a twin. */
export function findExistingTest<T extends { id: string; name: string; date: string | null }>(
  title: string, date: string | null, tests: T[],
): T | null {
  const same = tests.filter((t) => tidy(t.name) === tidy(title));
  if (same.length === 0) return null;
  return same.find((t) => date && t.date === date) ?? (date ? null : same[0]);
}

export function today(now: Date = new Date()): string {
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${m}-${d}`;
}

/** The title to use when the heading prints none: "Mathematics test, 2026-10-09". */
export function fallbackTitle(subjectLabel: string, date: string): string {
  return `${subjectLabel.replace(/^Class\s+[A-Z0-9]+\s+/i, "")} test, ${date}`;
}

/** One line saying what was read, for the notice under the upload box. */
export function summarise(d: Detected, subjectLabel: string | null): string {
  return [
    d.title, subjectLabel?.replace(/^Class\s+[A-Z0-9]+\s+/i, "") ?? d.subject,
    d.total_marks != null ? `${d.total_marks} marks` : null, d.date, d.duration,
  ].filter(Boolean).join(" · ");
}
