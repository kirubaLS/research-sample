"use client";

import { useCallback, useRef, useState } from "react";
import {
  api,
  ApiError,
  ApiUnreachable,
  ConfirmResult,
  MapResult,
  ScanResult,
  ScanReview,
  StagedQuestion,
} from "@/lib/api";
import { getApiKey } from "@/lib/session";

/**
 * Reading a question paper, and watching the book make sense of it.
 *
 * The layout is the argument. A question and what the book made of it sit on one row,
 * because the only thing a teacher is really checking is whether those two belong
 * together -- and that judgement is impossible when the paper is on one screen and the
 * classification on another.
 *
 * Nothing here hides a gap. A question the pipeline could not place keeps its row and
 * states the reason, because an unplaceable question is a fact about the paper, and a
 * screen that quietly showed 34 of 39 rows would be lying by omission.
 */

type Stage = "start" | "scanned" | "confirmed" | "mapped";

const SUBJECTS = [
  ["X.MATH", "Class X Mathematics"],
  ["X.SCI", "Class X Science"],
] as const;

export default function PaperPage() {
  const [subject, setSubject] = useState<string>("X.MATH");
  const [title, setTitle] = useState("Cycle Test I");
  const [assessmentId, setAssessmentId] = useState<string | null>(null);
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [review, setReview] = useState<ScanReview | null>(null);
  const [mapped, setMapped] = useState<MapResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "mapped" | "blocked">("all");
  const [confirmedBy, setConfirmedBy] = useState("");
  const [confirmation, setConfirmation] = useState<ConfirmResult | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const confirmed = !!(confirmation || review?.confirmed_at);
  const stage: Stage = mapped ? "mapped" : confirmed ? "confirmed" : scan ? "scanned" : "start";

  function explain(err: unknown): string {
    if (err instanceof ApiUnreachable) return "Could not reach the API.";
    if (!(err instanceof ApiError)) return "Something went wrong.";
    try {
      const body = JSON.parse(err.message) as { detail?: string };
      if (body.detail) return body.detail;
    } catch {
      /* the body was not JSON; fall through to the status */
    }
    if (err.status === 404) return "Sign in again — that key was not recognised.";
    return `The API returned ${err.status}.`;
  }

  const refresh = useCallback(async (id: string) => {
    const key = getApiKey();
    if (!key) return;
    setReview(await api.readScan(key, id));
  }, []);

  async function onFiles(files: File[]) {
    const key = getApiKey();
    if (!key) {
      setError("Sign in first.");
      return;
    }
    setError(null);
    setBusy("Reading the paper…");
    try {
      let id = assessmentId;
      if (!id) {
        const created = await api.createAssessment(key, { subject_code: subject, title });
        id = created.assessment_id;
        setAssessmentId(id);
      }
      setScan(await api.scanPaper(key, id, files));
      setMapped(null);
      setConfirmation(null);
      await refresh(id);
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function onEdit(address: string, patch: Record<string, unknown>) {
    const key = getApiKey();
    if (!key || !assessmentId) return;
    setError(null);
    try {
      await api.editScanned(key, assessmentId, address, { ...patch, by: confirmedBy || "teacher" });
      await refresh(assessmentId);
    } catch (err) {
      setError(explain(err));
    }
  }

  async function onConfirm() {
    const key = getApiKey();
    if (!key || !assessmentId) return;
    setError(null);
    setBusy("Recording your confirmation…");
    try {
      setConfirmation(await api.confirmScan(key, assessmentId, confirmedBy || "teacher"));
      await refresh(assessmentId);
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  async function onMap() {
    const key = getApiKey();
    if (!key || !assessmentId) return;
    setError(null);
    setBusy("Matching every question against the book…");
    try {
      setMapped(await api.mapPaper(key, assessmentId));
      await refresh(assessmentId);
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  const rows = (review?.questions ?? []).filter((q) =>
    filter === "all" ? true : filter === "mapped" ? !!q.mapped_to : !q.mapped_to,
  );
  const blockedCount = (review?.questions ?? []).filter((q) => !q.mapped_to).length;

  return (
    <main className="paper-page">
      <header className="ph">
        <div>
          <p className="eyebrow">Question paper</p>
          <h1>Read a paper, and map it onto the book</h1>
          <p className="lede">
            Every question is matched to a chapter, a section and a concept family — all of
            them from the textbook you loaded, none of them from memory. A question that
            cannot be matched keeps its place here and says why.
          </p>
        </div>
      </header>

      <ol className="steps" aria-label="Progress">
        {(
          [
            ["Upload", "the paper as a PDF"],
            ["Check", "correct anything the reader got wrong"],
            ["Confirm", "put your name to these questions"],
            ["Map", "each question onto the book"],
          ] as const
        ).map(([label, hint], i) => {
          const reached = ["start", "scanned", "confirmed", "mapped"].indexOf(stage);
          const state = i < reached ? "done" : i === reached ? "now" : "todo";
          return (
            <li key={label} className={`step step-${state}`}>
              <span className="step-n">{i + 1}</span>
              <span className="step-b">
                <strong>{label}</strong>
                <em>{hint}</em>
              </span>
            </li>
          );
        })}
      </ol>

      {stage === "start" && (
        <section className="card">
          <div className="grid-2">
            <label className="field">
              <span>Subject</span>
              <select value={subject} onChange={(e) => setSubject(e.target.value)}>
                {SUBJECTS.map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>What is this test called?</span>
              <input value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
          </div>

          <div
            className="drop"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const dropped = Array.from(e.dataTransfer.files ?? []);
              if (dropped.length) onFiles(dropped);
            }}
          >
            <p className="drop-title">Drop the question paper here</p>
            <p className="drop-hint">
              One page or many — PDFs or photographs, in the order you add them. A paper
              with selectable text is read now; a photographed one is reported plainly
              rather than returned as an empty result.
            </p>
            <button type="button" onClick={() => fileInput.current?.click()} disabled={!!busy}>
              {busy ?? "Choose pages"}
            </button>
            <input
              ref={fileInput}
              type="file"
              accept="application/pdf,image/*"
              multiple
              // Hidden with CSS, not the `hidden` attribute: `hidden` removes the input
              // from the accessibility tree, so assistive technology and automated tests
              // cannot reach the only control that accepts a file.
              className="visually-hidden"
              onChange={(e) => {
                const chosen = Array.from(e.target.files ?? []);
                if (chosen.length) onFiles(chosen);
              }}
            />
          </div>
        </section>
      )}

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      {scan && (
        <section className="card">
          <div className="tiles">
            <Tile n={scan.questions} label="questions read" />
            <Tile n={scan.choice_alternatives} label="choice alternatives" />
            <Tile n={scan.total_marks} label="marks in total" />
            <Tile n={scan.pages} label="pages" />
            {scan.declared.questions != null && (
              <Tile
                n={scan.declared.questions}
                label="the paper declares"
                tone={scan.declared.questions === scan.questions ? "good" : "warn"}
              />
            )}
          </div>

          {scan.problems.length === 0 ? (
            <p className="verdict good">
              What was read agrees with everything the paper says about itself.
            </p>
          ) : (
            <div className="verdict warn">
              <p>
                <strong>The paper disagrees with what was read.</strong> Nothing is wrong
                with storing it — but these are the gaps a person has to close.
              </p>
              <ul>
                {scan.problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </div>
          )}

          {stage === "scanned" && (
            <div className="confirmbar">
              <label className="field">
                <span>Who checked this paper?</span>
                <input
                  value={confirmedBy}
                  onChange={(e) => setConfirmedBy(e.target.value)}
                  placeholder="Your name"
                  autoComplete="name"
                />
              </label>
              <button type="button" className="primary" onClick={onConfirm} disabled={!!busy}>
                {busy ?? "These questions are correct"}
              </button>
              <p className="muted">
                Nothing is mapped until someone checks it. Correct any row below first —
                after you confirm, the rows are locked and re-reading the paper is the only
                way to change them.
              </p>
            </div>
          )}

          {stage === "confirmed" && (
            <button type="button" className="primary" onClick={onMap} disabled={!!busy}>
              {busy ?? "Map these questions onto the book"}
            </button>
          )}
        </section>
      )}

      {mapped && (
        <section className="card">
          <div className="tiles">
            <Tile n={mapped.mapped} label="mapped to the book" tone="good" />
            <Tile n={mapped.blocked} label="could not be mapped" tone={mapped.blocked ? "warn" : undefined} />
            <Tile n={mapped.needs_review} label="want a second look" />
          </div>
          <p className="muted">
            Matched by {mapped.retrieval === "hybrid" ? "keyword and meaning search together" : "keyword search alone"}.
          </p>
        </section>
      )}

      {review && review.questions.length > 0 && (
        <section className="card">
          <div className="toolbar">
            <h2>The paper, question by question</h2>
            <div className="filters" role="group" aria-label="Filter questions">
              {(
                [
                  ["all", `All ${review.questions.length}`],
                  ["mapped", `Mapped ${review.mapped}`],
                  ["blocked", `Unmapped ${blockedCount}`],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={filter === value ? "on" : ""}
                  onClick={() => setFilter(value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {review.confirmed_at && (
            <p className="verdict good">
              Confirmed by {review.confirmed_by ?? "someone"}
              {review.edited > 0 && ` · ${review.edited} row(s) corrected first`}. These
              rows are locked; re-read the paper to change them.
            </p>
          )}

          <ul className="qlist">
            {rows.map((q) => (
              <QuestionRow
                key={q.address}
                q={q}
                editable={!confirmed && !q.mapped_to}
                onEdit={onEdit}
              />
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}

function Tile({ n, label, tone }: { n: number; label: string; tone?: "good" | "warn" }) {
  return (
    <div className={`tile${tone ? ` tile-${tone}` : ""}`}>
      <span className="tile-n">{n}</span>
      <span className="tile-l">{label}</span>
    </div>
  );
}

function QuestionRow({
  q,
  editable,
  onEdit,
}: {
  q: StagedQuestion;
  editable: boolean;
  onEdit: (address: string, patch: Record<string, unknown>) => void;
}) {
  const placed = q.mapped_to;
  const missing = q.max_marks == null;
  return (
    <li className={`qrow${placed ? "" : " qrow-blocked"}${missing ? " qrow-missing" : ""}`}>
      <div className="qhead">
        <span className="qno">
          {q.section ? `${q.section} · ` : ""}
          {q.question_no}
          {q.choice_alt === "b" ? " (or)" : ""}
          {q.edited_by && <span className="editedby">corrected by {q.edited_by}</span>}
        </span>
        {editable ? (
          <span className="qedit">
            <label>
              <span className="sr">Marks for question {q.question_no}</span>
              <input
                type="number"
                inputMode="decimal"
                min={0}
                step={0.5}
                defaultValue={q.max_marks ?? ""}
                placeholder="marks"
                onBlur={(e) => {
                  const value = e.target.value.trim();
                  if (value === "" || Number(value) === q.max_marks) return;
                  onEdit(q.address, { max_marks: Number(value) });
                }}
              />
            </label>
            <button
              type="button"
              className="remove"
              onClick={() => onEdit(q.address, { remove: true })}
              aria-label={`Remove question ${q.question_no}, it is not a question`}
            >
              Not a question
            </button>
          </span>
        ) : (
          <span className="qmarks">
            {missing ? <em className="warnish">no marks read</em> : `${q.max_marks} marks`}
          </span>
        )}
      </div>

      <p className="qstem">{q.stem_text || <em>no text was extracted for this question</em>}</p>

      {placed ? (
        <div className="qmap">
          <Chip label="Chapter" value={placed.chapter} />
          {placed.curriculum_section && <Chip label="Section" value={placed.curriculum_section} />}
          <Chip label="Concept" value={placed.concept_family} strong />
          <Chip label="Board unit" value={placed.board_unit} />
        </div>
      ) : (
        <p className="qblocked">{q.blocked_reason ?? "not mapped"}</p>
      )}
    </li>
  );
}

function Chip({ label, value, strong }: { label: string; value: string | null; strong?: boolean }) {
  if (!value) return null;
  return (
    <span className={`chip${strong ? " chip-strong" : ""}`}>
      <span className="chip-l">{label}</span>
      {value}
    </span>
  );
}
