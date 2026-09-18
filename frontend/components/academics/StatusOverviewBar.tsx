/**
 * The single segmented status bar from the reference ("Class Overview"): one
 * horizontal track split into on-track/needs-attention/requires-review segments by
 * proportion, with a legend row of colored dots + counts underneath. Reused wherever a
 * screen already has a `status_counts`-shaped read (class overview, class roster, a
 * single test's results) -- it never computes a new bucket, only renders one that's
 * already there.
 *
 * Per dataviz status-color rules: good/warning/serious are fixed, reserved hues, always
 * shipped with a label (never color alone), and "not assessed" -- a neutral absence of
 * data, not a severity -- gets ink-3 gray, kept out of the 0-100% status math and shown
 * only as its own separate legend line when present.
 */

export interface StatusCounts {
  on_track: number;
  needs_attention: number;
  requires_review: number;
  not_assessed?: number;
}

const SEGMENTS: { key: keyof StatusCounts; label: string; color: string }[] = [
  { key: "on_track", label: "On Track", color: "var(--verify)" },
  { key: "needs_attention", label: "Needs Attention", color: "var(--warn)" },
  { key: "requires_review", label: "Requires Review", color: "var(--risk)" },
];

export function StatusOverviewBar({
  counts,
  title,
}: {
  counts: StatusCounts;
  title?: string;
}) {
  const assessedTotal = counts.on_track + counts.needs_attention + counts.requires_review;
  const denom = assessedTotal || 1;
  const notAssessed = counts.not_assessed ?? 0;

  return (
    <div className="sob">
      {title && <h3 className="sob-title">{title}</h3>}
      <div className="sob-track" role="img" aria-label="Status distribution">
        {assessedTotal === 0 ? (
          <div style={{ width: "100%", background: "var(--rule)" }} />
        ) : (
          SEGMENTS.map((s) => {
            const n = counts[s.key] ?? 0;
            return (
              n > 0 && (
                <div
                  key={s.key}
                  style={{ width: `${(n / denom) * 100}%`, background: s.color }}
                  title={`${s.label}: ${n}`}
                />
              )
            );
          })
        )}
      </div>
      <div className="sob-legend">
        {SEGMENTS.map((s) => (
          <span key={s.key} className="sob-item">
            <span className="sob-dot" style={{ background: s.color }} />
            <strong>{counts[s.key] ?? 0}</strong>
            <span className="sob-lbl">
              {s.label}
              {assessedTotal > 0 && ` (${Math.round(((counts[s.key] ?? 0) / denom) * 100)}%)`}
            </span>
          </span>
        ))}
        {notAssessed > 0 && (
          <span className="sob-item">
            <span className="sob-dot" style={{ background: "var(--ink-3)" }} />
            <strong>{notAssessed}</strong>
            <span className="sob-lbl">Not Yet Assessed</span>
          </span>
        )}
      </div>

      <style jsx>{`
        .sob-title { margin: 0 0 12px; font-size: 15px; }
        .sob-track {
          display: flex;
          height: 12px;
          border-radius: 999px;
          overflow: hidden;
          background: var(--rule);
        }
        .sob-track > div { transition: width var(--dur-slow) var(--ease); }
        .sob-legend {
          display: flex;
          flex-wrap: wrap;
          gap: 16px;
          margin-top: 12px;
        }
        .sob-item {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-size: 13.5px;
          color: var(--ink-2);
        }
        .sob-item strong { font-variant-numeric: tabular-nums; color: var(--ink); }
        .sob-dot { width: 9px; height: 9px; border-radius: 999px; flex: none; }
        .sob-lbl { color: var(--ink-3); }
      `}</style>
    </div>
  );
}
