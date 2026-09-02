"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  ApiError,
  BookStatus,
  type FamilyProposals,
  type Subject,
} from "@/lib/api";
import { getPlatformKey } from "@/lib/session";

type Line = { text: string; bad?: boolean };

/**
 * Loading a book without a shell.
 *
 * The contents page goes first and stays first: it is the oracle every chapter is checked
 * against, and the server refuses a chapter until it has one.
 */
export default function BooksPage() {
  // From the deployment, never a list written into this screen: this is the page that
  // loads a book, so it is the last place that should be told in advance which books exist.
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subject, setSubject] = useState<string>("");
  const [edition, setEdition] = useState("Reprint 2026-27");
  const [status, setStatus] = useState<BookStatus | null>(null);
  const [log, setLog] = useState<Line[]>([]);
  const [busy, setBusy] = useState(false);
  const [families, setFamilies] = useState<FamilyProposals | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());

  const say = (text: string, bad = false) => setLog((l) => [...l, { text, bad }]);

  const refresh = useCallback(async () => {
    const key = getPlatformKey();
    // Nothing to ask about until the subject list has arrived.
    if (!key || !subject) return;
    try {
      setStatus(await api.bookStatus(key, subject));
    } catch {
      setStatus(null);
    }
  }, [subject]);

  useEffect(() => {
    const key = getPlatformKey();
    if (!key) return;
    api
      .subjects(key)
      .then(({ subjects: found }) => {
        setSubjects(found);
        setSubject((current) => current || found[0]?.subject_code || "");
      })
      .catch(() => setSubjects([]));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Cleared when the subject changes: the proposals belong to one book.
  useEffect(() => {
    setFamilies(null);
    setPicked(new Set());
  }, [subject]);

  async function loadFamilies() {
    const key = getPlatformKey();
    if (!key || !subject) return;
    setBusy(true);
    try {
      const out = await api.proposeFamilies(key, subject);
      setFamilies(out);
      say(`${out.proposed} families suggested by the book, ${out.existing} already exist.`);
    } catch (err) {
      say(describe(err), true);
    } finally {
      setBusy(false);
    }
  }

  async function saveFamilies() {
    const key = getPlatformKey();
    if (!key || !subject || !families) return;
    setBusy(true);
    try {
      const chosen = families.families.filter((f) => picked.has(f.code));
      const out = await api.createFamilies(key, subject, chosen);
      say(`${out.created} created, ${out.skipped} already existed.`);
      setPicked(new Set());
      setFamilies(await api.proposeFamilies(key, subject));
    } catch (err) {
      say(describe(err), true);
    } finally {
      setBusy(false);
    }
  }

  function describe(err: unknown): string {
    if (!(err instanceof ApiError)) return "Could not reach the API.";
    if (err.status === 404) {
      // Two very different causes, and the API cannot distinguish them for us: the
      // operator key is rejected with 404 on purpose, so a wrong key must not confirm
      // that anything exists. Version skew is the far likelier one in practice -- this
      // page ships with API routes that an older backend build does not have.
      return (
        "The API returned 404 for this route. Most likely the backend has not been " +
        "redeployed with the book-upload routes yet -- deploy the same commit as this " +
        "site. (A rejected operator key also answers 404, deliberately.)"
      );
    }
    // FastAPI wraps the message in {"detail": ...}; the raw JSON buries a clear sentence
    try {
      const body = JSON.parse(err.message);
      const detail = body.detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) return detail.map((d) => d.msg ?? String(d)).join("; ");
    } catch {
      /* not JSON -- fall through to the raw text */
    }
    return err.message;
  }

  async function sendContents(event: React.ChangeEvent<HTMLInputElement>) {
    const key = getPlatformKey();
    const file = event.target.files?.[0];
    if (!key || !file) return;
    setBusy(true);
    try {
      const result = await api.uploadContents(key, subject, file, edition);
      say(`contents page: ${result.chapters_expected} chapters, ${result.sections_expected} sections expected`);
      await refresh();
    } catch (err) {
      say(describe(err), true);
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  async function sendChapters(event: React.ChangeEvent<HTMLInputElement>) {
    const key = getPlatformKey();
    const files = Array.from(event.target.files ?? []);
    if (!key || !files.length) return;
    setBusy(true);
    // sequential on purpose: each upload writes taxonomy rows the next one may reuse,
    // and parallel requests would race to create the same chapter node
    for (const file of files.sort((a, b) => a.name.localeCompare(b.name))) {
      try {
        const r = await api.uploadChapter(key, subject, file);
        say(
          `ch${r.chapter} ${r.title} - ${r.sections} sections, ${r.chunks} chunks` +
            (r.board_unit_mapped ? "" : " - no board unit yet"),
          !r.board_unit_mapped,
        );
      } catch (err) {
        say(`${file.name}: ${describe(err)}`, true);
      }
    }
    setBusy(false);
    event.target.value = "";
    await refresh();
  }

  async function embed() {
    const key = getPlatformKey();
    if (!key) return;
    setBusy(true);
    try {
      // one batch per request: a single call embedding everything would sit long enough
      // for a proxy to cut it off, and a dropped request would cost the whole run
      for (;;) {
        const r = await api.embedBatch(key, subject);
        if (r.embedded) say(`embedded ${r.embedded}, ${r.remaining} to go`);
        if (r.done) break;
      }
      say("embedding complete");
      await refresh();
    } catch (err) {
      say(describe(err), true);
    } finally {
      setBusy(false);
      await refresh();
    }
  }

  async function setupCurriculum() {
    const key = getPlatformKey();
    if (!key) return;
    setBusy(true);
    try {
      const r = await api.setupCurriculum(key, subject);
      say(`${r.label}: ${r.board_units} board units, ${r.chapters} chapters mapped`);
      await refresh();
    } catch (err) {
      say(describe(err), true);
    } finally {
      setBusy(false);
    }
  }

  const curriculumReady = status?.curriculum_ready ?? false;
  const ready = status?.contents_uploaded ?? false;

  return (
    <main>
      <div className="hero">
        <p className="eyebrow">Knowledge base</p>
        <h1>Load a book</h1>
        <p className="lede">
          The chapter tree, the taught content and the exercises come from the NCERT book.
          Upload the contents page first. Every chapter is checked against it, and one
          that disagrees is refused rather than loaded.
        </p>
      </div>

      <div className="card" style={{ marginTop: 22 }}>
        <div className="grid two">
          <div className="field">
            <label htmlFor="subject">Subject</label>
            <select id="subject" value={subject} onChange={(e) => setSubject(e.target.value)}>
              {subjects.map(({ subject_code: code, label }) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="edition">Edition</label>
            <input id="edition" value={edition} onChange={(e) => setEdition(e.target.value)} />
            <p className="hint">Printed on the prelims page. Recorded so a reprint that moves section numbers is detectable.</p>
          </div>
        </div>
      </div>

      {status && (
        <div className="grid three" style={{ marginTop: 18 }}>
          <div className="stat">
            <span className="value">
              {status.loaded_chapters}/{status.expected_chapters || "?"}
            </span>
            <span className="label">chapters loaded</span>
          </div>
          <div className="stat">
            <span className="value">{status.chunks}</span>
            <span className="label">chunks</span>
          </div>
          <div className="stat">
            <span className="value">{status.embedded}</span>
            <span className="label">embedded</span>
          </div>
        </div>
      )}

      {status && <div className="notice" style={{ marginTop: 18 }}>{status.next}</div>}

      <div className="section-head">
        <h2>1 &middot; Curriculum</h2>
      </div>
      <div className="card">
        <p className="cardnote" style={{ marginBottom: 14 }}>
          The board units and their weightage, from CBSE&apos;s syllabus rather than from the
          book. A unit may span several chapters (Algebra covers four) or exist where no
          chapter does, so it cannot be derived from the book and has to be in place before
          one is loaded.
        </p>
        {curriculumReady ? (
          <p className="small mono">Already set up.</p>
        ) : (
          <button onClick={setupCurriculum} disabled={busy}>
            {busy ? "Working…" : "Set up the curriculum"}
          </button>
        )}
      </div>

      <div className="section-head">
        <h2>2 &middot; Contents page</h2>
      </div>
      <div className="card">
        <p className="cardnote" style={{ marginBottom: 14 }}>
          The prelims file, which NCERT names <span className="mono">jemh1ps.pdf</span> for
          Maths. It lists every section of every chapter, which is what makes an extraction
          checkable rather than merely plausible.
        </p>
        <input
          type="file"
          accept="application/pdf"
          onChange={sendContents}
          disabled={busy || !curriculumReady}
        />
        {!curriculumReady && <p className="hint">Set up the curriculum first.</p>}
      </div>

      <div className="section-head">
        <h2>3 &middot; Chapters</h2>
      </div>
      <div className="card">
        <p className="cardnote" style={{ marginBottom: 14 }}>
          Select them all at once, under NCERT&apos;s own names (
          <span className="mono">jemh101.pdf</span>) or as{" "}
          <span className="mono">NN-slug.pdf</span>, with no renaming needed. The contents
          page, the answers and the appendices are refused: the answers file matches
          &ldquo;EXERCISE&rdquo; 31 times and would load the answer key as practice content.
        </p>
        <input
          type="file"
          accept="application/pdf"
          multiple
          onChange={sendChapters}
          disabled={busy || !ready}
        />
        {!ready && <p className="hint">Upload the contents page first.</p>}
      </div>

      <div className="section-head">
        <h2>4 &middot; Embed</h2>
      </div>
      <div className="card">
        <p className="cardnote" style={{ marginBottom: 14 }}>
          Without vectors only an exact match resolves, so <span className="mono">PRACTISED</span>,{" "}
          <span className="mono">ADAPTED</span> and <span className="mono">NOVEL</span> all
          collapse and the competency tier falls back to whatever the paper declares.
        </p>
        {status && !status.embeddings_configured && (
          <div className="notice warn" style={{ marginBottom: 14 }}>
            The embedding service is not configured for this deployment, so nothing can be
            embedded yet. Add its key and publish again.
          </div>
        )}
        <button onClick={embed} disabled={busy || !status?.chunks || !status?.embeddings_configured}>
          {busy ? "Working…" : `Embed ${status ? status.chunks - status.embedded : 0} chunks`}
        </button>
      </div>

      {status && status.coverage?.length > 0 && (
        <>
          <div className="section-head">
            <h2>Chapter by chapter</h2>
          </div>
          <div className="card">
            <p className="cardnote" style={{ marginBottom: 14 }}>
              A whole-book total hides the thing that matters. A chapter with no passages
              behind it can never be matched, so every question from it comes back saying
              no chapter matched, however healthy the total looks.
            </p>
            {status.chapters_with_nothing_behind_them.length > 0 && (
              <div className="notice warn" style={{ marginBottom: 14 }}>
                {status.chapters_with_nothing_behind_them.length} of{" "}
                {status.coverage.length} chapters have nothing behind them:{" "}
                {status.chapters_with_nothing_behind_them.join(", ")}. Upload those
                chapters before reading a paper that covers them.
              </div>
            )}
            <ul className="famlist">
              {status.coverage.map((c) => (
                <li key={c.chapter_code} className={c.chunks ? undefined : "have"}>
                  <span className="fam-l">{c.chapter}</span>
                  <span className="fam-m" style={{ marginLeft: 0 }}>
                    {c.chunks === 0
                      ? "nothing loaded"
                      : `${c.chunks} passages \u00b7 ${c.embedded} embedded \u00b7 ${c.with_a_section} carry a section`}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}

      <div className="section-head">
        <h2>5 &middot; Concept families</h2>
      </div>
      <div className="card">
        <p className="cardnote" style={{ marginBottom: 14 }}>
          A family is the learning area a report compares against itself over time. Chapter
          is too coarse to act on and section numbers move when the book is reprinted, so
          neither can carry a trend. Loading a book does not create these: a question can
          only be placed in a chapter that has them, so a chapter with none blocks every
          question that belongs to it. What a proposal run has already worked out comes
          first here; the book&rsquo;s own section headings fill in the chapters no run has
          covered.
        </p>

        {families === null ? (
          <button onClick={loadFamilies} disabled={busy || !status?.chunks}>
            {busy ? "Working…" : "Show what this book suggests"}
          </button>
        ) : (
          <>
            <p className="small" style={{ marginBottom: 12 }}>
              {families.proposed} suggested,{" "}
              {families.families.filter((f) => f.already_exists).length} of them already
              created. {families.existing} exist for this subject in total.
            </p>
            {families.without_a_section > 0 && (
              <div className="notice warn" style={{ marginBottom: 14 }}>
                {families.without_a_section} of these name no section of the chapter. They
                can be created, but a question can only be matched to a family by the
                section it came from, so a chapter whose families all lack one still has
                to be settled by a person question by question.
              </div>
            )}
            <ul className="famlist">
              {families.families.map((f) => (
                <li key={f.code} className={f.already_exists ? "have" : undefined}>
                  <label>
                    <input
                      type="checkbox"
                      checked={f.already_exists || picked.has(f.code)}
                      disabled={f.already_exists}
                      onChange={(e) => {
                        setPicked((was) => {
                          const next = new Set(was);
                          if (e.target.checked) next.add(f.code);
                          else next.delete(f.code);
                          return next;
                        });
                      }}
                    />
                    <span className="fam-l">{f.label}</span>
                  </label>
                  <span className="fam-m">
                    {f.chapter_label}
                    {/* Plain text, not an entity: this is a JS expression, and an entity
                        written here reaches the page as its own characters. */}
                    {f.from_sections.length > 0
                      ? ` \u00b7 section${f.from_sections.length > 1 ? "s" : ""} ${f.from_sections.join(", ")}`
                      : " \u00b7 no section named"}
                    {f.already_exists ? " \u00b7 created" : ""}
                  </span>
                </li>
              ))}
            </ul>
            <div className="row" style={{ marginTop: 14 }}>
              <button onClick={saveFamilies} disabled={busy || picked.size === 0}>
                {busy ? "Working…" : `Create ${picked.size} famil${picked.size === 1 ? "y" : "ies"}`}
              </button>
              <button
                className="ghost"
                onClick={() =>
                  setPicked(
                    new Set(
                      families.families.filter((f) => !f.already_exists).map((f) => f.code),
                    ),
                  )
                }
              >
                Select every one that is not created
              </button>
            </div>
          </>
        )}
      </div>

      {log.length > 0 && (
        <>
          <div className="section-head">
            <h2>Log</h2>
          </div>
          <div className="card">
            {log.map((line, i) => (
              <p key={i} className="small mono" style={{ color: line.bad ? "var(--mark)" : undefined }}>
                {line.text}
              </p>
            ))}
          </div>
        </>
      )}
    </main>
  );
}
