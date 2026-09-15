"use client";

/**
 * Teacher shell (§3, §6): same sidebar-plus-content shape as the staff shell, navigated
 * from this teacher key's real assignments (GET /admin/me's `assignments`) rather than a
 * fixture. Gated exactly like AdminGate -- a stored key is re-validated against
 * /admin/me on mount, and only a key whose role is actually "teacher" gets in; a
 * principal/admin key that somehow lands here is sent to /admin instead of shown a
 * teacher's nav it was never issued for.
 */

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { TeacherNav } from "@/components/teacher/TeacherNav";
import { Mascot } from "@/components/Mascot";
import { api, ApiUnreachable } from "@/lib/api";
import { getApiKey, setApiKey, setRole, signOut } from "@/lib/session";

export default function TeacherLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [ok, setOk] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) {
      router.replace("/login");
      return;
    }
    api
      .whoami(key)
      .then((me) => {
        setRole({ role: me.role, can: me.can, scope: me.scope, assignments: me.assignments });
        if (me.role !== "teacher") {
          router.replace("/admin");
          return;
        }
        setApiKey(key, me.name);
        setOk(true);
        setReady(true);
      })
      .catch((err) => {
        if (err instanceof ApiUnreachable) {
          setError("Could not reach the server. Try again in a minute.");
          setReady(true);
          return;
        }
        signOut();
        router.replace("/login");
      });
  }, [router]);

  if (!ready) {
    return (
      <main className="narrow">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={28} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      </main>
    );
  }
  if (error) {
    return (
      <main className="narrow">
        <p className="error">{error}</p>
      </main>
    );
  }
  if (!ok) return null;

  return (
    <div className="deskshell">
      <TeacherNav />
      <div className="panel">{children}</div>
    </div>
  );
}
