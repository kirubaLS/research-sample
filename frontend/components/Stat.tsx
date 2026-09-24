"use client";

import type { ReactNode } from "react";

type Tone = "green" | "risk" | "gold";

const TONE_COLOR: Record<Tone, string> = {
  green: "var(--brand-green)",
  risk: "var(--risk)",
  gold: "#8a6410", // matches .tag--gold's own text color
};

/** A `.stat` tile with an optional icon and severity color -- the same tile shape used
 * everywhere else in the design system, just given a color once a count actually means
 * something (a positive "Blocked" count is a problem; a zero one is not, so it stays
 * neutral rather than shouting green for "good"). */
export function Stat({
  label, value, icon, tone,
}: {
  label: string;
  value: number | string;
  icon?: ReactNode;
  tone?: Tone;
}) {
  const color = tone ? TONE_COLOR[tone] : undefined;
  return (
    <div className="stat">
      <div className="stat__label" style={{ display: "flex", alignItems: "center", gap: 5 }}>
        {icon && <span style={{ color, display: "inline-flex" }}>{icon}</span>}
        {label}
      </div>
      <div className="stat__value" style={{ color }}>{value}</div>
    </div>
  );
}
