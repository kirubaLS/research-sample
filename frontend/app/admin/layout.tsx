"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Building2, LogOut, Radio, ShieldCheck, UserPlus } from "lucide-react";
import { Wordmark } from "@/components/Mascot";
import { adminSchools, formatDate, portfolioKpis, staffInitials, TODAY } from "@/lib/avai-admin-data";
import { signOutStaff, useStaffSession } from "@/lib/adminState";
import { useOpsVersion } from "@/lib/opsDirectory";

/**
 * AVAI staff console chrome. Deliberately a different product from the
 * school-facing app: cool navy canvas, blue accents, denser type. The
 * sign-in screen at /admin renders bare; everything under it is gated.
 */

const nav = [
  { href: "/admin/schools", label: "Schools", icon: Building2, match: (p: string) => p.startsWith("/admin/schools") },
  { href: "/admin/onboard", label: "Onboarding", icon: UserPlus, match: (p: string) => p.startsWith("/admin/onboard") },
];

/** Mobile check runs in an effect, so the first client render matches the server. */
function useNarrow() {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 860px)");
    const sync = () => setNarrow(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return narrow;
}

function titleFor(pathname: string): string {
  const detail = /^\/admin\/schools\/([^/]+)/.exec(pathname);
  if (detail) return adminSchools.find((s) => s.id === detail[1])?.name ?? "Account";
  if (pathname.startsWith("/admin/onboard")) return "Onboard a school";
  return "Portfolio";
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/admin") return <>{children}</>;
  return <ConsoleShell>{children}</ConsoleShell>;
}

function ConsoleShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { staff, ready } = useStaffSession();
  const narrow = useNarrow();
  useOpsVersion();

  useEffect(() => {
    if (ready && !staff) router.replace("/admin");
  }, [ready, staff, router]);

  if (!ready || !staff) {
    return (
      <div className="ops-shell">
        <div className="ops-main">
          <div className="content" style={{ display: "grid", gap: 14, paddingTop: 40 }}>
            <div className="shimmer" style={{ width: 220, height: 20 }} />
            <div className="shimmer" style={{ width: "100%", height: 120 }} />
            <div className="shimmer" style={{ width: "100%", height: 320 }} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="ops-shell">
      <aside className="ops-side">
        <div style={{ display: "flex", alignItems: "center", gap: 11, padding: "18px 16px 14px" }}>
          <div style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 6 }}>
            <Wordmark height={30} onDark />
            <div style={{ fontSize: 10.5, letterSpacing: ".14em", textTransform: "uppercase", color: "var(--brand-orange)", fontWeight: 700 }}>
              Ops console
            </div>
          </div>
        </div>

        <div
          style={{
            margin: "0 12px 8px",
            padding: "10px 12px",
            borderRadius: 10,
            background: "rgba(255,255,255,.06)",
            border: "1px solid rgba(255,255,255,.08)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 11.5, color: "#dbe6fb" }}>
            <span className="pulse-dot" style={{ "--accent": "var(--brand-green)" } as React.CSSProperties} />
            {portfolioKpis.schoolsLive} live · {portfolioKpis.onboardingCount} onboarding
          </div>
          <div style={{ fontSize: 10.5, color: "#8fa2c2", marginTop: 3 }}>Data as of {formatDate(TODAY)}</div>
        </div>

        <nav className="ops-nav" aria-label="Console sections">
          {nav.map((item) => {
            const active = item.match(pathname);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`ops-navlink${active ? " ops-navlink--active" : ""}`}
                aria-current={active ? "page" : undefined}
              >
                <Icon size={15} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div style={{ padding: 14, borderTop: "1px solid rgba(255,255,255,.08)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span
              style={{
                width: 32,
                height: 32,
                flex: "0 0 auto",
                borderRadius: "50%",
                display: "grid",
                placeItems: "center",
                fontSize: 12,
                fontWeight: 700,
                color: "#fff",
                background: "linear-gradient(180deg, #2f76e6, #1d5fd0)",
                boxShadow: "inset 0 1px 0 rgba(255,255,255,.25)",
              }}
            >
              {staffInitials(staff.name)}
            </span>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 650, color: "#fff", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {staff.name}
              </div>
              <div style={{ fontSize: 10.5, color: "#8fa2c2" }}>{staff.role}</div>
            </div>
          </div>
          <button
            type="button"
            className="ops-navlink"
            style={{ width: "100%", marginTop: 10, background: "rgba(255,255,255,.05)", cursor: "pointer" }}
            onClick={() => {
              signOutStaff();
              router.replace("/admin");
            }}
          >
            <LogOut size={14} /> Sign out
          </button>
        </div>
      </aside>

      <div className="ops-main">
        <header className="ops-topbar">
          {narrow && <Wordmark height={22} />}
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 10.5, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--brand-blue)", fontWeight: 700 }}>
              AVAI internal
            </div>
            <div style={{ fontSize: 15.5, fontWeight: 700, letterSpacing: "-.01em", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {titleFor(pathname)}
            </div>
          </div>

          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
            <span className="tag" style={{ background: "#fff", borderColor: "#d9e2f2", color: "var(--brand-ink-soft)" }}>
              <ShieldCheck size={12} /> Staff only
            </span>
            <span className="tag tag--info" style={{ whiteSpace: "nowrap" }}>
              <Radio size={12} /> {adminSchools.length} accounts
            </span>
          </div>
        </header>

        {narrow && (
          <div style={{ display: "flex", gap: 8, padding: "10px 16px 0" }}>
            {nav.map((item) => {
              const active = item.match(pathname);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`btn btn--sm${active ? " btn--blue" : ""}`}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon size={13} /> {item.label}
                </Link>
              );
            })}
          </div>
        )}

        <div className="content">{children}</div>
      </div>
    </div>
  );
}
