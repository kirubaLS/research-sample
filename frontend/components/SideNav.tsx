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
import { GrowthIllustration } from "@/components/GrowthIllustration";
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

// Classes and Exams are what a principal actually opens day to day -- the landing page
// after sign-in is /principal/classes (see app/login/page.tsx), and this nav leads with
// it. Papers/Enter Marks/Scan Answer Sheets are real, frequently-used screens for
// whoever is doing the scanning and marks entry, but a principal mostly is not that
// person day to day, so they move into the collapsed "More" group below rather than
// sitting as peers to Classes at the top -- open, not removed.
const PRIMARY: Item[] = [
  { href: "/principal/classes", label: "Classes", glyph: "▣", needs: "read_results" },
  { href: "/principal/exams", label: "Exams", glyph: "▧", needs: "read_results" },
  { href: "/principal/teachers", label: "Manage Teachers", glyph: "☺", needs: null },
  { href: "/admin", label: "Settings", glyph: "▤", needs: null },
];

const MORE: Item[] = [
  { href: "/principal/papers", label: "Papers", glyph: "▦", needs: "scan_papers" },
  { href: "/principal/enter-marks", label: "Enter Marks", glyph: "▧", needs: "enter_marks" },
  { href: "/principal/scan-answers", label: "Scan Answer Sheets", glyph: "▥", needs: "enter_marks" },
  { href: "/principal/share", label: "Share Reports", glyph: "↗", needs: "read_results" },
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
  // Collapsed by default -- Papers/Enter Marks/Scan Answer Sheets are real, working
  // screens, just not ones a principal opens as often as Overview/Test, so they start
  // tucked away rather than competing for space at the top of every visit. Auto-opens
  // when a page inside it is the current one, so following a link here or landing on
  // one of these pages directly (e.g. a bookmark) never hides the nav item that is
  // actually active.
  const [moreOpen, setMoreOpen] = useState(false);

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

  useEffect(() => {
    if (MORE.some((item) => pathname === item.href)) setMoreOpen(true);
  }, [pathname]);

  if (!signedIn && !console_) return null;

  // Every signed-in key still passes items with needs: null (Dashboard, and the whole
  // Platform group once console_ has already gated the group itself); anything else
  // waits on the server's own answer for that one capability, never assumed from the role
  // name.
  const visible = (items: Item[]) =>
    items.filter((item) => item.needs === null || Boolean(role?.can[item.needs]));

  const link = (item: Item) => (
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
  );

  const group = (title: string, items: Item[]) => {
    const shown = visible(items);
    // A group that filtered down to nothing draws no heading either -- an empty
    // "Assessment" label with no links under it is not "showing only what they can
    // access", it is showing a promise of tabs that never appear.
    if (shown.length === 0) return null;
    return (
      <div className="group" key={title}>
        <p className="grouplabel">{title}</p>
        {shown.map(link)}
      </div>
    );
  };

  const moreItems = visible(MORE);

  return (
    <nav className="sidenav" aria-label="Sections">
      {signedIn && group("Assessment", PRIMARY)}
      {signedIn && moreItems.length > 0 && (
        <div className="group">
          <button
            type="button"
            className="item more-toggle"
            onClick={() => setMoreOpen((v) => !v)}
            aria-expanded={moreOpen}
          >
            <span className="glyph" aria-hidden>{moreOpen ? "▾" : "▸"}</span>
            More
          </button>
          {moreOpen && moreItems.map(link)}
        </div>
      )}
      {console_ && group("Platform", PLATFORM)}
      {/* Desktop only (hidden by .sidenav's own <=900px rule turning this into a
          horizontal scroll row, where a footer illustration has nowhere to sit) -- the
          same "turning assessments into a path forward" idea the front door's
          illustration carries, here as the standing reminder of why the nav exists. */}
      <div className="navfooter">
        <GrowthIllustration />
        <p className="navfooter-line">Turning assessments into brighter futures.</p>
      </div>
    </nav>
  );
}
