"use client";

/**
 * §6.1 -- teacher sidebar: Home · Test · Enter Marks, but only the sections
 * relevant to this teacher key's real assignments (GET /admin/me) render. No mascot
 * here -- this is an operational staff screen, per the mascot placement rule in §0.
 *
 * Previously also carried Home, My Classes and My Subjects -- three more entries that
 * opened the exact same roster Overview already shows, just from a plainer read
 * (GET /admin/teacher/sections, no status/avg-score data) with no status data of its
 * own; then Overview itself was replaced by /teacher/home, the subject-first landing
 * page from the current design pass. /teacher, /teacher/classes, /teacher/subjects and
 * /teacher/overview all still redirect to /teacher/home rather than disappearing
 * outright, in case anything still links to them.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { getRole, getSchoolName } from "@/lib/session";

export function TeacherNav() {
  const pathname = usePathname() ?? "";
  const role = getRole();

  const items: { href: string; label: string; glyph: string }[] = [
    { href: "/teacher/home", label: "Home", glyph: "◧" },
    { href: "/teacher/tests", label: "Test", glyph: "▤" },
  ];
  // Gated the same way SideNav gates the principal's own Papers/Enter Marks/Scan Answer
  // Sheets links -- role.can comes from the server (GET /admin/me), which only turns
  // these on for a teacher key holding at least one *subject* assignment, so a
  // class-only teacher never sees them.
  if (role?.can.scan_papers) items.push({ href: "/teacher/paper", label: "Papers", glyph: "▦" });
  if (role?.can.enter_marks) items.push({ href: "/teacher/answers", label: "Enter Marks", glyph: "▧" });
  if (role?.can.enter_marks) items.push({ href: "/teacher/gridsheet", label: "Scan Answer Sheets", glyph: "▥" });

  return (
    <nav className="sidenav" aria-label="Teacher sections">
      <div className="group">
        <p className="grouplabel">{getSchoolName() || "Teacher"}</p>
        {items.map((item) => {
          const on = pathname === item.href || (item.href !== "/teacher" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`item${on ? " on" : ""}`}
              aria-current={on ? "page" : undefined}
            >
              <span className="glyph" aria-hidden>{item.glyph}</span>
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
