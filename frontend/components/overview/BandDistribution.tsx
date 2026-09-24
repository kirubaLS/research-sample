"use client";

import { motion, useReducedMotion } from "framer-motion";
import { CountUp, EASE_OUT } from "@/components/motion";

export interface BandSegment {
  /** The band's range, e.g. "450 - 500". */
  label: string;
  count: number;
  /** Whole-percent share; the set is rounded to add to 100 by the caller. */
  share: number;
  color: string;
}

/** One full-width segmented bar over the projected Board total, with an
 * equal-width legend column per band underneath. Every segment and every
 * legend column opens the same student list for that band. */
export function BandDistribution({
  title,
  subtitle,
  segments,
  onSelect,
}: {
  title: string;
  subtitle: string;
  segments: BandSegment[];
  onSelect: (index: number) => void;
}) {
  const reduce = useReducedMotion();
  const total = segments.reduce((sum, s) => sum + s.count, 0);

  return (
    <div className="card">
      <div className="card__head">
        <div>
          <h3 style={{ fontSize: 16 }}>{title}</h3>
          <p className="small muted" style={{ marginTop: 2 }}>
            {subtitle}
          </p>
        </div>
        <span className="tag">{total} students</span>
      </div>
      <div className="card__body">
        <div className="segbar">
          {segments.map((seg, i) =>
            seg.count === 0 ? null : (
              <motion.button
                key={seg.label}
                type="button"
                className="segbar__seg"
                style={{ "--seg": seg.color, flexBasis: 0, flexShrink: 1 } as React.CSSProperties}
                initial={reduce ? false : { flexGrow: 0 }}
                animate={{ flexGrow: seg.count }}
                transition={{ duration: 0.8, delay: 0.1 + i * 0.07, ease: EASE_OUT }}
                onClick={() => onSelect(i)}
                aria-label={`${seg.count} students scoring ${seg.label}, open the list`}
              >
                {seg.share >= 8 ? `${seg.share}%` : ""}
              </motion.button>
            )
          )}
        </div>

        <div className="segbar__legend">
          {segments.map((seg, i) => (
            <motion.button
              key={seg.label}
              type="button"
              className="segbar__legend-item"
              onClick={() => onSelect(i)}
              whileHover={reduce ? undefined : { y: -2 }}
              transition={{ duration: 0.18, ease: EASE_OUT }}
              style={{
                "--seg": seg.color,
                // Equal columns under the bar; the basis lets them wrap
                // onto a second row on a phone instead of crushing.
                flex: "1 1 108px",
                alignItems: "center",
                background: "none",
                border: "none",
                padding: "8px 0 0",
                textAlign: "left",
                font: "inherit",
                cursor: "pointer",
              } as React.CSSProperties}
              aria-label={`${seg.count} students scoring ${seg.label}, open the list`}
            >
              <span style={{ display: "grid", gap: 1, minWidth: 0 }}>
                <span style={{ display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
                  <b style={{ fontSize: 19, letterSpacing: "-0.01em" }}>
                    <CountUp value={seg.count} delay={0.2 + i * 0.07} />
                  </b>
                  <span style={{ fontSize: 12 }}>({seg.label})</span>
                </span>
                <span style={{ fontSize: 11.5 }}>{seg.share}% of students</span>
              </span>
            </motion.button>
          ))}
        </div>
      </div>
    </div>
  );
}
