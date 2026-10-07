"use client";

import { useEffect, useState } from "react";
import { BookOpenCheck, ChevronDown, ChevronRight, Loader2, Play, ShieldCheck } from "lucide-react";
import { Reveal } from "@/components/motion";
import { api, PlatformSchool, PromptLabPaper, PromptLabResult, PromptLabRun, PromptLabTaxonomy } from "@/lib/api";
import { getPlatformKey } from "@/lib/session";
import { OpsEmpty } from "../ui";

/**
 * Prompt mapper: map questions to chapter and topic with ONE cheap model call per batch (Haiku),
 * choosing from the book's complete topic list. It is an experiment beside the real pipeline,
 * not part of it, and it is read only: nothing is saved and no paper, school or student is
 * touched. Run it on a stored paper and it compares each answer with the mapping already saved,
 * which is how to see whether a closed topic list covers topics better than retrieval does.
 */

const SECTIONS = [
  { value: "", label: "No section hint" },
  { value: "A", label: "A · History" },
  { value: "B", label: "B · Geography" },
  { value: "C", label: "C · Political Science" },
  { value: "D", label: "D · Economics" },
];

function money(n: number): string {
  return n === 0 ? "$0" : `$${n < 0.01 ? n.toFixed(4) : n.toFixed(3)}`;
}

function pct(a: number, b: number): string {
  return b === 0 ? "—" : `${Math.round((a / b) * 100)}%`;
}

