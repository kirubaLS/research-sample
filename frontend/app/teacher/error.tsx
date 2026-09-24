"use client";

import { ErrorFallback } from "@/components/ErrorFallback";

/** Catches a crash anywhere in the Teacher section. The sidebar comes from
 * teacher/layout.tsx, one level up, so it stays put and navigable even
 * while this page's content has fallen over. */
export default function TeacherError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorFallback error={error} reset={reset} homeHref="/teacher/home" homeLabel="Go to My Home" />;
}
