"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { DrawnPath, EASE_OUT, GrowBar } from "@/components/motion";
import { statusAccent, type AccountStatus } from "@/lib/avai-admin-data";

/** Small shared pieces for the AVAI staff console. Charts here are
 * hand-rolled SVG/CSS, the project ships no chart library. */

// ------------------------------------------------------------
// Toast, every "action" in this console is a demo acknowledgement
// ------------------------------------------------------------

export function useToast() {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = useCallback((text: string) => {
    setMessage(text);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setMessage(null), 3200);
  }, []);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  return { message, show };
}

export function Toast({ message }: { message: string | null }) {
  return (
    <AnimatePresence>
      {message && (
        <motion.div
          className="toast"
          role="status"
          aria-live="polite"
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 10 }}
          transition={{ duration: 0.28, ease: EASE_OUT }}
        >
          {message}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ------------------------------------------------------------
// Status
// ------------------------------------------------------------

export function StatusPill({ status, size = "md" }: { status: AccountStatus; size?: "sm" | "md" }) {
  const accent = statusAccent(status);
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 7,
        padding: size === "sm" ? "3px 9px" : "4px 11px",
        borderRadius: 999,
        fontSize: size === "sm" ? 11.5 : 12.5,
        fontWeight: 650,
        whiteSpace: "nowrap",
        color: accent,
        background: `color-mix(in srgb, ${accent} 12%, #fff)`,
        border: `1px solid color-mix(in srgb, ${accent} 26%, transparent)`,
        boxShadow: "inset 0 1px 0 rgba(255,255,255,.6)",
      }}
    >
      <span className="healthdot" style={{ "--accent": accent } as React.CSSProperties} />
      {status}
    </span>
  );
}

// ------------------------------------------------------------
// Sortable table headers
// ------------------------------------------------------------

export type SortDir = "asc" | "desc";

export function SortHeader<K extends string>({
  label,
  field,
  sort,
  dir,
  onSort,
  align = "left",
}: {
  label: string;
  field: K;
  sort: K;
  dir: SortDir;
  onSort: (field: K) => void;
  align?: "left" | "right";
}) {
  const on = sort === field;
  return (
    <th
      scope="col"
      aria-sort={on ? (dir === "asc" ? "ascending" : "descending") : "none"}
      style={{ textAlign: align, whiteSpace: "nowrap" }}
    >
      <button
        type="button"
        onClick={() => onSort(field)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 5,
          background: "none",
          border: "none",
          padding: 0,
          font: "inherit",
          color: on ? "var(--brand-blue)" : "inherit",
          cursor: "pointer",
          letterSpacing: "inherit",
          textTransform: "inherit",
        }}
      >
        {label}
        {on ? (
          dir === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} />
        ) : (
          <ChevronsUpDown size={11} style={{ opacity: 0.4 }} />
        )}
      </button>
    </th>
  );
}

// ------------------------------------------------------------
// Charts
// ------------------------------------------------------------

export interface ChartPoint {
  label: string;
  value: number;
}

/** Column chart: one bar per bucket, growing from the baseline. */
export function MiniColumns({
  data,
  accent = "var(--brand-blue)",
  height = 132,
  valueSuffix = "",
}: {
  data: ChartPoint[];
  accent?: string;
  height?: number;
  valueSuffix?: string;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "stretch", height }}>
      {data.map((d, i) => (
        <div key={d.label} style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 6 }}>
          <div
            className="mono"
            style={{ fontSize: 11, fontWeight: 650, textAlign: "center", color: d.value ? "var(--text)" : "var(--muted)" }}
          >
            {d.value}
            {valueSuffix}
          </div>
          <div style={{ flex: 1, display: "flex", alignItems: "flex-end" }}>
            <GrowBar
              height={`${Math.max(4, (d.value / max) * 100)}%`}
              delay={0.06 * i}
              style={{
                width: "100%",
                borderRadius: "9px 9px 4px 4px",
                background: d.value
                  ? `linear-gradient(180deg, color-mix(in srgb, ${accent} 74%, #fff), ${accent})`
                  : "repeating-linear-gradient(135deg, #dfe6f2 0 5px, #eaeff8 5px 10px)",
                boxShadow: d.value ? `0 8px 18px -12px ${accent}, inset 0 1px 0 rgba(255,255,255,.4)` : "none",
              }}
            />
          </div>
          <div className="muted" style={{ fontSize: 10.5, textAlign: "center", letterSpacing: ".02em" }}>
            {d.label}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Cumulative line + soft area, drawn in on mount. */
export function MiniArea({
  data,
  accent = "var(--brand-teal)",
  height = 132,
}: {
  data: ChartPoint[];
  accent?: string;
  height?: number;
}) {
  const gid = useId().replace(/:/g, "");
  const reduce = useReducedMotion();
  const w = 320;
  const h = 96;
  const pad = 6;
  const max = Math.max(1, ...data.map((d) => d.value));
  const pts = data.map((d, i) => {
    const x = data.length === 1 ? w / 2 : pad + (i * (w - pad * 2)) / (data.length - 1);
    const y = h - pad - (d.value / max) * (h - pad * 2);
    return { x, y, ...d };
  });
  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const area = `${line} L${pts[pts.length - 1]?.x.toFixed(1)} ${h} L${pts[0]?.x.toFixed(1)} ${h} Z`;

  return (
    <div style={{ height }}>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={height - 20} role="img" aria-label="Cumulative students onboarded per week" preserveAspectRatio="none">
        <defs>
          <linearGradient id={`fill-${gid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={accent} stopOpacity="0.28" />
            <stop offset="100%" stopColor={accent} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={0} x2={w} y1={h * f} y2={h * f} stroke="#dbe3f1" strokeWidth={1} strokeDasharray="3 5" />
        ))}
        <motion.path
          d={area}
          fill={`url(#fill-${gid})`}
          initial={reduce ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.7, delay: 0.5, ease: EASE_OUT }}
        />
        <DrawnPath d={line} stroke={accent} width={2.4} duration={1.1} />
        {pts.map((p, i) => (
          <motion.circle
            key={p.label}
            cx={p.x}
            cy={p.y}
            r={3}
            fill="#fff"
            stroke={accent}
            strokeWidth={2}
            initial={reduce ? false : { opacity: 0, scale: 0 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3, delay: 0.5 + i * 0.06, ease: EASE_OUT }}
          />
        ))}
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
        {data.map((d, i) => (
          <span
            key={d.label}
            className="muted"
            style={{ fontSize: 10.5, visibility: i === 0 || i === data.length - 1 || i === Math.floor(data.length / 2) ? "visible" : "hidden" }}
          >
            {d.label}
          </span>
        ))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------
// Empty state
// ------------------------------------------------------------

export function OpsEmpty({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="small muted"
      style={{
        border: "1.5px dashed var(--line-strong)",
        borderRadius: "var(--radius-md)",
        padding: "18px 16px",
        textAlign: "center",
        background: "rgba(255,255,255,.55)",
      }}
    >
      {children}
    </div>
  );
}
