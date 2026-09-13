"use client";

/**
 * §3, §7 -- Student shell: lighter single-column layout, no sidebar (a sidebar would be
 * empty most of the time for a surface this narrow).
 *
 * TODO(backend): Dependency Index #2 -- gated on `isMockStudentSession()`, a purely local
 * demo flag set by the mocked roll-no/PIN form in /login. There is no real student auth
 * to gate on yet.
 */

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AvaiLogo } from "@/components/AvaiLogo";
import { Mascot } from "@/components/Mascot";
import { exitMockStudentSession, isMockStudentSession } from "@/lib/session";

export default function StudentLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [ok, setOk] = useState(false);

  useEffect(() => {
    if (isMockStudentSession()) {
      setOk(true);
      setReady(true);
    } else {
      router.replace("/login?tab=student");
    }
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
  if (!ok) return null;

  return (
    <div className="studentshell">
      <header className="studenttopbar">
        <AvaiLogo height={22} />
        <button
          type="button"
          className="secondary tiny"
          onClick={() => {
            exitMockStudentSession();
            router.push("/login?tab=student");
          }}
        >
          Sign out
        </button>
      </header>
      <div className="studentbody">{children}</div>
      <style jsx>{`
        .studentshell { max-width: 560px; margin: 0 auto; }
        .studenttopbar {
          display: flex; align-items: center; justify-content: space-between;
          padding: 14px 20px; border-bottom: 1px solid var(--rule);
        }
        .studentbody { padding: 4px 20px 40px; }
      `}</style>
    </div>
  );
}
