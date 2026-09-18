"use client";

// §6.1 -- "My Subjects" folded into Overview, same reason as classes/page.tsx.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function MySubjects() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/teacher/overview");
  }, [router]);
  return null;
}
