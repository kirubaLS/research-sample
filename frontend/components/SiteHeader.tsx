"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * The navigation that was missing. A student following a class link sees only the brand —
 * no route into the staff side is offered to someone taking the test.
 */
export function SiteHeader() {
  const pathname = usePathname() ?? "";
  const isStudentFlow = pathname.startsWith("/t/");

  return (
    <header className="siteheader">
      <div className="inner">
        <Link href="/" className="brand">
          <span className="glyph" aria-hidden>
            Y
          </span>
          <span>
            <span className="name">Yaadhum</span>
            <br />
            <span className="sub">Assessment diagnostics</span>
          </span>
        </Link>

        {!isStudentFlow && (
          <nav className="navlinks">
            <Link href="/admin" aria-current={pathname.startsWith("/admin") ? "page" : undefined}>
              Dashboard
            </Link>
            <Link
              href="/admin/scan"
              aria-current={pathname === "/admin/scan" ? "page" : undefined}
            >
              Scan scripts
            </Link>
          </nav>
        )}
      </div>
    </header>
  );
}
