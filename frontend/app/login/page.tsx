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
    <div className="login">
      <section className="login__brand">
        <div className="login__logo">
          <AvaiLogo height={30} />
          <span className="login__wordmark">AVAI</span>
        </div>

        <div className="login__hero">
          <Mascot pose="hello" size={64} />
          <h1>Every opportunity belongs to every student.</h1>
          <p>Sign in to see the findings, findings and follow-ups for your school.</p>
        </div>

        <div className="login__foot">Trouble signing in? Ask your school office.</div>
      </section>

      <section className="login__panel">
        <div className="login__card">
          <h2>Sign in</h2>
          <p className="muted small" style={{ marginTop: 4 }}>
            Pick the one that&rsquo;s you: the sign-in fields are different for each.
          </p>

          <div className="tabs" role="tablist" aria-label="Sign in as">
            <button
              type="button"
              role="tab"
              aria-selected={tab === "staff"}
              className={`tab${tab === "staff" ? " tab--active" : ""}`}
              onClick={() => setTab("staff")}
            >
              School Staff
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === "student"}
              className={`tab${tab === "student" ? " tab--active" : ""}`}
              onClick={() => setTab("student")}
            >
              Student
            </button>
          </div>

          {tab === "staff" ? <StaffSignIn /> : <StudentSignIn />}

          <p className="login__help">Trouble signing in? Ask your school office.</p>
        </div>
      </section>
    </div>
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
      router.push(me.role === "teacher" ? "/teacher/home" : "/principal/classes");
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        // Valid admin key, no school picked yet -- same as AdminGate: let /principal/classes
        // (any AdminGate-wrapped route works) resolve it.
        setApiKey(key, "");
        router.push("/principal/classes");
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
    <form className="login__form" onSubmit={submit}>
      <div className="field">
        <label htmlFor="key">Sign-in key</label>
        <input
          id="key"
          name="key"
          className="input"
          type="password"
          autoComplete="current-password"
          required
          placeholder="zozx6r94sEf1KWs7fRdXTNJNYXKEteuW"
        />
        <p className="small muted">
          The key you were personally issued: a principal&rsquo;s school key, or a
          teacher&rsquo;s own sign-in key. Not sure which you have? Ask your school office.
        </p>
      </div>
      {error && (
        <div className="evidence evidence--gold">
          <div>{error}</div>
        </div>
      )}
      <button type="submit" className="btn btn--primary" disabled={busy} style={{ justifyContent: "center", padding: 11 }}>
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
    <form className="login__form" onSubmit={submit}>
      <p className="small muted" style={{ marginTop: 0 }}>
        Sign in with the PIN your teacher gave you when they shared your report.
      </p>
      <div className="field">
        <label htmlFor="classCode">Class code</label>
        <input id="classCode" name="classCode" className="input" placeholder="the code your teacher gave you" required />
      </div>
      <div className="field">
        <label htmlFor="roll">Roll number</label>
        <input id="roll" name="roll" className="input" placeholder="e.g. 7" required />
      </div>
      <div className="field">
        <label htmlFor="pin">PIN</label>
        <input id="pin" name="pin" className="input" type="password" inputMode="numeric" placeholder="••••••" required />
      </div>
      {error && (
        <div className="evidence evidence--gold">
          <div>{error}</div>
        </div>
      )}
      <button type="submit" className="btn btn--primary" disabled={busy} style={{ justifyContent: "center", padding: 11 }}>
        {busy && <Mascot pose="loading" size={18} />}
        {busy ? "Checking…" : "Sign in"}
      </button>
    </form>
  );
}
