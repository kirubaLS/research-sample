"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogOut } from "lucide-react";
import { Wordmark } from "@/components/Mascot";
import { school } from "@/lib/avai-mock-data";
import { useAttend } from "@/lib/attendState";

/**
 * The student onboarding surface, the first AVAI screen a new school ever
 * sees. The entry screen is a full-bleed split, so it gets no chrome; every
 * step after it sits under a light glass bar that keeps the school's name
 * and the student's own name in view.
 */
export default function AttendLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { identity } = useAttend();
  const bare = pathname === "/attend";

  if (bare) return <>{children}</>;

  return (
    <div
      style={{
        minHeight: "100vh",
        background:
          "radial-gradient(900px 520px at 88% -8%, rgba(31,138,138,.14), transparent 62%), radial-gradient(760px 520px at -8% 104%, rgba(240,147,43,.13), transparent 62%), var(--brand-cream)",
      }}
    >
      <header
        className="surface--glass"
        style={{
          position: "sticky",
          top: 0,
          zIndex: 20,
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "11px clamp(14px, 4vw, 26px)",
          borderRadius: 0,
          borderWidth: "0 0 1px",
          borderStyle: "solid",
          borderColor: "var(--line)",
        }}
      >
        <Wordmark height={26} />
        <div style={{ minWidth: 0 }}>
          <div className="muted" style={{ fontSize: 11, lineHeight: 1.3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {school.name}
          </div>
        </div>

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
          {identity && (
            <span className="tag tag--teal" style={{ minWidth: 0 }}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {identity.name} · {identity.section} · {identity.rollNo}
              </span>
            </span>
          )}
          <Link href="/attend" className="btn btn--ghost btn--sm" style={{ flex: "0 0 auto" }} aria-label="Leave the assessment">
            <LogOut size={13} /> Exit
          </Link>
        </div>
      </header>

      <main style={{ maxWidth: 780, margin: "0 auto", padding: "clamp(16px, 4vw, 28px) clamp(14px, 4vw, 22px) 80px" }}>{children}</main>
    </div>
  );
}
