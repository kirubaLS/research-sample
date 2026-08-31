"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CopyLink } from "@/components/CopyLink";
import { api, type Overview } from "@/lib/api";
import { getApiKey } from "@/lib/session";

export default function Dashboard() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api.overview(key).then(setData).catch(() => setError("Could not load the dashboard."));
  }, []);

  if (error) {
    return (
      <main>
        <p className="error">{error}</p>
      </main>
    );
  }
  if (!data) {
    return (
      <main>
        <p className="muted">Loading…</p>
      </main>
    );
  }

  const pct = data.totals.students
    ? Math.round((data.totals.completed / data.totals.students) * 100)
    : 0;

  return (
    <main>
      <div className="hero">
        <p className="eyebrow">{data.school.name}</p>
        <h1>Dashboard</h1>
      </div>

      <div className="grid three" style={{ marginTop: 18 }}>
        <div className="stat">
          <div className="label">Students</div>
          <div className="value">{data.totals.students}</div>
        </div>
        <div className="stat">
          <div className="label">Completed the test</div>
          <div className="value verify">{data.totals.completed}</div>
        </div>
        <div className="stat">
          <div className="label">Flagged for review</div>
          <div className={`value ${data.totals.flagged ? "mark" : ""}`}>{data.totals.flagged}</div>
        </div>
      </div>

      <div className="section-head row between">
        <h2>Classes</h2>
        <span className="small muted">{pct}% of students have finished</span>
      </div>

      {data.sections.length === 0 ? (
        <div className="card empty">
          <div className="big">No classes yet</div>
          <p className="cardnote">
            Run <span className="mono">python -m scripts.seed</span> to create a demo class.
          </p>
        </div>
      ) : (
        <div className="grid two">
          {data.sections.map((s) => (
            <div className="card" key={s.section_id}>
              <div className="row between" style={{ marginBottom: 4 }}>
                <h3>{s.label}</h3>
                <span className="badge">{s.students} students</span>
              </div>

              <div className="progress" style={{ margin: "12px 0 6px" }}>
                <div
                  style={{ width: `${s.students ? (s.completed / s.students) * 100 : 0}%` }}
                />
              </div>
              <p className="small muted" style={{ marginBottom: 16 }}>
                {s.completed} of {s.students} finished
                {s.flagged > 0 && <> · {s.flagged} flagged</>}
              </p>

              <label>Student link — give this to the class</label>
              <CopyLink path={s.student_path} />

              <div className="row" style={{ marginTop: 16 }}>
                <Link className="btn secondary" href={`/admin/sections/${s.section_id}`}>
                  Open roster
                </Link>
                <Link className="btn secondary" href={s.student_path}>
                  Preview as a student
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="section-head">
        <h2>Papers and scripts</h2>
      </div>
      <div className="grid two">
        <Link href="/admin/paper" className="card">
          <h3>Read a question paper</h3>
          <p className="cardnote">
            Upload the paper and every question is matched to a chapter, a section and a
            concept family — from the textbook, not from memory. Anything that cannot be
            matched says so.
          </p>
          <span className="arrow">Open the paper reader →</span>
        </Link>

        <Link href="/admin/answers" className="card">
          <h3>Enter an answer sheet</h3>
          <p className="cardnote">
            Pick a paper that has been read, pick a student, and enter their marks question
            by question. Each row says which chapter and concept the mark counts towards,
            and a question nobody has marked yet stays visible until it is.
          </p>
          <span className="arrow">Open the answer sheet →</span>
        </Link>

        <Link href="/admin/scan" className="card">
          <h3>Scan a script</h3>
          <p className="cardnote">
            Capture the cover page and every page. The engine reconciles the marks against
            the totals the teacher wrote.
          </p>
          <span className="arrow">Open the scanner →</span>
        </Link>

        <div className="card">
          <h3>Assessments</h3>
          {data.assessments.length === 0 ? (
            <p className="cardnote">None yet.</p>
          ) : (
            <div className="stack" style={{ gap: 8 }}>
              {data.assessments.slice(0, 4).map((a) => (
                <div className="row between" key={a.id}>
                  <span className="small">
                    {a.title}
                    {a.paper_code && <span className="muted"> · {a.paper_code}</span>}
                  </span>
                  <span className={`badge ${a.frozen ? "green" : "amber"}`}>
                    {a.frozen ? "Q-matrix frozen" : a.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
