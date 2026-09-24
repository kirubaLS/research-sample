"use client";

import { useEffect, useState } from "react";
import { api, ApiError, apiBaseIsDefault, ApiUnreachable } from "@/lib/api";
import { getPlatformKey, setPlatformKey, signOutPlatform } from "@/lib/session";

/**
 * Sign-in for the operator console.
 *
 * Two credentials open this. The operator key bootstraps a deployment and is the only
 * way to issue the first admin key; an admin key, which belongs to no school, works here
 * too because creating and running schools is the whole of that role.
 *
 * A principal key never does, and neither does a school's own key -- that is an admin
 * bound to one school, so one leaked school credential still cannot reach a second
 * school's data.
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
          ? "Could not reach the server. It may be starting up, or this site may be pointed at the wrong address. Try again in a minute."
          : err instanceof ApiError && err.status === 404
          ? "Not accepted. Either the key is wrong, or the console has not been switched on for this deployment yet."
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
      <div className="loading">
        <p className="muted">Checking your session…</p>
      </div>
    );
  }

  if (!signedIn) {
    return (
      <main className="content" style={{ maxWidth: 460 }}>
        <p className="eyebrow">Operator console</p>
        <h1 className="page-title">Platform sign-in</h1>
        <p className="page-sub">
          For whoever runs this deployment. An admin key works here as well as on the
          dashboard. A principal&rsquo;s key does not; it opens their own school and
          nothing else.
        </p>

        {apiBaseIsDefault() && (
          <div className="evidence evidence--gold" style={{ marginTop: 18 }}>
            <p>
              This site has not been told where its server is, so it is asking your own
              computer and nothing will load. Point it at the server and publish it again.
              Restarting will not fix it on its own.
            </p>
          </div>
        )}

        <form onSubmit={submit} className="card" style={{ marginTop: 22 }}>
          <div className="card__body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="field">
              <label htmlFor="key">Your key</label>
              <input id="key" name="key" className="input" type="password" autoComplete="current-password" required />
              <p className="small muted">
                An admin key issued from this console. The first time, before any admin key
                exists, use the setup key chosen when this deployment was created.
              </p>
            </div>
            {error && (
              <div className="evidence">
                <p>{error}</p>
              </div>
            )}
            <button type="submit" className="btn btn--primary" disabled={busy}>
              {busy ? "Checking…" : "Sign in"}
            </button>
          </div>
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
        <span className="small muted">Platform console</span>
        <button
          className="btn btn--ghost btn--sm"
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
