"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError, type BookStatus, type Subject } from "@/lib/api";
import { plan, type SortedFile } from "@/lib/bookFiles";
import { getPlatformKey } from "@/lib/session";

/**
 * Loading a whole language in one go.
 *
 * Hindi is four books (Kshitij, Kritika, Sparsh, Sanchayan) and each book is a contents
 * page plus a dozen or more chapter PDFs, every one of which the Books page takes one
 * upload at a time. Here the whole folder is dropped at once: NCERT's own filenames say
 * which book and which chapter each PDF is, so the files sort themselves, and for every
 * book the same steps then run without anyone watching -- curriculum, contents page,
 * chapters in order, embedding, and the concept families the book suggests.
 *
 * Books run side by side and the chapters of one book run one after another: a chapter
 * upload writes taxonomy rows the next one may reuse, so two chapters of the same book in
 * flight together would race, while two different books share nothing.
 *
 * Everything is resumable by re-dropping the same folder: a chapter the server already
 * holds is skipped, a contents page already on file is skipped, and a curriculum already
 * set up is left alone. A browser tab that is closed mid-run loses only the chapters that
 * had not started.
 */

type Phase = "waiting" | "running" | "done" | "failed";

interface BookRun {
  subject: string;
  label: string;
  phase: Phase;
  step: string;
  done: number;
  total: number;
  lines: { text: string; bad?: boolean }[];
}

const LANGUAGES: { key: string; label: string; prefix: string; fallback: string | null; hint: string }[] = [
  {
    key: "hindi", label: "Hindi (four books)", prefix: "X.HIN.", fallback: null,
    hint: "Drop NCERT's own files: jhks1ps.pdf, jhks101.pdf ... for Kshitij; jhkr1 for Kritika, jhsp1 for Sparsh, jhsy1 for Sanchayan. Every file finds its book by name.",
  },
  {
    key: "tamil", label: "Tamil", prefix: "X.TAM", fallback: "X.TAM",
    hint: "The cbsetamil.com book has no NCERT codes, so name the files 00-contents.pdf and NN-title.pdf (01-annai-mozhiye.pdf). Anything without a book in its name goes to Tamil here.",
  },
  {
    key: "any", label: "Any NCERT book", prefix: "", fallback: null,
    hint: "Maths, Science, the four Social Science books, the two English readers and the four Hindi books, mixed in one folder. Files are routed by NCERT code.",
  },
];

