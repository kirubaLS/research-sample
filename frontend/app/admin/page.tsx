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
import { api, type Dashboard, type Overview, type SchoolStaffRow } from "@/lib/api";
import { getApiKey } from "@/lib/session";

const STAGE: Record<string, { label: string; tone: "low" | "medium" }> = {
  mapped: { label: "Mapped to the book", tone: "low" },
  read: { label: "Read, not yet mapped", tone: "medium" },
  scanned: { label: "Scanned, not yet read", tone: "medium" },
  empty: { label: "Nothing scanned", tone: "medium" },
};

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [staff, setStaff] = useState<SchoolStaffRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api.dashboard(key).then(setData).catch(() => setError("Could not load the dashboard."));
    api.overview(key).then(setOverview).catch(() => undefined);
    api.listStaff(key).then(setStaff).catch(() => undefined);
  }, []);

  if (error) return <main className="content"><div className="evidence evidence--gold"><div>{error}</div></div></main>;
  if (!data) return <main className="content"><p className="muted">Loading…</p></main>;

  const c = data.counts;
  const mappedPct = c.questions_total
    ? Math.round((c.questions_mapped / c.questions_total) * 100)
    : 0;
  // Both already computed for other parts of this same screen -- a paper's stage drives
  // its pill in the Papers card, and a student's script/mark counts drive their row in
  // Students. Filtering rather than a new endpoint: this is the same data, just the slice
  // that actually needs a person to do something about it.
  const needsMapping = data.papers.filter((p) => p.stage !== "mapped" && p.stage !== "empty");
  const needsMarks = data.students.filter((s) => s.scripts > 0 && s.papers_marked === 0);

  return (
    <main className="content">
      <section className="card" style={{ marginBottom: 20 }}>
        <div className="card__head" style={{ flexWrap: "wrap" }}>
          <div>
            <p className="eyebrow">{data.school.name}</p>
            <h1 className="page-title" style={{ marginTop: 4 }}>
              {c.papers_read === 0
                ? "Nothing has been read yet"
                : `${c.papers_read} paper${c.papers_read === 1 ? "" : "s"} read`}
            </h1>
          </div>
        </div>
        <div className="card__body">
          <p className="page-sub" style={{ maxWidth: "62ch" }}>
            {c.scripts_stored} answer script{c.scripts_stored === 1 ? "" : "s"} stored,{" "}
            {c.reports_issued} report{c.reports_issued === 1 ? "" : "s"} issued. Every
            number on this screen is a count of something saved, never an estimate.
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
            <Link className="btn btn--primary" href="/principal/papers">Read a question paper</Link>
            <Link className="btn" href="/principal/enter-marks">Enter an answer sheet</Link>
            <Link className="btn" href="/principal/scan-answers">Scan a class mark sheet</Link>
          </div>
        </div>
      </section>

      <div className="grid grid--4" style={{ marginBottom: 20 }}>
        <Tile label="Students" value={c.students} note={`${c.classes} class${c.classes === 1 ? "" : "es"}`} />
        <Tile label="Question papers stored" value={c.question_papers_stored} note="scans kept" />
        <Tile label="Answer scripts stored" value={c.scripts_stored} note="pages kept per student" />
        <Tile label="Reports issued" value={c.reports_issued} note="copies saved as sent" />
      </div>

      <section className="card" style={{ marginBottom: 20 }}>
        <div className="card__head">
          <h2 className="section-q">Questions mapped to the book</h2>
          <span className="stat__value stat__value--sm">
            {c.questions_mapped} <small className="muted" style={{ fontSize: 14, fontWeight: 400 }}>of {c.questions_total}</small>
          </span>
        </div>
        <div className="card__body">
          {/* A meter, not a donut: one ratio against its limit. The track is a lighter step
              of the same hue so the state reads across the whole bar. */}
          <div
            className="bar"
            role="img"
            aria-label={`${c.questions_mapped} of ${c.questions_total} questions mapped`}
          >
            <div className="bar__fill" style={{ width: `${mappedPct}%` }} />
          </div>
          <p className="muted small" style={{ marginTop: 10, maxWidth: "70ch" }}>
            {c.questions_total === 0
              ? "No paper has been read yet, so there is nothing to map."
              : c.questions_mapped === c.questions_total
                ? "Every question found so far carries a chapter, so every mark counts towards a finding."
                : `${c.questions_total - c.questions_mapped} question(s) carry no chapter yet. A mark on one of those counts towards no finding, so it is left out of the report rather than guessed at.`}
          </p>
        </div>
      </section>

      <div className="grid grid--2" style={{ marginBottom: 20 }}>
        <section className="card">
          <div className="card__head">
            <h2 className="section-q">Papers</h2>
            <Link className="small" href="/principal/papers">Read another</Link>
          </div>
          <div className="card__body">
            {data.papers.length === 0 ? (
              <p className="muted">None yet.</p>
            ) : (
              <ul className="list-rows">
                {data.papers.map((p) => {
                  const pct = p.questions ? Math.round((p.mapped / p.questions) * 100) : 0;
                  const stage = STAGE[p.stage];
                  return (
                    <li key={p.id} className="list-rows__row">
                      <div className="list-rows__top">
                        <span className="strong">{p.title}</span>
                        <span className={`attn attn--${stage.tone}`}>{stage.label}</span>
                      </div>
                      <div className="bar" style={{ height: 6, margin: "8px 0 6px" }} aria-hidden>
                        <div className="bar__fill" style={{ width: `${pct}%` }} />
                      </div>
                      <p className="muted small" style={{ margin: 0 }}>
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
          </div>
        </section>

        <section className="card">
          <div className="card__head">
            <h2 className="section-q">Students</h2>
            {overview?.sections[0] && (
              <Link className="small" href={`/admin/sections/${overview.sections[0].section_id}`}>
                Open a class
              </Link>
            )}
          </div>
          <div className="card__body">
            {data.students.length === 0 ? (
              <p className="muted">No students on the roster yet.</p>
            ) : (
              <ul className="list-rows">
                {data.students.map((s) => (
                  <li key={s.student_id} className="list-rows__row">
                    <div className="list-rows__top">
                      <Link className="strong" href={`/admin/students/${s.student_id}`}>
                        {s.name}
                      </Link>
                      <span className="muted small">roll {s.roll_no}</span>
                    </div>
                    <p className="muted small" style={{ margin: 0 }}>
                      {s.papers_marked} paper{s.papers_marked === 1 ? "" : "s"} marked ·{" "}
                      {s.scripts} script{s.scripts === 1 ? "" : "s"} stored ·{" "}
                      {s.reports} report{s.reports === 1 ? "" : "s"} issued
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>

      <div className="grid grid--2" style={{ marginBottom: 20 }}>
        <section className="card">
          <div className="card__head">
            <h2 className="section-q">Recently scanned scripts</h2>
            <Link className="small" href="/principal/enter-marks">Store another</Link>
          </div>
          <div className="card__body">
            {data.recent_scripts.length === 0 ? (
              <p className="muted">
                No answer script has been stored yet. A mark stands on its own until one is.
              </p>
            ) : (
              <ul className="list-rows">
                {data.recent_scripts.map((s) => (
                  <li key={s.document_id} className="list-rows__row">
                    <div className="list-rows__top">
                      <Link className="strong" href={`/admin/students/${s.student_id}`}>
                        {s.student}
                      </Link>
                      <span className="muted small">
                        {s.page_count} page{s.page_count === 1 ? "" : "s"}
                      </span>
                    </div>
                    <p className="muted small" style={{ margin: 0 }}>
                      {s.assessment_title ?? "a paper"} · stored {s.stored_at?.slice(0, 10)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card__head">
            <h2 className="section-q">Classes</h2>
          </div>
          <div className="card__body">
            {!overview || overview.sections.length === 0 ? (
              <p className="muted">No classes yet.</p>
            ) : (
              <ul className="list-rows">
                {overview.sections.map((s) => (
                  <li key={s.section_id} className="list-rows__row">
                    <div className="list-rows__top">
                      <Link className="strong" href={`/admin/sections/${s.section_id}`}>
                        {s.label}
                      </Link>
                      <span className="muted small">
                        {s.students} student{s.students === 1 ? "" : "s"}
                      </span>
                    </div>
                    <p className="muted small" style={{ margin: 0 }}>
                      {s.completed} of {s.students} finished the interest test
                      {s.flagged > 0 && ` · ${s.flagged} flagged`}
                    </p>
                    <CopyLink path={s.student_path} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>

      {(needsMapping.length > 0 || needsMarks.length > 0) && (
        <section className="card" style={{ marginBottom: 20 }}>
          <div className="card__head">
            <h2 className="section-q">Needs attention</h2>
          </div>
          <div className="card__body">
            <ul className="list-rows">
              {needsMapping.map((p) => (
                <li key={p.id} className="list-rows__row">
                  <div className="list-rows__top">
                    <Link className="strong" href="/principal/papers">{p.title}</Link>
                    <span className="attn attn--medium">{STAGE[p.stage].label}</span>
                  </div>
                  <p className="muted small" style={{ margin: 0 }}>
                    {p.mapped} of {p.questions} question{p.questions === 1 ? "" : "s"} mapped to
                    the book so far.
                  </p>
                </li>
              ))}
              {needsMarks.map((s) => (
                <li key={s.student_id} className="list-rows__row">
                  <div className="list-rows__top">
                    <Link className="strong" href={`/admin/students/${s.student_id}`}>{s.name}</Link>
                    <span className="attn attn--medium">Script stored, no marks yet</span>
                  </div>
                  <p className="muted small" style={{ margin: 0 }}>
                    {s.scripts} script{s.scripts === 1 ? "" : "s"} stored, roll {s.roll_no}.
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      <section className="card">
        <div className="card__head">
          <h2 className="section-q">Who has access</h2>
        </div>
        <div className="card__body">
          {!staff ? (
            <p className="muted">Loading…</p>
          ) : staff.length === 0 ? (
            <p className="muted">No keys issued for this school yet.</p>
          ) : (
            <ul className="list-rows">
              {staff.map((s) => (
                <li key={s.id} className="list-rows__row">
                  <div className="list-rows__top">
                    <span className="strong">{s.label || <span className="muted">unnamed</span>}</span>
                    <span className="muted small">
                      {s.role === "admin" ? "Admin" : "Principal"}
                      {s.revoked_at && " · revoked"}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="small muted" style={{ marginTop: 10 }}>
            Issuing or revoking a key happens in the operator console, not here.
          </p>
        </div>
      </section>

      <style jsx>{`
        .list-rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }
        .list-rows > li { min-width: 0; }
        .list-rows__row { border-bottom: 1px solid var(--line); padding-bottom: 12px; }
        .list-rows li:last-child { border-bottom: 0; padding-bottom: 0; }
        .list-rows__top { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
      `}</style>
    </main>
  );
}

function Tile({ label, value, note }: { label: string; value: number; note: string }) {
  return (
    <div className="stat">
      <p className="stat__label">{label}</p>
      <p className="stat__value">{value}</p>
      <p className="muted small" style={{ margin: 0 }}>{note}</p>
    </div>
  );
}
