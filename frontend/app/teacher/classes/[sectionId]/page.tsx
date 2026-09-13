"use client";

// §6.2 -- Class view (Class Teacher scope): the same roster/cohort a principal reads for
// one class, via the real teacher-scoped endpoints (GET /admin/teacher/sections/{id}/students,
// GET /admin/teacher/cohort/{id}) -- refused with 404 unless this key holds an assignment
// on the section. Marks entry stays with subject-assigned teachers only (spec §10.2), so
// this view is read-only regardless of the subject.

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { api, type RosterRow } from "@/lib/api";
import { getApiKey } from "@/lib/session";

type Tab = "roster" | "cohort";
type Cohort = { holland: Record<string, number>; streams: Record<string, number>; counted: number; withheld: number };

export default function ClassView({ params }: { params: Promise<{ sectionId: string }> }) {
  const { sectionId } = use(params);
  const [tab, setTab] = useState<Tab>("roster");
  const [section, setSection] = useState<{ id: string; label: string } | null>(null);
  const [roster, setRoster] = useState<RosterRow[] | null>(null);
  const [cohort, setCohort] = useState<Cohort | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherRoster(key, sectionId)
      .then((res) => {
        setSection(res.section);
        setRoster(res.students);
      })
      .catch(() => setError("Could not load this class. It may not be assigned to you."));
  }, [sectionId]);

  useEffect(() => {
    if (tab !== "cohort") return;
    const key = getApiKey();
    if (!key) return;
    api.teacherCohort(key, sectionId).then(setCohort);
  }, [tab, sectionId]);

  return (
    <main className="narrow">
      <div className="hero row between" style={{ alignItems: "flex-end" }}>
        <h1 style={{ margin: 0 }}>{section?.label ?? sectionId}</h1>
        <p className="cardnote">{roster?.length ?? "…"} students</p>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="subtabbar" style={{ display: "flex", gap: 4, marginBottom: 16, borderBottom: "1px solid var(--rule)" }}>
        {(["roster", "cohort"] as Tab[]).map((t) => (
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
            {t === "roster" ? "Roster" : "Cohort snapshot"}
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
                <th>Status</th>
                <th>Papers marked</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(roster ?? []).map((row) => (
                <tr key={row.student_id}>
                  <td>{row.roll_no}</td>
                  <td>{row.name}</td>
                  <td>{row.status.replace("_", " ")}</td>
                  <td>{row.papers_marked}</td>
                  <td>
                    <Link href={`/teacher/student/${row.student_id}`}>
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
            Cohort snapshot for {section?.label ?? sectionId} — Holland-code and stream-fit
            counts across the interest test, scoped to this section only.
          </p>
          {cohort ? (
            <>
              <p><strong>Counted:</strong> {cohort.counted} &nbsp; <strong>Withheld:</strong> {cohort.withheld}</p>
              <p className="cardnote">Holland: {JSON.stringify(cohort.holland)}</p>
              <p className="cardnote">Streams: {JSON.stringify(cohort.streams)}</p>
            </>
          ) : (
            <p className="muted">Loading…</p>
          )}
        </div>
      )}
    </main>
  );
}
