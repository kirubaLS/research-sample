"use client";

// §6.1 -- "My Classes" folded into Overview, which shows the same class list with real
// status data this plain roster read never had. Kept as a redirect for any bookmark or
// old link.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function MyClasses() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/teacher/overview");
  }, [router]);
  return null;
}
