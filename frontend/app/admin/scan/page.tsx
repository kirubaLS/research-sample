"use client";

import { useEffect, useState } from "react";
import { Scanner } from "@/components/Scanner";
import type { ScannedPage } from "@/lib/pageStore";
import { api, ApiError, ApiUnreachable, PaperSummary, RosterRow, SectionSummary } from "@/lib/api";
import { getApiKey } from "@/lib/session";

function explain(err: unknown): string {
  if (err instanceof ApiUnreachable) return "Could not reach the server.";
  if (err instanceof ApiError) return `Request failed (${err.status}).`;
  return "Something went wrong.";
}

/** The camera hands back a Blob per page; the upload route wants a File per page, in order. */
function toFiles(pages: ScannedPage[]): File[] {
  return pages
    .slice()
    .sort((a, b) => a.index - b.index)
    .map((p, i) => new File([p.blob], `page-${i + 1}.jpg`, { type: p.blob.type || "image/jpeg" }));
}

export default function ScanPage() {
  const [sessionId] = useState(() => crypto.randomUUID());
  const [mode, setMode] = useState<"cover" | "script">("cover");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [sections, setSections] = useState<SectionSummary[]>([]);
  const [students, setStudents] = useState<RosterRow[]>([]);
  const [paperId, setPaperId] = useState("");
  const [sectionId, setSectionId] = useState("");
  const [studentId, setStudentId] = useState("");

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    (async () => {
      try {
        const [list, overview] = await Promise.all([api.listPapers(key), api.overview(key)]);
        setPapers(list.assessments.filter((p) => p.ready_for_answer_sheets));
        setSections(overview.sections);
      } catch (err) {
        setError(explain(err));
      }
    })();
  }, []);

  useEffect(() => {
    const key = getApiKey();
    if (!key || !sectionId) {
      setStudents([]);
      return;
    }
    (async () => {
      try {
        setStudents((await api.roster(key, sectionId)).students);
      } catch (err) {
        setError(explain(err));
      }
    })();
  }, [sectionId]);

  async function upload(pages: ScannedPage[]) {
    // The cover is captured to help the person line up the script, but a script's pages
    // are what actually gets stored -- the cover carries no marks of its own to read.
    if (mode === "cover") {
      setMode("script");
      return;
    }
    const key = getApiKey();
    if (!key || !paperId || !studentId) {
      setError("Choose a paper and a student before scanning the script.");
      return;
    }
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const doc = await api.uploadAnswerPages(key, paperId, studentId, toFiles(pages));
      setStatus(
        `${doc.page_count} page${doc.page_count === 1 ? "" : "s"} saved against this student's ` +
          "script. Open the Answer sheet screen to enter marks against it.",
      );
      setMode("cover");
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(false);
    }
  }

  const ready = !!paperId && !!studentId;

  return (
    <main className="narrow">
      <div className="hero">
        <p className="eyebrow">Answer scripts</p>
        <h1>{mode === "cover" ? "Scan the cover page" : "Scan every page"}</h1>
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <label>
          Paper
          <select value={paperId} onChange={(e) => setPaperId(e.target.value)}>
            <option value="">Choose a paper</option>
            {papers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}{p.paper_code ? ` (${p.paper_code})` : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          Section
          <select value={sectionId} onChange={(e) => { setSectionId(e.target.value); setStudentId(""); }}>
            <option value="">Choose a section</option>
            {sections.map((s) => (
              <option key={s.section_id} value={s.section_id}>{s.label}</option>
            ))}
          </select>
        </label>
        <label>
          Student
          <select value={studentId} onChange={(e) => setStudentId(e.target.value)} disabled={!sectionId}>
            <option value="">Choose a student</option>
            {students.map((s) => (
              <option key={s.student_id} value={s.student_id}>{s.name}</option>
            ))}
          </select>
        </label>
        {!ready && (
          <p className="muted" style={{ marginTop: 8 }}>
            Choose a paper and a student before scanning -- a script has to know whose it is
            and against what before a single page is captured.
          </p>
        )}
      </div>

      <p className="lede" style={{ marginBottom: 20 }}>
        {mode === "cover"
          ? "The cover carries the question numbers and marks. One clear frame is enough."
          : "Capture each page in order. Retake replaces a single page and keeps its position."}
      </p>
      <div className="card" style={{ opacity: ready ? 1 : 0.5, pointerEvents: ready ? "auto" : "none" }}>
        <Scanner sessionId={sessionId} mode={mode} onComplete={upload} />
      </div>
      {busy && <p className="notice" style={{ marginTop: 14 }}>Saving the script…</p>}
      {status && <p className="notice" style={{ marginTop: 14 }}>{status}</p>}
      {error && <p className="notice warn" style={{ marginTop: 14 }}>{error}</p>}
    </main>
  );
}
