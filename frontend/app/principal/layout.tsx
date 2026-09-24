"use client";

import { useEffect, useState } from "react";
import { CalendarClock, HelpCircle, LayoutGrid, Send, Users } from "lucide-react";
import { RoleGuard, StaffShell, type NavItem } from "@/components/Shell";
import { api, type SectionSummary } from "@/lib/api";
import { getApiKey } from "@/lib/session";

export default function PrincipalLayout({ children }: { children: React.ReactNode }) {
  const [sections, setSections] = useState<SectionSummary[]>([]);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .overview(key)
      .then((res) => setSections(res.sections))
      .catch(() => setSections([]));
  }, []);

  const nav: NavItem[] = [
    { href: "/principal/classes", label: "Class X", icon: LayoutGrid, match: (p) => p === "/principal/classes" },
    ...sections.map((s) => ({
      href: `/principal/classes/${s.section_id}`,
      label: s.label,
      icon: Users,
      sub: true,
      match: (p: string) => p.startsWith(`/principal/classes/${s.section_id}`),
    })),
    { href: "/principal/exams", label: "Exams", icon: CalendarClock },
    { href: "/principal/share", label: "Share reports", icon: Send },
    { href: "/principal/help", label: "Help & Contact", icon: HelpCircle },
  ];

  return (
    <RoleGuard role="principal">
      {(user) => (
        <StaffShell user={user} nav={nav} roleLabel="Principal" tabs={["/principal/classes", "/principal/exams", "/principal/share"]}>
          {children}
        </StaffShell>
      )}
    </RoleGuard>
  );
}
