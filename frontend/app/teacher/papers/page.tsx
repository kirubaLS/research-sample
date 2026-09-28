"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Retired: the exam-cell "Papers & Marks" screen has been folded into the one common
 * teacher dashboard everybody now lands on. Kept as a redirect (not deleted) so an old
 * bookmark/deep link still works instead of 404ing. */
export default function LegacyTeacherPapersRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/teacher/dashboard");
  }, [router]);
  return null;
}
