"use client";

/**
 * The landing screen.
 *
 * Every figure is a count of rows that exist. There is no target, no projection, and no
 * "progress" that is not marks entered over questions on the paper. A dashboard that
 * estimates is one somebody eventually acts on, and this product's whole claim is that it
 * does not say things it cannot show.
 *
 * The one ratio drawn as a meter is questions mapped to the book, because that is the
 * ratio that decides whether a report can be written at all: a question with no chapter
 * contributes to no finding. A two-slice donut was the obvious thing to copy and is the
 * wrong form for one ratio against its limit.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { CopyLink } from "@/components/CopyLink";
import { api, type Dashboard, type Overview } from "@/lib/api";
import { getApiKey } from "@/lib/session";

const STAGE: Record<string, { label: string; tone: string }> = {
  mapped: { label: "Mapped to the book", tone: "good" },
  read: { label: "Read, not yet mapped", tone: "warn" },
  scanned: { label: "Scanned, not yet read", tone: "warn" },
  empty: { label: "Nothing scanned", tone: "idle" },
};

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api.dashboard(key).then(setData).catch(() => setError("Could not load the dashboard."));
    api.overview(key).then(setOverview).catch(() => undefined);
  }, []);

  if (error) return <main className="wrap"><p className="error">{error}</p></main>;
  if (!data) return <main className="wrap"><p className="muted">Loading…</p></main>;

  const c = data.counts;
  const mappedPct = c.questions_total
    ? Math.round((c.questions_mapped / c.questions_total) * 100)
    : 0;

  return (
    <main className="wrap">
      <section className="hello">
        <div>
          <p className="eyebrow">{data.school.name}</p>
          <h1>
            {c.papers_read === 0
              ? "Nothing has been read yet"
              : `${c.papers_read} paper${c.papers_read === 1 ? "" : "s"} read`}
          </h1>
          <p className="lede">
            {c.scripts_stored} answer script{c.scripts_stored === 1 ? "" : "s"} stored,{" "}
            {c.reports_issued} report{c.reports_issued === 1 ? "" : "s"} issued. Every
            number on this screen is a count of something saved, never an estimate.
          </p>
        </div>
        <div className="quick">
          <Link className="btn" href="/admin/paper">Read a question paper</Link>
          <Link className="btn secondary" href="/admin/answers">Enter an answer sheet</Link>
        </div>
      </section>

      <div className="tiles">
        <Tile label="Students" value={c.students} note={`${c.classes} class${c.classes === 1 ? "" : "es"}`} />
        <Tile label="Question papers stored" value={c.question_papers_stored} note="scans kept" />
        <Tile label="Answer scripts stored" value={c.scripts_stored} note="pages kept per student" />
        <Tile label="Reports issued" value={c.reports_issued} note="copies saved as sent" />
      </div>

      <section className="card">
        <div className="cardhead">
          <h2>Questions mapped to the book</h2>
          <span className="figure">
            {c.questions_mapped} <span className="of">of {c.questions_total}</span>
          </span>
        </div>
        {/* A meter, not a donut: one ratio against its limit. The track is a lighter step
            of the same hue so the state reads across the whole bar. */}
        <div
          className="meter"
          role="img"
          aria-label={`${c.questions_mapped} of ${c.questions_total} questions mapped`}
        >
          <div className="fill" style={{ width: `${mappedPct}%` }} />
        </div>
        <p className="note">
          {c.questions_total === 0
            ? "No paper has been read yet, so there is nothing to map."
            : c.questions_mapped === c.questions_total
              ? "Every question found so far carries a chapter, so every mark counts towards a finding."
              : `${c.questions_total - c.questions_mapped} question(s) carry no chapter yet. A mark on one of those counts towards no finding, so it is left out of the report rather than guessed at.`}
        </p>
      </section>

      <div className="two">
        <section className="card">
          <div className="cardhead">
            <h2>Papers</h2>
            <Link className="small" href="/admin/paper">Read another</Link>
          </div>
          {data.papers.length === 0 ? (
            <p className="muted">None yet.</p>
          ) : (
            <ul className="rows">
              {data.papers.map((p) => {
                const pct = p.questions ? Math.round((p.mapped / p.questions) * 100) : 0;
                const stage = STAGE[p.stage];
                return (
                  <li key={p.id} className="row">
                    <div className="rowtop">
                      <span className="name">{p.title}</span>
                      <span className={`pill ${stage.tone}`}>{stage.label}</span>
                    </div>
                    <div className="meter thin" aria-hidden>
                      <div className="fill" style={{ width: `${pct}%` }} />
                    </div>
                    <p className="sub">
                      {p.questions} question{p.questions === 1 ? "" : "s"} ·{" "}
                      {p.mapped} mapped · {p.students_marked} student
                      {p.students_marked === 1 ? "" : "s"} marked
                      {p.paper_stored ? " · paper kept" : " · paper not stored"}
                    </p>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="card">
          <div className="cardhead">
            <h2>Students</h2>
            {overview?.sections[0] && (
              <Link className="small" href={`/admin/sections/${overview.sections[0].section_id}`}>
                Open a class
              </Link>
            )}
          </div>
          {data.students.length === 0 ? (
            <p className="muted">No students on the roster yet.</p>
          ) : (
            <ul className="rows">
              {data.students.map((s) => (
                <li key={s.student_id} className="row">
                  <div className="rowtop">
                    <Link className="name" href={`/admin/students/${s.student_id}`}>
                      {s.name}
                    </Link>
                    <span className="muted small">roll {s.roll_no}</span>
                  </div>
                  <p className="sub">
                    {s.papers_marked} paper{s.papers_marked === 1 ? "" : "s"} marked ·{" "}
                    {s.scripts} script{s.scripts === 1 ? "" : "s"} stored ·{" "}
                    {s.reports} report{s.reports === 1 ? "" : "s"} issued
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="two">
        <section className="card">
          <div className="cardhead">
            <h2>Recently scanned scripts</h2>
            <Link className="small" href="/admin/answers">Store another</Link>
          </div>
          {data.recent_scripts.length === 0 ? (
            <p className="muted">
              No answer script has been stored yet. A mark stands on its own until one is.
            </p>
          ) : (
            <ul className="rows">
              {data.recent_scripts.map((s) => (
                <li key={s.document_id} className="row">
                  <div className="rowtop">
                    <Link className="name" href={`/admin/students/${s.student_id}`}>
                      {s.student}
                    </Link>
                    <span className="muted small">
                      {s.page_count} page{s.page_count === 1 ? "" : "s"}
                    </span>
                  </div>
                  <p className="sub">
                    {s.assessment_title ?? "a paper"} · stored {s.stored_at?.slice(0, 10)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card">
          <div className="cardhead">
            <h2>Classes</h2>
          </div>
          {!overview || overview.sections.length === 0 ? (
            <p className="muted">No classes yet.</p>
          ) : (
            <ul className="rows">
              {overview.sections.map((s) => (
                <li key={s.section_id} className="row">
                  <div className="rowtop">
                    <Link className="name" href={`/admin/sections/${s.section_id}`}>
                      {s.label}
                    </Link>
                    <span className="muted small">{s.students} students</span>
                  </div>
                  <p className="sub">The link to give this class:</p>
                  <CopyLink path={s.student_path} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <style jsx>{`
        .wrap { max-width: 1180px; margin: 0 auto; padding-top: 22px; }

        .hello {
          display: flex; justify-content: space-between; gap: 18px; flex-wrap: wrap;
          align-items: flex-start; background: var(--surface); border: 1px solid var(--rule);
          border-radius: var(--radius); padding: 20px 22px; margin-bottom: 16px;
        }
        .hello h1 { margin: 4px 0 6px; font-size: 27px; }
        .lede { color: var(--ink-2); margin: 0; max-width: 62ch; font-size: 15px; }
        .quick { display: flex; gap: 8px; flex-wrap: wrap; }

        .tiles {
          display: grid; gap: 12px; margin-bottom: 16px;
          grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        }

        .card {
          background: var(--surface); border: 1px solid var(--rule);
          border-radius: var(--radius); padding: 18px 20px; margin-bottom: 16px;
        }
        .cardhead {
          display: flex; justify-content: space-between; align-items: baseline;
          gap: 12px; margin-bottom: 12px;
        }
        .cardhead h2 { margin: 0; font-size: 17px; }
        .figure { font-size: 22px; font-weight: 600; }
        .figure .of { font-size: 14px; font-weight: 400; color: var(--ink-3); }

        .meter {
          height: 10px; border-radius: 999px; background: var(--surface-2);
          overflow: hidden;
        }
        .meter.thin { height: 6px; margin: 8px 0 6px; }
        /* The same token the existing progress bars use. The brand accent is a red, and a
           meter that fills red as things go right reads as an alarm. */
        .fill { height: 100%; background: var(--verify); border-radius: 999px; }

        .note { color: var(--ink-2); font-size: 13.5px; margin: 10px 0 0; max-width: 70ch; }

        .two { display: grid; gap: 16px; grid-template-columns: 1fr 1fr; }
        /* Same reason as the copy field: a grid track sized 1fr still refuses to go below its
           content unless the child is told it may. */
        .two > * { min-width: 0; }
        .rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }
        .rows > li { min-width: 0; }
        .row { border-bottom: 1px solid var(--rule); padding-bottom: 12px; }
        .rows li:last-child { border-bottom: 0; padding-bottom: 0; }
        .rowtop { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
        .name { font-weight: 600; color: var(--ink); text-decoration: none; }
        a.name:hover { text-decoration: underline; }
        .sub { color: var(--ink-2); font-size: 13px; margin: 4px 0 0; }

        .pill {
          font-size: 11.5px; padding: 2px 9px; border-radius: 999px;
          background: var(--surface-2); color: var(--ink-2); white-space: nowrap;
        }
        .pill.good { background: #e7f2ea; color: #1c6b33; }
        .pill.warn { background: #fdf1de; color: #8a5b00; }

        @media (max-width: 900px) { .two { grid-template-columns: 1fr; } }
      `}</style>
    </main>
  );
}

function Tile({ label, value, note }: { label: string; value: number; note: string }) {
  return (
    <div className="tile">
      <p className="label">{label}</p>
      <p className="value">{value}</p>
      <p className="note">{note}</p>
      <style jsx>{`
        .tile {
          background: var(--surface); border: 1px solid var(--rule);
          border-radius: var(--radius); padding: 16px 18px;
        }
        .label {
          margin: 0; font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase;
          color: var(--ink-3);
        }
        /* Proportional figures: a stat value is read as a number, not lined up in a column. */
        .value { margin: 6px 0 2px; font-size: 30px; font-weight: 600; line-height: 1; }
        .note { margin: 0; font-size: 12.5px; color: var(--ink-2); }
      `}</style>
    </div>
  );
}
