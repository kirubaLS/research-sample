"use client";

// Replaced by /principal/classes/[section]. Kept as a redirect for any bookmark or old
// link.

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AdminAcademicsSectionRedirect({
  params,
}: {
  params: Promise<{ sectionId: string }>;
}) {
  const { sectionId } = use(params);
  const router = useRouter();
  useEffect(() => {
    router.replace(`/principal/classes/${sectionId}`);
  }, [router, sectionId]);
  return null;
}
