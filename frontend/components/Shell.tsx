"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowLeft, LogOut, Menu, X, type LucideIcon } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { homeFor, initials, useAuth, type CurrentUser } from "@/lib/auth";
import { getSchoolName } from "@/lib/session";
import { PAGE_HEADER_ACTIONS_ID, PageHeaderProvider, useCurrentPageHeader } from "@/lib/pageHeader";

export type Role = "principal" | "teacher" | "admin";
import { Mascot, Wordmark } from "./Mascot";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  group?: string;
  /** Indented under the item above it. */
  sub?: boolean;
  match?: (path: string) => boolean;
}

/** Gate a shell to one role. Redirects to /login (or the right home) otherwise. */
export function RoleGuard({ role, children }: { role: Role; children: (user: CurrentUser) => React.ReactNode }) {
  const { user, ready } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const examsOnly = user?.role === "teacher" && user.examsOnly;
  const offLimits = examsOnly && !pathname.startsWith("/teacher/papers");

  useEffect(() => {
    if (!ready) return;
    if (!user) router.replace("/login");
    else if (user.role !== role) router.replace(homeFor(user));
    else if (offLimits) router.replace("/teacher/papers");
  }, [ready, user, role, router, offLimits]);

  if (!ready || !user || user.role !== role || offLimits) return <LoadingScreen />;
  return <>{children(user)}</>;
}

/** Loading state, one of the sanctioned mascot placements (§0). */
export function LoadingScreen({ label = "Loading AVAI…" }: { label?: string }) {
  return (
    <div className="loading">
      <Mascot pose="thinking" size={112} float />
      <motion.div
        className="small"
        style={{ fontWeight: 600, letterSpacing: ".01em" }}
        animate={{ opacity: [0.55, 1, 0.55] }}
        transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
      >
        {label}
      </motion.div>
      <div className="shimmer" style={{ width: 140, height: 4, minHeight: 0, borderRadius: 999 }} />
    </div>
  );
}

/** The sticky "which page am I on" bar: current page title + a back
 * button, pinned to the top of the content area through any scroll. Fed
 * by whichever page is mounted, via usePageHeader(). Skipped on the
 * single-screen test sheet, which has its own compact header built in. */
function PageHeaderBar() {
  const header = useCurrentPageHeader();
  const router = useRouter();
  const ref = useRef<HTMLDivElement>(null);

  // Published as a CSS var so any sticky element further down the page
  // (.roster-sticky, a standalone .filterbar) can sit right below this bar
  // instead of guessing its height or sticking underneath it at the same
  // top:0. Reset to 0 when there's no header so nothing sticks to a gap.
  // header is a fresh object whenever title/subtitle/backHref change, so a
  // subtitle appearing (which makes the bar taller) re-measures too.
  useLayoutEffect(() => {
    document.documentElement.style.setProperty("--page-header-h", header && ref.current ? `${ref.current.offsetHeight}px` : "0px");
    return () => document.documentElement.style.setProperty("--page-header-h", "0px");
  }, [header, header?.subtitle]);

  if (!header) return null;
  return (
    <div className="page-header-bar" ref={ref}>
      {header.backHref && (
        <button className="btn btn--ghost btn--sm" onClick={() => router.push(header.backHref!)}>
          <ArrowLeft size={13} /> Back
        </button>
      )}
      <div className="page-header-bar__text">
        <h1 className="page-header-bar__title">{header.title}</h1>
        {header.subtitle && <div className="page-header-bar__sub">{header.subtitle}</div>}
      </div>
      {/* Filled by <HeaderActions> via a portal, see src/lib/pageHeader.tsx. */}
      <div className="page-header-bar__actions" id={PAGE_HEADER_ACTIONS_ID} />
    </div>
  );
}

/** Staff shell (Principal + Teacher). Deliberately mascot-free. On a phone
 * the sidebar becomes a slide-in menu, with the top-level pages repeated in
 * a bottom tab bar so the common destinations are one thumb-tap away. */
