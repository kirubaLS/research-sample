/**
 * Sorting a pile of book PDFs into the books they belong to, from their names alone.
 *
 * NCERT names every file it publishes with a code that already says which book and which
 * chapter it is: jhks101.pdf is Kshitij chapter 1, jhsp1ps.pdf is the Sparsh prelims
 * (contents) page. Four Hindi books arrive as four such piles, and asking somebody to
 * upload them one book and one file at a time is a requirement with nothing behind it, so
 * the page that loads a language reads the codes and routes each file itself.
 *
 * This mirrors app/ingest/book.py's chapter_number() and is_contents() on the server:
 * the server still has the final say, this is only so the plan shown before the first
 * upload is the plan that will run.
 */

/** NCERT book code (the letters plus the one digit that follows) -> subject code. */
export const NCERT_BOOKS: Record<string, string> = {
  jemh1: "X.MATH",
  jesc1: "X.SCI",
  jess1: "X.HIST",
  jess2: "X.GEO",
  jess3: "X.POL",
  jess4: "X.ECO",
  jeff1: "X.ENG.FF",
  jefp1: "X.ENG.FWF",
  jhks1: "X.HIN.KS",
  jhkr1: "X.HIN.KR",
  jhsp1: "X.HIN.SP",
  jhsy1: "X.HIN.SY",
};

export type FileRole = "contents" | "chapter" | "skip";

export interface SortedFile {
  file: File;
  /** the subject the name points at, or null when the name says nothing about the book */
  subject: string | null;
  role: FileRole;
  /** for a chapter, its number; the server refuses a chapter file without one */
  chapter: number | null;
  /** why a file is skipped, in words a person can act on */
  note: string;
}

const NCERT = /^([a-z]{3,5}\d)([a-z0-9]{2})$/;

export function sortFile(file: File): SortedFile {
  const name = file.name;
  const stem = name.replace(/\.pdf$/i, "");
  const lower = stem.toLowerCase();

  if (!/\.pdf$/i.test(name)) {
    return { file, subject: null, role: "skip", chapter: null, note: "not a PDF" };
  }
  if (lower === "00-contents") {
    return { file, subject: null, role: "contents", chapter: null, note: "contents page" };
  }
  const numbered = /^(\d{2})-/.exec(name);
  if (numbered) {
    return {
      file, subject: null, role: "chapter", chapter: Number(numbered[1]),
      note: `chapter ${Number(numbered[1])}`,
    };
  }
  const m = NCERT.exec(lower);
  if (m) {
    const subject = NCERT_BOOKS[m[1]] ?? null;
    const tail = m[2];
    if (tail === "ps") {
      return { file, subject, role: "contents", chapter: null, note: "contents page" };
    }
    if (/^\d{2}$/.test(tail)) {
      return { file, subject, role: "chapter", chapter: Number(tail), note: `chapter ${Number(tail)}` };
    }
    const what = tail === "an" ? "answers" : tail.startsWith("a") ? "appendix" : tail;
    return { file, subject, role: "skip", chapter: null, note: `${what}: not loaded, on purpose` };
  }
  return {
    file, subject: null, role: "skip", chapter: null,
    note: "name says neither the book nor the chapter: rename it NN-title.pdf (00-contents.pdf for the contents page)",
  };
}

/** Group a selection by book. Files whose name names no book go to ``fallback``. */
export function plan(files: File[], fallback: string | null): Map<string, SortedFile[]> {
  const out = new Map<string, SortedFile[]>();
  for (const file of files) {
    const sorted = sortFile(file);
    const subject = sorted.subject ?? fallback;
    if (!subject) continue;
    sorted.subject = subject;
    const list = out.get(subject) ?? [];
    list.push(sorted);
    out.set(subject, list);
  }
  for (const list of out.values()) {
    list.sort((a, b) => {
      if (a.role !== b.role) return a.role === "contents" ? -1 : b.role === "contents" ? 1 : 0;
      return (a.chapter ?? 999) - (b.chapter ?? 999) || a.file.name.localeCompare(b.file.name);
    });
  }
  return out;
}
