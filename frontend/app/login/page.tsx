"use client";

/**
 * §4 -- one entry screen, two visible tabs ("School Staff" / "Student"). Staff and
 * students authenticate completely differently, so the split is visible up front rather
 * than one form with a role dropdown.
 *
 * - School Staff: the real `api.whoami` sign-in (identical to AdminGate's own flow) --
 *   a sign-in key that really checks against the backend. A principal, admin and teacher
 *   key all use this same form; `GET /admin/me`'s `role` decides which shell to land on.
 * - Student tab: also real now -- `api.studentLogin` trades a class code, roll number
 *   and PIN for a StudentSession token (app/api/student.py). The PIN only ever works if
 *   a teacher shared a report and handed it out; wrong-credentials messaging stays
 *   generic on purpose, matching the backend's "same 404 either way" answer.
 *
 * Wrong-credentials messaging on the real Principal path stays generic, matching the
 * backend's existing "revoked keys 404 identically to nonexistent ones" convention.
 */

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AvaiLogo } from "@/components/AvaiLogo";
import { Mascot } from "@/components/Mascot";
import { api, ApiError, ApiUnreachable } from "@/lib/api";
import { setApiKey, setRole, setStudentSession } from "@/lib/session";

type Tab = "staff" | "student";

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

  return (
    <main className="narrow login-page">
      <div className="login-head">
        <AvaiLogo height={30} />
        <Mascot pose="hello" size={34} />
      </div>

      <p className="login-sub">
        Pick the one that&rsquo;s you: the sign-in fields are different for each.
      </p>

      <div className="tabbar" role="tablist" aria-label="Sign in as">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "staff"}
          className={`tabbtn${tab === "staff" ? " on" : ""}`}
          onClick={() => setTab("staff")}
        >
          <span className="tabtitle">School Staff</span>
          <span className="tabhint">Principal or teacher, sign in with your key</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "student"}
          className={`tabbtn${tab === "student" ? " on" : ""}`}
          onClick={() => setTab("student")}
        >
          <span className="tabtitle">Student</span>
          <span className="tabhint">Viewing a report your teacher shared</span>
        </button>
      </div>

      <div className="card login-card">
        {tab === "staff" ? <StaffSignIn /> : <StudentSignIn />}
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
        .login-sub {
          text-align: center; color: var(--ink-3); font-size: 13.5px; margin: 0 0 16px;
        }
        .tabbar {
          display: flex; gap: 6px; background: var(--surface-2); border-radius: var(--radius-sm);
          padding: 4px; margin-bottom: 16px;
        }
        .tabbtn {
          flex: 1; border: 0; background: transparent; padding: 10px 12px; border-radius: 8px;
          cursor: pointer; display: flex; flex-direction: column; gap: 2px; text-align: left;
        }
        .tabtitle { font-weight: 700; font-size: 14.5px; color: var(--ink-3); }
        .tabhint { font-size: 11.5px; color: var(--ink-3); opacity: 0.8; }
        .tabbtn.on { background: var(--surface); box-shadow: var(--shadow-xs); }
        .tabbtn.on .tabtitle { color: var(--brand-ink); }
        .tabbtn.on .tabhint { color: var(--ink-2); }
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

function StaffSignIn() {
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
      setRole({ role: me.role, can: me.can, scope: me.scope, assignments: me.assignments });
      router.push(me.role === "teacher" ? "/teacher/home" : "/admin/academics");
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        // Valid admin key, no school picked yet -- same as AdminGate: let /admin/academics
        // (any /admin/* route works -- AdminGate wraps them all) resolve it.
        setApiKey(key, "");
        router.push("/admin/academics");
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
        <p className="hint">
          The key you were personally issued: a principal&rsquo;s school key, or a
          teacher&rsquo;s own sign-in key. Not sure which you have? Ask your school office.
        </p>
      </div>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={busy} style={{ width: "100%", display: "inline-flex", justifyContent: "center", gap: 8 }}>
        {busy && <Mascot pose="loading" size={18} />}
        {busy ? "Checking…" : "Sign in"}
      </button>
    </form>
  );
}

function StudentSignIn() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const data = new FormData(event.currentTarget);
    const roll = String(data.get("roll") ?? "").trim();
    const classCode = String(data.get("classCode") ?? "").trim();
    const pin = String(data.get("pin") ?? "").trim();
    if (!roll || !classCode || !pin) {
      setError("Enter your class code, roll number and PIN.");
      return;
    }
    setBusy(true);
    try {
      const result = await api.studentLogin(classCode, roll, pin);
      setStudentSession(result.session_token, result.student_name);
      router.push("/student");
    } catch (err) {
      setError(
        err instanceof ApiUnreachable
          ? "Could not reach the server. Try again in a minute."
          : "That roll number, class code or PIN was not recognised. Check with your teacher.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <p className="cardnote" style={{ marginTop: 0 }}>
        Sign in with the PIN your teacher gave you when they shared your report.
      </p>
      <div className="field">
        <label htmlFor="classCode">Class code</label>
        <input id="classCode" name="classCode" placeholder="the code your teacher gave you" required />
      </div>
      <div className="field">
        <label htmlFor="roll">Roll number</label>
        <input id="roll" name="roll" placeholder="e.g. 7" required />
      </div>
      <div className="field">
        <label htmlFor="pin">PIN</label>
        <input id="pin" name="pin" type="password" inputMode="numeric" placeholder="••••••" required />
      </div>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={busy} style={{ width: "100%", display: "inline-flex", justifyContent: "center", gap: 8 }}>
        {busy && <Mascot pose="loading" size={18} />}
        {busy ? "Checking…" : "Sign in"}
      </button>
    </form>
  );
}
