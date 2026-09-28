"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Retired: "My Home" (per-subject cards linking out to fragmented per-subject pages)
 * has been folded into the one common teacher dashboard, reachable via the sidebar's
 * single "Dashboard" nav item. Kept as a redirect so an old bookmark still works. */
export default function LegacyTeacherHomeRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/teacher/dashboard");
  }, [router]);
  return null;
}
