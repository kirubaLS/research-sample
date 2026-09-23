"use client";

// Replaced by /principal/exams/[assessmentId]. Kept as a redirect for any bookmark or
// old link.

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AdminAcademicsTestRedirect({
  params,
}: {
  params: Promise<{ assessmentId: string }>;
}) {
  const { assessmentId } = use(params);
  const router = useRouter();
  useEffect(() => {
    router.replace(`/principal/exams/${assessmentId}`);
  }, [router, assessmentId]);
  return null;
}
