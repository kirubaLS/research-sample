"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getActiveSchool, getApiKey, getPlatformKey, getRole } from "@/lib/session";

/**
 * The navigation that was missing. A student following a class link sees only the brand —
 * no route into the staff side is offered to someone taking the test.
 */
export function SiteHeader() {
  const pathname = usePathname() ?? "";
  const isStudentFlow = pathname.startsWith("/t/");
  // On the staff screens the standing side navigation already carries these, and a second
  // copy of the same four links in the bar above it is noise, doubly so on a phone where
  // both rows scroll sideways.
  const hasSideNav = pathname.startsWith("/admin") || pathname.startsWith("/platform");

  // The console is for whoever runs the deployment, not for a school, so the link only
  // appears once an operator has signed in here. Read after mount: localStorage does not
  // exist during the server render, and reading it inline would mismatch on hydration.
  const [isOperator, setIsOperator] = useState(false);
  useEffect(() => setIsOperator(Boolean(getPlatformKey())), [pathname]);

  // A principal reads results; they do not run the scanners. Offering links that lead to
  // a refusal is worse than not offering them, so the nav follows the role. Read after
  // mount for the same reason as the operator key above.
  // Nothing on the staff side is offered until somebody is actually signed in, and then
  // only what their key opens. Offering a link that leads to a sign-in page or a refusal
  // is worse than not offering it. Read after mount, like the operator key above.
  const [canRun, setCanRun] = useState(false);
  const [canManageSchools, setCanManageSchools] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    const role = getRole();
    const staffKey = Boolean(getApiKey());
    setSignedIn(staffKey);
    setCanManageSchools(Boolean(role?.can.manage_schools) || Boolean(getPlatformKey()));
    // An admin who has not chosen a school yet has nothing for these screens to act on.
    setCanRun(staffKey && Boolean(role?.can.scan_papers) && Boolean(getActiveSchool() || role?.scope === "one_school"));
  }, [pathname]);

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

        {!isStudentFlow && !hasSideNav && (
          <nav className="navlinks">
            {signedIn && (
              <Link href="/admin" aria-current={pathname === "/admin" ? "page" : undefined}>
                Dashboard
              </Link>
            )}
            {canRun && (
              <Link
                href="/admin/paper"
                aria-current={pathname === "/admin/paper" ? "page" : undefined}
              >
                Question paper
              </Link>
            )}
            {canRun && (
              <Link
                href="/admin/answers"
                aria-current={pathname === "/admin/answers" ? "page" : undefined}
              >
                Answer sheet
              </Link>
            )}
            {canRun && (
              <Link
                href="/admin/scan"
                aria-current={pathname === "/admin/scan" ? "page" : undefined}
              >
                Scan scripts
              </Link>
            )}
            {(isOperator || canManageSchools || pathname.startsWith("/platform")) && (
              <Link
                href="/platform"
                aria-current={pathname.startsWith("/platform") ? "page" : undefined}
              >
                Schools
              </Link>
            )}
            {(isOperator || canManageSchools || pathname.startsWith("/platform")) && (
              <Link
                href="/platform/books"
                aria-current={pathname === "/platform/books" ? "page" : undefined}
              >
                Books
              </Link>
            )}
            {(isOperator || canManageSchools || pathname.startsWith("/platform")) && (
              <Link
                href="/platform/probe"
                aria-current={pathname === "/platform/probe" ? "page" : undefined}
              >
                Probe
              </Link>
            )}
          </nav>
        )}
      </div>
    </header>
  );
}
