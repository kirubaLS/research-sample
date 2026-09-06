"use client";

/**
 * The standing navigation, on the left where a dashboard of this shape puts it.
 *
 * Grouped by what somebody came to do rather than by which service owns the route, and
 * every item is a place that exists: an entry that leads to a sign-in or a refusal is
 * worse than no entry, so what a key cannot open is not drawn.
 *
 * On a phone it becomes a row that scrolls, because a slide-out drawer is a second
 * interaction to learn before the first task can start.
 *
 * The styles live in the global sheet rather than in a styled-jsx block here: every entry
 * is a Link, and a scoped block never reaches inside another component, so the rules
 * silently matched nothing and the nav rendered as a row of bare text.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getApiKey, getPlatformKey, getRole } from "@/lib/session";

interface Item {
  href: string;
  label: string;
  glyph: string;
}

const WORK: Item[] = [
  { href: "/admin", label: "Dashboard", glyph: "▤" },
  { href: "/admin/paper", label: "Question paper", glyph: "▦" },
  { href: "/admin/answers", label: "Answer sheet", glyph: "▧" },
  { href: "/admin/gridsheet", label: "Class mark sheet", glyph: "▥" },
  { href: "/admin/scan", label: "Scan scripts", glyph: "▨" },
];

const PLATFORM: Item[] = [
  { href: "/platform", label: "Schools", glyph: "▣" },
  { href: "/platform/books", label: "Books", glyph: "▥" },
  { href: "/platform/probe", label: "Probe", glyph: "▩" },
];

export function SideNav() {
  const pathname = usePathname() ?? "";
  const [signedIn, setSignedIn] = useState(false);
  const [console_, setConsole] = useState(false);

  useEffect(() => {
    setSignedIn(Boolean(getApiKey()));
    // A known role is authoritative and wins outright, in either direction: a principal
    // who once ran the operator console on this same browser must not still see it after
    // signing in as a principal, and a signed-in admin must see it even before anything
    // else has touched the platform key. The raw platform key is a fallback only for the
    // one case with no role opinion at all -- a pure /platform visit that never went
    // through the admin sign-in, so getRole() has nothing cached to say either way.
    const role = getRole();
    setConsole(role ? Boolean(role.can.manage_schools) : Boolean(getPlatformKey()));
  }, [pathname]);

  if (!signedIn && !console_) return null;

  const group = (title: string, items: Item[]) => (
    <div className="group" key={title}>
      <p className="grouplabel">{title}</p>
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={`item${pathname === item.href ? " on" : ""}`}
          aria-current={pathname === item.href ? "page" : undefined}
        >
          <span className="glyph" aria-hidden>
            {item.glyph}
          </span>
          {item.label}
        </Link>
      ))}
    </div>
  );

  return (
    <nav className="sidenav" aria-label="Sections">
      {signedIn && group("Assessment", WORK)}
      {console_ && group("Platform", PLATFORM)}
    </nav>
  );
}
