"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AnswerRow,
  AnswerSheet,
  api,
  ApiError,
  ApiUnreachable,
  PaperSummary,
  RosterRow,
  SectionSummary,
} from "@/lib/api";
import { getApiKey } from "@/lib/session";

/**
 * Entering one student's marks against a paper that has already been read and mapped.
 *
 * The screen is driven by the paper, never by the marks that happen to exist. Every
 * question on the paper gets a row whether or not anything has been recorded against it,
 * because the gap is the thing the person is looking for -- a list built from the marks
 * looks complete while missing exactly what needs attention.
 *
 * Nothing is saved until Confirm. A mark worth more than the question is refused by the
 * server rather than clamped, and the refusal is shown against the row that caused it:
 * a silently corrected typo becomes a plausible number nobody ever questions again.
 */

type Draft = { marks: string; state: string };

/**
 * Where a mark came from, said in words. The stored values name the part of the pipeline
 * that produced them, which means nothing to the person reading the sheet.
 */
const SOURCE_LABEL: Record<string, string> = {
  page_ocr: "read from the page",
  cover_ocr: "read from the cover",
  csv: "imported from a file",
  teacher: "confirmed by a teacher",
};

/** "1 mark" or "3 marks". A person should never have to read "mark(s)". */
function counted(n: number): string {
  return `${n} mark${n === 1 ? "" : "s"}`;
}

const STATES = [
  ["awarded", "Awarded"],
  ["zero", "Zero"],
  ["absent", "Absent"],
  ["not_offered", "Not offered (other choice attempted)"],
] as const;

