"use client";

// Replaced by /principal/students/[studentId]. Kept as a redirect for any bookmark or
// old link.

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AdminAcademicsStudentRedirect({
  params,
}: {
  params: Promise<{ studentId: string }>;
}) {
  const { studentId } = use(params);
  const router = useRouter();
  useEffect(() => {
    router.replace(`/principal/students/${studentId}`);
  }, [router, studentId]);
  return null;
}
