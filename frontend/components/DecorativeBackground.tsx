/**
 * Large, soft organic blobs behind every page's content -- the "more graphic vectors,
 * more elegant" pass, done as generated vector shapes rather than hosted image assets
 * (nothing to fetch, nothing that can 404, and it re-themes with the rest of the site
 * for free since every fill is a CSS custom property, not a baked-in color).
 *
 * blobs (https://blobs.dev, MIT) generates a deterministic smooth SVG path from a seed --
 * same seed always draws the same shape, so the background is stable across renders and
 * across server/client (no window/document access in the library, so this is safe to
 * render during SSR) rather than reshuffling every time a page mounts.
 *
 * Fixed position, behind everything, never intercepting a click or a tap: this is
 * atmosphere, not content, so it is aria-hidden and pointer-events: none throughout.
 */
import { svgPath } from "blobs/v2";

interface Spot {
  seed: string;
  size: number;
  top: string;
  left: string;
  color: string;
  opacity: number;
}

const SPOTS: Spot[] = [
  { seed: "yaadhum-1", size: 640, top: "-12%", left: "-10%", color: "var(--mark)", opacity: 0.1 },
  { seed: "yaadhum-2", size: 560, top: "8%", left: "72%", color: "var(--info)", opacity: 0.09 },
  { seed: "yaadhum-3", size: 480, top: "62%", left: "-8%", color: "var(--verify)", opacity: 0.08 },
  { seed: "yaadhum-4", size: 520, top: "78%", left: "68%", color: "var(--risk)", opacity: 0.07 },
];

function Blob({ spot }: { spot: Spot }) {
  const d = svgPath({ seed: spot.seed, size: 200, extraPoints: 6, randomness: 4 });
  return (
    <svg
      viewBox="0 0 200 200"
      style={{
        position: "absolute",
        top: spot.top,
        left: spot.left,
        width: spot.size,
        height: spot.size,
        opacity: spot.opacity,
      }}
    >
      <path d={d} fill={spot.color} />
    </svg>
  );
}

export function DecorativeBackground() {
  return (
    <div
      aria-hidden
      style={{
        position: "fixed",
        inset: 0,
        zIndex: -1,
        overflow: "hidden",
        pointerEvents: "none",
        filter: "blur(48px)",
      }}
    >
      {SPOTS.map((spot) => (
        <Blob key={spot.seed} spot={spot} />
      ))}
    </div>
  );
}
