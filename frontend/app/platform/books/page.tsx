"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, BookStatus } from "@/lib/api";
import { getPlatformKey } from "@/lib/session";

const SUBJECTS = [
  ["X.MATH", "Class X Mathematics"],
  ["X.SCI", "Class X Science"],
] as const;

type Line = { text: string; bad?: boolean };

/**
 * Loading a book without a shell.
 *
 * The contents page goes first and stays first: it is the oracle every chapter is checked
 * against, and the server refuses a chapter until it has one.
 */
export default function BooksPage() {
  const [subject, setSubject] = useState<string>("X.MATH");
  const [edition, setEdition] = useState("Reprint 2026-27");
  const [status, setStatus] = useState<BookStatus | null>(null);
  const [log, setLog] = useState<Line[]>([]);
  const [busy, setBusy] = useState(false);

  const say = (text: string, bad = false) => setLog((l) => [...l, { text, bad }]);

  const refresh = useCallback(async () => {
    const key = getPlatformKey();
    if (!key) return;
    try {
      setStatus(await api.bookStatus(key, subject));
    } catch {
      setStatus(null);
    }
  }, [subject]);

  useEffect(() => {
    refresh();
  }, [refresh]);

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

  const ready = status?.contents_uploaded ?? false;

  return (
    <main>
      <div className="hero">
        <p className="eyebrow">Knowledge base</p>
        <h1>Load a book</h1>
        <p className="lede">
          The chapter tree, the taught content and the exercises come from the NCERT book.
          Upload the contents page first &mdash; every chapter is checked against it, and one
          that disagrees is refused rather than loaded.
        </p>
      </div>

      <div className="card" style={{ marginTop: 22 }}>
        <div className="grid two">
          <div className="field">
            <label htmlFor="subject">Subject</label>
            <select id="subject" value={subject} onChange={(e) => setSubject(e.target.value)}>
              {SUBJECTS.map(([code, label]) => (
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
        <h2>1 &middot; Contents page</h2>
      </div>
      <div className="card">
        <p className="cardnote" style={{ marginBottom: 14 }}>
          The prelims file &mdash; <span className="mono">00-contents.pdf</span>. It lists every
          section of every chapter, which is what makes an extraction checkable rather than
          merely plausible.
        </p>
        <input type="file" accept="application/pdf" onChange={sendContents} disabled={busy} />
      </div>

      <div className="section-head">
        <h2>2 &middot; Chapters</h2>
      </div>
      <div className="card">
        <p className="cardnote" style={{ marginBottom: 14 }}>
          Named <span className="mono">NN-slug.pdf</span>, e.g.{" "}
          <span className="mono">12-surface-areas-and-volumes.pdf</span>. Select them all at
          once. The answers file and the appendices are refused: the answers file matches
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
        <h2>3 &middot; Embed</h2>
      </div>
      <div className="card">
        <p className="cardnote" style={{ marginBottom: 14 }}>
          Without vectors only an exact match resolves, so <span className="mono">PRACTISED</span>,{" "}
          <span className="mono">ADAPTED</span> and <span className="mono">NOVEL</span> all
          collapse and the competency tier falls back to whatever the paper declares.
        </p>
        {status && !status.embeddings_configured && (
          <div className="notice warn" style={{ marginBottom: 14 }}>
            No embedding key on the API service. Set{" "}
            <span className="mono">YAADHUM_JINA_API_KEY</span> and redeploy.
          </div>
        )}
        <button onClick={embed} disabled={busy || !status?.chunks || !status?.embeddings_configured}>
          {busy ? "Working…" : `Embed ${status ? status.chunks - status.embedded : 0} chunks`}
        </button>
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
