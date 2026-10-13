"use client";

import { useEffect, useRef, useState } from "react";
import { FileScan, Loader2, Play, ShieldCheck, X } from "lucide-react";
import { Reveal } from "@/components/motion";
import { api, OcrLabQuestion, OcrLabResult, OcrLabState } from "@/lib/api";
import { getPlatformKey } from "@/lib/session";
import { OpsEmpty } from "../ui";

/**
 * OCR mapper: upload a question paper (a PDF or photographs), read it the way the teacher
 * dashboard reads one, then map every question to chapter and topic. It is an admin tool beside
 * the real pipeline and stores nothing: no paper, question or placement is created, and the
 * uploaded pages are deleted as soon as they have been read.
 */

function money(n: number): string {
  return n === 0 ? "$0" : `$${n < 0.01 ? n.toFixed(4) : n.toFixed(3)}`;
}

export default function OcrLabPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [mode, setMode] = useState<"upload" | "paste">("upload");
  const [pasted, setPasted] = useState("");
  const [mapTopics, setMapTopics] = useState(true);
  const [subject, setSubject] = useState<"X.SST" | "X.SCI" | "X.MATH">("X.SST");
  // a trial prompt per subject, kept in this browser only; used for the next run when switched on
  const [trial, setTrial] = useState<Record<string, string>>({});
  const [useTrial, setUseTrial] = useState(false);
  const [loadingPrompt, setLoadingPrompt] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<OcrLabState | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const running = starting || (job !== null && ["queued", "reading", "mapping"].includes(job.status));

  useEffect(
    () => () => {
      if (timer.current) clearInterval(timer.current);
    },
    [],
  );

  function watch(jobId: string) {
    const key = getPlatformKey();
    if (!key) return;
    if (timer.current) clearInterval(timer.current);
    const tick = async () => {
      try {
        const state = await api.ocrLabPoll(key, jobId);
        setJob(state);
        if (state.status === "done" || state.status === "failed") {
          if (timer.current) clearInterval(timer.current);
        }
      } catch (e) {
        if (timer.current) clearInterval(timer.current);
        setError(e instanceof Error ? e.message : "Lost track of the job.");
      }
    };
    void tick();
    timer.current = setInterval(() => void tick(), 2000);
  }

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("ocr-lab-trial-prompts");
      if (saved) setTrial(JSON.parse(saved) as Record<string, string>);
    } catch {
      /* no saved drafts */
    }
  }, []);

  function editTrial(text: string) {
    const next = { ...trial, [subject]: text };
    setTrial(next);
    try {
      window.localStorage.setItem("ocr-lab-trial-prompts", JSON.stringify(next));
    } catch {
      /* the draft stays in memory */
    }
  }

  async function loadBuiltIn() {
    const key = getPlatformKey();
    if (!key) return;
    setLoadingPrompt(true);
    setError(null);
    try {
      editTrial((await api.ocrLabPrompt(key, subject)).prompt);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the prompt.");
    } finally {
      setLoadingPrompt(false);
    }
  }

  const trialText = (trial[subject] ?? "").trim();
  const sendPrompt = useTrial ? trialText : "";

  async function start() {
    const key = getPlatformKey();
    const ready = mode === "paste" ? pasted.trim().length > 0 : files.length > 0;
    if (!key || !ready || running || (useTrial && !trialText)) return;
    setStarting(true);
    setError(null);
    setJob(null);
    try {
      const { job_id } =
        mode === "paste"
          ? await api.ocrLabPaste(key, pasted, subject, sendPrompt)
          : await api.ocrLabStart(key, files, mapTopics, subject, sendPrompt);
      watch(job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The upload failed.");
    } finally {
      setStarting(false);
    }
  }

  const progress =
    job && job.total > 0 && job.status === "reading" ? Math.round((job.done / job.total) * 100) : null;

  return (
    <>
      <Reveal>
        <h1 className="page-title">OCR mapper</h1>
        <p className="page-sub">
          Upload a question paper and see it read the way the teacher dashboard reads one, then mapped to chapter and
          topic. Nothing is stored: no paper, question or placement is created, and the pages are deleted once read.
        </p>
      </Reveal>

      {error && (
        <div className="evidence evidence--gold" style={{ marginTop: 18 }}>
          <div>{error}</div>
        </div>
      )}

      <section className="section" style={{ marginTop: 18 }} aria-labelledby="oc-h">
        <div className="section__head">
          <h2 id="oc-h" className="section-q" style={{ fontSize: 17 }}>
            <FileScan size={16} style={{ verticalAlign: -2 }} /> The paper
          </h2>
          <span className="tag tag--green">
            <ShieldCheck size={12} /> Stores nothing
          </span>
        </div>
        <div className="card">
          <div className="card__body" style={{ display: "grid", gap: 14 }}>
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" className={`btn btn--sm${mode === "upload" ? " btn--blue" : ""}`} disabled={running} onClick={() => setMode("upload")}>
                Upload a paper
              </button>
              <button type="button" className={`btn btn--sm${mode === "paste" ? " btn--blue" : ""}`} disabled={running} onClick={() => setMode("paste")}>
                Paste questions
              </button>
            </div>

            {mode === "paste" && (
              <div className="field field--wide">
                <label htmlFor="oc-paste">Questions, exactly as they appear on the paper</label>
                <textarea
                  id="oc-paste"
                  className="input"
                  rows={10}
                  value={pasted}
                  disabled={running}
                  onChange={(e) => setPasted(e.target.value)}
                  placeholder={"Paste one question, or many. Number each (1. 2. 3. or Q1) Q2)) or leave a blank line between them.\nInclude MCQ options and both statements of an Assertion-Reason question."}
                />
                <span className="small muted">Up to 100 questions. Nothing is read or stored; only the topic mapping runs.</span>
              </div>
            )}

            <div className="field field--wide" hidden={mode === "paste"}>
              <label htmlFor="oc-files">PDF, or photographs of the pages in order</label>
              <input
                id="oc-files"
                type="file"
                multiple
                accept=".pdf,.jpg,.jpeg,.png,.webp,.heic,.tif,.tiff,application/pdf,image/*"
                disabled={running}
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
              {files.length > 0 && (
                <ul className="small" style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                  {files.map((f, i) => (
                    <li key={`${f.name}-${i}`}>
                      {i + 1}. {f.name} <span className="muted">({Math.max(1, Math.round(f.size / 1024))} KB)</span>
                    </li>
                  ))}
                </ul>
              )}
              <span className="small muted">Pages are read in the order chosen. Up to 30 pages.</span>
            </div>

            <div className="field" style={{ maxWidth: 280 }}>
              <label htmlFor="ocr-subject">Subject</label>
              <select
                id="ocr-subject" className="select" value={subject} disabled={running}
                onChange={(e) => setSubject(e.target.value as "X.SST" | "X.SCI" | "X.MATH")}
              >
                <option value="X.SST">Social Science</option>
                <option value="X.SCI">Science (Chemistry, Biology, Physics, Environment)</option>
                <option value="X.MATH">Mathematics</option>
              </select>
            </div>

            <details className="field field--wide" open={useTrial}>
              <summary className="small" style={{ cursor: "pointer" }}>
                Prompt {useTrial ? <strong>· trial prompt on</strong> : <span className="muted">· built-in</span>}
              </summary>
              <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
                <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input type="checkbox" checked={useTrial} disabled={running} onChange={(e) => setUseTrial(e.target.checked)} />
                  <span>Use my edited prompt for the next run <span className="muted">(this subject only; nothing is saved on the server)</span></span>
                </label>
                <textarea
                  className="input"
                  rows={16}
                  spellCheck={false}
                  style={{ fontFamily: "ui-monospace, monospace", fontSize: 12 }}
                  value={trial[subject] ?? ""}
                  disabled={running}
                  onChange={(e) => editTrial(e.target.value)}
                  placeholder="Load the built-in prompt for this subject, then edit it."
                />
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button type="button" className="btn btn--sm" disabled={running || loadingPrompt} onClick={() => void loadBuiltIn()}>
                    {loadingPrompt ? <Loader2 size={13} className="spin" /> : null} Load the built-in prompt
                  </button>
                  <button type="button" className="btn btn--sm" disabled={running || !trial[subject]} onClick={() => { editTrial(""); setUseTrial(false); }}>
                    <X size={13} /> Discard my edits
                  </button>
                </div>
                <span className="small muted">
                  The topic list the answers are checked against is the built-in one, so keep using its IDs. To change the
                  list itself, change the prompt file. Edits are kept in this browser, per subject.
                </span>
                {useTrial && !trialText && <span className="small" style={{ color: "var(--gold, #a8741a)" }}>Switched on, but the prompt is empty.</span>}
              </div>
            </details>

            <label style={{ display: "flex", gap: 8, alignItems: "center" }} hidden={mode === "paste"}>
              <input type="checkbox" checked={mapTopics} disabled={running} onChange={(e) => setMapTopics(e.target.checked)} />
              <span>
                Also map each question to chapter and topic <span className="muted">(Haiku reads the book&apos;s own text, and a stronger model rechecks doubtful answers)</span>
              </span>
            </label>

            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <button type="button" className="btn btn--blue" disabled={(mode === "paste" ? pasted.trim().length === 0 : files.length === 0) || running || (useTrial && !trialText)} onClick={() => void start()}>
                {running ? <Loader2 size={14} className="spin" /> : <Play size={14} />}
                {running ? "Working…" : mode === "paste" ? "Map questions" : "Read and map"}
              </button>
              {mode === "paste" && pasted.length > 0 && !running && (
                <button type="button" className="btn btn--sm" onClick={() => { setPasted(""); setJob(null); setError(null); }}>
                  <X size={13} /> Clear
                </button>
              )}
              {mode === "upload" && files.length > 0 && !running && (
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={() => {
                    setFiles([]);
                    setJob(null);
                    setError(null);
                    const el = document.getElementById("oc-files") as HTMLInputElement | null;
                    if (el) el.value = "";
                  }}
                >
                  <X size={13} /> Clear
                </button>
              )}
            </div>

            {job && running && (
              <div aria-live="polite" style={{ display: "grid", gap: 6 }}>
                <div className="small">
                  {job.status === "mapping"
                    ? "Mapping questions to chapters and topics…"
                    : job.route === "vision"
                      ? `Reading page ${Math.min(job.done + 1, job.total)} of ${job.total} with the vision model…`
                      : "Reading…"}
                  {job.note && <span className="muted"> {job.note}.</span>}
                </div>
                {progress !== null && (
                  <div style={{ height: 6, borderRadius: 4, background: "var(--line, #e3e8ef)", overflow: "hidden" }}>
                    <div style={{ width: `${progress}%`, height: "100%", background: "var(--brand-blue, #2f76e6)", transition: "width .3s" }} />
                  </div>
                )}
              </div>
            )}
            {job?.status === "failed" && (
              <div className="evidence evidence--gold">
                <div>The read failed: {job.error}</div>
              </div>
            )}
          </div>
        </div>
      </section>

      {job?.result && <ResultView result={job.result} finished={job.status === "done"} />}
    </>
  );
}

