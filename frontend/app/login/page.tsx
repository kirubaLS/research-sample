"use client";

/**
 * §4 -- one entry screen, two visible tabs ("School Staff" / "Student"). Staff and
 * students authenticate completely differently, so the split is visible up front rather
 * than one form with a role dropdown.
 *
 * - School Staff → Principal path: ✅ BUILDABLE NOW, the real `api.whoami` sign-in
 *   (identical to AdminGate's own flow) -- a school code + sign-in key that really checks
 *   against the backend.
 * - School Staff → Teacher path: 🔧 BACKEND REQUIRED (Dependency Index #1). There is no
 *   teacher auth today, so this is a clearly-labeled "Preview teacher view (demo data)"
 *   affordance, not a real sign-in.
 * - Student tab: 🔧 BACKEND REQUIRED (Dependency Index #2). Roll number + school code +
 *   PIN, built and stateful, but any non-empty PIN "unlocks" a fixed set of mock reports --
 *   there is no backend to actually check it against.
 *
 * Wrong-credentials messaging on the real Principal path stays generic, matching the
 * backend's existing "revoked keys 404 identically to nonexistent ones" convention.
 */

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AvaiLogo } from "@/components/AvaiLogo";
import { Mascot } from "@/components/Mascot";
import { api, ApiError, ApiUnreachable } from "@/lib/api";
import {
  enterMockStudentSession,
  enterMockTeacherPreview,
  setApiKey,
  setRole,
} from "@/lib/session";
import { MOCK_STUDENT_IDENTITY } from "@/lib/mocks/student";

type Tab = "staff" | "student";
type StaffPath = "principal" | "teacher";

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>(params.get("tab") === "student" ? "student" : "staff");
  const [staffPath, setStaffPath] = useState<StaffPath>("principal");

  return (
    <main className="narrow login-page">
      <div className="login-head">
        <AvaiLogo height={30} />
        <Mascot pose="hello" size={34} />
      </div>

      <div className="tabbar" role="tablist" aria-label="Sign in as">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "staff"}
          className={`tabbtn${tab === "staff" ? " on" : ""}`}
          onClick={() => setTab("staff")}
        >
          School Staff
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "student"}
          className={`tabbtn${tab === "student" ? " on" : ""}`}
          onClick={() => setTab("student")}
        >
          Student
        </button>
      </div>

      <div className="card login-card">
        {tab === "staff" ? (
          <>
            <div className="subtabbar">
              <button
                type="button"
                className={`subtab${staffPath === "principal" ? " on" : ""}`}
                onClick={() => setStaffPath("principal")}
              >
                Principal / Admin
              </button>
              <button
                type="button"
                className={`subtab${staffPath === "teacher" ? " on" : ""}`}
                onClick={() => setStaffPath("teacher")}
              >
                Teacher
              </button>
            </div>
            {staffPath === "principal" ? <PrincipalSignIn /> : <TeacherPreview />}
          </>
        ) : (
          <StudentSignIn />
        )}
      </div>

      <p className="small muted" style={{ marginTop: 14, textAlign: "center" }}>
        Trouble signing in? Ask your school office.
      </p>

      <style jsx>{`
        .login-page { max-width: 460px; padding-top: 48px; }
        .login-head {
          display: flex; align-items: center; justify-content: center; gap: 12px;
          margin-bottom: 22px;
        }
        .tabbar {
          display: flex; gap: 6px; background: var(--surface-2); border-radius: var(--radius-sm);
          padding: 4px; margin-bottom: 16px;
        }
        .tabbtn {
          flex: 1; border: 0; background: transparent; padding: 9px 12px; border-radius: 8px;
          font-weight: 600; font-size: 14.5px; color: var(--ink-3); cursor: pointer;
        }
        .tabbtn.on { background: var(--surface); color: var(--brand-ink); box-shadow: var(--shadow-xs); }
        .login-card { padding: 22px; }
        .subtabbar {
          display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid var(--rule);
        }
        .subtab {
          border: 0; background: transparent; padding: 8px 4px; margin-right: 14px;
          font-size: 13.5px; font-weight: 600; color: var(--ink-3); cursor: pointer;
          border-bottom: 2px solid transparent;
        }
        .subtab.on { color: var(--brand-ink); border-bottom-color: var(--brand-ink); }
      `}</style>
    </main>
  );
}

