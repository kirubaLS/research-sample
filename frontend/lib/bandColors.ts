/** Shared ordinal ramp for Board-mark bands, best band first, one hue per
 * step, green→gold→red so "better" always reads as greener without ever
 * needing a legend to say so. Reused by every band table/pie on the Class
 * X dashboard so a color always means the same thing across the page. */
export const TOTAL_BAND_COLORS = ["#3a9d6a", "#e0a62a", "#d17a2a", "#c94a3a"];
export const SUBJECT_BAND_COLORS = ["#3a9d6a", "#8aab3c", "#e0a62a", "#d17a2a", "#c94a3a"];

/** The same ramp applied to a bare percentage, so an average score is
 * coloured on the identical scale as the bands sitting beside it. */
export function scoreColor(pct: number): string {
  if (pct >= 80) return "#3a9d6a";
  if (pct >= 70) return "#8aab3c";
  if (pct >= 60) return "#e0a62a";
  if (pct >= 50) return "#d17a2a";
  return "#c94a3a";
}

/** Attention-tier colours, in the overview's tier order (On Track, Need
 * Support, At Risk), green/amber/red, matching the band ramp's ends. */
export const TIER_COLORS = ["#3a9d6a", "#e0a62a", "#c94a3a"];
