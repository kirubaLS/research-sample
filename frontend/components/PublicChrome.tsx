"use client";

/**
 * Staff routes (/admin, /principal, /teacher) render their own StaffShell chrome
 * (sidebar, sign-out, school name) -- nesting the old site header/footer/background
 * around them too would double up on navigation and fight the new sidebar grid layout,
 * which also owns the .shell classname now. Everything else (front door, /login, the
 * student flow) still gets the plain header + footer wrapper.
 */
import { usePathname } from "next/navigation";
import { DecorativeBackground } from "@/components/DecorativeBackground";
import { SiteHeader } from "@/components/SiteHeader";

const SHELLED_PREFIXES = ["/admin", "/principal", "/teacher"];

export function PublicChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "";
  const shelled = SHELLED_PREFIXES.some((p) => pathname.startsWith(p));

  if (shelled) return <>{children}</>;

  return (
    <>
      <DecorativeBackground />
      <div className="wrap-outer">
        <SiteHeader />
        {children}
        <footer className="sitefooter">
          <div className="inner">
            <span>Avai</span>
            <span className="mono">CBSE Class X · Tamil Nadu</span>
          </div>
        </footer>
      </div>
    </>
  );
}
