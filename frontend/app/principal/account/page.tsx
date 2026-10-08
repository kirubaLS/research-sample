"use client";

/**
 * Change password -- a principal swaps the random key they were issued for one they chose.
 * The key is what they sign in with, so the old one stops working the moment this saves;
 * the browser is given the new one so this session carries on without a second sign-in.
 */

import { useState } from "react";
import { CheckCircle2, Eye, EyeOff } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { passwordProblem } from "@/lib/password";
import { usePageHeader } from "@/lib/pageHeader";
import { getApiKey, getSchoolName, setApiKey } from "@/lib/session";

export default function ChangePasswordPage() {
  usePageHeader({ title: "Change password" });
  const [pw, setPw] = useState("");
  const [again, setAgain] = useState("");
  const [show, setShow] = useState(false);
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const problem = passwordProblem(pw);
  const mismatch = again !== pw ? "The two passwords do not match." : null;
  const pwError = (tried || pw) && problem;
  const againError = (tried || again) && mismatch;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setTried(true);
    setError(null);
    setDone(false);
    if (problem || mismatch) return;
    const key = getApiKey();
    if (!key) {
      setError("You are signed out. Sign in again first.");
      return;
    }
    setBusy(true);
    try {
      await api.changeOwnPassword(key, pw);
      setApiKey(pw, getSchoolName() ?? "");
      setPw("");
      setAgain("");
      setTried(false);
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "That password cannot be used. Choose a different one."
          : err instanceof ApiError && err.status === 422
            ? "That password is not acceptable. Check the rules below."
            : "Could not save the new password. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="card" style={{ maxWidth: 520 }} noValidate>
      <div className="card__body" style={{ display: "grid", gap: 14 }}>
        <p className="small muted" style={{ margin: 0 }}>
          Choose a password you can remember. You sign in with it from now on, and the old one stops working
          straight away. Your school&apos;s operator can see it.
        </p>
        <div className="field">
          <label htmlFor="pw-new">New password</label>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              id="pw-new" className="input" type={show ? "text" : "password"} autoComplete="new-password"
              value={pw} onChange={(e) => setPw(e.target.value)} aria-invalid={!!pwError}
            />
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setShow((v) => !v)} aria-label={show ? "Hide password" : "Show password"}>
              {show ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
          {pwError && <div role="alert" style={{ fontSize: 12.5, fontWeight: 600, color: "var(--risk)" }}>{problem}</div>}
        </div>
        <div className="field">
          <label htmlFor="pw-again">Type it again</label>
          <input
            id="pw-again" className="input" type={show ? "text" : "password"} autoComplete="new-password"
            value={again} onChange={(e) => setAgain(e.target.value)} aria-invalid={!!againError}
          />
          {againError && <div role="alert" style={{ fontSize: 12.5, fontWeight: 600, color: "var(--risk)" }}>{mismatch}</div>}
        </div>
        <ul className="small muted" style={{ margin: 0, paddingLeft: 18 }}>
          <li>At least 10 characters, no spaces</li>
          <li>Letters and digits both</li>
          <li>Not a common password</li>
        </ul>
        {error && <div className="evidence evidence--gold"><div>{error}</div></div>}
        {done && (
          <div className="small" style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--brand-green)", fontWeight: 600 }}>
            <CheckCircle2 size={14} /> Password changed. Use the new one next time you sign in.
          </div>
        )}
      </div>
      <div className="card__foot" style={{ justifyContent: "flex-end" }}>
        <button type="submit" className="btn btn--blue" disabled={busy}>{busy ? "Saving…" : "Save password"}</button>
      </div>
    </form>
  );
}