function PrincipalSignIn() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    const key = String(new FormData(event.currentTarget).get("key") ?? "").trim();
    try {
      const me = await api.whoami(key);
      setApiKey(key, me.name);
      setRole({ role: me.role, can: me.can, scope: me.scope });
      router.push("/admin");
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        // Valid admin key, no school picked yet -- same as AdminGate: let /admin resolve it.
        setApiKey(key, "");
        router.push("/admin");
        return;
      }
      setError(
        err instanceof ApiUnreachable
          ? "Could not reach the server. Try again in a minute."
          : "That key was not recognised. Check it and try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <div className="field">
        <label htmlFor="key">Sign-in key</label>
        <input id="key" name="key" type="password" autoComplete="current-password" required
          placeholder="zozx6r94sEf1KWs7fRdXTNJNYXKEteuW" />
        <p className="hint">Your school&rsquo;s own key, issued by whoever set up this deployment.</p>
      </div>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={busy} style={{ width: "100%", display: "inline-flex", justifyContent: "center", gap: 8 }}>
        {busy && <Mascot pose="loading" size={18} />}
        {busy ? "Checking…" : "Sign in"}
      </button>
    </form>
  );
}

function TeacherPreview() {
  const router = useRouter();
  return (
    <div>
      <p className="cardnote" style={{ marginTop: 0 }}>
        Teacher sign-in is not built yet — there is no <code>teacher</code> role on the
        backend today.{" "}
        <span className="small muted">(TODO(backend): Dependency Index #1.)</span> You can
        preview the teacher experience against a fixed demo teacher instead.
      </p>
      <button
        type="button"
        style={{ width: "100%" }}
        onClick={() => {
          enterMockTeacherPreview();
          router.push("/teacher");
        }}
      >
        Preview teacher view (demo data)
      </button>
    </div>
  );
}

function StudentSignIn() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // TODO(backend): Dependency Index #2 -- there is no student-auth endpoint. Any non-empty
  // roll no + school code + PIN "signs in" and lands on the mocked student portal; a
  // blank field is the only thing rejected here, purely for a plausible-looking demo flow.
  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const data = new FormData(event.currentTarget);
    const roll = String(data.get("roll") ?? "").trim();
    const school = String(data.get("school") ?? "").trim();
    const pin = String(data.get("pin") ?? "").trim();
    if (!roll || !school || !pin) {
      setError("Enter your school code, roll number and PIN.");
      return;
    }
    setBusy(true);
    setTimeout(() => {
      enterMockStudentSession();
      router.push("/student");
    }, 350);
  }

  return (
    <form onSubmit={submit}>
      <p className="cardnote" style={{ marginTop: 0 }}>
        Sign in with the PIN your teacher gave you when they shared your report.{" "}
        <span className="small muted">
          (Demo only — TODO(backend): Dependency Index #2. Any values below "sign in".)
        </span>
      </p>
      <div className="field">
        <label htmlFor="school">School code</label>
        <input id="school" name="school" placeholder={MOCK_STUDENT_IDENTITY.schoolCode} required />
      </div>
      <div className="field">
        <label htmlFor="roll">Roll number</label>
        <input id="roll" name="roll" placeholder={MOCK_STUDENT_IDENTITY.rollNo} required />
      </div>
      <div className="field">
        <label htmlFor="pin">PIN</label>
        <input id="pin" name="pin" type="password" inputMode="numeric" placeholder="••••" required />
      </div>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={busy} style={{ width: "100%", display: "inline-flex", justifyContent: "center", gap: 8 }}>
        {busy && <Mascot pose="loading" size={18} />}
        {busy ? "Checking…" : "Sign in"}
      </button>
    </form>
  );
}
