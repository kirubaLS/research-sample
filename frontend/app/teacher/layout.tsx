"use client";

import { FileText } from "lucide-react";
import { RoleGuard, StaffShell, type NavItem } from "@/components/Shell";
import { getRole } from "@/lib/session";

/** Every teacher key -- exam-cell or a plain subject/class teacher alike -- gets exactly
 * one nav entry, "Papers & Marks", to the one common dashboard (Question papers/Enter
 * marks/Insights/My class, each real and scoped to whatever this key actually holds).
 * /teacher/papers and /teacher/dashboard are the same screen. */
export default function TeacherLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleGuard role="teacher">
      {(user) => {
        const nav: NavItem[] = [{
          href: "/teacher/papers", label: "Papers & Marks", icon: FileText,
          match: (p) => p.startsWith("/teacher/papers") || p.startsWith("/teacher/dashboard"),
        }];
        const role = getRole();
        const meta = [
          role?.board, role?.state, role?.academic_year ? `Academic year ${role.academic_year}` : null,
        ].filter(Boolean).join(" · ");
        return (
          <StaffShell
            user={user}
            nav={nav}
            roleLabel="Teacher"
            sidebarMeta={meta ? <div className="sidebar__meta-sub">{meta}</div> : undefined}
          >
            {children}
          </StaffShell>
        );
      }}
    </RoleGuard>
  );
}
