"use client";

import { LayoutDashboard } from "lucide-react";
import { RoleGuard, StaffShell, type NavItem } from "@/components/Shell";

/** Every teacher key -- exam-cell or a plain subject/class teacher alike -- gets exactly
 * one nav entry, to the one common dashboard (Question papers/Enter marks/Insights/My
 * class, each real and scoped to whatever this key actually holds). This replaces the
 * old fragmentation of one nav row per class assignment and one per subject×section
 * assignment: see app/teacher/dashboard/page.tsx for where all of that real
 * functionality now lives. */
export default function TeacherLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleGuard role="teacher">
      {(user) => {
        const nav: NavItem[] = [{ href: "/teacher/dashboard", label: "Dashboard", icon: LayoutDashboard }];
        return (
          <StaffShell user={user} nav={nav} roleLabel="Teacher">
            {children}
          </StaffShell>
        );
      }}
    </RoleGuard>
  );
}