export default function BulkBooksPage() {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [language, setLanguage] = useState(LANGUAGES[0]);
  const [edition, setEdition] = useState("Reprint 2026-27");
  const [files, setFiles] = useState<File[]>([]);
  const [statuses, setStatuses] = useState<Record<string, BookStatus | null>>({});
  const [embedAfter, setEmbedAfter] = useState(true);
  const [familiesAfter, setFamiliesAfter] = useState(true);
  const [runs, setRuns] = useState<Record<string, BookRun>>({});
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    const key = getPlatformKey();
    if (!key) return;
    api.subjects(key).then(({ subjects: s }) => setSubjects(s)).catch(() => setSubjects([]));
  }, []);

  const labelOf = (code: string) => subjects.find((s) => s.subject_code === code)?.label ?? code;

  const sorted = useMemo(() => plan(files, language.fallback), [files, language]);

  // Only books of the chosen language are loaded; a Maths file in a Hindi folder is
  // reported, not quietly loaded into Maths.
  const inScope = useMemo(() => {
    const out = new Map<string, SortedFile[]>();
    for (const [subject, list] of sorted) {
      if (subject.startsWith(language.prefix)) out.set(subject, list);
    }
    return out;
  }, [sorted, language]);
  const outOfScope = useMemo(
    () => [...sorted].filter(([subject]) => !subject.startsWith(language.prefix)),
    [sorted, language],
  );
  const unrouted = useMemo(
    () => files.filter((f) => !plan([f], language.fallback).size),
    [files, language],
  );

  // The server's view of each book, so the plan can say what is already there.
  useEffect(() => {
    const key = getPlatformKey();
    if (!key) return;
    for (const subject of inScope.keys()) {
      if (subject in statuses) continue;
      setStatuses((s) => ({ ...s, [subject]: null }));
      api.bookStatus(key, subject)
        .then((st) => setStatuses((s) => ({ ...s, [subject]: st })))
        .catch(() => setStatuses((s) => ({ ...s, [subject]: null })));
    }
  }, [inScope, statuses]);

  function loadedChapters(subject: string): Set<number> {
    const st = statuses[subject];
    const out = new Set<number>();
    for (const entry of Object.values(st?.files ?? {})) {
      if (typeof entry.chapter === "number") out.add(entry.chapter);
    }
    return out;
  }

  function addFiles(list: FileList | File[] | null) {
    if (!list) return;
    const incoming = Array.from(list);
    setFiles((have) => {
      const seen = new Set(have.map((f) => f.name));
      return [...have, ...incoming.filter((f) => !seen.has(f.name))];
    });
  }

  function describe(err: unknown): string {
    if (!(err instanceof ApiError)) return "Could not reach the API.";
    try {
      const detail = JSON.parse(err.message).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) return detail.map((d) => d.msg ?? String(d)).join("; ");
    } catch {
      /* raw text */
    }
    return err.message || `HTTP ${err.status}`;
  }

  function update(subject: string, patch: Partial<BookRun>) {
    setRuns((r) => ({ ...r, [subject]: { ...r[subject], ...patch } }));
  }
  function say(subject: string, text: string, bad = false) {
    setRuns((r) => ({
      ...r,
      [subject]: { ...r[subject], lines: [...r[subject].lines, { text, bad }] },
    }));
  }

  async function runBook(key: string, subject: string, list: SortedFile[]) {
    const contents = list.find((f) => f.role === "contents");
    const chapters = list.filter((f) => f.role === "chapter");
    const already = loadedChapters(subject);
    const todo = chapters.filter((f) => f.chapter !== null && !already.has(f.chapter));
    const skipped = chapters.length - todo.length;
    let status = statuses[subject] ?? null;
    let failed = 0;

    update(subject, { phase: "running", total: todo.length, done: 0 });
    try {
      // 1. curriculum -- the board units and chapter list the book is checked against
      if (!status?.curriculum_ready) {
        update(subject, { step: "setting up the curriculum" });
        const r = await api.setupCurriculum(key, subject);
        say(subject, `curriculum: ${r.board_units} units, ${r.chapters} chapters`);
      }
      // 2. contents page -- the oracle; the server refuses a chapter until it has one
      if (contents && !status?.contents_uploaded) {
        update(subject, { step: `contents page ${contents.file.name}` });
        const r = await api.uploadContents(key, subject, contents.file, edition);
        say(subject, `contents page: ${r.chapters_expected} chapters expected`);
      } else if (!contents && !status?.contents_uploaded) {
        say(subject, "no contents page in the drop and none on the server: chapters cannot be checked, stopping this book", true);
        update(subject, { phase: "failed", step: "needs a contents page" });
        return;
      } else if (contents) {
        say(subject, "contents page already on the server, skipped");
      }
      if (skipped) say(subject, `${skipped} chapter${skipped === 1 ? "" : "s"} already loaded, skipped`);

      // 3. chapters, one after another
      let done = 0;
      for (const f of todo) {
        update(subject, { step: `chapter ${f.chapter}: ${f.file.name}` });
        try {
          const r = await api.uploadChapter(key, subject, f.file);
          say(subject, `ch${r.chapter} ${r.title}: ${r.sections} sections, ${r.chunks} chunks`);
        } catch (err) {
          failed += 1;
          say(subject, `${f.file.name}: ${describe(err)}`, true);
        }
        done += 1;
        update(subject, { done });
      }

      status = await api.bookStatus(key, subject);

      // 4. embed, one batch per request so no single call outlives the proxy
      if (embedAfter && status.embeddings_configured && status.chunks > status.embedded) {
        update(subject, { step: "embedding" });
        for (;;) {
          const r = await api.embedBatch(key, subject);
          update(subject, { step: `embedding, ${r.remaining} to go` });
          if (r.done) break;
        }
        say(subject, "embedded");
      } else if (embedAfter && !status.embeddings_configured) {
        say(subject, "embedding service not configured, nothing embedded", true);
      }

      // 5. concept families: everything the book suggests that does not exist yet
      if (familiesAfter && status.chunks > 0) {
        update(subject, { step: "creating concept families" });
        const proposals = await api.proposeFamilies(key, subject);
        const fresh = proposals.families.filter((f) => !f.already_exists);
        if (fresh.length) {
          const r = await api.createFamilies(key, subject, fresh);
          say(subject, `${r.created} concept families created, ${proposals.existing} existed`);
        } else {
          say(subject, `concept families: all ${proposals.existing} already exist`);
        }
      }

      update(subject, {
        phase: failed ? "failed" : "done",
        step: failed ? `${failed} chapter${failed === 1 ? "" : "s"} refused, see below` : "complete",
      });
    } catch (err) {
      say(subject, describe(err), true);
      update(subject, { phase: "failed", step: "stopped" });
    } finally {
      api.bookStatus(key, subject)
        .then((st) => setStatuses((s) => ({ ...s, [subject]: st })))
        .catch(() => undefined);
    }
  }

  async function runAll() {
    const key = getPlatformKey();
    if (!key || !inScope.size) return;
    setBusy(true);
    const initial: Record<string, BookRun> = {};
    for (const subject of inScope.keys()) {
      initial[subject] = {
        subject, label: labelOf(subject), phase: "waiting", step: "queued",
        done: 0, total: 0, lines: [],
      };
    }
    setRuns(initial);
    await Promise.all([...inScope].map(([subject, list]) => runBook(key, subject, list)));
    setBusy(false);
  }

  const totalChapters = [...inScope.values()].reduce(
    (n, list) => n + list.filter((f) => f.role === "chapter").length, 0,
  );

  return (
    <main>
      <div className="hero">
        <p className="eyebrow">Knowledge base</p>
        <h1>Load a whole language</h1>
        <p className="lede">
          Drop every PDF of every book at once. Each file finds its book and chapter from its
          name, and the books load side by side: curriculum, contents page, chapters,
          embedding and concept families, with nothing to click per file. One book at a
          time is still on the <Link href="/platform/books">Books</Link> page.
        </p>
      </div>

      <div className="card" style={{ marginTop: 22 }}>
        <div className="grid two">
          <div className="field">
            <label htmlFor="language">Language</label>
            <select
              id="language"
              value={language.key}
              disabled={busy}
              onChange={(e) => setLanguage(LANGUAGES.find((l) => l.key === e.target.value) ?? LANGUAGES[0])}
            >
              {LANGUAGES.map((l) => (
                <option key={l.key} value={l.key}>{l.label}</option>
              ))}
            </select>
            <p className="hint">{language.hint}</p>
          </div>
          <div className="field">
            <label htmlFor="edition">Edition</label>
            <input id="edition" value={edition} disabled={busy} onChange={(e) => setEdition(e.target.value)} />
            <p className="hint">Printed on the prelims page. Recorded for every book in this drop.</p>
          </div>
        </div>
        <div className="row" style={{ marginTop: 4 }}>
          <label className="small">
            <input type="checkbox" checked={embedAfter} disabled={busy} onChange={(e) => setEmbedAfter(e.target.checked)} />{" "}
            embed each book when its chapters are in
          </label>
          <label className="small">
            <input type="checkbox" checked={familiesAfter} disabled={busy} onChange={(e) => setFamiliesAfter(e.target.checked)} />{" "}
            create every concept family the book suggests
          </label>
        </div>
      </div>

      <div className="section-head">
        <h2>1 &middot; Files</h2>
      </div>
      <div
        className="card"
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
        style={{
          borderStyle: "dashed",
          borderColor: dragging ? "var(--mark)" : undefined,
          background: dragging ? "var(--mark-soft)" : undefined,
        }}
      >
        <p className="cardnote" style={{ marginBottom: 14 }}>
          Drag the PDFs here, pick them, or pick the whole folder. Add more than once: a
          second drop adds to the first. Answers and appendices are recognised and left
          out; the contents page of each book goes first automatically.
        </p>
        <div className="row">
          <label className="btn secondary" style={{ cursor: "pointer" }}>
            Pick files
            <input type="file" accept="application/pdf" multiple hidden disabled={busy}
              onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
          </label>
          <label className="btn secondary" style={{ cursor: "pointer" }}>
            Pick a folder
            <input type="file" hidden disabled={busy}
              // @ts-expect-error non-standard but every desktop browser honours it
              webkitdirectory="" directory=""
              onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
          </label>
          {files.length > 0 && !busy && (
            <button className="ghost" onClick={() => { setFiles([]); setRuns({}); }}>Clear</button>
          )}
          <span className="small muted">{files.length ? `${files.length} files` : "nothing yet"}</span>
        </div>
      </div>

      {files.length > 0 && (
        <>
          <div className="section-head">
            <h2>2 &middot; Plan</h2>
          </div>
          {inScope.size === 0 && (
            <div className="notice warn">
              None of these files belongs to a {language.label} book by its name. Check the
              language above, or for Tamil name the files NN-title.pdf.
            </div>
          )}
          <div className="stack">
            {[...inScope].map(([subject, list]) => {
              const st = statuses[subject];
              const already = loadedChapters(subject);
              const contents = list.find((f) => f.role === "contents");
              const chapters = list.filter((f) => f.role === "chapter");
              const fresh = chapters.filter((f) => f.chapter !== null && !already.has(f.chapter));
              const skipped = list.filter((f) => f.role === "skip");
              return (
                <div className="card" key={subject}>
                  <div className="row between">
                    <div>
                      <h3 style={{ margin: 0 }}>{labelOf(subject)}</h3>
                      <p className="small mono muted" style={{ margin: 0 }}>{subject}</p>
                    </div>
                    <span className="small muted">
                      {st === undefined || st === null
                        ? "asking the server…"
                        : `${st.loaded_chapters}/${st.expected_chapters || "?"} chapters on the server`}
                    </span>
                  </div>
                  <ul className="famlist" style={{ marginTop: 12 }}>
                    <li>
                      <span className="fam-l">curriculum</span>
                      <span className="fam-m" style={{ marginLeft: 0 }}>
                        {st?.curriculum_ready ? "already set up" : "will be set up"}
                      </span>
                    </li>
                    <li className={contents && st?.contents_uploaded ? "have" : undefined}>
                      <span className="fam-l">contents page</span>
                      <span className="fam-m" style={{ marginLeft: 0 }}>
                        {contents
                          ? st?.contents_uploaded ? `${contents.file.name}, already on the server` : contents.file.name
                          : st?.contents_uploaded ? "already on the server" : "missing: this book cannot load without it"}
                      </span>
                    </li>
                    <li>
                      <span className="fam-l">chapters</span>
                      <span className="fam-m" style={{ marginLeft: 0 }}>
                        {fresh.length} to upload
                        {chapters.length - fresh.length > 0 ? `, ${chapters.length - fresh.length} already loaded` : ""}
                        {fresh.length ? `: ${fresh.map((f) => f.chapter).join(", ")}` : ""}
                      </span>
                    </li>
                    {skipped.map((f) => (
                      <li key={f.file.name} className="have">
                        <span className="fam-l">{f.file.name}</span>
                        <span className="fam-m" style={{ marginLeft: 0 }}>{f.note}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>

          {(outOfScope.length > 0 || unrouted.length > 0) && (
            <div className="notice warn" style={{ marginTop: 14 }}>
              Not loaded in this run:{" "}
              {outOfScope.map(([subject, list]) => `${list.length} file${list.length === 1 ? "" : "s"} of ${labelOf(subject)}`).join(", ")}
              {outOfScope.length && unrouted.length ? "; " : ""}
              {unrouted.length > 0 && (
                <>
                  {unrouted.length} whose name says no book ({unrouted.slice(0, 5).map((f) => f.name).join(", ")}
                  {unrouted.length > 5 ? ", …" : ""}). Rename those NN-title.pdf, or choose Tamil so they go to the Tamil book.
                </>
              )}
            </div>
          )}

          <div className="row" style={{ marginTop: 18 }}>
            <button onClick={runAll} disabled={busy || !inScope.size}>
              {busy ? "Loading…" : `Load ${inScope.size} book${inScope.size === 1 ? "" : "s"}, ${totalChapters} chapter files`}
            </button>
            <span className="small muted">
              Hindi chapters are read by OCR and take minutes each. Leave this tab open; a
              re-drop of the same folder later picks up where it stopped.
            </span>
          </div>
        </>
      )}

      {Object.keys(runs).length > 0 && (
        <>
          <div className="section-head">
            <h2>3 &middot; Progress</h2>
          </div>
          <div className="stack">
            {Object.values(runs).map((run) => (
              <div className="card" key={run.subject}>
                <div className="row between">
                  <h3 style={{ margin: 0 }}>{run.label}</h3>
                  <span
                    className="small mono"
                    style={{ color: run.phase === "failed" ? "var(--mark)" : run.phase === "done" ? "var(--verify)" : undefined }}
                  >
                    {run.phase === "running" ? run.step : run.phase === "waiting" ? "queued" : run.step}
                  </span>
                </div>
                {run.total > 0 && (
                  <div className={`progress${run.phase === "done" ? " verify" : ""}`} style={{ marginTop: 10 }}>
                    <div style={{ width: `${Math.round((run.done / run.total) * 100)}%` }} />
                  </div>
                )}
                {run.lines.length > 0 && (
                  <div style={{ marginTop: 10 }}>
                    {run.lines.map((line, i) => (
                      <p key={i} className="small mono" style={{ margin: "2px 0", color: line.bad ? "var(--mark)" : undefined }}>
                        {line.text}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </main>
  );
}
