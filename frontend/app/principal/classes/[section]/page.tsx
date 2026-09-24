"use client";

import { useParams } from "next/navigation";
import { ClassOverview } from "@/components/overview/ClassOverview";

/** Principal → Class 10A / 10B. The Class X overview scoped to one section, with the
 * section's searchable student list at the end. Section existence is resolved by
 * ClassOverview itself against the real GET /admin/academics classes list. */
export default function ClassSectionPage() {
  const { section } = useParams<{ section: string }>();
  return <ClassOverview key={section} section={section} />;
}
