"use client";

import { useEffect, useState } from "react";
import { api, ApiError, apiBase, apiBaseIsDefault, ApiUnreachable } from "@/lib/api";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { getApiKey, getSchoolName, setApiKey, setRole, signOut, type StaffRole } from "@/lib/session";

/**
 * Routes an admin key opens and a principal key does not. A principal signs in to read
 * results and progress; producing them -- scanning a paper, entering marks -- is the
 * admin's job and a separate credential.
 *
 * This list only decides what is *offered*. Every one of these screens calls an endpoint
 * the API refuses to a principal anyway, so a stale browser cannot become a way in.
 */
const ADMIN_ONLY = ["/admin/paper", "/admin/answers", "/admin/scan"];

/**
 * The dashboard's sign-in.
 *
 * A school key, validated against /admin/me and held in the browser. Students never see
 * this — they arrive on a class link and have no account at all.
 */
export function AdminGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "";
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [staff, setStaff] = useState<StaffRole | null>(null);
  const [school, setSchool] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const key = getApiKey();
    if (!key) {
      setReady(true);
      return;
    }
    api
      .whoami(key)
      .then((me) => {
        setSchool(me.name);
        setStaff({ role: me.role, can: me.can });
        setRole({ role: me.role, can: me.can });
        setSignedIn(true);
      })
      .catch(() => signOut())
      .finally(() => setReady(true));
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    const key = String(new FormData(event.currentTarget).get("key") ?? "").trim();
    try {
      const me = await api.whoami(key);
      setApiKey(key, me.name);
      setRole({ role: me.role, can: me.can });
      setStaff({ role: me.role, can: me.can });
      setSchool(me.name);
      setSignedIn(true);
    } catch (err) {
      setError(
        err instanceof ApiUnreachable
          ? `Could not reach the API at ${err.base}. Either the backend is down, or this site was built without NEXT_PUBLIC_API_BASE pointing at it, or the API's CORS origins do not include this site.`
          : err instanceof ApiError && err.status === 404
            ? "That key was not recognised. Check it against the one the operator console issued."
            : "Something went wrong signing in.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!ready) {
    return (
      <main className="narrow">
        <p className="muted">Checking your session…</p>
      </main>
    );
  }

  if (!signedIn) {
    return (
      <main className="narrow">
        <div className="hero">
          <p className="eyebrow">Principal &amp; admin</p>
          <h1>Sign in</h1>
          <p className="lede">
            The dashboard is for school staff. Students do not sign in — they open a class
            link instead.
          </p>
        </div>

        {apiBaseIsDefault() && (
          <div className="notice warn" style={{ marginTop: 18 }}>
            This site was built without <span className="mono">NEXT_PUBLIC_API_BASE</span>, so
            it is calling <span className="mono">{apiBase()}</span> — your own machine. Set it
            to the API service&apos;s URL and deploy again; it is read at build time, so a
            restart alone will not pick it up.
          </div>
        )}

        <form onSubmit={submit} className="card" style={{ marginTop: 22 }}>
          <div className="field">
            <label htmlFor="key">School API key</label>
            <input
              id="key"
              name="key"
              type="password"
              autoComplete="current-password"
              placeholder="zozx6r94sEf1KWs7fRdXTNJNYXKEteuW"
              required
            />
            <p className="hint">
              There are no admin accounts and no passwords — one key per school, held by the
              principal. It is issued in the operator console at{" "}
              <span className="mono">/platform</span>, which also re-issues it if this one is
              lost. From a shell, <span className="mono">python -m scripts.admin_key</span>
              {" "}prints it instead.
            </p>
          </div>
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={busy}>
            {busy ? "Checking…" : "Sign in"}
          </button>
        </form>
      </main>
    );
  }

  const blocked =
    staff !== null && staff.role !== "admin" && ADMIN_ONLY.some((p) => pathname.startsWith(p));

  return (
    <>
      <div
        style={{
          maxWidth: "var(--max)",
          margin: "0 auto",
          padding: "10px 22px 0",
          display: "flex",
          justifyContent: "flex-end",
          gap: 12,
          alignItems: "center",
        }}
      >
        <span className="small muted">
          {school ?? getSchoolName()}
          {staff && ` · ${staff.role === "admin" ? "Admin" : "Principal"}`}
        </span>
        <button
          className="secondary tiny"
          onClick={() => {
            signOut();
            setSignedIn(false);
          }}
        >
          Sign out
        </button>
      </div>
      {blocked ? (
        <main className="narrow">
          <div className="hero">
            <p className="eyebrow">Principal</p>
            <h1>That screen needs an admin key</h1>
            <p className="lede">
              Your key reads every student&rsquo;s results and progress across the school.
              Producing them &mdash; scanning a question paper, entering marks &mdash; is a
              separate credential, so that a signed-in office laptop cannot alter a mark.
            </p>
          </div>
          <p style={{ marginTop: 18 }}>
            <Link href="/admin">Back to the dashboard</Link>
          </p>
        </main>
      ) : (
        children
      )}
    </>
  );
}
