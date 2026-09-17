"use client";

/**
 * The class-overview landing screen: every class, a status split derived from real
 * marks (on track / needs attention / requires review / not yet assessed), an average
 * score and how many papers actually have marks on them. Tap a class to see its
 * students.
 *
 * Deliberately does not show an "aspiration", "action plan" or "recheck" column -- this
 * deployment has no data model for any of those, and this screen only ever shows a
 * number it can trace back to a real MarkEvent.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { Mascot } from "@/components/Mascot";
import { api, type AcademicsOverview, type ClassAcademicSummary } from "@/lib/api";
import { downloadBlob } from "@/lib/download";
import { getApiKey } from "@/lib/session";

export default function AcademicsOverviewPage() {
  const [data, setData] = useState<AcademicsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"pdf" | "xlsx" | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .academicsOverview(key)
      .then(setData)
      .catch(() => setError("Could not load the class overview."));
  }, []);

  async function download(kind: "pdf" | "xlsx") {
    const key = getApiKey();
    if (!key) return;
    setDownloading(kind);
    try {
      const blob = kind === "pdf" ? await api.academicsOverviewPdf(key) : await api.academicsOverviewXlsx(key);
      downloadBlob(blob, `class-overview.${kind}`);
    } catch {
      setError(`Could not generate the ${kind === "pdf" ? "PDF" : "Excel"} file.`);
    } finally {
      setDownloading(null);
    }
  }

  return (
    <main className="wrap">
      <div className="hero row between" style={{ alignItems: "flex-end" }}>
        <div>
          <p className="eyebrow">Overview</p>
          <h1 style={{ margin: 0 }}>All Classes</h1>
          <p className="lede">
            Tap a class to see every student, their subject-wise marks and what needs
            attention.
          </p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button type="button" className="secondary" disabled={!!downloading} onClick={() => download("xlsx")}>
            {downloading === "xlsx" ? "Preparing…" : "Download Excel"}
          </button>
          <button type="button" disabled={!!downloading} onClick={() => download("pdf")}>
            {downloading === "pdf" ? "Preparing…" : "Download PDF"}
          </button>
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      {!data && !error && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      )}

      {data && data.classes.length === 0 && (
        <p className="muted">No classes yet.</p>
      )}

      {data && data.classes.length > 0 && (
        <div className="classgrid">
          {data.classes.map((c) => (
            <ClassCard key={c.section_id} c={c} />
          ))}
        </div>
      )}

      <style jsx>{`
        .classgrid {
          display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
          gap: 16px; margin-top: 20px;
        }
      `}</style>
    </main>
  );
}

function ClassCard({ c }: { c: ClassAcademicSummary }) {
  const counts = c.status_counts;
  const total = c.student_count || 1;
  const segments: { key: string; n: number; color: string }[] = [
    { key: "on_track", n: counts.on_track, color: "var(--verify)" },
    { key: "needs_attention", n: counts.needs_attention, color: "var(--warn)" },
    { key: "requires_review", n: counts.requires_review, color: "var(--risk)" },
    { key: "not_assessed", n: counts.not_assessed, color: "var(--rule-2)" },
  ];

  return (
    <Link href={`/admin/academics/${c.section_id}`} className="classcard-link">
      <div className="card classcard">
        <div className="row between" style={{ alignItems: "flex-start" }}>
          <div>
            <h2 style={{ margin: 0 }}>{c.grade}{c.name}</h2>
            <p className="cardnote" style={{ margin: "2px 0 0" }}>{c.student_count} Students</p>
          </div>
          {c.avg_score_pct != null && (
            <span className="badge blue">{c.avg_score_pct}% avg</span>
          )}
        </div>

        <div className="stackbar" aria-hidden>
          {segments.map((s) => (
            s.n > 0 && (
              <div
                key={s.key}
                style={{ width: `${(s.n / total) * 100}%`, background: s.color }}
              />
            )
          ))}
        </div>

        <div className="row" style={{ gap: 14, flexWrap: "wrap", marginTop: 10 }}>
          <Legend label="On Track" n={counts.on_track} color="var(--verify)" />
          <Legend label="Attention" n={counts.needs_attention} color="var(--warn)" />
          <Legend label="Review" n={counts.requires_review} color="var(--risk)" />
          {counts.not_assessed > 0 && (
            <Legend label="Not Assessed" n={counts.not_assessed} color="var(--ink-3)" />
          )}
        </div>

        <p className="small muted" style={{ marginTop: 10, marginBottom: 0 }}>
          {c.test_count} paper{c.test_count === 1 ? "" : "s"} with marks recorded
        </p>
      </div>

      <style jsx>{`
        .classcard-link { text-decoration: none; color: inherit; display: block; }
        .classcard { cursor: pointer; transition: box-shadow 0.15s ease, transform 0.15s ease; height: 100%; }
        .classcard:hover { box-shadow: var(--shadow-sm); transform: translateY(-1px); }
        .stackbar {
          display: flex; height: 8px; border-radius: 999px; overflow: hidden;
          background: var(--rule); margin-top: 14px;
        }
      `}</style>
    </Link>
  );
}

function Legend({ label, n, color }: { label: string; n: number; color: string }) {
  return (
    <span className="small" style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "var(--ink-2)" }}>
      <span style={{ width: 8, height: 8, borderRadius: 999, background: color, display: "inline-block" }} />
      {n} {label}
    </span>
  );
}
