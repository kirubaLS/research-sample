"use client";

/**
 * AVAI mascot & logo, the blue/orange bird artwork (public/mascot, public/brand).
 *
 * Placement rule (spec §0) still applies: <Mascot> only appears on login,
 * loading states and student screens, never inside the Principal or
 * Teacher shells. <Logomark> is the compact app-icon glyph and is allowed
 * everywhere, including the staff sidebars.
 */
import { motion, useReducedMotion } from "framer-motion";

export type MascotPose = "hello" | "improve" | "achieve" | "neutral" | "thinking";

const poseSrc: Record<MascotPose, string> = {
  hello: "/mascot/avai-wave.png",
  achieve: "/mascot/avai-wave.png",
  improve: "/mascot/avai-head.png",
  neutral: "/mascot/avai-head.png",
  thinking: "/mascot/avai-head.png",
};

export function Mascot({
  pose = "neutral",
  size = 120,
  className,
  float = false,
  glow = true,
}: {
  pose?: MascotPose;
  size?: number;
  className?: string;
  /** Slow idle float. Off by default; ignored under reduced motion. */
  float?: boolean;
  /** Soft radial halo behind the bird. The art has no background of its own. */
  glow?: boolean;
}) {
  const reduce = useReducedMotion();
  const floating = float && !reduce;
  return (
    <motion.span
      className={className}
      animate={floating ? { y: [0, -7, 0] } : undefined}
      transition={floating ? { repeat: Infinity, duration: 4.4, ease: "easeInOut" } : undefined}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: size,
        height: size,
        flex: "0 0 auto",
        padding: Math.round(size * 0.06),
        borderRadius: "50%",
        background: glow
          ? "radial-gradient(circle at 50% 56%, rgba(31,138,138,.18), rgba(29,95,208,.12) 42%, rgba(240,147,43,.08) 62%, transparent 72%)"
          : "none",
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={poseSrc[pose]}
        alt={`AVAI mascot, ${pose} pose`}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "contain",
          display: "block",
          filter: "drop-shadow(0 10px 18px rgba(21,37,46,.18))",
        }}
      />
    </motion.span>
  );
}

/** Compact app-icon logomark used in sidebars/topbars/login. Self-contained artwork. */
export function Logomark({ size = 28 }: { size?: number }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/brand/logo-icon.png"
      width={size}
      height={size}
      alt="AVAI"
      style={{
        display: "block",
        borderRadius: size * 0.28,
        flex: "0 0 auto",
        boxShadow: "0 4px 12px -4px rgba(21,37,46,.45), inset 0 1px 0 rgba(255,255,255,.2)",
      }}
    />
  );
}

/** The AVAI wordmark. `onDark` swaps the navy letters for white so the
 *  logo stays legible on the dark sidebars and sign-in panels. */
export function Wordmark({ height = 28, onDark = false }: { height?: number; onDark?: boolean }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={onDark ? "/brand/avai-wordmark-light.png" : "/brand/avai-wordmark.png"}
      alt="AVAI"
      height={height}
      style={{ height, width: "auto", display: "block", flex: "0 0 auto" }}
    />
  );
}
