"use client";

// Replaced by /principal/papers. Kept as a redirect for any bookmark or old link.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AdminPaperRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/principal/papers");
  }, [router]);
  return null;
}
