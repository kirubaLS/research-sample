"use client";

// §6.3 -- folded into /teacher/overview/[sectionId], which now also carries an Enter
// Marks link and per-student Share with student, both of which this page used to be
// the only place for. Kept as a redirect.

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function SubjectView({
  params,
}: {
  params: Promise<{ subjectCode: string; sectionId: string }>;
}) {
  const { sectionId } = use(params);
  const router = useRouter();
  useEffect(() => {
    router.replace(`/teacher/overview/${sectionId}`);
  }, [router, sectionId]);
  return null;
}
