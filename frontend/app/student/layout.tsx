"use client";

/**
 * §3, §7 -- Student shell: lighter single-column layout, no sidebar (a sidebar would be
 * empty most of the time for a surface this narrow).
 *
 * Gated on a real StudentSession token (see app/api/student.py). The token itself is
 * re-validated against the backend on every mount by GET /student/reports -- a token
 * this browser still has but the server has since expired or revoked (e.g. `logout` on
 * another tab) is sent straight back to /login rather than shown a shell that can't
 * actually read anything.
 */

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AvaiLogo } from "@/components/AvaiLogo";
import { Mascot } from "@/components/Mascot";
import { api, ApiUnreachable } from "@/lib/api";
import { clearStudentSession, getStudentSession, setStudentSession } from "@/lib/session";

export default function StudentLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [ok, setOk] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getStudentSession();
    if (!token) {
      router.replace("/login?tab=student");
      return;
    }
    api
      .studentReports(token)
      .then((res) => {
        setStudentSession(token, res.student_name);
        setOk(true);
        setReady(true);
      })
      .catch((err) => {
        if (err instanceof ApiUnreachable) {
          setError("Could not reach the server. Try again in a minute.");
          setReady(true);
          return;
        }
        clearStudentSession();
        router.replace("/login?tab=student");
      });
  }, [router]);

  if (!ready) {
    return (
      <div className="loading">
        <Mascot pose="loading" size={28} />
        <p className="muted">Loading…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="error-fallback">
        <p>{error}</p>
      </div>
    );
  }
  if (!ok) return null;

  return (
    <div className="student-shell">
      <header className="student-top">
        <AvaiLogo height={22} />
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={() => {
            const token = getStudentSession();
            if (token) void api.studentLogout(token);
            clearStudentSession();
            router.push("/login?tab=student");
          }}
        >
          Sign out
        </button>
      </header>
      <div className="student-main">{children}</div>
    </div>
  );
}
