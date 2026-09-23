"use client";

/**
 * A class's real score distribution, banded -- the honest, data-backed version of the
 * "mark bands" a design reference for this screen asked for. Every count here is a real
 * avg_score_pct already on the page's own roster, just bucketed by a standard CBSE-style
 * grading cutoff, not a threshold this deployment invented for the occasion. Deliberately
 * NOT here: a longitudinal "late bloomer" classification, an anomaly score, or a
 * mark-band comparison against a projected Board total -- none of those have a real
 * definition in this system, and faking one would be worse than not showing it.
 */

import type { ClassStudentRow } from "@/lib/api";

const SCORE_BANDS: { label: string; min: number; max: number; color: string }[] = [
  { label: "90-100%", min: 90, max: 100, color: "var(--verify)" },
  { label: "75-89%", min: 75, max: 89, color: "var(--verify-2, var(--verify))" },
  { label: "60-74%", min: 60, max: 74, color: "var(--info)" },
  { label: "40-59%", min: 40, max: 59, color: "var(--warn)" },
  { label: "0-39%", min: 0, max: 39, color: "var(--risk)" },
];

export function ScoreDistribution({ students }: { students: ClassStudentRow[] }) {
  const scored = students.filter((s): s is ClassStudentRow & { avg_score_pct: number } => s.avg_score_pct != null);
  const notAssessed = students.length - scored.length;
  if (scored.length === 0) return null;

  const counts = SCORE_BANDS.map(
    (band) => scored.filter((s) => s.avg_score_pct >= band.min && s.avg_score_pct <= band.max).length,
  );
  const max = Math.max(1, ...counts);

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <h2 style={{ marginTop: 0, fontSize: 15 }}>Score distribution</h2>
      <p className="cardnote" style={{ margin: "0 0 14px" }}>
        {scored.length} student{scored.length === 1 ? "" : "s"} with a score, by band.
        {notAssessed > 0 && ` ${notAssessed} not yet assessed and left out -- there is no score to place.`}
      </p>
      <div className="distbars">
        {SCORE_BANDS.map((band, i) => (
          <div className="distbar-row" key={band.label}>
            <span className="distbar-label">{band.label}</span>
            <div className="distbar-track">
              <div
                className="distbar-fill"
                style={{ width: `${(counts[i] / max) * 100}%`, background: band.color }}
              />
            </div>
            <span className="distbar-value">{counts[i]}</span>
          </div>
        ))}
      </div>
      <style jsx>{`
        .distbars { display: flex; flex-direction: column; gap: 8px; }
        .distbar-row { display: grid; grid-template-columns: 64px 1fr 28px; align-items: center; gap: 10px; }
        .distbar-label { font-size: 12.5px; font-weight: 600; color: var(--ink-2); }
        .distbar-track { height: 10px; border-radius: 999px; background: var(--rule); overflow: hidden; }
        .distbar-fill { height: 100%; border-radius: 999px; transition: width 0.3s ease; }
        .distbar-value { font-size: 12.5px; color: var(--ink-2); text-align: right; font-variant-numeric: tabular-nums; }
      `}</style>
    </div>
  );
}
