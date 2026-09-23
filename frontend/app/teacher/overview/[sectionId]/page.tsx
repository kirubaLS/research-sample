"use client";

// §6.2 -- folded into /teacher/home/[sectionId], the replacement for this whole
// /teacher/overview tree. Kept as a redirect for any bookmark or old link.

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function TeacherOverviewSectionRedirect({
  params,
}: {
  params: Promise<{ sectionId: string }>;
}) {
  const { sectionId } = use(params);
  const router = useRouter();
  useEffect(() => {
    router.replace(`/teacher/home/${sectionId}`);
  }, [router, sectionId]);
  return null;
}
