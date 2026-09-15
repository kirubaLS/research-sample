/**
 * The Avai bird mascot -- real artwork supplied by the brand designer, cropped from the
 * reference sheet at frontend/public/brand/12.jpeg into one PNG per pose
 * (frontend/public/brand/mascot-<pose>-bare.png, captions cropped off so it drops into any
 * layout). No inline-SVG redraw anymore; this *is* the designer's art.
 *
 * Per §0 of the Avai design spec, the mascot is a student-facing / transitional-moment
 * device, not a dashboard decoration -- see the placement table there for exactly where
 * it is and isn't allowed to appear (never on BoardX, rosters, or mark-entry grids).
 *
 * `pose` maps to the poses named in the brand sheet:
 *   - "hello"    : login screen, student empty states.
 *   - "loading"  : any async job-wait state (scan/gridsheet/placement/report polling) --
 *                  uses the designer's own ring-around-bird loading art.
 *   - "improve"  : student report screen when this attempt beats the last one on file.
 *   - "achieve"  : student report screen for a standout result.
 *   - "explore"  : roadmap pathway/stream-exploration surfaces (not wired anywhere yet).
 *   - "learn" / "practice" : available for future surfaces the brand sheet names.
 */

type Pose = "hello" | "loading" | "improve" | "achieve" | "explore" | "learn" | "practice";

const SRC: Record<Pose, string> = {
  hello: "/brand/mascot-hello-bare.png",
  loading: "/brand/mascot-loading-bare.png",
  improve: "/brand/mascot-improve-bare.png",
  achieve: "/brand/mascot-achieve-bare.png",
  explore: "/brand/mascot-explore-bare.png",
  learn: "/brand/mascot-learn-bare.png",
  practice: "/brand/mascot-practice-bare.png",
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
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={SRC[pose]}
      alt={`Avai mascot, ${pose} pose`}
      width={size}
      height={size}
      className={className}
      style={{
        width: size,
        height: size,
        objectFit: "contain",
        display: "inline-block",
        animation: pose === "loading" ? "mascot-spin 1.6s linear infinite" : undefined,
      }}
    />
  );
}
