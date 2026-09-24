"use client";

import { animate, useReducedMotion } from "framer-motion";
import { useEffect, useId, useState } from "react";
import { EASE_OUT } from "@/components/motion";

export interface PieSlice {
  label: string;
  value: number;
  color: string;
}

/** A donut chart built by hand with stroke-dasharray circles, no charting
 * library in this project. The ring sweeps out on mount, the hovered slice
 * lifts (thicker stroke, the rest dimmed) and the centre reads that slice's
 * share; with nothing hovered the centre prints the total, so the chart
 * still reads with color turned off. */
export function BandPie({ slices, size = 180, centerLabel = "students" }: { slices: PieSlice[]; size?: number; centerLabel?: string }) {
  const reduce = useReducedMotion();
  const shadowId = useId();
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  const signature = slices.map((s) => `${s.label}:${s.value}`).join("|");

  const [progress, setProgress] = useState(1);
  const [hovered, setHovered] = useState<number | null>(null);

  useEffect(() => {
    setHovered(null);
    if (reduce) {
      setProgress(1);
      return;
    }
    setProgress(0);
    const controls = animate(0, 1, { duration: 0.85, ease: EASE_OUT, onUpdate: setProgress });
    return () => controls.stop();
  }, [signature, reduce]);

  const r = size / 2;
  const liftedStroke = size * 0.31;
  const baseStroke = size * 0.25;
  const radius = r - liftedStroke / 2;
  const circumference = 2 * Math.PI * radius;

  const active = hovered !== null ? slices[hovered] : null;
  const activeShare = active && total ? Math.round((active.value / total) * 100) : 0;

  let offset = 0;
  const arcs = slices.map((s, i) => {
    const frac = total ? s.value / total : 0;
    const start = offset;
    offset += frac;
    return { slice: s, index: i, frac, start };
  });

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={`${total} ${centerLabel}: ${slices.map((s) => `${s.label} ${s.value}`).join(", ")}`}
        style={{ overflow: "visible", flex: "0 0 auto" }}
      >
        <defs>
          <filter id={shadowId} x="-25%" y="-25%" width="150%" height="150%">
            <feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#15252e" floodOpacity="0.18" />
          </filter>
        </defs>
        <circle cx={r} cy={r} r={radius} fill="none" stroke="var(--surface-2)" strokeWidth={baseStroke} />
        <g transform={`rotate(-90 ${r} ${r})`} filter={`url(#${shadowId})`}>
          {arcs
            .filter((a) => a.slice.value > 0)
            .map((a) => {
              const isHovered = hovered === a.index;
              const dash = Math.max(a.frac * circumference * progress - 2, 0.001);
              return (
                <circle
                  key={a.slice.label}
                  cx={r}
                  cy={r}
                  r={radius}
                  fill="none"
                  stroke={a.slice.color}
                  strokeWidth={isHovered ? liftedStroke : baseStroke}
                  strokeLinecap="butt"
                  strokeDasharray={`${dash} ${Math.max(circumference - dash, 0.001)}`}
                  strokeDashoffset={-a.start * circumference * progress}
                  opacity={hovered === null || isHovered ? 1 : 0.42}
                  style={{ transition: "stroke-width .2s var(--ease-out), opacity .2s ease", cursor: "default" }}
                  onMouseEnter={() => setHovered(a.index)}
                  onMouseLeave={() => setHovered(null)}
                >
                  <title>{`${a.slice.label}: ${a.slice.value} of ${total} (${Math.round(a.frac * 100)}%)`}</title>
                </circle>
              );
            })}
          {total === 0 && <circle cx={r} cy={r} r={radius} fill="none" stroke="var(--line)" strokeWidth={baseStroke} />}
        </g>
        <text x={r} y={r - 2} textAnchor="middle" fontSize={size * 0.16} fontWeight={700} fill="var(--text)" style={{ fontVariantNumeric: "tabular-nums" }}>
          {active ? active.value : total}
        </text>
        <text x={r} y={r + 16} textAnchor="middle" fontSize={size * 0.072} fill="var(--muted)">
          {active ? `${activeShare}% · ${active.label}` : centerLabel}
        </text>
      </svg>

      <div style={{ display: "grid", gap: 4, minWidth: 0 }}>
        {slices.map((s, i) => {
          const isHovered = hovered === i;
          return (
            <div
              key={s.label}
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 12.5,
                padding: "3px 8px",
                borderRadius: 8,
                background: isHovered ? "var(--surface-2)" : "transparent",
                transition: "background .16s ease",
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: 3,
                  background: s.color,
                  flex: "0 0 auto",
                  boxShadow: isHovered ? `0 0 0 3px color-mix(in srgb, ${s.color} 26%, transparent)` : "none",
                  transition: "box-shadow .16s ease",
                }}
              />
              <span className="muted" style={{ minWidth: 82 }}>
                {s.label}
              </span>
              <span className="strong" style={{ fontVariantNumeric: "tabular-nums" }}>
                {s.value}
              </span>
              <span className="muted">({total ? Math.round((s.value / total) * 100) : 0}%)</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
