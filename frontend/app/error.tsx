"use client";

import { ErrorFallback } from "@/components/ErrorFallback";

/** Root-level catch: anything under a route with no error.tsx of its own
 * (/, /login) lands here rather than going blank. */
export default function RootError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorFallback error={error} reset={reset} homeHref="/" homeLabel="Go home" />;
}