export default function AnswersPage() {
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [sections, setSections] = useState<SectionSummary[]>([]);
  const [students, setStudents] = useState<RosterRow[]>([]);
  const [paperId, setPaperId] = useState("");
  const [sectionId, setSectionId] = useState("");
  const [studentId, setStudentId] = useState("");
  const [sheet, setSheet] = useState<AnswerSheet | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [rejected, setRejected] = useState<Record<string, string>>({});
  const [by, setBy] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  function explain(err: unknown): string {
    if (err instanceof ApiUnreachable) return "Could not reach the API.";
    if (!(err instanceof ApiError)) return "Something went wrong.";
    try {
      const body = JSON.parse(err.message) as { detail?: string };
      if (body.detail) return body.detail;
    } catch {
      /* not JSON */
    }
    return `Request failed (${err.status}).`;
  }

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    (async () => {
      try {
        const [list, overview] = await Promise.all([api.listPapers(key), api.overview(key)]);
        setPapers(list.assessments);
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

  const load = useCallback(async () => {
    const key = getApiKey();
    if (!key || !paperId || !studentId) return;
    setBusy("Opening the sheet");
    setError(null);
    setSaved(null);
    setRejected({});
    try {
      const body = await api.answerSheet(key, paperId, studentId);
      setSheet(body);
      // The draft starts from what is stored, so re-opening a half-entered sheet shows
      // the marks already there rather than blank boxes over the top of them.
      setDrafts(
        Object.fromEntries(
          body.questions.map((q) => [
            q.address,
            { marks: q.marks == null ? "" : String(q.marks), state: q.state ?? "awarded" },
          ]),
        ),
      );
    } catch (err) {
      setSheet(null);
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }, [paperId, studentId]);

  useEffect(() => {
    if (paperId && studentId) void load();
  }, [paperId, studentId, load]);

  const ready = papers.filter((p) => p.ready_for_answer_sheets);

  // The running total counts only what has actually been entered, and says so, so a
  // partial sheet can never be mistaken for a low score.
  const running = useMemo(() => {
    if (!sheet) return { scored: 0, available: 0, entered: 0 };
    let scored = 0;
    let available = 0;
    let entered = 0;
    for (const q of sheet.questions) {
      const d = drafts[q.address];
      if (!d || d.state === "not_offered") continue;
      available += q.max_marks;
      if (d.state === "awarded" && d.marks.trim() !== "") {
        scored += Number(d.marks);
        entered += 1;
      } else if (d.state === "zero" || d.state === "absent") {
        entered += 1;
      }
    }
    return { scored, available, entered };
  }, [sheet, drafts]);

  function set(address: string, patch: Partial<Draft>) {
    setDrafts((d) => ({ ...d, [address]: { ...d[address], ...patch } }));
    setRejected((r) => {
      if (!(address in r)) return r;
      const next = { ...r };
      delete next[address];
      return next;
    });
  }

  async function confirm() {
    const key = getApiKey();
    if (!key || !sheet) return;
    if (!by.trim()) {
      setError("Put your name to these marks before confirming them.");
      return;
    }
    const answers = sheet.questions
      .map((q) => {
        const d = drafts[q.address];
        if (!d) return null;
        if (d.state === "awarded") {
          if (d.marks.trim() === "") return null;   // untouched, not zero
          return { address: q.address, state: "awarded", marks: Number(d.marks) };
        }
        if (d.state === "zero") return { address: q.address, state: "awarded", marks: 0 };
        return { address: q.address, state: d.state };
      })
      .filter((a): a is { address: string; state: string; marks?: number } => a !== null);

    if (answers.length === 0) {
      setError("Nothing has been entered yet.");
      return;
    }

    setBusy("Confirming");
    setError(null);
    try {
      const out = await api.confirmAnswers(key, sheet.assessment.id, sheet.student.id, answers, by);
      // Re-read first, then say what happened: reloading clears the last message, so
      // setting it beforehand wiped the only confirmation the person ever gets.
      await load();
      setRejected(Object.fromEntries(out.rejected.map((r) => [r.address, r.reason])));
      setSaved(
        out.complete
          ? `Complete. ${out.scored} of ${out.available}, with ${counted(out.written)} recorded.`
          : `${counted(out.written)} recorded. ${out.remaining} question${
              out.remaining === 1 ? "" : "s"
            } still to enter, so ${out.scored} of ${out.available} is a running figure, not a result.`,
      );
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="wrap">
      <p className="eyebrow">Answer sheet</p>
      <h1>Enter one student&rsquo;s marks</h1>
      <p className="lede">
        Enter one student&rsquo;s marks against a paper that has already been scanned and
        mapped to the book. Every question appears, including the ones with nothing against
        them yet.
      </p>

      <section className="panel">
        <div className="picks">
          <label>
            <span>Paper</span>
            <select value={paperId} onChange={(e) => setPaperId(e.target.value)}>
              <option value="">Choose a paper…</option>
              {ready.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title} · {p.subject_code} · {p.questions} questions
                  {p.stage === "mapped" ? "" : " (not linked to the book yet)"}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Class</span>
            <select value={sectionId} onChange={(e) => setSectionId(e.target.value)}>
              <option value="">Choose a class…</option>
              {sections.map((s) => (
                <option key={s.section_id} value={s.section_id}>
                  {s.label} · {s.students} students
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Student</span>
            <select
              value={studentId}
              onChange={(e) => setStudentId(e.target.value)}
              disabled={!students.length}
            >
              <option value="">Choose a student…</option>
              {students.map((s) => (
                <option key={s.student_id} value={s.student_id}>
                  {s.roll_no}. {s.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {papers.length > 0 && ready.length === 0 && (
          <p className="warnish">
            No paper has been read yet. Scan and confirm one on the Question paper screen
            first. Marks have nothing to attach to until then.
          </p>
        )}
      </section>

      {error && <p className="error">{error}</p>}
      {busy && <p className="muted">{busy}…</p>}

      {sheet && (
        <>
          <section className="panel sticky">
            <div className="tally">
              <div>
                <strong>{sheet.student.name}</strong>
                <span className="muted"> · roll {sheet.student.roll_no}</span>
              </div>
              <div>
                <strong>
                  {running.scored} / {running.available}
                </strong>
                <span className="muted">
                  {" "}
                  · {running.entered} of {sheet.questions.length} entered
                </span>
              </div>
            </div>
            <div className="confirmrow">
              <label>
                <span className="sr">Your name</span>
                <input
                  value={by}
                  onChange={(e) => setBy(e.target.value)}
                  placeholder="Your name"
                  autoComplete="name"
                />
              </label>
              <button onClick={confirm} disabled={!!busy}>
                Confirm these marks
              </button>
            </div>
            {saved && <p className="ok">{saved}</p>}
          </section>

          <ol className="qlist">
            {sheet.questions.map((q) => (
              <Row
                key={q.address}
                q={q}
                draft={drafts[q.address] ?? { marks: "", state: "awarded" }}
                rejected={rejected[q.address]}
                onChange={(patch) => set(q.address, patch)}
              />
            ))}
          </ol>
        </>
      )}

      <style jsx>{`
        .wrap { max-width: 860px; margin: 0 auto; padding: 20px 16px 64px; }
        h1 { margin: 0 0 4px; font-size: 26px; }
        .lede { color: #555; margin: 0 0 20px; max-width: 60ch; }
        .panel { border: 1px solid #e3e3e6; border-radius: 12px; padding: 14px; margin-bottom: 16px; background: #fff; }
        .sticky { position: sticky; top: 0; z-index: 5; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
        .picks { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
        .picks label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: #555; }
        select, input { padding: 10px; border: 1px solid #ccc; border-radius: 8px; font-size: 16px; background: #fff; }
        .tally { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; font-size: 16px; }
        .confirmrow { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
        .confirmrow label { flex: 1 1 180px; display: flex; }
        .confirmrow input { width: 100%; }
        button { padding: 10px 16px; border-radius: 8px; border: 0; background: #16324f; color: #fff; font-size: 15px; }
        button[disabled] { opacity: .5; }
        .qlist { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
        .muted { color: #666; }
        .error { color: #a11; }
        .ok { color: #196b2c; margin: 8px 0 0; }
        .warnish { color: #8a5b00; }
        .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
        @media (max-width: 560px) {
          .picks { grid-template-columns: 1fr; }
          .sticky { position: static; }
        }
      `}</style>
    </main>
  );
}

function Row({
  q,
  draft,
  rejected,
  onChange,
}: {
  q: AnswerRow;
  draft: Draft;
  rejected?: string;
  onChange: (patch: Partial<Draft>) => void;
}) {
  const entered = draft.state !== "awarded" || draft.marks.trim() !== "";
  return (
    <li className={`row${entered ? "" : " pending"}${rejected ? " bad" : ""}`}>
      <div className="head">
        <span className="no">
          {q.section ? `${q.section} · ` : ""}
          {q.question_no}
          {q.choice_alt === "b" ? " (or)" : ""}
        </span>
        <span className="worth">out of {q.max_marks}</span>
      </div>

      {q.stem_text && <p className="stem">{q.stem_text}</p>}

      <div className="chips">
        {q.chapter && <span className="chip">{q.chapter}</span>}
        {q.concept_family && <span className="chip strong">{q.concept_family}</span>}
        {q.source && q.source !== "teacher" && (
          <span className="chip">{SOURCE_LABEL[q.source] ?? "read automatically"}</span>
        )}
        {q.source === "teacher" && <span className="chip strong">confirmed</span>}
      </div>

      <div className="entry">
        <label>
          <span className="sr">Marks for question {q.question_no}</span>
          <input
            type="number"
            inputMode="decimal"
            min={0}
            max={q.max_marks}
            step={0.5}
            value={draft.marks}
            disabled={draft.state !== "awarded"}
            placeholder="marks"
            onChange={(e) => onChange({ marks: e.target.value })}
          />
        </label>
        <label>
          <span className="sr">State for question {q.question_no}</span>
          <select value={draft.state} onChange={(e) => onChange({ state: e.target.value })}>
            {STATES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {rejected && <p className="rej">Not recorded. {rejected}</p>}

      <style jsx>{`
        li { border: 1px solid #e3e3e6; border-left: 4px solid #16324f; border-radius: 10px; padding: 12px; background: #fff; }
        li.pending { border-left-color: #d9a441; }
        li.bad { border-left-color: #a11; background: #fff7f7; }
        .head { display: flex; justify-content: space-between; gap: 10px; font-size: 15px; }
        .no { font-weight: 600; }
        .worth { color: #666; font-size: 13px; }
        .stem { margin: 6px 0; color: #333; font-size: 14px; }
        .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
        .chip { font-size: 12px; background: #f1f2f4; border-radius: 999px; padding: 2px 9px; color: #444; }
        .chip.strong { background: #16324f; color: #fff; }
        .entry { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
        .entry label { display: flex; }
        input { width: 110px; padding: 10px; border: 1px solid #ccc; border-radius: 8px; font-size: 16px; }
        select { flex: 1 1 180px; padding: 10px; border: 1px solid #ccc; border-radius: 8px; font-size: 16px; background: #fff; }
        input[disabled] { background: #f4f4f5; color: #999; }
        .rej { color: #a11; font-size: 13px; margin: 8px 0 0; }
        .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
      `}</style>
    </li>
  );
}
