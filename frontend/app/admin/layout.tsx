"use client";

import { AdminGate } from "@/components/AdminGate";
import { StaffShell } from "@/components/StaffShell";
import { ADMIN_NAV } from "@/components/staffNav";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminGate>
      <StaffShell nav={ADMIN_NAV} roleLabel="Admin">
        {children}
      </StaffShell>
    </AdminGate>
  );
}
