/**
 * The Avai bird mascot -- inline SVG, no external asset host, matching the style of
 * HeroIllustration/GrowthIllustration (hand-drawn shapes riding the same CSS custom
 * properties everything else uses, so it rebrands for free if the tokens ever move).
 * Recreated from the brand reference image: cream body, a sweeping teal-to-gold
 * gradient wing, round dark eye, orange beak -- no image asset exists in this project,
 * so this is a faithful redraw rather than an embed.
 *
 * Per §0 of the Avai design spec, the mascot is a student-facing / transitional-moment
 * device, not a dashboard decoration -- see the placement table there for exactly where
 * it is and isn't allowed to appear (never on BoardX, rosters, or mark-entry grids).
 *
 * `pose` maps to the poses named in the brand sheet:
 *   - "hello"   : login screen, student empty states -- calm, wing at rest.
 *   - "loading" : any async job-wait state (scan/gridsheet/placement/report polling) --
 *                 adds a small spinning ring around the bird instead of a bare spinner.
 *   - "improve" : student report screen when this attempt beats the last one on file.
 *   - "achieve" : student report screen for a standout result -- gold sparkle, wing up.
 *   - "explore" : roadmap pathway/stream-exploration surfaces (not wired anywhere yet).
 */

type Pose = "hello" | "loading" | "improve" | "achieve" | "explore";

const WING_UP: Record<Pose, boolean> = {
  hello: false,
  loading: false,
  improve: true,
  achieve: true,
  explore: true,
};

let gradId = 0;

export function Mascot({
  pose = "hello",
  size = 48,
  className,
}: {
  pose?: Pose;
  size?: number;
  className?: string;
}) {
  const wingUp = WING_UP[pose];
  const id = `mascot-wing-${gradId++}`;

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
            stroke="var(--brand-teal)"
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray="70 200"
            opacity="0.85"
          />
        </svg>
      )}

      <svg viewBox="0 0 100 100" width="100%" height="100%">
        <defs>
          <linearGradient id={id} x1="0" y1="1" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--brand-teal)" />
            <stop offset="100%" stopColor="var(--brand-gold)" />
          </linearGradient>
        </defs>

        {/* tail feather, behind the body */}
        <path
          d={
            wingUp
              ? "M40 68 C 20 80, 8 92, 4 100 C 16 96, 30 88, 44 76 Z"
              : "M42 66 C 24 74, 10 82, 2 92 C 16 90, 32 84, 46 74 Z"
          }
          fill={`url(#${id})`}
          opacity="0.9"
        />

        {/* main wing -- the sweeping gradient shape from the reference art */}
        <path
          d={
            wingUp
              ? "M52 54 C 34 42, 22 18, 26 2 C 40 18, 52 30, 62 48 C 58 50, 54 52, 52 54 Z"
              : "M50 56 C 30 54, 12 62, 6 78 C 22 76, 40 70, 54 62 C 52 60, 51 58, 50 56 Z"
          }
          fill={`url(#${id})`}
        />

        {/* body */}
        <ellipse cx="52" cy="62" rx="26" ry="24" fill="var(--brand-cream)" stroke="var(--rule)" strokeWidth="1" />

        {/* head */}
        <circle cx="58" cy="34" r="19" fill="var(--brand-cream)" stroke="var(--rule)" strokeWidth="1" />
        {/* crest feathers */}
        <path d="M50 18 C 47 8, 56 4, 61 10 C 55 10, 51 13, 50 18 Z" fill="var(--brand-gold)" />
        <path d="M58 15 C 58 6, 68 5, 70 13 C 64 11, 60 12, 58 15 Z" fill="var(--brand-teal)" />
        {/* eye */}
        <circle cx="66" cy="33" r="5" fill="var(--brand-ink)" />
        <circle cx="67.6" cy="31.4" r="1.6" fill="#fff" />
        {/* beak */}
        <path d="M76 35 L88 39 L76 43 Z" fill="var(--brand-gold)" />
        {/* feet */}
        <path d="M42 84 L38 92 M50 86 L48 94" stroke="var(--brand-gold)" strokeWidth="3" strokeLinecap="round" />

        {(pose === "achieve" || pose === "improve") && (
          <path
            d="M84 10 L86.5 17 L94 19.5 L86.5 22 L84 29 L81.5 22 L74 19.5 L81.5 17 Z"
            fill="var(--brand-gold)"
          />
        )}
        {pose === "explore" && (
          <g stroke="var(--brand-ink)" strokeWidth="3" strokeLinecap="round">
            <line x1="82" y1="68" x2="82" y2="96" />
            <path d="M82 68 L96 74 L82 80 Z" fill="var(--brand-teal)" stroke="none" />
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