export default function PromptLabPage() {
  const [schools, setSchools] = useState<PlatformSchool[]>([]);
  const [schoolId, setSchoolId] = useState("");
  const [papers, setPapers] = useState<PromptLabPaper[] | null>(null);
  const [paperId, setPaperId] = useState("");
  const [text, setText] = useState("");
  const [section, setSection] = useState("");

  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<PromptLabRun | null>(null);

  const [tax, setTax] = useState<PromptLabTaxonomy | null>(null);
  const [showTax, setShowTax] = useState(false);

  useEffect(() => {
    const key = getPlatformKey();
    if (!key) return;
    api.listSchools(key).then(setSchools).catch(() => {});
    api.promptLabTaxonomy(key).then(setTax).catch(() => {});
  }, []);

  useEffect(() => {
    const key = getPlatformKey();
    setPapers(null);
    setPaperId("");
    if (!key || !schoolId) return;
    api
      .promptLabPapers(key, schoolId)
      .then((r) => setPapers(r.papers))
      .catch(() => setPapers([]));
  }, [schoolId]);

  const questions = text
    .split(/^\s*---+\s*$/m)
    .map((t) => t.trim())
    .filter((t) => t.length >= 3);
  const canRun = !running && (paperId !== "" || questions.length > 0);

  async function go() {
    const key = getPlatformKey();
    if (!key || !canRun) return;
    setRunning(true);
    setError(null);
    try {
      setRun(
        await api.promptLabRun(
          key,
          paperId
            ? { assessment_id: paperId }
            : { questions: questions.map((t) => ({ text: t, section: section || null })) },
        ),
      );
    } catch (e) {
      setRun(null);
      setError(e instanceof Error ? e.message : "The mapper could not run.");
    } finally {
      setRunning(false);
    }
  }

  async function openTaxonomy() {
    const key = getPlatformKey();
    if (!key) return;
    if (!showTax && tax && tax.text === null) {
      try {
        setTax(await api.promptLabTaxonomy(key, true));
      } catch {
        /* the counts above still show */
      }
    }
    setShowTax((v) => !v);
  }

  return (
    <>
      <Reveal>
        <h1 className="page-title">Prompt mapper</h1>
        <p className="page-sub">
          Map questions to chapter and topic with one cheap model call, choosing from the book&apos;s complete topic
          list. An experiment beside the real pipeline: nothing is saved and nothing existing is touched.
        </p>
      </Reveal>

      {error && (
        <div className="evidence evidence--gold" style={{ marginTop: 18 }}>
          <div>{error}</div>
        </div>
      )}

      <section className="section" style={{ marginTop: 18 }} aria-labelledby="pm-h">
        <div className="section__head">
          <h2 id="pm-h" className="section-q" style={{ fontSize: 17 }}>
            <BookOpenCheck size={16} style={{ verticalAlign: -2 }} /> Questions to map
          </h2>
          <span style={{ display: "inline-flex", gap: 8 }}>
            {tax && <span className="tag">{tax.model}</span>}
            <span className="tag tag--green">
              <ShieldCheck size={12} /> Read only
            </span>
          </span>
        </div>

        <div className="card">
          <div className="card__body" style={{ display: "grid", gap: 14 }}>
            <div className="filterbar" style={{ position: "static", background: "transparent", backdropFilter: "none" }}>
              <div className="filter">
                <label htmlFor="pm-school">Load a stored paper from</label>
                <select id="pm-school" className="select" value={schoolId} onChange={(e) => setSchoolId(e.target.value)}>
                  <option value="">Type questions instead</option>
                  {schools.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
              {schoolId && (
                <div className="filter">
                  <label htmlFor="pm-paper">Paper</label>
                  <select id="pm-paper" className="select" value={paperId} onChange={(e) => setPaperId(e.target.value)}>
                    <option value="">{papers === null ? "Loading…" : papers.length ? "Choose a paper" : "No Social Science papers"}</option>
                    {(papers ?? []).map((p) => (
                      <option key={p.assessment_id} value={p.assessment_id}>
                        {p.title} · {p.questions} questions
                      </option>
                    ))}
                  </select>
                </div>
              )}
              {!paperId && (
                <div className="filter">
                  <label htmlFor="pm-section">Section (for typed questions)</label>
                  <select id="pm-section" className="select" value={section} onChange={(e) => setSection(e.target.value)}>
                    {SECTIONS.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {!paperId && (
              <div className="field field--wide">
                <label htmlFor="pm-text">Questions</label>
                <textarea
                  id="pm-text"
                  className="input"
                  rows={8}
                  value={text}
                  placeholder={"One question per block. Put a line with --- between questions.\n\nWhy did Gandhiji call off the Non-Cooperation Movement?\n---\nName the type of soil best suited for cotton."}
                  onChange={(e) => setText(e.target.value)}
                />
                <span className="small muted">
                  {questions.length} question{questions.length === 1 ? "" : "s"} · up to 80 per run. Paste a case-based
                  passage together with its sub-question.
                </span>
              </div>
            )}
            {paperId && (
              <p className="small muted" style={{ margin: 0 }}>
                Every question of this paper will be mapped and compared with the mapping already saved on it. The
                saved mapping is not changed.
              </p>
            )}

            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <button type="button" className="btn btn--blue" disabled={!canRun} onClick={() => void go()}>
                {running ? <Loader2 size={14} className="spin" /> : <Play size={14} />}
                {running ? "Mapping…" : "Map with Haiku"}
              </button>
              {tax && (
                <span className="small muted">
                  The model chooses from {tax.topics} topics in {tax.chapters} chapters (about {tax.approx_tokens.toLocaleString()} tokens, cached).
                </span>
              )}
            </div>
          </div>
        </div>
      </section>

      {run && <RunView run={run} />}

      <section className="section" style={{ marginTop: 22 }} aria-labelledby="tx-h">
        <div className="section__head">
          <h2 id="tx-h" className="section-q" style={{ fontSize: 17 }}>
            The topic list the model sees
          </h2>
          <button type="button" className="btn btn--sm" onClick={() => void openTaxonomy()}>
            {showTax ? <ChevronDown size={13} /> : <ChevronRight size={13} />} {showTax ? "Hide" : "Show"}
          </button>
        </div>
        <p className="small muted" style={{ marginTop: 0 }}>
          Built from the audited book data, so every section and sub-section of the four books is a choice and nothing the
          books lack is. Hints in brackets are names, dates and terms from each section.
        </p>
        {showTax && tax?.text && (
          <pre
            className="card"
            style={{ padding: 14, maxHeight: 420, overflow: "auto", fontSize: 12, whiteSpace: "pre-wrap", margin: 0 }}
          >
            {tax.text}
          </pre>
        )}
      </section>
    </>
  );
}

function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="kpi" style={{ alignItems: "flex-start" }}>
      <div className="kpi__text">
        <div className="kpi__label">{label}</div>
        <div className="kpi__value" style={{ fontSize: 20 }}>{value}</div>
        {sub && <div className="kpi__sub">{sub}</div>}
      </div>
    </div>
  );
}

function RunView({ run }: { run: PromptLabRun }) {
  const s = run.summary;
  const [only, setOnly] = useState<"all" | "review" | "differs">("all");
  const rows = run.results.filter((r) =>
    only === "all" ? true : only === "review" ? r.needs_review : !!r.stored && !r.stored.topic_agrees,
  );

  return (
    <section className="section" style={{ marginTop: 22 }} aria-labelledby="pr-h">
      <div className="section__head">
        <h2 id="pr-h" className="section-q" style={{ fontSize: 17 }}>
          Result
        </h2>
        <span className="tag">
          {run.calls} call{run.calls === 1 ? "" : "s"} · {money(run.spend.estimated_usd)}
        </span>
      </div>

      <div className="grid grid--4">
        <Stat label="Mapped to a topic" value={`${s.mapped} / ${s.questions}`} sub={pct(s.mapped, s.questions)} />
        <Stat label="In the syllabus" value={`${s.in_syllabus} / ${s.questions}`} sub={pct(s.in_syllabus, s.questions)} />
        <Stat label="Need review" value={s.needs_review} sub={`${s.high} high confidence`} />
        {s.compared > 0 ? (
          <Stat
            label="Agrees with saved mapping"
            value={`${pct(s.chapter_agrees, s.compared)} chapter`}
            sub={`${pct(s.topic_agrees, s.compared)} topic · ${s.compared} compared`}
          />
        ) : (
          <Stat label="Tokens" value={(run.spend.input_tokens + run.spend.cache_read_tokens).toLocaleString()} sub={`${run.spend.output_tokens.toLocaleString()} out`} />
        )}
      </div>

      {run.errors.length > 0 && (
        <div className="evidence evidence--gold" style={{ marginTop: 12 }}>
          <div>
            {run.errors.map((e, i) => (
              <div key={i}>{e}</div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, margin: "14px 0 8px" }}>
        {(["all", "review", ...(s.compared > 0 ? ["differs"] : [])] as ("all" | "review" | "differs")[]).map((k) => (
          <button key={k} type="button" className={`btn btn--sm${only === k ? " btn--blue" : ""}`} onClick={() => setOnly(k)}>
            {k === "all" ? "All" : k === "review" ? "Needs review" : "Differs from saved"}
          </button>
        ))}
      </div>

      <div className="card" style={{ overflow: "hidden" }}>
        {rows.length === 0 ? (
          <div className="card__body">
            <OpsEmpty>Nothing in this view.</OpsEmpty>
          </div>
        ) : (
          <div className="table-wrap table-wrap--scroll" style={{ maxHeight: 640 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Question</th>
                  <th>Chapter</th>
                  <th>Topic</th>
                  <th>Confidence</th>
                  {s.compared > 0 && <th>Saved mapping</th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <Row key={r.row} r={r} compared={s.compared > 0} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

function Row({ r, compared }: { r: PromptLabResult; compared: boolean }) {
  const tone = r.confidence === "high" ? "tag--green" : r.confidence === "low" ? "tag--gold" : "";
  return (
    <tr>
      <td style={{ maxWidth: 360 }}>
        <div>{r.text.slice(0, 170)}</div>
        <div className="small muted">{r.reason}</div>
        {r.problems.map((p, i) => (
          <div key={i} className="small" style={{ color: "var(--gold, #a8741a)" }}>
            {p}
          </div>
        ))}
      </td>
      <td className="small">{r.chapter?.title ?? "—"}</td>
      <td className="small">
        {r.topic ? (
          <>
            <strong>{r.topic.number}</strong> {r.topic.title}
            {r.topic.major_number && r.topic.major_number !== r.topic.number && (
              <div className="muted">two-level topic {r.topic.major_number} {r.topic.major_title}</div>
            )}
          </>
        ) : (
          "—"
        )}
        {r.secondary.length > 0 && <div className="muted">also: {r.secondary.map((x) => x.title).join("; ")}</div>}
      </td>
      <td>
        <span className={`tag ${tone}`}>{r.confidence}</span>
        {r.syllabus_status !== "in_syllabus" && <div className="small muted">{r.syllabus_status.replace("_", " ")}</div>}
      </td>
      {compared && (
        <td className="small">
          {r.stored ? (
            <>
              {r.stored.chapter}
              {r.stored.section ? ` · ${r.stored.section}` : ""}
              <div>
                <span className={`tag ${r.stored.topic_agrees ? "tag--green" : "tag--gold"}`}>
                  {r.stored.topic_agrees ? "topic agrees" : r.stored.chapter_agrees ? "chapter agrees, topic differs" : "differs"}
                </span>
              </div>
            </>
          ) : (
            "—"
          )}
        </td>
      )}
    </tr>
  );
}
