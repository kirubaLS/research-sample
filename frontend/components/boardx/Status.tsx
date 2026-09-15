"use client";

/**
 * §5.8 -- three separate status dimensions that must never collapse into one visual
 * language. This is the founder's most important UX rule for BoardX, and it overrides the
 * simpler flat-badge convention (§9) everywhere on this surface:
 *
 *   Attention     -- a color-coded PILL (risk/warn/brand-green/neutral-purple/grey)
 *   Board Urgency -- a filled-BAR / dot-strength indicator, its own palette (teal-ink),
 *                    never the Attention red/amber/green set
 *   Confidence    -- an OUTLINE pill/label, a distinct shape from both of the above
 *
 * A topic worth 8 marks at 4/4 board years must never look identical to one at 1/4 --
 * urgency is independent of whether the school should currently be "worried" (Attention)
 * or how sure BoardX is (Confidence).
 */

export type Attention =
  | "IMMEDIATE ATTENTION"
  | "WATCH"
  | "ON TRACK"
  | "INVESTIGATION REQUIRED"
  | "INSUFFICIENT EVIDENCE";

export type UrgencyTier = "VERY HIGH" | "HIGH" | "MEDIUM" | "LOW" | null;

export type ConfidenceTier = "HIGH" | "MEDIUM" | "EMERGING";

const ATTENTION_STYLE: Record<Attention, { bg: string; fg: string }> = {
  "IMMEDIATE ATTENTION": { bg: "var(--risk-soft)", fg: "var(--risk)" },
  WATCH: { bg: "var(--warn-soft)", fg: "var(--warn)" },
  "ON TRACK": { bg: "var(--verify-soft)", fg: "var(--verify)" },
  "INVESTIGATION REQUIRED": { bg: "#efe7f7", fg: "#6b4fa0" },
  "INSUFFICIENT EVIDENCE": { bg: "var(--surface-2)", fg: "var(--ink-3)" },
};

export function AttentionPill({ state }: { state: Attention }) {
  const s = ATTENTION_STYLE[state];
  return (
    <span
      className="bx-attention"
      style={{ background: s.bg, color: s.fg }}
    >
      {state.replace(/\b\w/g, (c) => c)[0] + state.slice(1).toLowerCase()}
      <style jsx>{`
        .bx-attention {
          display: inline-block; padding: 3px 10px; border-radius: 999px;
          font-size: 12px; font-weight: 700; letter-spacing: 0.01em; line-height: 1.6;
        }
      `}</style>
    </span>
  );
}

const URGENCY_DOTS: Record<Exclude<UrgencyTier, null>, number> = {
  "VERY HIGH": 4, HIGH: 3, MEDIUM: 2, LOW: 1,
};

/** Filled-bar / dot-strength indicator -- deliberately a teal/ink ramp, never the
 *  Attention red/amber/green palette, so urgency and attention can sit side by side
 *  on one finding without reading as the same signal. */
export function BoardUrgencyIndicator({
  tier, yearsAppeared, yearsEligible,
}: {
  tier: UrgencyTier;
  yearsAppeared?: number | null;
  yearsEligible?: number | null;
}) {
  const filled = tier ? URGENCY_DOTS[tier] : 0;
  const years = yearsEligible ? `${yearsAppeared ?? 0}/${yearsEligible} recent Board years` : null;
  return (
    <span className="bx-urgency">
      <span className="bx-urgency-label">Board Urgency</span>
      <span className="bx-urgency-value">{tier ?? "Not yet scored"}</span>
      <span className="bx-dots" aria-hidden>
        {[0, 1, 2, 3].map((i) => (
          <i key={i} className={i < filled ? "on" : ""} />
        ))}
      </span>
      {years && <span className="bx-urgency-years">{years}</span>}
      <style jsx>{`
        .bx-urgency { display: inline-flex; align-items: center; gap: 7px; flex-wrap: wrap; font-size: 13px; }
        .bx-urgency-label { color: var(--ink-3); font-size: 12px; }
        .bx-urgency-value { font-weight: 700; color: var(--brand-ink); }
        .bx-dots { display: inline-flex; gap: 3px; }
        .bx-dots i {
          width: 8px; height: 8px; border-radius: 2px; background: var(--rule-2); display: inline-block;
        }
        .bx-dots i.on { background: var(--brand-teal); }
        .bx-urgency-years { color: var(--ink-3); font-size: 12px; }
      `}</style>
    </span>
  );
}

const CONFIDENCE_LABEL: Record<ConfidenceTier, string> = {
  HIGH: "High confidence", MEDIUM: "Medium confidence", EMERGING: "Emerging evidence",
};

/** Outline pill -- a distinct shape (border only, no fill) from both the Attention pill
 *  (solid fill) and the Urgency indicator (dots/bar), per §5.8. */
export function ConfidencePill({ tier }: { tier: ConfidenceTier }) {
  return (
    <span className="bx-confidence">
      {CONFIDENCE_LABEL[tier]}
      <style jsx>{`
        .bx-confidence {
          display: inline-block; padding: 2px 10px; border-radius: 6px;
          border: 1.5px solid var(--brand-ink-2); color: var(--brand-ink-2);
          font-size: 11.5px; font-weight: 700; letter-spacing: 0.02em;
        }
      `}</style>
    </span>
  );
}

/** Derives an Attention state from real attainment/rate numbers using plain threshold
 *  buckets -- presentation logic only, not a Dependency Index item: no new backend
 *  aggregation is invented here, just a UI classification of a number BoardX already has. */
export function attentionFromRate(rate: number | null | undefined, sufficient = true): Attention {
  if (!sufficient) return "INSUFFICIENT EVIDENCE";
  if (rate == null) return "INSUFFICIENT EVIDENCE";
  if (rate < 0.5) return "IMMEDIATE ATTENTION";
  if (rate < 0.7) return "WATCH";
  return "ON TRACK";
}
