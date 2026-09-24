"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

/**
 * Shared body for every route segment's error.tsx. A crash anywhere below
 * this point used to unmount the whole React tree and leave a blank
 * screen, Next only shows something in its place if an error.tsx exists
 * for that segment, so every segment gets one, all rendering through here.
 *
 * `reset` re-mounts the segment (Next.js's built-in recovery); "Go home"
 * is a hard navigation, since the crash may have left routing state bad.
 */
export function ErrorFallback({
  error,
  reset,
  homeHref,
  homeLabel,
}: {
  error: Error & { digest?: string };
  reset: () => void;
  homeHref: string;
  homeLabel: string;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="error-fallback">
      <div className="error-fallback__icon">
        <AlertTriangle size={26} />
      </div>
      <h2>Something went wrong</h2>
      <p>This page hit an error and couldn&apos;t finish loading. Nothing you did caused this, try again, or head back home.</p>
      <div className="error-fallback__actions">
        <button className="btn btn--primary" onClick={reset}>
          <RotateCcw size={14} /> Try again
        </button>
        <a className="btn" href={homeHref}>
          {homeLabel}
        </a>
      </div>
      {error.message && <div className="error-fallback__detail">{error.digest ? `Error ${error.digest}` : error.message}</div>}
    </div>
  );
}
