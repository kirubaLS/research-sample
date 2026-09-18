/**
 * The colored icon-badge stat tile from the reference screens: a soft-tinted circular
 * icon badge beside a big number and a label, instead of a bare number in a divider
 * grid. Tone picks a badge color from the app's own token set (never a new hex) --
 * "verify"/"warn"/"risk"/"info"/"violet"/"gold" mirror the semantic colors already used
 * for status everywhere else, so a "good" tile and a "good" badge always agree.
 */

import type { ReactNode } from "react";

export type StatTone = "verify" | "warn" | "risk" | "info" | "violet" | "gold" | "neutral";

const TONE_VARS: Record<StatTone, { fg: string; bg: string }> = {
  verify: { fg: "var(--verify)", bg: "var(--verify-soft)" },
  warn: { fg: "var(--warn)", bg: "var(--warn-soft)" },
  risk: { fg: "var(--risk)", bg: "var(--risk-soft)" },
  info: { fg: "var(--info)", bg: "var(--info-soft)" },
  violet: { fg: "var(--violet)", bg: "var(--violet-soft)" },
  gold: { fg: "var(--brand-gold)", bg: "var(--brand-gold-soft)" },
  neutral: { fg: "var(--ink-2)", bg: "var(--surface-2)" },
};

export function StatTile({
  icon,
  value,
  label,
  tone = "neutral",
  sub,
}: {
  icon: ReactNode;
  value: ReactNode;
  label: string;
  tone?: StatTone;
  /** A short colored footnote, e.g. "100% Active" or "+5% from last month". */
  sub?: ReactNode;
}) {
  const c = TONE_VARS[tone];
  return (
    <div className="stattile card">
      <span className="stattile-badge" style={{ background: c.bg, color: c.fg }}>
        {icon}
      </span>
      <div className="stattile-body">
        <span className="stattile-value">{value}</span>
        <span className="stattile-label">{label}</span>
        {sub && (
          <span className="stattile-sub" style={{ color: c.fg }}>
            {sub}
          </span>
        )}
      </div>

      <style jsx>{`
        .stattile {
          display: flex;
          align-items: center;
          gap: 14px;
          padding: 16px 18px;
        }
        .stattile-badge {
          flex: none;
          width: 46px;
          height: 46px;
          border-radius: 50%;
          display: grid;
          place-items: center;
        }
        .stattile-body {
          display: flex;
          flex-direction: column;
          gap: 1px;
          min-width: 0;
        }
        .stattile-value {
          font-family: var(--font-display), system-ui, sans-serif;
          font-size: 26px;
          font-weight: 800;
          line-height: 1.15;
          letter-spacing: -0.01em;
          color: var(--ink);
          font-variant-numeric: tabular-nums;
        }
        .stattile-label {
          font-size: 12.5px;
          color: var(--ink-3);
          font-weight: 600;
        }
        .stattile-sub {
          font-size: 12px;
          font-weight: 700;
          margin-top: 2px;
        }
      `}</style>
    </div>
  );
}

export function StatTileRow({ children }: { children: ReactNode }) {
  return (
    <div className="stattilerow">
      {children}
      <style jsx>{`
        .stattilerow {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
          gap: 14px;
          margin-bottom: 20px;
        }
      `}</style>
    </div>
  );
}
