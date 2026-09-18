"use client";

// §6.2 -- folded into /teacher/overview/[sectionId], which now also carries the cohort
// snapshot tab this page used to be the only place for. Kept as a redirect.

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ClassView({ params }: { params: Promise<{ sectionId: string }> }) {
  const { sectionId } = use(params);
  const router = useRouter();
  useEffect(() => {
    router.replace(`/teacher/overview/${sectionId}`);
  }, [router, sectionId]);
  return null;
}
