/**
 * The Avai bird mascot -- inline SVG, no external asset host, matching the style of
 * HeroIllustration/GrowthIllustration (hand-drawn shapes riding the same CSS custom
 * properties everything else uses, so it rebrands for free if the tokens ever move).
 *
 * Per §0 of the Avai design spec, the mascot is a student-facing / transitional-moment
 * device, not a dashboard decoration -- see the placement table there for exactly where
 * it is and isn't allowed to appear (never on BoardX, rosters, or mark-entry grids).
 *
 * `pose` maps to the poses named in the brand sheet:
 *   - "hello"   : login screen, student empty states -- calm, neutral accent color.
 *   - "loading" : any async job-wait state (scan/gridsheet/placement/report polling) --
 *                 adds a small spinning ring around the bird instead of a bare spinner.
 *   - "improve" : student report screen when this attempt beats the last one on file.
 *   - "achieve" : student report screen for a standout result -- gold accent + sparkle.
 *   - "explore" : roadmap pathway/stream-exploration surfaces (not wired anywhere yet).
 */

type Pose = "hello" | "loading" | "improve" | "achieve" | "explore";

const ACCENT: Record<Pose, string> = {
  hello: "var(--brand-teal)",
  loading: "var(--brand-teal)",
  improve: "var(--brand-teal)",
  achieve: "var(--brand-gold)",
  explore: "var(--brand-teal)",
};

export function Mascot({
  pose = "hello",
  size = 48,
  className,
}: {
  pose?: Pose;
  size?: number;
  className?: string;
}) {
  const accent = ACCENT[pose];
  const wingUp = pose === "improve" || pose === "achieve" || pose === "explore";

  return (
    <span
      className={className}
      style={{
        display: "inline-block",
        width: size,
        height: size,
        position: "relative",
      }}
      role="img"
      aria-label={`Avai mascot, ${pose} pose`}
    >
      {pose === "loading" && (
        <svg
          viewBox="0 0 100 100"
          style={{
            position: "absolute",
            inset: -size * 0.12,
            width: size * 1.24,
            height: size * 1.24,
            animation: "mascot-spin 1.1s linear infinite",
          }}
          aria-hidden
        >
          <circle
            cx="50"
            cy="50"
            r="44"
            fill="none"
            stroke={accent}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray="70 200"
            opacity="0.85"
          />
        </svg>
      )}

      <svg viewBox="0 0 100 100" width="100%" height="100%">
        {/* body */}
        <ellipse cx="50" cy="58" rx="30" ry="28" fill="var(--brand-ink)" />
        {/* belly */}
        <ellipse cx="50" cy="66" rx="18" ry="16" fill="var(--brand-cream)" />
        {/* wing, angled up for the "improve/achieve/explore" poses */}
        <path
          d={
            wingUp
              ? "M30 56 C 14 48, 8 30, 14 18 C 22 30, 30 40, 36 52 Z"
              : "M28 58 C 12 58, 6 70, 14 82 C 22 74, 30 66, 36 60 Z"
          }
          fill={accent}
        />
        {/* head */}
        <circle cx="50" cy="30" r="20" fill="var(--brand-ink)" />
        {/* eye */}
        <circle cx="57" cy="27" r="4.2" fill="var(--brand-cream)" />
        <circle cx="58.3" cy="26" r="2" fill="var(--brand-ink)" />
        {/* beak */}
        <path d="M68 29 L80 33 L68 37 Z" fill={accent} />
        {/* small crest feather */}
        <path d="M46 12 C 44 4, 52 2, 56 8 C 51 8, 48 10, 46 12 Z" fill={accent} />

        {(pose === "achieve" || pose === "improve") && (
          <g>
            <path
              d="M80 14 L82 20 L88 22 L82 24 L80 30 L78 24 L72 22 L78 20 Z"
              fill="var(--brand-gold)"
            />
          </g>
        )}
        {pose === "explore" && (
          <g stroke="var(--brand-ink)" strokeWidth="3" strokeLinecap="round">
            <line x1="78" y1="70" x2="78" y2="94" />
            <path d="M78 70 L94 76 L78 82 Z" fill={accent} stroke="none" />
          </g>
        )}
      </svg>

      <style jsx>{`
        @keyframes mascot-spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </span>
  );
}
