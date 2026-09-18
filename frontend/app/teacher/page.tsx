"use client";

// §6.1 -- Overview now covers everything this screen used to show (My Classes / My
// Subjects), with real status data the old roster-only read never had -- see
// TeacherNav.tsx's own note. Kept as a redirect rather than deleted outright in case a
// bookmark or an old link still points at plain /teacher.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function TeacherHome() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/teacher/overview");
  }, [router]);
  return null;
}
