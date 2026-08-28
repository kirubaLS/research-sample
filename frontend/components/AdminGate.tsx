"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { getApiKey, getSchoolName, setApiKey, signOut } from "@/lib/session";

/**
 * The dashboard's sign-in.
 *
 * A school key, validated against /admin/me and held in the browser. Students never see
 * this — they arrive on a class link and have no account at all.
 */
export function AdminGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
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
      setSchool(me.name);
      setSignedIn(true);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 404
          ? "That key was not recognised. Check it against the one your setup printed."
          : "Could not reach the API. Is the backend running?",
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
              Printed by <span className="mono">python -m scripts.seed</span> when the school
              was created.
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
        <span className="small muted">{school ?? getSchoolName()}</span>
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
      {children}
    </>
  );
}
