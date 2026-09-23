"use client";

// Replaced by /principal/classes. Kept as a redirect rather than deleted outright,
// matching this codebase's own convention for a retired route, in case a bookmark or an
// old link still points here.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AdminAcademicsRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/principal/classes");
  }, [router]);
  return null;
}
