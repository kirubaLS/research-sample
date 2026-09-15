/**
 * A student climbing toward a star, drawn as inline SVG rather than an image file: no
 * asset to host, it inherits the page's palette through currentColor and CSS variables,
 * and it never asks a slow connection to fetch anything extra. This is the one place in
 * the product that speaks to a student in a picture instead of a sentence -- the same
 * "assessments become a path forward" idea the copy already carries, given a shape.
 */
export function GrowthIllustration({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 320 260"
      className={className}
      role="img"
      aria-label="A student climbing a set of stairs toward a star"
      style={{ width: "100%", height: "auto", display: "block" }}
    >
      <defs>
        <linearGradient id="gi-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--mark-soft)" />
          <stop offset="100%" stopColor="transparent" />
        </linearGradient>
        <linearGradient id="gi-step" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--mark-2)" />
          <stop offset="100%" stopColor="var(--mark)" />
        </linearGradient>
      </defs>

      <ellipse cx="160" cy="230" rx="150" ry="26" fill="url(#gi-sky)" />

      {/* the stairs, each tread a little higher and a little lighter */}
      <g opacity="0.95">
        <rect x="18" y="196" width="70" height="20" rx="6" fill="var(--surface-2)" />
        <rect x="78" y="168" width="70" height="48" rx="6" fill="var(--surface-2)" />
        <rect x="138" y="140" width="70" height="76" rx="6" fill="url(#gi-step)" opacity="0.55" />
        <rect x="198" y="112" width="70" height="104" rx="6" fill="url(#gi-step)" opacity="0.8" />
        <rect x="248" y="86" width="54" height="130" rx="6" fill="url(#gi-step)" />
      </g>

      {/* the star the climb is toward */}
      <g transform="translate(272 40)">
        <path
          d="M12 0 L15.5 8.2 24 9 17.5 14.8 19.5 23 12 18.4 4.5 23 6.5 14.8 0 9 8.5 8.2 Z"
          fill="var(--warn)"
        />
      </g>

      {/* a small dashed path from the top step to the star, the "still climbing" beat */}
      <path
        d="M275 96 C 282 82, 282 64, 276 46"
        fill="none"
        stroke="var(--warn)"
        strokeWidth="2"
        strokeDasharray="4 5"
        strokeLinecap="round"
        opacity="0.6"
      />

      {/* the student, a few shapes only -- backpack, head, a raised arm */}
      <g transform="translate(198 96)">
        <rect x="10" y="26" width="20" height="26" rx="8" fill="var(--info)" />
        <circle cx="20" cy="14" r="11" fill="#f0c9a0" />
        <path d="M9 14a11 11 0 0 1 22 0" fill="var(--ink)" opacity="0.85" />
        <rect x="4" y="30" width="10" height="16" rx="4" fill="var(--mark-2)" />
        <path d="M26 30 L34 16" stroke="#f0c9a0" strokeWidth="6" strokeLinecap="round" />
        <rect x="8" y="48" width="8" height="16" rx="3" fill="var(--ink-2)" />
        <rect x="20" y="48" width="8" height="16" rx="3" fill="var(--ink-2)" />
      </g>
    </svg>
  );
}
