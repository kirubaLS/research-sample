"use client";

/** A real background step (mapping against the book, reading a scan, classifying) is
 * a wait worth a bit more than a spinner and a line of text -- a pulsing accent dot plus
 * a shimmering bar reads as "working" at a glance, reusing the same `.pulse-dot`/
 * `.shimmer` primitives the rest of the design system already defines rather than a
 * one-off animation. No progress percentage is shown because none of the steps this
 * wraps report one -- a bar that never fills is worse than one that is honestly
 * indeterminate. */
export function BusyBanner({ label }: { label: string }) {
  return (
    <div className="evidence evidence--neutral" style={{ alignItems: "center" }}>
      <span className="pulse-dot" style={{ "--accent": "var(--brand-teal)" } as React.CSSProperties} />
      <div style={{ display: "grid", gap: 7, flex: 1, minWidth: 0 }}>
        <div className="small strong">{label}</div>
        <div className="shimmer" style={{ width: "min(220px, 60%)" }} />
      </div>
    </div>
  );
}
