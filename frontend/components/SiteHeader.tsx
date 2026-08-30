"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getPlatformKey } from "@/lib/session";

/**
 * The navigation that was missing. A student following a class link sees only the brand —
 * no route into the staff side is offered to someone taking the test.
 */
export function SiteHeader() {
  const pathname = usePathname() ?? "";
  const isStudentFlow = pathname.startsWith("/t/");

  // The console is for whoever runs the deployment, not for a school, so the link only
  // appears once an operator has signed in here. Read after mount: localStorage does not
  // exist during the server render, and reading it inline would mismatch on hydration.
  const [isOperator, setIsOperator] = useState(false);
  useEffect(() => setIsOperator(Boolean(getPlatformKey())), [pathname]);

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
            {(isOperator || pathname.startsWith("/platform")) && (
              <Link
                href="/platform"
                aria-current={pathname.startsWith("/platform") ? "page" : undefined}
              >
                Schools
              </Link>
            )}
            {(isOperator || pathname.startsWith("/platform")) && (
              <Link
                href="/platform/books"
                aria-current={pathname === "/platform/books" ? "page" : undefined}
              >
                Books
              </Link>
            )}
          </nav>
        )}
      </div>
    </header>
  );
}