export function StaffShell({
  user,
  nav,
  roleLabel,
  children,
  sidebarMeta,
  tabs: tabHrefs,
}: {
  user: CurrentUser;
  nav: NavItem[];
  roleLabel: string;
  children: React.ReactNode;
  /** Which nav items appear in the phone tab bar (default: top-level ones). */
  tabs?: string[];
  /** Extra content (e.g. an evidence badge) shown under the school/academic
   * year line at the top of the sidebar. */
  sidebarMeta?: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { signOut } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [menuOpen]);

  const isActive = (item: NavItem) => (item.match ? item.match(pathname) : pathname.startsWith(item.href));
  const tabs = tabHrefs ? nav.filter((i) => tabHrefs.includes(i.href)) : nav.filter((i) => !i.group && !i.sub).slice(0, 3);

  function sidebarBody(onNavigate?: () => void) {
    let lastGroup: string | undefined;
    return (
      <>
        <div className="sidebar__meta">
          <div className="sidebar__meta-school">{getSchoolName() || "Your school"}</div>
          {sidebarMeta}
        </div>
        <nav className="sidebar__nav" aria-label="Primary">
          {nav.map((item) => {
            const groupHeader = item.group && item.group !== lastGroup ? <div className="sidebar__group" key={`g-${item.group}`}>{item.group}</div> : null;
            lastGroup = item.group ?? lastGroup;
            const active = isActive(item);
            const Icon = item.icon;
            return (
              <div key={item.href} style={{ display: "contents" }}>
                {groupHeader}
                <Link href={item.href} onClick={onNavigate} className={`navlink ${item.sub ? "navlink--sub" : ""} ${active ? "navlink--active" : ""}`} aria-current={active ? "page" : undefined}>
                  <Icon size={16} /> {item.label}
                </Link>
              </div>
            );
          })}
        </nav>
        <div className="sidebar__footer">
          <div className="sidebar__user">
            <span className="avatar">{initials(user.name)}</span>
            <div>
              <div style={{ fontWeight: 600 }}>{user.name}</div>
              <div style={{ color: "#a9b6bf", fontSize: 11.5 }}>{roleLabel}</div>
            </div>
          </div>
          <button
            className="sidebar__signout"
            onClick={() => {
              signOut();
              router.push("/login");
            }}
          >
            <LogOut size={13} /> Sign out
          </button>
        </div>
      </>
    );
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar__brand" style={{ flexDirection: "column", alignItems: "flex-start", gap: 6 }}>
          <Wordmark height={30} onDark />
          <div className="sidebar__brand-sub">{roleLabel}</div>
        </div>
        {sidebarBody()}
      </aside>

      <div className="main">
        <header className="mtopbar">
          <Wordmark height={22} onDark />
          <div className="mtopbar__text">
            <div className="mtopbar__school">{getSchoolName() || "Your school"}</div>
          </div>
          <span className="avatar mtopbar__avatar" aria-hidden="true">
            {initials(user.name)}
          </span>
          <button className="mtopbar__menu" onClick={() => setMenuOpen(true)} aria-label="Open menu" aria-expanded={menuOpen}>
            <Menu size={20} />
          </button>
        </header>
        <PageHeaderProvider>
          <PageHeaderBar />
          <main className="content">{children}</main>
        </PageHeaderProvider>
      </div>

      <nav className="mtabs" aria-label="Quick navigation">
        {tabs.map((item) => {
          const Icon = item.icon;
          const active = isActive(item);
          return (
            <Link key={item.href} href={item.href} className={`mtabs__item ${active ? "mtabs__item--active" : ""}`} aria-current={active ? "page" : undefined}>
              <Icon size={20} />
              <span>{item.label}</span>
            </Link>
          );
        })}
        <button className={`mtabs__item ${menuOpen ? "mtabs__item--active" : ""}`} onClick={() => setMenuOpen(true)}>
          <Menu size={20} />
          <span>Menu</span>
        </button>
      </nav>

      <AnimatePresence>
        {menuOpen && (
          <>
            <motion.div className="mdrawer-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMenuOpen(false)} />
            <motion.aside
              className="sidebar mdrawer"
              role="dialog"
              aria-modal="true"
              aria-label="Menu"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            >
              <div className="sidebar__brand" style={{ justifyContent: "space-between" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <Wordmark height={28} onDark />
                  <div className="sidebar__brand-sub">{roleLabel}</div>
                </div>
                <button className="mdrawer__close" onClick={() => setMenuOpen(false)} aria-label="Close menu">
                  <X size={20} />
                </button>
              </div>
              {sidebarBody(() => setMenuOpen(false))}
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
