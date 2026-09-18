"use client";

/**
 * §6.1 -- teacher sidebar: Home · My Classes · My Subjects · Enter Marks, but only the
 * sections relevant to this teacher key's real assignments (GET /admin/me) render -- a
 * pure subject teacher never sees "My Classes" at all. No mascot here -- this is an
 * operational staff screen, per the mascot placement rule in §0.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { getRole, getSchoolName } from "@/lib/session";

export function TeacherNav() {
  const pathname = usePathname() ?? "";
  const role = getRole();
  const assignments = role?.assignments ?? [];
  const hasClass = assignments.some((a) => a.type === "class");
  const hasSubject = assignments.some((a) => a.type === "subject");

  const items: { href: string; label: string; glyph: string }[] = [
    { href: "/teacher", label: "Home", glyph: "▣" },
    { href: "/teacher/overview", label: "Overview", glyph: "◧" },
    { href: "/teacher/tests", label: "Test", glyph: "▤" },
  ];
  if (hasClass) items.push({ href: "/teacher/classes", label: "My Classes", glyph: "▦" });
  if (hasSubject) items.push({ href: "/teacher/subjects", label: "My Subjects", glyph: "▧" });

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
