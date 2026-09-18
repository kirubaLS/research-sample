/**
 * A small inline-SVG icon set for academics stat tiles and cards. No icon library
 * dependency -- each icon is a tiny, stroke-based glyph in the spirit of the reference
 * screens (people/clipboard/calendar/bar-chart/brain/lightbulb/puzzle/book/calculator).
 * All strokes inherit `currentColor` so a tile can tint the icon via its badge color.
 */

import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const base = {
  width: 20,
  height: 20,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function PeopleIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.5 19.5c0-3 2.5-5 5.5-5s5.5 2 5.5 5" />
      <circle cx="17" cy="8.5" r="2.4" />
      <path d="M15.8 14.2c2.3.3 4.2 2.1 4.2 5.3" />
    </svg>
  );
}

export function ClipboardIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <rect x="5" y="4.5" width="14" height="16" rx="2.2" />
      <path d="M9 4.5V4a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 4v.5" />
      <path d="M8.5 11h7M8.5 14.5h7M8.5 17.5h4" />
    </svg>
  );
}

export function CalendarIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <rect x="4" y="5.5" width="16" height="14.5" rx="2.2" />
      <path d="M4 9.5h16" />
      <path d="M8 3.5v3.5M16 3.5v3.5" />
      <path d="M9 13.5h2M13 13.5h2M9 16.5h2" />
    </svg>
  );
}

export function BarChartIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M5 20V11" />
      <path d="M12 20V6" />
      <path d="M19 20v-7" />
      <path d="M3.5 20h17" strokeWidth="1.6" />
    </svg>
  );
}

export function BrainIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M9.5 4.5a2.8 2.8 0 0 0-2.8 2.8 2.6 2.6 0 0 0-1.7 4.4A2.9 2.9 0 0 0 6.8 17a2.7 2.7 0 0 0 2.7 2.5c1 0 1.9-.5 2.5-1.3" />
      <path d="M9.5 4.5c.9 0 1.7.4 2.2 1v11.7" />
      <path d="M14.5 4.5a2.8 2.8 0 0 1 2.8 2.8 2.6 2.6 0 0 1 1.7 4.4A2.9 2.9 0 0 1 17.2 17a2.7 2.7 0 0 1-2.7 2.5c-1 0-1.9-.5-2.5-1.3" />
    </svg>
  );
}

export function LightbulbIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M9 18h6" />
      <path d="M10 21h4" />
      <path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1 2.2h5.2c0-1 .4-1.7 1-2.2A6 6 0 0 0 12 3Z" />
    </svg>
  );
}

export function PuzzleIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M9 4.5h3.5a1.5 1.5 0 0 1 0 3H14v3h2.5a1.5 1.5 0 1 1 0 4H14v3.5H4.5V17a1.5 1.5 0 1 0 0-3V9H8V6.5a1.5 1.5 0 0 1 1-2Z" />
    </svg>
  );
}

export function BookIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M4 5.5c2-1 5-1.2 8 .3v13c-3-1.5-6-1.3-8-.3Z" />
      <path d="M20 5.5c-2-1-5-1.2-8 .3v13c3-1.5 6-1.3 8-.3Z" />
    </svg>
  );
}

export function CalculatorIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <rect x="5.5" y="3.5" width="13" height="17" rx="2" />
      <path d="M8 7.5h8" />
      <path d="M8 12h1.2M11.4 12h1.2M14.8 12h1.2M8 15.2h1.2M11.4 15.2h1.2M14.8 15.2v3.2M8 18.4h1.2M11.4 18.4h1.2" />
    </svg>
  );
}

export function TargetIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="4.2" />
      <circle cx="12" cy="12" r="0.6" fill="currentColor" />
    </svg>
  );
}
