"use client";

// Replaced by /principal/students/[studentId]/subjects/[subjectCode]. Kept as a
// redirect for any bookmark or old link.

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AdminAcademicsStudentSubjectRedirect({
  params,
}: {
  params: Promise<{ studentId: string; subjectCode: string }>;
}) {
  const { studentId, subjectCode } = use(params);
  const router = useRouter();
  useEffect(() => {
    router.replace(`/principal/students/${studentId}/subjects/${subjectCode}`);
  }, [router, studentId, subjectCode]);
  return null;
}
