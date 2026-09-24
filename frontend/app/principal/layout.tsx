"use client";

import { CalendarClock, HelpCircle, LayoutGrid, Send, Users } from "lucide-react";
import { RoleGuard, StaffShell, type NavItem } from "@/components/Shell";
import { assessmentContext, sectionLabel, sections } from "@/lib/avai-mock-data";
import { useMarksVersion } from "@/lib/liveData";

const nav: NavItem[] = [
  { href: "/principal/classes", label: "Class X", icon: LayoutGrid, match: (p) => p === "/principal/classes" },
  ...sections.map((s) => ({
    href: `/principal/classes/${s}`,
    label: sectionLabel(s),
    icon: Users,
    sub: true,
    match: (p: string) => p.startsWith(`/principal/classes/${s}`),
  })),
  { href: "/principal/exams", label: "Exams", icon: CalendarClock },
  { href: "/principal/share", label: "Share reports", icon: Send },
  { href: "/principal/help", label: "Help & Contact", icon: HelpCircle },
];

export default function PrincipalLayout({ children }: { children: React.ReactNode }) {
  // Every figure below is derived from the saved marks, so a teacher saving
  // an answer card remounts the page and all of its numbers recompute.
  const version = useMarksVersion();
  return (
    <RoleGuard role="principal">
      {(user) => (
        <StaffShell
          user={user}
          nav={nav}
          roleLabel="Principal"
          tabs={["/principal/classes", "/principal/exams", "/principal/share"]}
          sidebarMeta={<span className="sidebar__evidence">Evidence: {assessmentContext.assessmentEvidence}</span>}
        >
          <div key={version} style={{ display: "contents" }}>
            {children}
          </div>
        </StaffShell>
      )}
    </RoleGuard>
  );
}
