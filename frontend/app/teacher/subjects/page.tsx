"use client";

// §6.1 -- "My Subjects" folded into /teacher/home, same reason as classes/page.tsx.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function MySubjects() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/teacher/home");
  }, [router]);
  return null;
}
