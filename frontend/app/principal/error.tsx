"use client";

import { ErrorFallback } from "@/components/ErrorFallback";

/** Catches a crash anywhere in the Principal section. The sidebar comes
 * from principal/layout.tsx, one level up, so it stays put and navigable
 * even while this page's content has fallen over. */
export default function PrincipalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorFallback error={error} reset={reset} homeHref="/principal/classes" homeLabel="Go to Classes" />;
}
