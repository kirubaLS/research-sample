"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Retired: the class-teacher homeroom view now lives inside the common teacher
 * dashboard's "My class" tab (app/teacher/dashboard/page.tsx), reusing the same real
 * KPIs/risk-badge/roster/"since last test" logic. Kept as a redirect so an old
 * bookmark/deep link still works instead of 404ing; the dashboard itself picks the
 * right class from the signed-in teacher's own assignments. */
export default function LegacyClassViewRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/teacher/dashboard");
  }, [router]);
  return null;
}
