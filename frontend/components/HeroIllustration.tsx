/**
 * The front door's hero graphic: a report turning into a rising, confident trend --
 * literally what the product does (a mark sheet becomes something actionable), drawn
 * rather than photographed so it never needs an asset host and always matches today's
 * palette through the same CSS custom properties every other component uses.
 */
export function HeroIllustration({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 420 360"
      className={className}
      role="img"
      aria-label="A mark sheet turning into a rising performance trend"
      style={{ width: "100%", height: "auto", display: "block" }}
    >
      <defs>
        <linearGradient id="hero-card" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--surface)" />
          <stop offset="100%" stopColor="var(--surface-2)" />
        </linearGradient>
        <linearGradient id="hero-bar" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="var(--mark)" />
          <stop offset="100%" stopColor="var(--mark-2)" />
        </linearGradient>
      </defs>

      {/* soft ground shadow */}
      <ellipse cx="210" cy="330" rx="150" ry="16" fill="var(--mark-soft)" />

      {/* the "mark sheet" card, tilted slightly for depth */}
      <g transform="rotate(-4 130 170)">
        <rect x="30" y="60" width="200" height="220" rx="18" fill="url(#hero-card)"
          stroke="var(--rule)" strokeWidth="1.5" />
        <rect x="54" y="92" width="120" height="10" rx="5" fill="var(--rule-2)" />
        <rect x="54" y="116" width="152" height="8" rx="4" fill="var(--rule)" />
        <rect x="54" y="134" width="152" height="8" rx="4" fill="var(--rule)" />
        <rect x="54" y="152" width="100" height="8" rx="4" fill="var(--rule)" />
        {/* a row of marks, one flagged -- the product's whole idea in miniature */}
        <rect x="54" y="182" width="152" height="34" rx="8" fill="var(--verify-soft)" />
        <circle cx="70" cy="199" r="6" fill="var(--verify)" />
        <rect x="86" y="194" width="90" height="8" rx="4" fill="var(--verify)" opacity="0.5" />
        <rect x="54" y="224" width="152" height="34" rx="8" fill="var(--risk-soft)" />
        <circle cx="70" cy="241" r="6" fill="var(--risk)" />
        <rect x="86" y="236" width="90" height="8" rx="4" fill="var(--risk)" opacity="0.5" />
      </g>

      {/* the rising trend the report becomes, in front of and to the right of the card */}
      <g transform="translate(190 60)">
        <rect x="0" y="0" width="200" height="240" rx="20" fill="var(--surface)"
          stroke="var(--rule)" strokeWidth="1.5" />
        <g transform="translate(24 40)">
          <rect x="0" y="130" width="24" height="40" rx="6" fill="url(#hero-bar)" opacity="0.55" />
          <rect x="36" y="100" width="24" height="70" rx="6" fill="url(#hero-bar)" opacity="0.7" />
          <rect x="72" y="64" width="24" height="106" rx="6" fill="url(#hero-bar)" opacity="0.85" />
          <rect x="108" y="30" width="24" height="140" rx="6" fill="url(#hero-bar)" />
          <path
            d="M12 130 C 48 100, 84 64, 120 30"
            fill="none" stroke="var(--verify)" strokeWidth="4" strokeLinecap="round"
          />
          <circle cx="120" cy="30" r="7" fill="var(--verify)" />
        </g>
      </g>

      {/* a small star for "achievement", echoing the front door's own illustration */}
      <g transform="translate(346 26)">
        <path
          d="M14 0 L18 10 29 11 20.5 18 23.5 29 14 22.5 4.5 29 7.5 18 -1 11 10 10 Z"
          fill="var(--warn)"
        />
      </g>
    </svg>
  );
}
