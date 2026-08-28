"use client";

import { useEffect, useState } from "react";
import { api, ApiError, apiBase, apiBaseIsDefault, ApiUnreachable } from "@/lib/api";
import { getPlatformKey, setPlatformKey, signOutPlatform } from "@/lib/session";

/**
 * Sign-in for the operator console.
 *
 * A separate credential from the school key, on purpose: a principal holds one key for
 * one school, and if that key could also create schools or read another school's key,
 * one leaked key would compromise every school on the deployment.
 */
export function PlatformGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const key = getPlatformKey();
    if (!key) {
      setReady(true);
      return;
    }
    api
      .platformWhoami(key)
      .then(() => setSignedIn(true))
      .catch(() => signOutPlatform())
      .finally(() => setReady(true));
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    const key = String(new FormData(event.currentTarget).get("key") ?? "").trim();
    try {
      await api.platformWhoami(key);
      setPlatformKey(key);
      setSignedIn(true);
    } catch (err) {
      // The API answers 404 for both "wrong key" and "console disabled" so that a probe
      // cannot tell them apart — which means the UI has to name both possibilities.
      setError(
        err instanceof ApiUnreachable
          ? `Could not reach the API at ${err.base}. Either the backend is down, or this site was built without NEXT_PUBLIC_API_BASE pointing at it, or the API's CORS origins do not include this site.`
          : err instanceof ApiError && err.status === 404
          ? "Not accepted. Either the key is wrong, or YAADHUM_PLATFORM_ADMIN_KEY is not set on the API service — the console stays off until it is."
          : err instanceof ApiError && err.status === 429
            ? "Too many attempts from this network. Try again shortly."
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
          <p className="eyebrow">Operator console</p>
          <h1>Platform sign-in</h1>
          <p className="lede">
            For whoever runs this deployment — not for a school. Principals sign in at{" "}
            <span className="mono">/admin</span> with their school key instead.
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
            <label htmlFor="key">Platform key</label>
            <input id="key" name="key" type="password" autoComplete="current-password" required />
            <p className="hint">
              The value of <span className="mono">YAADHUM_PLATFORM_ADMIN_KEY</span> on the API
              service. Generate one with{" "}
              <span className="mono">python -c &quot;import secrets;print(secrets.token_urlsafe(32))&quot;</span>{" "}
              and set it in the Render dashboard.
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
        <span className="small muted">Platform operator</span>
        <button
          className="secondary tiny"
          onClick={() => {
            signOutPlatform();
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
