"use client";

import { useParams } from "next/navigation";
import { classRosterFull } from "@/lib/avai-mock-data";
import { EvidenceState } from "@/components/EvidenceState";
import { ClassOverview } from "@/components/overview/ClassOverview";

/** Principal → Class 10A / 10B. The Class X overview scoped to one section,
 * with the section's searchable student list at the end. */
export default function ClassSectionPage() {
  const { section } = useParams<{ section: string }>();
  if (!classRosterFull[section]) return <EvidenceState kind="cause">No section called {section}.</EvidenceState>;
  return <ClassOverview key={section} section={section} />;
}
