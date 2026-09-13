"use client";

/**
 * Mocked Teacher shell (§3, §6). Same shape as the staff shell (sidebar + content), but a
 * teacher-scoped nav built from the fixture teacher's assignments (§6.1) rather than the
 * principal's full `WORK` nav.
 *
 * TODO(backend): Dependency Index #1 -- gated on `isMockTeacherPreview()`, a purely local
 * demo flag, never a real teacher session. There is no real teacher auth to gate on yet.
 */

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { TeacherNav } from "@/components/teacher/TeacherNav";
import { exitMockTeacherPreview, isMockTeacherPreview } from "@/lib/session";
import { Mascot } from "@/components/Mascot";

export default function TeacherLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [ok, setOk] = useState(false);

  useEffect(() => {
    if (isMockTeacherPreview()) {
      setOk(true);
      setReady(true);
    } else {
      router.replace("/login");
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
    <div className="deskshell">
      <TeacherNav />
      <div className="panel">
        <div
          className="demo-banner"
          style={{
            maxWidth: "var(--max)",
            margin: "0 auto 14px",
            padding: "8px 14px",
            borderRadius: "var(--radius-sm)",
            background: "var(--info-soft)",
            color: "var(--info)",
            fontSize: 13,
            fontWeight: 600,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 10,
          }}
        >
          <span>
            Demo data — previewing the teacher experience. No real teacher sign-in exists
            yet (Dependency Index #1).
          </span>
          <button
            type="button"
            className="secondary tiny"
            onClick={() => {
              exitMockTeacherPreview();
              router.push("/login");
            }}
          >
            Exit preview
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
