"use client";

import { animate, motion, useReducedMotion, type Variants } from "framer-motion";
import { useEffect, useState } from "react";

/** Shared motion primitives. Everything here degrades to a static render
 * under prefers-reduced-motion, so pages can use them unconditionally. */

export const EASE_OUT = [0.22, 0.68, 0.36, 1] as const;

/** Fade + 8px rise on mount. `delay` is in seconds. */
export function Reveal({
  children,
  delay = 0,
  y = 8,
  className,
  style,
}: {
  children: React.ReactNode;
  delay?: number;
  y?: number;
  className?: string;
  style?: React.CSSProperties;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      style={style}
      initial={reduce ? false : { opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: EASE_OUT }}
    >
      {children}
    </motion.div>
  );
}

const staggerParent: Variants = {
  hidden: {},
  shown: (gap: number) => ({ transition: { staggerChildren: gap, delayChildren: 0.02 } }),
};
const staggerChild: Variants = {
  hidden: { opacity: 0, y: 10 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.45, ease: EASE_OUT } },
};

/** Wraps a list of <StaggerItem> children so they reveal in sequence. */
export function Stagger({
  children,
  gap = 0.06,
  className,
  style,
}: {
  children: React.ReactNode;
  /** Seconds between consecutive children. */
  gap?: number;
  className?: string;
  style?: React.CSSProperties;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      style={style}
      variants={staggerParent}
      custom={reduce ? 0 : gap}
      initial={reduce ? false : "hidden"}
      animate="shown"
    >
      {children}
    </motion.div>
  );
}

export function StaggerItem({ children, className, style }: { children: React.ReactNode; className?: string; style?: React.CSSProperties }) {
  return (
    <motion.div className={className} style={style} variants={staggerChild}>
      {children}
    </motion.div>
  );
}

/** Counts from 0 up to `value` on mount. Deterministic, no timers beyond
 * the animation itself, and it lands exactly on `value`. */
export function CountUp({
  value,
  decimals = 0,
  duration = 0.9,
  delay = 0,
  prefix = "",
  suffix = "",
  className,
  style,
}: {
  value: number;
  decimals?: number;
  duration?: number;
  delay?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
  style?: React.CSSProperties;
}) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(value);

  useEffect(() => {
    if (reduce) {
      setShown(value);
      return;
    }
    setShown(0);
    const controls = animate(0, value, {
      duration,
      delay,
      ease: EASE_OUT,
      onUpdate: (v) => setShown(v),
    });
    return () => controls.stop();
  }, [value, duration, delay, reduce]);

  return (
    <span className={className} style={{ fontVariantNumeric: "tabular-nums", ...style }}>
      {prefix}
      {shown.toFixed(decimals)}
      {suffix}
    </span>
  );
}

/** A .bar whose fill grows to `value`% on mount. */
export function AnimatedBar({
  value,
  accent = "var(--brand-teal)",
  height = 8,
  delay = 0,
  duration = 0.8,
  className,
  label,
}: {
  /** 0-100. */
  value: number;
  accent?: string;
  height?: number;
  delay?: number;
  duration?: number;
  className?: string;
  label?: string;
}) {
  const reduce = useReducedMotion();
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      className={`bar ${className ?? ""}`}
      style={{ height }}
      role="img"
      aria-label={label ?? `${Math.round(pct)} percent`}
    >
      <motion.div
        className="bar__fill"
        style={{ background: `linear-gradient(90deg, color-mix(in srgb, ${accent} 72%, #fff), ${accent})` }}
        initial={reduce ? false : { width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration, delay, ease: EASE_OUT }}
      />
    </div>
  );
}

/** An SVG path that draws itself. Use inside an <svg>. */
export function DrawnPath({
  d,
  stroke = "var(--brand-teal)",
  width = 2,
  delay = 0,
  duration = 1.1,
  fill = "none",
  strokeDasharray,
}: {
  d: string;
  stroke?: string;
  width?: number;
  delay?: number;
  duration?: number;
  fill?: string;
  strokeDasharray?: string;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.path
      d={d}
      fill={fill}
      stroke={stroke}
      strokeWidth={width}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray={strokeDasharray}
      initial={reduce ? false : { pathLength: 0, opacity: 0 }}
      animate={{ pathLength: 1, opacity: 1 }}
      transition={{ duration, delay, ease: EASE_OUT }}
    />
  );
}

/** A chart bar (or any block) that grows from its baseline. */
export function GrowBar({
  height,
  delay = 0,
  duration = 0.7,
  className,
  style,
  children,
}: {
  /** Final height, e.g. "64%" or 120. */
  height: number | string;
  delay?: number;
  duration?: number;
  className?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      style={style}
      initial={reduce ? false : { height: 0 }}
      animate={{ height }}
      transition={{ duration, delay, ease: EASE_OUT }}
    >
      {children}
    </motion.div>
  );
}
