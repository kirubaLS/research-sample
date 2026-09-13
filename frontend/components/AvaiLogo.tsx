/**
 * The Avai wordmark, recreated as inline SVG from the brand reference (no image asset
 * exists in this project -- inline SVG matches how HeroIllustration/Mascot already work,
 * and rebrands for free through the same CSS custom properties).
 *
 * Shape: "AVAI" in the display face, a teal-to-gold gradient swoosh sweeping through the
 * two A's (echoing the mascot's wing), a small teal dot over the "i", optional
 * "LEARN GROW ACHIEVE" tagline row underneath.
 */
export function AvaiLogo({
  height = 32,
  withTagline = false,
  className,
}: {
  height?: number;
  withTagline?: boolean;
  className?: string;
}) {
  const w = withTagline ? 200 : 180;
  const h = withTagline ? 64 : 44;
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      height={height}
      width="auto"
      className={className}
      role="img"
      aria-label="Avai"
      style={{ display: "block" }}
    >
      <defs>
        <linearGradient id="avai-swoosh" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--brand-teal)" />
          <stop offset="100%" stopColor="var(--brand-gold)" />
        </linearGradient>
      </defs>

      {/* swoosh, drawn first so the wordmark strokes sit on top of it */}
      <path
        d="M6 36 C 18 30, 26 20, 34 4 C 30 20, 34 30, 46 34 C 34 32, 22 34, 6 36 Z"
        fill="url(#avai-swoosh)"
      />

      <text
        x="34"
        y="32"
        fontFamily="var(--font-display), sans-serif"
        fontWeight={800}
        fontSize="34"
        letterSpacing="-0.5"
        fill="var(--brand-ink)"
      >
        VAI
      </text>
      <circle cx="150" cy="8" r="4.5" fill="var(--brand-teal)" />

      {withTagline && (
        <text
          x="6"
          y="54"
          fontFamily="var(--font-display), sans-serif"
          fontWeight={600}
          fontSize="9"
          letterSpacing="2.5"
          fill="var(--ink-3)"
        >
          LEARN · GROW · ACHIEVE
        </text>
      )}
    </svg>
  );
}
