import { Flame } from "lucide-react";
import type { BoardUrgency, Confidence } from "@/lib/avai-mock-data";

/**
 * The three status dimensions of BoardX (spec §5.4). They are kept as three
 * separate components with three separate visual grammars so they can never
 * be read as one colour scale:
 *   Attention  → solid pill (green / gold / red)
 *   Urgency    → outlined chip with a flame glyph, warm ramp
 *   Confidence → 3-dot meter, cool blue ramp
 */

/** `level` drives the colour; `label` overrides the text when the bare
 * level would be ambiguous (a class-level "High" reads as high-performing
 * unless it says what is high). */
export function AttentionPill({ level, label }: { level: string; label?: string }) {
  const key = level.toLowerCase().replace(/\s+/g, "");
  return <span className={`attn attn--${key}`}>{label ?? level}</span>;
}

const urgencyLabel: Record<BoardUrgency, string> = {
  VERY_HIGH: "Very high",
  HIGH: "High",
  MEDIUM: "Medium",
  LOW: "Low",
};

export function UrgencyChip({ level, withLabel = true }: { level: BoardUrgency; withLabel?: boolean }) {
  return (
    <span className={`urg urg--${level.toLowerCase()}`} title="Board urgency, how often this competency recurs in recent Board papers">
      <Flame />
      {withLabel ? `Board urgency: ${urgencyLabel[level]}` : urgencyLabel[level]}
    </span>
  );
}

const confidenceLabel: Record<Confidence, string> = { HIGH: "High confidence", MEDIUM: "Medium confidence", EMERGING: "Emerging signal" };

export function ConfidenceMeter({ level, short = false }: { level: Confidence; short?: boolean }) {
  return (
    <span className={`conf conf--${level.toLowerCase()}`} title="Confidence, strength of evidence that this pattern exists">
      <span className="conf__dots" aria-hidden="true">
        <span className="conf__dot" />
        <span className="conf__dot" />
        <span className="conf__dot" />
      </span>
      {short ? level.charAt(0) + level.slice(1).toLowerCase() : confidenceLabel[level]}
    </span>
  );
}
