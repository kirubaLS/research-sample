"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AlertCircle, ArrowRight, KeyRound, ShieldCheck } from "lucide-react";
import { Mascot, Wordmark } from "@/components/Mascot";
import { Reveal } from "@/components/motion";
import { api, ApiError, ApiUnreachable } from "@/lib/api";
import { getPlatformKey, setPlatformKey } from "@/lib/session";

/**
 * AVAI operator sign-in. Real: the pasted value is the platform's own
 * X-Platform-Key/X-API-Key credential (see api.ts's `operator()`), checked
 * with GET /platform/me before it is stored. There is no operator email +
 * password concept on the real backend (the reference's "demo staff
 * accounts" list and its "any password works" note are UI-only mock) --
 * signing in here means holding the key itself, same as a principal or
 * teacher signs in with their own key at /login.
 */
export default function AdminSignInPage() {
  const router = useRouter();
  const [key, setKey] = useState(() => getPlatformKey() ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = key.trim();
    if (!trimmed) {
      setError("Enter the operator key.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.platformWhoami(trimmed);
      setPlatformKey(trimmed);
      router.push("/admin/schools");
    } catch (err) {
      if (err instanceof ApiUnreachable) setError("Could not reach the server. Check the connection and try again.");
      else if (err instanceof ApiError && (err.status === 401 || err.status === 403)) setError("That key was not accepted.");
      else setError("Could not sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <aside className="auth__aside" style={{ alignItems: "center", justifyContent: "center", textAlign: "center" }}>
        <Reveal>
          <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", gap: 20, alignItems: "center" }}>
            <Wordmark height={52} onDark />
            <Mascot pose="hello" size={170} float />
            <h1 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(24px, 2.8vw, 34px)", fontWeight: 500, lineHeight: 1.25, maxWidth: 380 }}>
              Every opportunity belongs to every student.
            </h1>
          </div>
        </Reveal>
      </aside>

      <div className="auth__panel">
        <div>
          <Reveal>
            <div className="surface" style={{ padding: "26px 24px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 4 }}>
                <ShieldCheck size={18} style={{ color: "var(--brand-blue)" }} />
                <h2 style={{ fontSize: 21 }}>Operator sign-in</h2>
              </div>
              <p className="small muted" style={{ marginBottom: 20 }}>
                Paste the operator key AVAI issued you. Principals and teachers sign in at the school app, not here.
              </p>

              <form className="login__form" onSubmit={submit} noValidate>
                <div className="field">
                  <label htmlFor="platform-key">Operator key</label>
                  <input
                    id="platform-key"
                    className="input mono"
                    type="password"
                    autoComplete="off"
                    placeholder="Paste your key"
                    value={key}
                    aria-invalid={!!error}
                    aria-describedby={error ? "platform-error" : undefined}
                    onChange={(e) => {
                      setKey(e.target.value);
                      setError(null);
                    }}
                  />
                  <span className="small muted" style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                    <KeyRound size={11} /> Sent to X-Platform-Key on every request, checked against GET /platform/me.
                  </span>
                </div>

                {error && (
                  <div id="platform-error" className="evidence" style={{ background: "var(--risk-soft)", borderColor: "#eec3bb", color: "#8f3226" }}>
                    <AlertCircle size={15} />
                    <span>{error}</span>
                  </div>
                )}

                <button type="submit" className="btn btn--blue" style={{ justifyContent: "center", padding: "10px 14px" }} disabled={busy}>
                  {busy ? "Checking…" : "Enter console"} <ArrowRight size={14} />
                </button>
              </form>
            </div>
          </Reveal>

          <p className="login__help">
            Looking for the school app? <Link href="/login" className="btn--link">Principal and teacher sign-in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
