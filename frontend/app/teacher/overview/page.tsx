"use client";

// §6.1 -- replaced by /teacher/home (subject-first). Kept as a redirect rather than
// deleted outright, matching this codebase's own convention for a retired route, in case
// a bookmark or an old link still points here.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function TeacherOverviewRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/teacher/home");
  }, [router]);
  return null;
}
