"use client";

import { scoreColor } from "@/lib/bandColors";

export interface SubjectPerformanceRow {
  subject: string;
  /** School-wide average for this subject, out of 100. */
  avgPct: number;
  /** One count per band, in band order. */
  counts: number[];
}

/** Subject × band table: how many students land in each 100-mark band in
 * every subject, with the subject's own average beside it. Every count is
 * a button that opens that (subject, band) student list. */
export function SubjectPerformance({
  title,
  subtitle,
  bandLabels,
  bandColors,
  rows,
  onOpen,
  controls,
}: {
  title: string;
  subtitle: string;
  bandLabels: string[];
  bandColors: string[];
  rows: SubjectPerformanceRow[];
  onOpen: (subject: string, bandIndex: number) => void;
  /** Rendered on the right of the card head, e.g. a test-picker select. */
  controls?: React.ReactNode;
}) {
  return (
    <div className="card">
      <div className="card__head">
        <div>
          <h3 style={{ fontSize: 16 }}>{title}</h3>
          <p className="small muted" style={{ marginTop: 2 }}>
            {subtitle}
          </p>
        </div>
        {controls}
      </div>
      <div className="card__body" style={{ paddingTop: 14 }}>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Subject</th>
                <th className="num">Average Score</th>
                {bandLabels.map((label, i) => (
                  <th key={label} className="num">
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: 2, background: bandColors[i], flex: "0 0 auto" }} />
                      {label}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, r) => (
                <tr key={row.subject} className="reveal" style={{ "--d": `${r * 55}ms` } as React.CSSProperties}>
                  <td className="strong">{row.subject}</td>
                  <td className="num">
                    <span className="pillnum pillnum--solid" style={{ "--accent": scoreColor(row.avgPct) } as React.CSSProperties}>
                      {row.avgPct.toFixed(1)}
                    </span>
                  </td>
                  {row.counts.map((count, i) =>
                    count > 0 ? (
                      <td key={bandLabels[i]} className="num">
                        <button
                          type="button"
                          className="pillnum"
                          style={{ "--accent": bandColors[i] } as React.CSSProperties}
                          onClick={() => onOpen(row.subject, i)}
                          aria-label={`${count} students scoring ${bandLabels[i]} in ${row.subject}, open the list`}
                        >
                          {count}
                        </button>
                      </td>
                    ) : (
                      <td key={bandLabels[i]} className="num muted">
                        0
                      </td>
                    )
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
