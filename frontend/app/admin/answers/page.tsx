"use client";

// Replaced by /principal/enter-marks. Kept as a redirect for any bookmark or old link.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AdminAnswersRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/principal/enter-marks");
  }, [router]);
  return null;
}
