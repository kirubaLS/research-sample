"use client";

// §6.2 -- Class view (Class Teacher scope): every subject visible read-only, "Enter
// Marks" withheld for subjects outside the teacher's own subject assignment.
// TODO(backend): Dependency Index #1 -- roster/cohort/papers below are all mocked;
// a real version would be the principal's existing section view, permission-clipped by a
// real teacher_assignment row.

import Link from "next/link";
import { use, useState } from "react";
import { MOCK_CLASS_ROSTERS, MOCK_PAPERS_THIS_TERM, MOCK_SUBJECTS, MOCK_TEACHER, subjectLabel } from "@/lib/mocks/teacher";

type Tab = "roster" | "cohort" | "papers";

export default function ClassView({ params }: { params: Promise<{ sectionId: string }> }) {
  const { sectionId } = use(params);
  const [tab, setTab] = useState<Tab>("roster");
  const roster = MOCK_CLASS_ROSTERS[sectionId] ?? [];
  const papers = MOCK_PAPERS_THIS_TERM[sectionId] ?? [];
  const ownSubjects = new Set(
    MOCK_TEACHER.assignments
      .filter((a) => a.type === "subject" && a.sectionId === sectionId)
      .map((a) => (a.type === "subject" ? a.subjectCode : "")),
  );

  return (
    <main className="narrow">
      <div className="hero row between" style={{ alignItems: "flex-end" }}>
        <h1 style={{ margin: 0 }}>{sectionId}</h1>
        <p className="cardnote">{roster.length} students</p>
      </div>

      <div className="subtabbar" style={{ display: "flex", gap: 4, marginBottom: 16, borderBottom: "1px solid var(--rule)" }}>
        {(["roster", "cohort", "papers"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`subtab-btn${tab === t ? " on" : ""}`}
            style={{
              border: 0, background: "transparent", padding: "8px 4px", marginRight: 14,
              fontSize: 13.5, fontWeight: 600, cursor: "pointer",
              color: tab === t ? "var(--brand-ink)" : "var(--ink-3)",
              borderBottom: tab === t ? "2px solid var(--brand-ink)" : "2px solid transparent",
            }}
          >
            {t === "roster" ? "Roster" : t === "cohort" ? "Cohort snapshot" : "Papers"}
          </button>
        ))}
      </div>

      {tab === "roster" && (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Roll</th>
                <th>Name</th>
                {MOCK_SUBJECTS.map((s) => <th key={s.code}>{s.label}</th>)}
                <th />
              </tr>
            </thead>
            <tbody>
              {roster.map((row) => (
                <tr key={row.studentId}>
                  <td>{row.roll}</td>
                  <td>{row.name}</td>
                  {MOCK_SUBJECTS.map((s) => (
                    <td key={s.code}>{row.scores[s.code] ?? "—"}</td>
                  ))}
                  <td>
                    <Link href={`/teacher/student/${row.studentId}`}>
                      <button type="button" className="secondary tiny">View</button>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "cohort" && (
        <div className="card">
          <p className="cardnote" style={{ marginTop: 0 }}>
            Cohort snapshot for {sectionId} — band counts and tier breakdown, scoped to
            this section only. Reuses the same cohort-report visualization as BoardX's
            Standard Performance Snapshot (§5.3.2), here read-only for one section.
          </p>
          <p className="small muted">
            TODO(backend): Dependency Index #1 — a real version reads
            <code> GET /reports/cohort/{"{assessment_id}"}</code> filtered to this section
            once teacher scoping exists; that endpoint itself is already buildable.
          </p>
        </div>
      )}

      {tab === "papers" && (
        <div className="stack" style={{ gap: 8 }}>
          {papers.length === 0 && <p className="muted">No papers recorded this term.</p>}
          {papers.map((p, i) => {
            const canEnter = ownSubjects.has(p.subjectCode);
            return (
              <div className="card row between" key={i}>
                <div>
                  <strong>{p.title}</strong>
                  <p className="cardnote">{subjectLabel(p.subjectCode)}</p>
                </div>
                {canEnter ? (
                  <Link href="/admin/answers">
                    <button type="button" className="secondary tiny">Enter marks</button>
                  </Link>
                ) : (
                  <span
                    className="small muted"
                    title="Only teachers assigned to this subject can enter marks"
                  >
                    Read-only
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
