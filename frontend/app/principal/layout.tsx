"use client";

import { AdminGate } from "@/components/AdminGate";
import { StaffShell } from "@/components/StaffShell";
import { PRINCIPAL_NAV } from "@/components/staffNav";

export default function PrincipalLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminGate>
      <StaffShell nav={PRINCIPAL_NAV} roleLabel="Principal">
        {children}
      </StaffShell>
    </AdminGate>
  );
}
