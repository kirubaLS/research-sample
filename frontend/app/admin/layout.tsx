import { AdminGate } from "@/components/AdminGate";
import { SideNav } from "@/components/SideNav";

/**
 * Sidebar beside content, which is what a dashboard of this shape is: the standing
 * navigation stays put and only the panel changes. It collapses to a scrolling row on a
 * phone rather than a drawer, because a drawer is one more thing to learn before the
 * first task starts.
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminGate>
      <div className="deskshell">
        <SideNav />
        <div className="panel">{children}</div>
      </div>
    </AdminGate>
  );
}
