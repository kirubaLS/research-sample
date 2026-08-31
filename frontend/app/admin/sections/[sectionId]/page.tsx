"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { CopyLink } from "@/components/CopyLink";
import { api, type RosterRow } from "@/lib/api";
import { getApiKey } from "@/lib/session";

const STATUS: Record<RosterRow["status"], { label: string; cls: string }> = {
  complete: { label: "Complete", cls: "green" },
  in_progress: { label: "In progress", cls: "amber" },
  not_started: { label: "Not started", cls: "" },
};

export default function RosterPage({ params }: { params: Promise<{ sectionId: string }> }) {
  const { sectionId } = use(params);
  const [data, setData] = useState<Awaited<ReturnType<typeof api.roster>> | null>(null);
  const [cohort, setCohort] = useState<Awaited<ReturnType<typeof api.cohort>> | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api.roster(key, sectionId).then(setData).catch(() => undefined);
    api.cohort(key, sectionId).then(setCohort).catch(() => undefined);
  }, [sectionId]);

  if (!data) {
    return (
      <main>
        <p className="muted">Loading…</p>
      </main>
    );
  }

  return (
    <main>
      <div className="hero">
        <p className="eyebrow">
          <Link href="/admin" style={{ color: "inherit" }}>
            ← Dashboard
          </Link>
        </p>
        <h1>{data.section.label}</h1>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <label>Student link</label>
        <CopyLink path={data.section.student_path} />
      </div>

      {cohort && cohort.counted > 0 && (
        <>
          <div className="section-head">
            <h2>Where this class leans</h2>
          </div>
          <div className="card">
            {Object.entries(cohort.streams)
              .sort((a, b) => b[1] - a[1])
              .map(([stream, n]) => (
                <div className="scalerow" key={stream}>
                  <span className="nm">{stream}</span>
                  <div className="scaletrack">
                    <div
                      className="scalefill"
                      style={{ width: `${(n / cohort.counted) * 100}%` }}
                    />
                  </div>
                  <span className="pct">{n}</span>
                </div>
              ))}
            <p className="small muted" style={{ marginTop: 12, marginBottom: 0 }}>
              {cohort.counted} profile{cohort.counted === 1 ? "" : "s"} counted
              {cohort.withheld > 0 && (
                <> · {cohort.withheld} withheld as too undifferentiated to call</>
              )}
            </p>
          </div>
        </>
      )}

      <div className="section-head">
        <h2>Students</h2>
      </div>
      <div className="card flush">
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Roll</th>
                <th>Name</th>
                <th>Status</th>
                <th>Code</th>
                <th>Indicated stream</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.students.map((s) => (
                <tr key={s.student_id}>
                  <td className="num strong">{s.roll_no}</td>
                  <td className="strong">{s.name}</td>
                  <td>
                    <span className={`badge ${STATUS[s.status].cls}`}>
                      {STATUS[s.status].label}
                    </span>
                    {s.validity && s.validity !== "valid" && (
                      <span className="badge red" style={{ marginLeft: 6 }}>
                        {s.validity}
                      </span>
                    )}
                  </td>
                  <td className="mono">{s.holland_code ?? "not yet"}</td>
                  <td>{s.withheld ? <span className="muted">withheld</span> : (s.top_stream ?? "not yet")}</td>
                  <td>
                    {s.status === "complete" && (
                      <Link className="btn secondary tiny" href={`/admin/students/${s.student_id}`}>
                        Report
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
