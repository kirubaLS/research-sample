"use client";

/**
 * The staff sidebar shell (admin/principal/teacher), replacing the old top-header
 * layout -- adapted from the reference design's Shell.tsx, wired to this app's real
 * session (lib/session.ts) instead of the reference's own mock auth. On a phone the
 * sidebar collapses into a slide-in drawer with a bottom tab bar, same as the reference.
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LogOut, Menu, X, type LucideIcon } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { AvaiLogo } from "@/components/AvaiLogo";
import {
  clearActiveSchool,
  getApiKey,
  getRole,
  getSchoolName,
  signOut,
  signOutPlatform,
  type StaffRole,
} from "@/lib/session";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  group?: string;
  needs: keyof StaffRole["can"] | null;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "A";
}

export function StaffShell({
  nav,
  roleLabel,
  children,
}: {
  nav: NavItem[];
  roleLabel: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [role, setRole] = useState<StaffRole | null>(null);
  const [school, setSchool] = useState<string | null>(null);

  useEffect(() => {
    setRole(getRole());
    setSchool(getSchoolName());
  }, [pathname]);

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

  const visible = nav.filter((item) => item.needs === null || Boolean(role?.can[item.needs]));
  const isActive = (item: NavItem) => pathname === item.href || pathname.startsWith(item.href + "/");
  const tabs = visible.filter((i) => !i.group).slice(0, 3);
  const displayName = school ?? "Avai";

  function handleSignOut() {
    signOut();
    signOutPlatform();
    clearActiveSchool();
    router.push("/login");
  }

  function sidebarBody(onNavigate?: () => void) {
    let lastGroup: string | undefined;
    return (
      <>
        <div className="sidebar__meta">
          <div className="sidebar__meta-school">{displayName}</div>
        </div>
        <nav className="sidebar__nav" aria-label="Primary">
          {visible.map((item) => {
            const groupHeader =
              item.group && item.group !== lastGroup ? (
                <div className="sidebar__group" key={`g-${item.group}`}>{item.group}</div>
              ) : null;
            lastGroup = item.group ?? lastGroup;
            const active = isActive(item);
            const Icon = item.icon;
            return (
              <div key={item.href} style={{ display: "contents" }}>
                {groupHeader}
                <Link
                  href={item.href}
                  onClick={onNavigate}
                  className={`navlink ${active ? "navlink--active" : ""}`}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon size={16} /> {item.label}
                </Link>
              </div>
            );
          })}
        </nav>
        <div className="sidebar__footer">
          <div className="sidebar__user">
            <span className="avatar">{initials(roleLabel)}</span>
            <div>
              <div style={{ fontWeight: 600 }}>{roleLabel}</div>
            </div>
          </div>
          <button className="sidebar__signout" onClick={handleSignOut}>
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
          <AvaiLogo height={30} />
          <div className="sidebar__brand-sub">{roleLabel}</div>
        </div>
        {sidebarBody()}
      </aside>

      <div className="main">
        <header className="mtopbar">
          <AvaiLogo height={22} />
          <div className="mtopbar__text">
            <div className="mtopbar__school">{displayName}</div>
          </div>
          <span className="avatar mtopbar__avatar" aria-hidden="true">{initials(roleLabel)}</span>
          <button className="mtopbar__menu" onClick={() => setMenuOpen(true)} aria-label="Open menu" aria-expanded={menuOpen}>
            <Menu size={20} />
          </button>
        </header>
        <main className="content">{children}</main>
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
                  <AvaiLogo height={28} />
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
