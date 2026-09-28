"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Retired: the subject Insights/Question paper/Enter marks view now lives inside the
 * common teacher dashboard ("Insights" tab plus the shared Question papers/Enter marks
 * tabs, app/teacher/dashboard/page.tsx), reusing the same real SubjectRoster/KPI/cohort
 * logic. Kept as a redirect so an old bookmark/deep link still works instead of 404ing. */
export default function LegacySubjectViewRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/teacher/dashboard");
  }, [router]);
  return null;
}
