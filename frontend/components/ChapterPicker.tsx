"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Plus, X } from "lucide-react";
import type { SubjectChapters } from "@/lib/api";

/** Which chapters of one subject a test covers.
 *
 * Two ways in, both the way a teacher thinks: the chapter's number in the book fills in
 * its name, and the first letters of a name list the chapters that start with them.
 * Picking a suggestion fills the number. Add puts the chapter on the list; the list is
 * the scope the paper is created with. A multi-book subject (Social Science, English)
 * shows its books one under another, since each numbers its chapters from one. */
export function ChapterPicker({
  label, chapters, picked, onChange,
}: {
  label: string;
  chapters: SubjectChapters | null;
  picked: Set<string>;
  onChange: (next: Set<string>) => void;
}) {
  const books = chapters?.books ?? [];
  const multiBook = books.length > 1;
  const all = useMemo(
    () => books.flatMap((b) => b.chapters.map((c) => ({ ...c, book: b.subject_code, bookLabel: shortBook(b.label) }))),
    [books],
  );
  const total = all.length;
  const [bookCode, setBookCode] = useState<string>("");
  const [number, setNumber] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!bookCode && books.length) setBookCode(books[0].subject_code);
  }, [books, bookCode]);

  // the pool the number and the name search work over: the chosen book of a
  // multi-book subject, or the one book there is
  const pool = useMemo(
    () => all.filter((c) => !multiBook || c.book === bookCode),
    [all, multiBook, bookCode],
  );

  const byNumber = useMemo(() => {
    const n = Number(number);
    return Number.isInteger(n) && n > 0 ? pool.find((c) => c.number === n) ?? null : null;
  }, [number, pool]);

  const suggestions = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return pool.filter((c) => !picked.has(c.code)).slice(0, 8);
    const starts = pool.filter((c) => c.label.toLowerCase().startsWith(q));
    const words = pool.filter(
      (c) => !starts.includes(c) && c.label.toLowerCase().split(/\s+/).some((w) => w.startsWith(q)),
    );
    const contains = pool.filter((c) => !starts.includes(c) && !words.includes(c) && c.label.toLowerCase().includes(q));
    return [...starts, ...words, ...contains].slice(0, 8);
  }, [query, pool]);

  // typing a number fills the name; the name is the chapter's own, read-only until cleared
  useEffect(() => {
    if (byNumber) setQuery(byNumber.label);
  }, [byNumber]);

  useEffect(() => {
    function away(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, []);

  const exact = pool.find((c) => c.label.toLowerCase() === query.trim().toLowerCase()) ?? byNumber;

  function choose(c: (typeof pool)[number]) {
    setNumber(String(c.number));
    setQuery(c.label);
    setOpen(false);
  }

  function add() {
    const c = exact ?? (suggestions.length === 1 ? suggestions[0] : null);
    if (!c) return;
    const next = new Set(picked);
    next.add(c.code);
    onChange(next);
    setNumber("");
    setQuery("");
    setOpen(false);
  }

  function remove(code: string) {
    const next = new Set(picked);
    next.delete(code);
    onChange(next);
  }

  const allPicked = total > 0 && all.every((c) => picked.has(c.code));
  function toggleAll() {
    onChange(allPicked ? new Set() : new Set(all.map((c) => c.code)));
  }

  const chosen = all.filter((c) => picked.has(c.code));

  return (
    <div className="pm-chapters" ref={boxRef}>
      <div className="pm-chapters__head">
        <div>
          <span className="strong">{label}</span>{" "}
          <span className="small muted">{chapters ? `${chosen.length} of ${total} chapters` : "Loading chapters…"}</span>
        </div>
        <label className="pm-chapters__all">
          <input type="checkbox" checked={allPicked} onChange={toggleAll} disabled={!chapters} /> Select all chapters
        </label>
      </div>
      {multiBook && (
        <div className="pm-chipset" style={{ marginBottom: 8 }}>
          {books.map((b) => (
            <button
              type="button"
              key={b.subject_code}
              className={`pm-chip ${bookCode === b.subject_code ? "pm-chip--on" : ""}`}
              onClick={() => { setBookCode(b.subject_code); setNumber(""); setQuery(""); }}
            >
              {shortBook(b.label)}
            </button>
          ))}
        </div>
      )}
      <div className="pm-chapters__row">
        <input
          className="input pm-chapters__number"
          inputMode="numeric"
          placeholder="Unit no."
          aria-label={`${label} chapter number`}
          value={number}
          disabled={!chapters}
          onChange={(e) => { setNumber(e.target.value.replace(/[^0-9]/g, "")); setOpen(true); }}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
        />
        <div className="pm-chapters__search">
          <input
            className="input"
            placeholder="Type a chapter name or unit number"
            aria-label={`${label} chapter name`}
            value={query}
            disabled={!chapters}
            onFocus={() => setOpen(true)}
            onChange={(e) => {
              const v = e.target.value;
              if (/^\d+$/.test(v.trim())) { setNumber(v.trim()); return; }
              setQuery(v); setNumber(""); setOpen(true); setHighlight(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setHighlight((h) => Math.min(h + 1, suggestions.length - 1)); setOpen(true); }
              else if (e.key === "ArrowUp") { e.preventDefault(); setHighlight((h) => Math.max(h - 1, 0)); }
              else if (e.key === "Enter") { e.preventDefault(); if (open && suggestions[highlight] && !exact) choose(suggestions[highlight]); else add(); }
              else if (e.key === "Escape") setOpen(false);
            }}
          />
          {open && chapters && suggestions.length > 0 && !(exact && suggestions.length === 1) && (
            <ul className="pm-chapters__suggest" role="listbox">
              {suggestions.map((c, i) => (
                <li
                  key={c.code}
                  role="option"
                  aria-selected={i === highlight}
                  className={`pm-chapters__option ${i === highlight ? "pm-chapters__option--hi" : ""} ${picked.has(c.code) ? "pm-chapters__option--picked" : ""}`}
                  onMouseDown={(e) => { e.preventDefault(); choose(c); }}
                  onMouseEnter={() => setHighlight(i)}
                >
                  <span className="pm-chapters__num">{c.number}</span>
                  <span>{c.label}</span>
                  {picked.has(c.code) && <span className="small muted" style={{ marginLeft: "auto" }}>added</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
        <button type="button" className="btn btn--sm" onClick={add} disabled={!chapters || !(exact ?? (suggestions.length === 1 ? suggestions[0] : null))}>
          <Plus size={13} /> Add
        </button>
      </div>
      {chosen.length > 0 && (
        <div className="pm-chipset" style={{ marginTop: 10 }}>
          {chosen.map((c) => (
            <span key={c.code} className="pm-chip pm-chip--on pm-chip--static">
              {multiBook ? `${c.bookLabel} · ` : ""}{c.number}. {c.label}
              <button type="button" className="pm-chip__x" aria-label={`Remove ${c.label}`} onClick={() => remove(c.code)}>
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function shortBook(label: string): string {
  // "Class X History (India and the Contemporary World – II)" -> "History"
  return label.replace(/^Class\s+[A-Z0-9]+\s+/i, "").replace(/\s*\(.*\)\s*$/, "");
}