function Check({ ok, label, detail }: { ok: boolean | null; label: string; detail: string }) {
  const tone = ok === null ? "" : ok ? "tag--green" : "tag--gold";
  return (
    <div>
      <div className="small muted">{label}</div>
      <span className={`tag ${tone}`}>{ok === null ? "not printed" : ok ? "matches" : "differs"}</span>{" "}
      <span className="small">{detail}</span>
    </div>
  );
}

function ResultView({ result, finished }: { result: OcrLabResult; finished: boolean }) {
  const { ocr, checks, questions, mapping } = result;
  const [reviewOnly, setReviewOnly] = useState(false);
  const real = questions.filter((q) => !q.is_context);
  const rows = questions.filter((q) => !reviewOnly || (mapping?.by_address[q.address]?.needs_review ?? false));

  return (
    <section className="section" style={{ marginTop: 22 }} aria-labelledby="ocr-res-h">
      <div className="section__head">
        <h2 id="ocr-res-h" className="section-q" style={{ fontSize: 17 }}>
          What was read
        </h2>
        <span style={{ display: "inline-flex", gap: 8 }}>
          <span className="tag">
            {ocr.route === "paste" ? "Pasted text" : ocr.route === "text" ? "Text layer (no OCR)" : `Vision OCR · ${ocr.model}`}
          </span>
          <span className="tag">
            {money(ocr.estimated_usd + (mapping?.spend.estimated_usd ?? 0))}
            {ocr.route === "vision" ? " (estimate)" : ""}
          </span>
        </span>
      </div>

      {ocr.route !== "paste" && <div className="card">
        <div className="card__body" style={{ display: "grid", gap: 12 }}>
          <div className="grid grid--2">
            <Check
              ok={checks.total_matches}
              label="Total marks"
              detail={`read ${checks.read_total}${checks.declared_total !== null ? `, the paper says ${checks.declared_total}` : ""}`}
            />
            <Check
              ok={checks.declared_count === null ? null : checks.declared_count === checks.read_count}
              label="Question count"
              detail={`read ${checks.read_count}${checks.declared_count !== null ? `, the paper says ${checks.declared_count}` : ""}`}
            />
          </div>
          {Object.keys(checks.section_titles).length > 0 && (
            <div className="small muted">
              Section titles: {Object.entries(checks.section_titles).map(([k, v]) => `${k} — ${v}`).join(" · ")}
            </div>
          )}
          {ocr.cascade && (
            <div className="small muted">
              Cheap-model read first ({ocr.cascade.cheap_model}):{" "}
              {ocr.cascade.escalated ? `re-read by ${ocr.cascade.strong_model} (${ocr.cascade.reasons.join("; ")})` : "kept"}
            </div>
          )}
          {checks.problems.map((p, i) => (
            <div key={i} className="small" style={{ color: "var(--gold, #a8741a)" }}>
              {p}
            </div>
          ))}
          {ocr.estimate_note && <div className="small muted">OCR cost is {ocr.estimate_note}.</div>}
        </div>
      </div>}

      {mapping && (
        <div className="grid grid--4" style={{ marginTop: 12 }}>
          <div className="kpi">
            <div className="kpi__text">
              <div className="kpi__label">Mapped to a topic</div>
              <div className="kpi__value" style={{ fontSize: 20 }}>
                {mapping.summary.mapped} / {mapping.summary.questions}
              </div>
            </div>
          </div>
          <div className="kpi">
            <div className="kpi__text">
              <div className="kpi__label">Need review</div>
              <div className="kpi__value" style={{ fontSize: 20 }}>{mapping.summary.needs_review}</div>
              <div className="kpi__sub">{mapping.summary.high} high confidence</div>
            </div>
          </div>
          <div className="kpi">
            <div className="kpi__text">
              <div className="kpi__label">Mapping cost</div>
              <div className="kpi__value" style={{ fontSize: 20 }}>{money(mapping.spend.estimated_usd)}</div>
              <div className="kpi__sub">
                {mapping.model} · {mapping.calls} call{mapping.calls === 1 ? "" : "s"}
                {mapping.custom_prompt ? " · trial prompt" : ""}
              </div>
            </div>
          </div>
          <div className="kpi">
            <div className="kpi__text">
              <div className="kpi__label">Questions read</div>
              <div className="kpi__value" style={{ fontSize: 20 }}>{real.length}</div>
              <div className="kpi__sub">{questions.length - real.length} shared passage(s)</div>
            </div>
          </div>
        </div>
      )}
      {mapping?.errors.map((e, i) => (
        <div key={i} className="evidence evidence--gold" style={{ marginTop: 10 }}>
          <div>{e}</div>
        </div>
      ))}
      {!finished && mapping === null && <p className="small muted">Mapping next…</p>}

      {mapping && (
        <div style={{ display: "flex", gap: 8, margin: "14px 0 8px" }}>
          <button type="button" className={`btn btn--sm${!reviewOnly ? " btn--blue" : ""}`} onClick={() => setReviewOnly(false)}>
            All
          </button>
          <button type="button" className={`btn btn--sm${reviewOnly ? " btn--blue" : ""}`} onClick={() => setReviewOnly(true)}>
            Needs review
          </button>
        </div>
      )}

      <div className="card" style={{ overflow: "hidden", marginTop: mapping ? 0 : 12 }}>
        {rows.length === 0 ? (
          <div className="card__body">
            <OpsEmpty>Nothing in this view.</OpsEmpty>
          </div>
        ) : (
          <div className="table-wrap table-wrap--scroll" style={{ maxHeight: 640 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>No.</th>
                  <th>Question</th>
                  <th>Marks</th>
                  {mapping && <th>Chapter</th>}
                  {mapping && <th>Topic</th>}
                  {mapping && <th>Confidence</th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((q) => (
                  <QuestionRow key={q.address} q={q} mapping={mapping?.by_address[q.address]} show={!!mapping} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

function QuestionRow({
  q,
  mapping,
  show,
}: {
  q: OcrLabQuestion;
  mapping: NonNullable<OcrLabResult["mapping"]>["by_address"][string] | undefined;
  show: boolean;
}) {
  const label = `${q.section ? `${q.section} · ` : ""}${q.question_no}${q.sub_part ? `(${q.sub_part})` : ""}${q.choice_alt ? ` ${q.choice_alt}` : ""}`;
  const tone = mapping?.confidence === "high" ? "tag--green" : mapping?.confidence === "low" ? "tag--gold" : "";
  return (
    <tr style={q.is_context ? { opacity: 0.75 } : undefined}>
      <td className="small" style={{ whiteSpace: "nowrap" }}>
        {label}
        {q.is_context && <div className="muted">passage</div>}
      </td>
      <td style={{ maxWidth: 420 }}>
        <div>{q.text.slice(0, 220)}</div>
        {mapping?.reason && <div className="small muted">{mapping.reason}</div>}
        {mapping?.problems.map((p, i) => (
          <div key={i} className="small" style={{ color: "var(--gold, #a8741a)" }}>
            {p}
          </div>
        ))}
      </td>
      <td className="small">{q.marks ?? "—"}</td>
      {show && <td className="small">{q.is_context ? "" : mapping?.chapter?.title ?? "—"}</td>}
      {show && (
        <td className="small">
          {q.is_context ? (
            ""
          ) : mapping?.topic ? (
            <>
              <strong>{mapping.topic.number}</strong> {mapping.topic.title}
              {mapping.topic.major_number && mapping.topic.major_number !== mapping.topic.number && (
                <div className="muted">two-level topic {mapping.topic.major_number} {mapping.topic.major_title}</div>
              )}
              {mapping.secondary.length > 0 && <div className="muted">also: {mapping.secondary.map((x) => x.title).join("; ")}</div>}
            </>
          ) : (
            "—"
          )}
        </td>
      )}
      {show && (
        <td>
          {!q.is_context && mapping && (
            <>
              <span className={`tag ${tone}`}>{mapping.confidence}</span>
              {mapping.syllabus_status !== "in_syllabus" && (
                <div className="small muted">{mapping.syllabus_status.replace("_", " ")}</div>
              )}
            </>
          )}
        </td>
      )}
    </tr>
  );
}
