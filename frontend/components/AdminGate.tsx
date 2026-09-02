"use client";

import { useEffect, useState } from "react";
import { api, ApiError, apiBaseIsDefault, ApiUnreachable } from "@/lib/api";
import Link from "next/link";
import {
  clearActiveSchool,
  getActiveSchool,
  getApiKey,
  getSchoolName,
  setActiveSchool,
  setApiKey,
  setRole,
  signOut,
  type StaffRole,
} from "@/lib/session";

/** Used only while an admin has not yet named a school; /admin/me replaces it after. */
const ADMIN_CAN = {
  read_results: true,
  scan_papers: true,
  enter_marks: true,
  manage_roster: true,
  manage_schools: true,
};

/**
 * The dashboard's sign-in.
 *
 * A school key, validated against /admin/me and held in the browser. Students never see
 * this — they arrive on a class link and have no account at all.
 */
export function AdminGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [staff, setStaff] = useState<StaffRole | null>(null);
  const [needsSchool, setNeedsSchool] = useState(false);
  const [stale, setStale] = useState<string | null>(null);
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
        setStaff({ role: me.role, can: me.can, scope: me.scope });
        setRole({ role: me.role, can: me.can, scope: me.scope });
        setSignedIn(true);
      })
      .catch((err) => {
        // 400 means the key works but belongs to no school: an admin who has not picked
        // one yet, or whose stored choice was deleted. Signing them out would be wrong.
        if (err instanceof ApiError && err.status === 400) {
          clearActiveSchool();
          setNeedsSchool(true);
          setSignedIn(true);
          setStaff({ role: "admin", scope: "all_schools", can: ADMIN_CAN });
          setRole({ role: "admin", scope: "all_schools", can: ADMIN_CAN });
          return;
        }
        // Only a rejected key signs anyone out. A server still starting, or a network
        // that dropped, is not a reason to throw away a session and make a teacher find
        // their key again -- they will simply see the error and can retry.
        if (err instanceof ApiError && err.status === 404) {
          signOut();
          return;
        }
        setStale(
          "Could not check your session just now. Reload in a moment; you are still signed in.",
        );
        setSignedIn(true);
      })
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
      setRole({ role: me.role, can: me.can, scope: me.scope });
      setStaff({ role: me.role, can: me.can, scope: me.scope });
      setSchool(me.name);
      setSignedIn(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        // An admin key. It is valid; it just has not said which school yet.
        setApiKey(key, "");
        clearActiveSchool();
        setStaff({ role: "admin", scope: "all_schools", can: ADMIN_CAN });
        setRole({ role: "admin", scope: "all_schools", can: ADMIN_CAN });
        setNeedsSchool(true);
        setSignedIn(true);
        setBusy(false);
        return;
      }
      setError(
        err instanceof ApiUnreachable
          ? "Could not reach the server. It may be starting up, or this site may be pointed at the wrong address. Try again in a minute, and tell whoever set up this deployment if it keeps happening."
          : err instanceof ApiError && err.status === 404
            ? "That key was not recognised. This box takes a school's own key, which is not the same as the key that runs the deployment."
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
            The dashboard is for school staff. Students do not sign in; they open the class
            link their teacher gives them.
          </p>
        </div>

        {apiBaseIsDefault() && (
          <div className="notice warn" style={{ marginTop: 18 }}>
            This site has not been told where its server is, so it is asking your own
            computer and nothing will load. Whoever set up this deployment needs to point
            it at the server and publish it again. Restarting will not fix it on its own.
          </div>
        )}

        <form onSubmit={submit} className="card" style={{ marginTop: 22 }}>
          <div className="field">
            <label htmlFor="key">Your key</label>
            <input
              id="key"
              name="key"
              type="password"
              autoComplete="current-password"
              placeholder="zozx6r94sEf1KWs7fRdXTNJNYXKEteuW"
              required
            />
            <p className="hint">
              A <strong>school&rsquo;s</strong> key, one per school, held by the principal.
              If it has been lost, a new one can be issued, and the old one stops working
              the moment it is.
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
        className="accountbar"
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
          {[needsSchool ? null : (school ?? getSchoolName()) || null,
            staff ? (staff.role === "admin" ? "Admin" : "Principal") : null]
            .filter(Boolean)
            .join(" · ")}
        </span>
        {staff?.scope === "all_schools" && !needsSchool && (
          <button
            className="secondary tiny"
            onClick={() => {
              clearActiveSchool();
              setNeedsSchool(true);
            }}
          >
            Switch school
          </button>
        )}
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
      <style jsx global>{`
        @media print {
          .accountbar {
            display: none !important;
          }
        }
      `}</style>
      {stale && (
        <p className="notice warn" style={{ maxWidth: "var(--max)", margin: "0 auto 12px" }}>
          {stale}
        </p>
      )}
      {needsSchool ? (
        <SchoolPicker
          onPick={(id) => {
            setActiveSchool(id);
            // A full reload, not a state flip: every screen already mounted has data for
            // no school or the previous one, and a half-switched dashboard is how someone
            // reads one school's numbers under another school's name.
            window.location.reload();
          }}
        />
      ) : (
        children
      )}
    </>
  );
}


/**
 * Which school an admin is acting on.
 *
 * There is no default and no "most recent" fallback. An admin key belongs to no school,
 * and a dashboard that quietly picked one would show a real school's numbers under a
 * heading nobody chose -- the API refuses to guess for exactly the same reason.
 */
function SchoolPicker({ onPick }: { onPick: (id: string) => void }) {
  const [schools, setSchools] = useState<{ id: string; name: string; students: number }[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .listSchools(key)
      .then((rows) => setSchools(rows.map((r) => ({ id: r.id, name: r.name, students: r.students }))))
      .catch(() => setError("Could not load the list of schools."));
  }, []);

  return (
    <main className="narrow">
      <div className="hero">
        <p className="eyebrow">Admin</p>
        <h1>Which school?</h1>
        <p className="lede">
          Your key works across every school on this deployment, so nothing is loaded until
          you say which one. You can switch at any time from the bar above.
        </p>
      </div>

      {error && <p className="error">{error}</p>}
      {!error && schools.length === 0 && <p className="muted">Loading schools…</p>}

      <div className="stack" style={{ gap: 10, marginTop: 18 }}>
        {schools.map((s) => (
          <button
            key={s.id}
            className="card schoolpick"
            onClick={() => onPick(s.id)}
            type="button"
          >
            <span className="schoolname">{s.name}</span>
            <span className="cardnote">
              {s.students} student{s.students === 1 ? "" : "s"}
            </span>
          </button>
        ))}
      </div>

      <p className="small muted" style={{ marginTop: 18 }}>
        Creating a school, loading a book or issuing a key happens in the{" "}
        <Link href="/platform">console</Link>.
      </p>

      <style jsx>{`
        .schoolpick {
          display: block;
          width: 100%;
          text-align: left;
          background: var(--surface, #fff);
          color: inherit;
          border: 1px solid var(--line, #e3e3e6);
          cursor: pointer;
        }
        .schoolpick:hover {
          border-color: var(--ink, #16324f);
        }
        .schoolname {
          display: block;
          font-size: 19px;
          font-weight: 600;
          color: var(--ink, #16324f);
        }
        .cardnote {
          display: block;
          margin-top: 4px;
        }
      `}</style>
    </main>
  );
}