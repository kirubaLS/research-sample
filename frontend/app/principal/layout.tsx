import { AdminGate } from "@/components/AdminGate";
import { SideNav } from "@/components/SideNav";

/**
 * Sidebar beside content, which is what a dashboard of this shape is: the standing
 * navigation stays put and only the panel changes. It collapses to a scrolling row on a
 * phone rather than a drawer, because a drawer is one more thing to learn before the
 * first task starts.
 *
 * The same shell app/admin/layout.tsx already uses -- /principal is a sibling top-level
 * route now, not nested under /admin, so it needs its own copy of the same wrapper
 * rather than inheriting one. AdminGate itself is unchanged: it still gates on a real
 * admin/principal/teacher key and still redirects a teacher key to /teacher/home.
 */
export default function PrincipalLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminGate>
      <div className="deskshell">
        <SideNav />
        <div className="panel">{children}</div>
      </div>
    </AdminGate>
  );
}
