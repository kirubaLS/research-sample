"use client";

/**
 * §6.1 -- teacher sidebar: Home · My Classes · My Subjects · Enter Marks, but only the
 * sections relevant to the fixture teacher's assignments render (a pure subject teacher
 * never sees "My Classes" at all). No mascot here -- this is an operational staff screen,
 * per the mascot placement rule in §0.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MOCK_TEACHER } from "@/lib/mocks/teacher";

export function TeacherNav() {
  const pathname = usePathname() ?? "";
  const hasClass = MOCK_TEACHER.assignments.some((a) => a.type === "class");
  const hasSubject = MOCK_TEACHER.assignments.some((a) => a.type === "subject");

  const items: { href: string; label: string; glyph: string }[] = [
    { href: "/teacher", label: "Home", glyph: "▣" },
  ];
  if (hasClass) items.push({ href: "/teacher/classes", label: "My Classes", glyph: "▦" });
  if (hasSubject) items.push({ href: "/teacher/subjects", label: "My Subjects", glyph: "▧" });
  items.push({ href: "/admin/answers", label: "Enter Marks", glyph: "▤" });

  return (
    <nav className="sidenav" aria-label="Teacher sections">
      <div className="group">
        <p className="grouplabel">{MOCK_TEACHER.name}</p>
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
