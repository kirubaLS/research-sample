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
import { getApiKey, getPlatformKey, getRole, type StaffRole } from "@/lib/session";

interface Item {
  href: string;
  label: string;
  glyph: string;
  /** Which capability on /admin/me's `can` object this tab actually needs. `null` means
   *  every signed-in key may see it (there is no narrower permission to check). Gating
   *  each tab by its own capability, not by "signed in" alone, means a role that loses a
   *  permission later loses the tab automatically -- nothing here has to be revisited by
   *  hand the next time the backend's `can` object grows a distinction it doesn't have
   *  yet. */
  needs: keyof StaffRole["can"] | null;
}

const WORK: Item[] = [
  { href: "/admin", label: "Dashboard", glyph: "▤", needs: null },
  { href: "/admin/paper", label: "Question paper", glyph: "▦", needs: "scan_papers" },
  { href: "/admin/answers", label: "Answer sheet", glyph: "▧", needs: "enter_marks" },
  { href: "/admin/gridsheet", label: "Class mark sheet", glyph: "▥", needs: "enter_marks" },
  { href: "/admin/scan", label: "Scan scripts", glyph: "▨", needs: "scan_papers" },
  { href: "/admin/boardx", label: "Board intelligence", glyph: "◈", needs: "read_results" },
];

const PLATFORM: Item[] = [
  { href: "/platform", label: "Schools", glyph: "▣", needs: null },
  { href: "/platform/books", label: "Books", glyph: "▥", needs: null },
  { href: "/platform/books/bulk", label: "Load a language", glyph: "▤", needs: null },
  { href: "/platform/probe", label: "Probe", glyph: "▩", needs: null },
];

export function SideNav() {
  const pathname = usePathname() ?? "";
  const [signedIn, setSignedIn] = useState(false);
  const [role, setRole] = useState<StaffRole | null>(null);
  const [console_, setConsole] = useState(false);

  useEffect(() => {
    setSignedIn(Boolean(getApiKey()));
    setRole(getRole());
    // The Platform group (Schools, Books, Load a language, Probe) is the operator
    // console, not a school console -- it belongs to whoever runs the deployment, never
    // to a school's own admin or principal key, even though an admin key with no school
    // could technically call those endpoints too. Gated on the real platform key alone,
    // so signing in with a school's admin key never surfaces it.
    setConsole(Boolean(getPlatformKey()));
  }, [pathname]);

  if (!signedIn && !console_) return null;

  // Every signed-in key still passes items with needs: null (Dashboard, and the whole
  // Platform group once console_ has already gated the group itself); anything else
  // waits on the server's own answer for that one capability, never assumed from the role
  // name.
  const visible = (items: Item[]) =>
    items.filter((item) => item.needs === null || Boolean(role?.can[item.needs]));

  const group = (title: string, items: Item[]) => {
    const shown = visible(items);
    // A group that filtered down to nothing draws no heading either -- an empty
    // "Assessment" label with no links under it is not "showing only what they can
    // access", it is showing a promise of tabs that never appear.
    if (shown.length === 0) return null;
    return (
      <div className="group" key={title}>
        <p className="grouplabel">{title}</p>
        {shown.map((item) => (
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
  };

  return (
    <nav className="sidenav" aria-label="Sections">
      {signedIn && group("Assessment", WORK)}
      {console_ && group("Platform", PLATFORM)}
    </nav>
  );
}
