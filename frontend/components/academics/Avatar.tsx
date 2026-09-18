/**
 * A colored circle with a person's initials, the same treatment the reference
 * screenshots use for every student row ("RK", "AS", ...). The color is a deterministic
 * hash of the name/id into the app's own soft-tint token set -- never a freehand hex --
 * so the same student always lands on the same color and no palette drifts off-brand.
 */

const TONES = [
  { bg: "var(--brand-teal-soft)", fg: "var(--brand-teal)" },
  { bg: "var(--brand-gold-soft)", fg: "var(--warn)" },
  { bg: "var(--brand-green-soft)", fg: "var(--brand-green)" },
  { bg: "var(--mark-soft)", fg: "var(--mark)" },
  { bg: "var(--risk-soft)", fg: "var(--risk)" },
  { bg: "var(--info-soft)", fg: "var(--info)" },
] as const;

function hash(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return h;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function Avatar({
  name,
  seed,
  size = 36,
}: {
  name: string;
  /** An id to hash instead of the name, when the name alone might collide/repeat. */
  seed?: string;
  size?: number;
}) {
  const tone = TONES[hash(seed || name) % TONES.length];
  return (
    <span
      aria-hidden
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: size,
        height: size,
        borderRadius: "50%",
        background: tone.bg,
        color: tone.fg,
        fontWeight: 700,
        fontSize: size * 0.38,
        flexShrink: 0,
        fontFamily: "var(--font-display), system-ui, sans-serif",
      }}
    >
      {initials(name)}
    </span>
  );
}
