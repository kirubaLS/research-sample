"use client";

import { useEffect, useMemo, useState } from "react";
import { FlaskConical, Loader2, Play, Search, ShieldCheck } from "lucide-react";
import { Reveal } from "@/components/motion";
import {
  api,
  LabResult,
  LabStoredQuestion,
  PlatformSchool,
  Subject,
} from "@/lib/api";
import { getPlatformKey } from "@/lib/session";
import { OpsEmpty } from "../ui";

/**
 * Question lab: put ONE question through the mapping pipeline and see every step.
 *
 * It is a read-only tool. The backend route (POST /platform/question-lab/run) opens its own
 * session, never commits and rolls back, so nothing here can change a paper, a school or a
 * student. "Retrieval only" is free; "Full" also runs the Claude judges, exactly as the
 * classify job configures them, and says what that cost.
 */

type Mode = "retrieval" | "full";

function money(n: number): string {
  return n === 0 ? "$0" : `$${n < 0.01 ? n.toFixed(4) : n.toFixed(3)}`;
}

function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

export default function QuestionLabPage() {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [schools, setSchools] = useState<PlatformSchool[]>([]);
  const [subject, setSubject] = useState("");
  const [schoolId, setSchoolId] = useState("");
  const [section, setSection] = useState("");
  const [marks, setMarks] = useState("1");
  const [mode, setMode] = useState<Mode>("retrieval");
  const [stem, setStem] = useState("");
  const [questionId, setQuestionId] = useState<string | null>(null);

  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LabResult | null>(null);

  const [query, setQuery] = useState("");
  const [finding, setFinding] = useState(false);
  const [found, setFound] = useState<LabStoredQuestion[] | null>(null);

  useEffect(() => {
    const key = getPlatformKey();
    if (!key) return;
    api
      .platformSubjects(key)
      .then((r) => {
        // any subject with book text: the lab runs on retrieval alone, embeddings or not
        const loaded = r.subjects.filter((s) => s.chunks > 0);
        setSubjects(loaded);
        setSubject((cur) => cur || loaded[0]?.subject_code || "");
      })
      .catch(() => setError("Could not load the subjects."));
    api.listSchools(key).then(setSchools).catch(() => {});
  }, []);

  const isSst = subject === "X.SST";
  const canRun = !!subject && stem.trim().length >= 3 && !running;

  async function run() {
    const key = getPlatformKey();
    if (!key || !canRun) return;
    setRunning(true);
    setError(null);
    try {
      setResult(
        await api.questionLabRun(key, {
          subject_code: subject,
          stem: stem.trim(),
          marks: Number(marks) || 1,
          mode,
          section: isSst && section ? section : null,
          school_id: schoolId || null,
          question_id: questionId,
        }),
      );
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : "The lab could not run this question.");
    } finally {
      setRunning(false);
    }
  }

  async function find() {
    const key = getPlatformKey();
    if (!key || query.trim().length < 3) return;
    setFinding(true);
    setError(null);
    try {
      setFound((await api.questionLabFind(key, query.trim(), schoolId || undefined)).questions);
    } catch (e) {
      setFound(null);
      setError(e instanceof Error ? e.message : "Search failed.");
    } finally {
      setFinding(false);
    }
  }

  function load(q: LabStoredQuestion) {
    setStem(q.stem ?? "");
    setMarks(String(q.marks));
    setQuestionId(q.question_id);
    setSchoolId(q.school_id);
    setSection(q.section ?? "");
    if (subjects.some((s) => s.subject_code === q.subject_code)) setSubject(q.subject_code);
    else {
      const group = subjects.find((s) => s.books.some((b) => b.subject_code === q.subject_code));
      if (group) setSubject(group.subject_code);
    }
    setResult(null);
  }

  const schoolName = useMemo(() => new Map(schools.map((s) => [s.id, s.name])), [schools]);

  return (
    <>
      <Reveal>
        <h1 className="page-title">Question lab</h1>
        <p className="page-sub">
          Type one question and see exactly how it would be mapped: chapter, topic, tier, and the
          evidence behind each. Nothing is saved, so it cannot affect any paper, school or student.
        </p>
      </Reveal>

      {error && (
        <div className="evidence evidence--gold" style={{ marginTop: 18 }}>
          <div>{error}</div>
        </div>
      )}

      <section className="section" style={{ marginTop: 18 }} aria-labelledby="lab-h">
        <div className="section__head">
          <h2 id="lab-h" className="section-q" style={{ fontSize: 17 }}>
            <FlaskConical size={16} style={{ verticalAlign: -2 }} /> Try a question
          </h2>
          <span className="tag tag--green">
            <ShieldCheck size={12} /> Read only
          </span>
        </div>

        <div className="card">
          <div className="card__body" style={{ display: "grid", gap: 14 }}>
            <div className="filterbar" style={{ position: "static", background: "transparent", backdropFilter: "none" }}>
              <div className="filter">
                <label htmlFor="lab-subject">Subject</label>
                <select id="lab-subject" className="select" value={subject} onChange={(e) => setSubject(e.target.value)}>
                  {subjects.map((s) => (
                    <option key={s.subject_code} value={s.subject_code}>
                      {s.label} ({s.subject_code})
                    </option>
                  ))}
                </select>
              </div>
              {isSst && (
                <div className="filter">
                  <label htmlFor="lab-section">Paper section</label>
                  <select id="lab-section" className="select" value={section} onChange={(e) => setSection(e.target.value)}>
                    <option value="">Any (search all four)</option>
                    <option value="A">A · History</option>
                    <option value="B">B · Geography</option>
                    <option value="C">C · Political Science</option>
                    <option value="D">D · Economics</option>
                  </select>
                </div>
              )}
              <div className="filter">
                <label htmlFor="lab-school">School (confirmed questions)</label>
                <select id="lab-school" className="select" value={schoolId} onChange={(e) => setSchoolId(e.target.value)}>
                  <option value="">None</option>
                  {schools.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="filter" style={{ maxWidth: 110 }}>
                <label htmlFor="lab-marks">Marks</label>
                <input id="lab-marks" className="input" inputMode="decimal" value={marks} onChange={(e) => setMarks(e.target.value)} />
              </div>
            </div>

            <div className="field field--wide">
              <label htmlFor="lab-stem">Question</label>
              <textarea
                id="lab-stem"
                className="input"
                rows={5}
                value={stem}
                placeholder="Paste or type one question exactly as it appears on the paper"
                onChange={(e) => {
                  setStem(e.target.value);
                  setQuestionId(null);
                }}
              />
              {questionId && (
                <span className="small muted">Loaded from a stored question; its saved mapping is shown for comparison.</span>
              )}
            </div>

            <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 8 }}>
              <legend className="small muted" style={{ marginBottom: 4 }}>How far to run it</legend>
              <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                <input type="radio" name="lab-mode" checked={mode === "retrieval"} onChange={() => setMode("retrieval")} />
                <span>
                  <strong>Retrieval only</strong> · free. Book search, the retrieval topic, and the gate, memory and classifier signals. No Claude call.
                </span>
              </label>
              <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                <input type="radio" name="lab-mode" checked={mode === "full"} onChange={() => setMode("full")} />
                <span>
                  <strong>Full</strong> · costs money. Also runs the chapter and topic judges as classify does, and shows the calls and cost.
                </span>
              </label>
            </fieldset>

            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <button type="button" className="btn btn--blue" disabled={!canRun} onClick={() => void run()}>
                {running ? <Loader2 size={14} className="spin" /> : <Play size={14} />}
                {running ? "Mapping…" : "Map this question"}
              </button>
              <button
                type="button"
                className="btn btn--sm"
                disabled={running}
                onClick={() => {
                  setStem("");
                  setResult(null);
                  setQuestionId(null);
                  setError(null);
                }}
              >
                Clear
              </button>
            </div>
          </div>
        </div>
      </section>

      <section className="section" style={{ marginTop: 18 }} aria-labelledby="find-h">
        <div className="section__head">
          <h2 id="find-h" className="section-q" style={{ fontSize: 17 }}>
            Or load a stored question
          </h2>
        </div>
        <div className="card">
          <div className="card__body" style={{ display: "grid", gap: 12 }}>
            <form
              style={{ display: "flex", gap: 8 }}
              onSubmit={(e) => {
                e.preventDefault();
                void find();
              }}
            >
              <input
                className="input"
                style={{ flex: 1 }}
                aria-label="Search stored questions"
                placeholder="Words from the question (3+ characters)"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <button type="submit" className="btn btn--sm" disabled={finding || query.trim().length < 3}>
                {finding ? <Loader2 size={13} className="spin" /> : <Search size={13} />} Find
              </button>
            </form>
            {found && found.length === 0 && <OpsEmpty>No stored question contains that.</OpsEmpty>}
            {found && found.length > 0 && (
              <div className="table-wrap table-wrap--scroll" style={{ maxHeight: 320 }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Question</th>
                      <th>Paper</th>
                      <th>Saved mapping</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {found.map((q) => (
                      <tr key={q.question_id}>
                        <td style={{ maxWidth: 380 }}>{(q.stem ?? "").slice(0, 160)}</td>
                        <td className="small">
                          {q.assessment}
                          <div className="muted">{schoolName.get(q.school_id) ?? ""} · {q.address}</div>
                        </td>
                        <td className="small">
                          {q.chapter ? `${q.chapter}${q.topic_section ? ` · ${q.topic_section}` : ""}` : "—"}
                        </td>
                        <td>
                          <button type="button" className="btn btn--sm" onClick={() => load(q)}>
                            Use
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </section>

      {result && <LabResultView result={result} />}
    </>
  );
}

function Fact({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="kpi" style={{ alignItems: "flex-start" }}>
      <div className="kpi__text">
        <div className="kpi__label">{label}</div>
        <div className="kpi__value" style={{ fontSize: 17, lineHeight: 1.25 }}>
          {value}
        </div>
        {sub && <div className="kpi__sub">{sub}</div>}
      </div>
    </div>
  );
}

function LabResultView({ result }: { result: LabResult }) {
  const f = result.final;
  const r = result.retrieval;
  const s = result.signals;
  const stored = result.stored;
  const sameChapter = stored ? stored.chapter === f.chapter : null;
  const sameTopic = stored && f.topic ? stored.section === f.topic.section : null;

  return (
    <section className="section" style={{ marginTop: 22 }} aria-labelledby="res-h">
      <div className="section__head">
        <h2 id="res-h" className="section-q" style={{ fontSize: 17 }}>
          Result
        </h2>
        <span style={{ display: "inline-flex", gap: 8 }}>
          <span className="tag">{result.mode === "full" ? "Full · judges ran" : "Retrieval only"}</span>
          <span className={`tag ${f.needs_review ? "tag--gold" : "tag--green"}`}>
            {f.needs_review ? "Would be flagged for review" : "Would be settled"}
          </span>
        </span>
      </div>

      <div className="evidence" style={{ marginBottom: 12 }}>
        <div>Nothing was saved. This ran against {result.chapters_in_book} chapters ({result.chunks} passages) of {result.books.join(", ")}.</div>
        {!result.v2_subject && (
          <div className="small muted" style={{ marginTop: 4 }}>
            This subject is not listed for the newer mapping logic, so the gate, memory and other gated options were off here, as they are in classify.
          </div>
        )}
      </div>

      <div className="grid grid--4">
        <Fact label="Chapter" value={f.chapter ?? "No chapter"} sub={f.board_unit ? `Unit ${f.board_unit}` : undefined} />
        <Fact
          label="Topic"
          value={f.topic?.section ? `${f.topic.section} · ${f.topic.heading ?? ""}` : "No topic"}
          sub={f.topic ? `decided by ${f.topic.source}${f.topic.verified === true ? ", verified" : ""}` : undefined}
        />
        <Fact label="Tier" value={f.tier ?? "Not decided"} sub={result.mode === "retrieval" ? "needs Full mode" : f.skill_required ?? undefined} />
        <Fact
          label="Concept family"
          value={f.family?.label ?? (f.family ? "None settled" : "—")}
          sub={f.family?.unsettled ?? f.family?.blocked ?? undefined}
        />
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <div className="card__body" style={{ display: "grid", gap: 6 }}>
          <div className="small muted">Why</div>
          <div>{f.reasoning}</div>
          {f.topic?.rationale && <div className="small muted">Topic: {f.topic.rationale}</div>}
          {f.topic && f.topic.secondaries.length > 0 && (
            <div className="small muted">
              Also tests: {f.topic.secondaries.map((x) => `${x.section} ${x.heading}`).join("; ")}
            </div>
          )}
          <div className="small muted">Confidence {f.source === "judges" ? pct(f.confidence) : `retrieval score ${f.confidence}`}</div>
        </div>
      </div>

      {stored && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="card__body" style={{ display: "grid", gap: 6 }}>
            <div className="small muted">Saved mapping for {stored.address}</div>
            <div>
              {stored.chapter ?? "No chapter"}
              {stored.section ? ` · ${stored.section}` : ""}
              {" "}
              <span className={`tag ${sameChapter && sameTopic !== false ? "tag--green" : "tag--gold"}`}>
                {sameChapter && sameTopic !== false ? "Matches the lab" : "Differs from the lab"}
              </span>
            </div>
            {stored.placement && (
              <div className="small muted">
                Latest placement: {stored.placement.source}
                {stored.placement.needs_review ? `, flagged (${stored.placement.review_reason ?? "review"})` : ", settled"}
                {stored.placement.tier ? `, ${stored.placement.tier}` : ""}
              </div>
            )}
          </div>
        </div>
      )}

      <h3 className="section-q" style={{ fontSize: 15, marginTop: 20 }}>How it decided</h3>
      <div className="grid grid--2" style={{ marginTop: 8 }}>
        <div className="card">
          <div className="card__body">
            <div className="small muted">Book retrieval ({r.retrievers.join(" + ")}){r.scope ? ` · ${r.scope}` : ""}</div>
            <div className="table-wrap" style={{ marginTop: 8 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Chapter</th>
                    <th>Score</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>{r.chapter ?? "—"}</strong></td>
                    <td>{r.score}</td>
                  </tr>
                  {r.ranking.map((x, i) => (
                    <tr key={i}>
                      <td>{x.chapter ?? "—"}</td>
                      <td>{x.score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="small muted" style={{ marginTop: 6 }}>
              Lead over the runner-up {r.margin} ·{" "}
              {r.retrievers.length < 2 ? "one retriever only (no embeddings)" : r.retrievers_agreed ? "retrievers agree" : "retrievers disagree"}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card__body" style={{ display: "grid", gap: 10 }}>
            <div>
              <div className="small muted">Tier 0 gate</div>
              <span className={`tag ${s.gate.would_pass ? "tag--green" : "tag--gold"}`}>
                {s.gate.would_pass ? "Would skip the chapter judge" : "Would ask the chapter judge"}
              </span>
              <div className="small muted">
                relative lead {pct(s.gate.relative_margin)} (needs {pct(s.gate.min_margin)})
                {s.gate.reason ? ` · ${s.gate.reason}` : ""}
              </div>
            </div>
            <div>
              <div className="small muted">Trained classifier</div>
              <div>
                {s.classifier.chapter ?? "No opinion"}{" "}
                {s.classifier.chapter && <span className="muted">({pct(s.classifier.confidence)})</span>}
              </div>
            </div>
            <div>
              <div className="small muted">Confirmed questions from the chosen school</div>
              {s.memory === null ? (
                <div className="small muted">No school chosen.</div>
              ) : s.memory.nearest.length === 0 ? (
                <div className="small muted">{s.memory.remembered_questions} remembered; none close to this one.</div>
              ) : (
                <>
                  <span className={`tag ${s.memory.would_reuse ? "tag--green" : ""}`}>
                    {s.memory.would_reuse ? "Would reuse a confirmed placement" : "No close twin"}
                  </span>
                  <ul className="small" style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                    {s.memory.nearest.map((n, i) => (
                      <li key={i}>
                        {pct(n.similarity)} · {n.chapter}
                        {n.section ? ` ${n.section}` : ""} — <span className="muted">{n.stem}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <div className="card__body">
          <div className="small muted">Passages that put it there</div>
          <ul className="small" style={{ margin: "6px 0 0", paddingLeft: 18, display: "grid", gap: 6 }}>
            {r.evidence.map((e, i) => (
              <li key={i}>
                <strong>{e.chapter}</strong> · {e.reference}
                {e.section ? ` (section ${e.section})` : ""} — <span className="muted">{e.text}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {result.mode === "full" && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="card__body" style={{ display: "grid", gap: 4 }}>
            <div className="small muted">What this one question cost</div>
            <div>
              {result.spend.calls} call{result.spend.calls === 1 ? "" : "s"} · {result.spend.models.join(", ") || "—"} ·{" "}
              {result.spend.input_tokens.toLocaleString()} in / {result.spend.output_tokens.toLocaleString()} out
              {result.spend.cache_read_tokens > 0 && ` / ${result.spend.cache_read_tokens.toLocaleString()} cached`}
            </div>
            <div>
              <strong>{money(result.spend.estimated_usd)}</strong> run live here ·{" "}
              <strong>{money(result.spend.estimated_usd_topic_batched)}</strong> as classify runs it (topic judge batched at half price)
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
