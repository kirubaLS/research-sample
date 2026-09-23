"use client";

// Replaced by /principal/teachers. Kept as a redirect for any bookmark or old link.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AdminTeachersRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/principal/teachers");
  }, [router]);
  return null;
}
