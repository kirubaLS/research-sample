"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  ApiUnreachable,
  ConfirmResult,
  MapResult,
  PlaceResult,
  ScanResult,
  ScanReview,
  StagedQuestion,
  type Subject,
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

type Stage = "start" | "scanned" | "confirmed" | "mapped" | "classified";

export default function PaperPage() {
  // The subjects come from the deployment, not from a list written here. A school that
  // loads a third book must see it offered without anybody editing this screen.
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subject, setSubject] = useState<string>("");
  const [title, setTitle] = useState("Cycle Test I");
  const [assessmentId, setAssessmentId] = useState<string | null>(null);
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [review, setReview] = useState<ScanReview | null>(null);
  const [mapped, setMapped] = useState<MapResult | null>(null);
  const [placed, setPlaced] = useState<PlaceResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "mapped" | "blocked">("all");
  const [confirmedBy, setConfirmedBy] = useState("");
  const [confirmation, setConfirmation] = useState<ConfirmResult | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .subjects(key)
      .then(({ subjects: found }) => {
        setSubjects(found);
        // A subject with no book loaded cannot map a question, so it is not the one to
        // land on. If none is loaded the first is still offered, and the map step says why
        // it cannot run rather than this screen pretending there is nothing to choose.
        setSubject((current) =>
          current || found.find((s) => s.book_loaded)?.subject_code
            || found[0]?.subject_code || "",
        );
      })
      .catch(() => setSubjects([]));
  }, []);

  const confirmed = !!(confirmation || review?.confirmed_at);
  const stage: Stage = placed
    ? "classified"
    : mapped
      ? "mapped"
      : confirmed
        ? "confirmed"
        : scan
          ? "scanned"
          : "start";

  function explain(err: unknown): string {
    if (err instanceof ApiUnreachable) return "Could not reach the API.";
    if (!(err instanceof ApiError)) return "Something went wrong.";
    try {
      const body = JSON.parse(err.message) as { detail?: string };
      if (body.detail) return body.detail;
    } catch {
      /* the body was not JSON; fall through to the status */
    }
    if (err.status === 404) return "That key was not recognised. Please sign in again.";
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
    if (!subject) {
      setError("Choose a subject before reading the paper.");
      return;
    }
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
      setPlaced(null);
      await refresh(assessmentId);
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  async function onClassify() {
    const key = getApiKey();
    if (!key || !assessmentId) return;
    setError(null);
    setBusy("Reading each question against the passages it matched…");
    try {
      setPlaced(await api.placePaper(key, assessmentId));
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
            Every question is matched to a chapter, a section and a concept family, all of
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
            ["Classify", "chapter, topic, sub topic and category"],
          ] as const
        ).map(([label, hint], i) => {
          const reached = ["start", "scanned", "confirmed", "mapped", "classified"].indexOf(stage);
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
                {subjects.map(({ subject_code: code, label: name }) => (
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
              One page or many, as PDFs or photographs, in the order you add them. A paper
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
            <Tile n={scan.sub_parts} label="sub parts" />
            <Tile n={scan.choice_alternatives} label="choice alternatives" />
            <Tile n={scan.pages} label="pages" />
            {scan.declared.questions != null && (
              <Tile
                n={scan.declared.questions}
                label="the paper declares"
                tone={scan.declared.questions === scan.questions ? "good" : "warn"}
              />
            )}
          </div>

          {/* The marks total, on its own and in words. A sub part whose label was missed
              takes its marks with it and leaves nothing behind to notice: every row still
              on screen looks right, and only this line shows the paper is short. */}
          <MarksCheck read={scan.total_marks} declared={scan.declared.total_marks} />

          {scan.problems.length === 0 ? (
            <p className="verdict good">
              What was read agrees with everything the paper says about itself.
            </p>
          ) : (
            <div className="verdict warn">
              <p>
                <strong>The paper disagrees with what was read.</strong> Nothing is wrong
                with storing it, but these are the gaps a person has to close.
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
                Nothing is mapped until someone checks it. Correct any row below first;
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

          {/* Retrieval finds the passages; it does not judge what a question asks a
              student to do. That is a separate reading, and it is the only thing that
              produces a category. */}
          {!placed && mapped.mapped > 0 && (
            <>
              <p className="note">
                Every question now sits in a chapter. Reading each one against the passages
                it matched settles its topic and sub topic, and gives it a category. A
                question the reading cannot settle keeps what it has and says so.
              </p>
              <button type="button" className="primary" onClick={onClassify} disabled={!!busy}>
                {busy ?? "Read and classify these questions"}
              </button>
            </>
          )}
        </section>
      )}

      {placed && (
        <section className="card">
          <div className="tiles">
            <Tile n={placed.labelled} label="chapter, topic and sub topic settled" tone="good" />
            <Tile
              n={placed.tiers}
              label="given a category"
              tone={placed.tiers === placed.placed ? "good" : "warn"}
            />
            <Tile
              n={placed.unsettled_family}
              label="sub topic wants a second look"
              tone={placed.unsettled_family ? "warn" : undefined}
            />
            <Tile
              n={placed.family_refused}
              label="left as they were"
              tone={placed.family_refused ? "warn" : undefined}
            />
          </div>

          {placed.tiers < placed.placed && (
            <p className="note">
              {placed.placed - placed.tiers} question
              {placed.placed - placed.tiers === 1 ? "" : "s"} came back without a category.
              That is an answer, not a gap: where the passages do not settle which kind of
              thinking a question asks for, nothing is recorded rather than a letter
              nobody can stand behind.
            </p>
          )}

          {/* Measured, not estimated. A model choice is a cost decision, and it should be
              made on the figure this run produced rather than on arithmetic about a
              prompt nobody had looked at. */}
          <p className="small muted">
            {placed.spend.calls} reading{placed.spend.calls === 1 ? "" : "s"} by{" "}
            {placed.spend.model} at {placed.spend.effort} effort, each shown{" "}
            {placed.spend.passages_shown} passages from up to{" "}
            {placed.spend.chapters_shown} chapters.{" "}
            {(placed.spend.input_tokens / 1000).toFixed(1)}k in,{" "}
            {(placed.spend.output_tokens / 1000).toFixed(1)}k out.
          </p>

          {placed.grounding_violations.length > 0 && (
            <div className="verdict warn">
              <p>
                <strong>
                  The book had to correct the reading on{" "}
                  {placed.grounding_violations.length} question
                  {placed.grounding_violations.length === 1 ? "" : "s"}.
                </strong>{" "}
                Every corrected field was dropped rather than stored. How often this
                happens is the measure of whether the next paper can be left to it.
              </p>
              <ul>
                {placed.grounding_violations.slice(0, 6).map((v) => (
                  <li key={v.question}>
                    {v.question} &middot; {v.problems.join("; ")}
                  </li>
                ))}
              </ul>
            </div>
          )}
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

function MarksCheck({ read, declared }: { read: number; declared: number | null }) {
  if (declared == null) {
    return (
      <p className="markscheck">
        <strong>{read} marks</strong> were read. This paper does not print a total of its
        own, so there is nothing to check the reading against.
      </p>
    );
  }
  const short = Math.round((declared - read) * 100) / 100;
  if (short === 0) {
    return (
      <p className="markscheck good">
        <strong>
          {read} of {declared} marks
        </strong>{" "}
        were read. The paper adds up to what it says it is worth.
      </p>
    );
  }
  return (
    <div className="markscheck warn">
      <p>
        <strong>
          {read} of {declared} marks
        </strong>{" "}
        were read, so {Math.abs(short)}{" "}
        {short > 0 ? "are missing" : "are counted twice"}.
      </p>
      <p className="small">
        {short > 0
          ? "A question whose parts are worth different marks is the usual cause. Open the ones with parts (i), (ii) and (iii) and check that each part carries its own marks."
          : "A question with an internal choice is the usual cause. Only one half of a choice counts towards the total."}
      </p>
    </div>
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
  // A case study opens with a paragraph its parts share. It is worth nothing on its own,
  // and showing it as a question with no marks sends a person hunting for a mark that was
  // never printed.
  const missing = q.max_marks == null && !q.is_context;
  return (
    <li className={`qrow${placed || q.is_context ? "" : " qrow-blocked"}${missing ? " qrow-missing" : ""}`}>
      <div className="qhead">
        <span className="qno">
          {q.section ? `${q.section} · ` : ""}
          {q.question_no}
          {q.sub_part ? ` (${q.sub_part})` : ""}
          {q.choice_alt ? ` (${q.choice_alt})` : ""}
          {/* A choice is answered instead of its other half, never as well as it. Saying
              so on the row is what stops the pair being read as two questions. */}
          {q.choice_alt === "b" && <span className="editedby">instead of (a)</span>}
          {q.edited_by && <span className="editedby">corrected by {q.edited_by}</span>}
        </span>
        {q.is_context ? (
          <span className="qmarks">
            <em className="muted">the stem its parts share</em>
          </span>
        ) : editable ? (
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
          {/* The topic is the book's own heading for the section the passages came from,
              so it is shown in the book's words with the number beside it. */}
          {placed.topic && (
            <Chip
              label="Topic"
              value={
                placed.curriculum_section
                  ? `${placed.curriculum_section} ${placed.topic}`
                  : placed.topic
              }
            />
          )}
          {!placed.topic && placed.curriculum_section && (
            <Chip label="Topic" value={placed.curriculum_section} />
          )}
          <Chip label="Sub topic" value={placed.concept_family} strong />
          <Chip label="Board unit" value={placed.board_unit} />
          {/* A tier nobody has worked out must not read as one that was. */}
          <Chip
            label="Category"
            value={placed.tier ?? "not classified yet"}
            title={placed.tier_label ?? undefined}
          />
        </div>
      ) : (
        <p className="qblocked">{q.blocked_reason ?? "not mapped"}</p>
      )}
    </li>
  );
}

function Chip({
  label,
  value,
  strong,
  title,
}: {
  label: string;
  value: string | null;
  strong?: boolean;
  title?: string;
}) {
  if (!value) return null;
  return (
    <span className={`chip${strong ? " chip-strong" : ""}`} title={title}>
      <span className="chip-l">{label}</span>
      {value}
    </span>
  );
}
