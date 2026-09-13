"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getApiKey, getPlatformKey } from "@/lib/session";
import { AvaiLogo } from "@/components/AvaiLogo";

/**
 * The navigation that was missing. A student following a class link sees only the brand —
 * no route into the staff side is offered to someone taking the test.
 *
 * The front door ("/", "/t", "/t/thanks" -- anywhere outside /admin and /platform, which
 * carry the standing SideNav instead) is a page a student reaches as often as staff do, so
 * it draws no operational tabs at all: no Dashboard, no Question paper, no Schools. Once
 * inside /admin the SideNav already names exactly what that signed-in key may do; a second,
 * looser copy of the same links up here duplicated the promise without the per-tab
 * permission check SideNav now does, so it is a sign-in affordance only, not a shortcut
 * rail.
 */
export function SiteHeader() {
  const pathname = usePathname() ?? "";
  const hasSideNav = pathname.startsWith("/admin") || pathname.startsWith("/platform");
  // /t and everything under it (the class-code entry, the test itself, the thank-you
  // page) is the student's whole path through the product -- no staff sign-in prompt
  // belongs anywhere on it, not even the single link the front door keeps.
  const isStudentFlow = pathname.startsWith("/t");

  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => setSignedIn(Boolean(getApiKey()) || Boolean(getPlatformKey())), [pathname]);

  return (
    <header className="siteheader">
      <div className="inner">
        <Link href="/" className="brand">
          <AvaiLogo height={26} />
          <span className="sub">Assessment diagnostics</span>
        </Link>

        {!hasSideNav && !isStudentFlow && (
          <nav className="navlinks">
            <Link href="/admin">{signedIn ? "Continue to dashboard" : "Staff sign in"}</Link>
          </nav>
        )}
      </div>
    </header>
  );
}
