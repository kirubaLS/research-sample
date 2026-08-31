"use client";

import { useEffect, useState } from "react";
import { api, ApiError, apiBase, apiBaseIsDefault, ApiUnreachable } from "@/lib/api";
import { usePathname } from "next/navigation";
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

/**
 * Routes an admin key opens and a principal key does not. A principal signs in to read
 * results and progress; producing them -- scanning a paper, entering marks -- is the
 * admin's job and a separate credential.
 *
 * This list only decides what is *offered*. Every one of these screens calls an endpoint
 * the API refuses to a principal anyway, so a stale browser cannot become a way in.
 */
const ADMIN_ONLY = ["/admin/paper", "/admin/answers", "/admin/scan"];

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
  const pathname = usePathname() ?? "";
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [staff, setStaff] = useState<StaffRole | null>(null);
  const [needsSchool, setNeedsSchool] = useState(false);
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
          return;
        }
        signOut();
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
        setNeedsSchool(true);
        setSignedIn(true);
        setBusy(false);
        return;
      }
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
              One key per person. A principal&rsquo;s key reads their own school; an
              admin&rsquo;s works across every school and is asked which one on the way in.
              Both are issued in the console at{" "}
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
      {needsSchool ? (
        <SchoolPicker
          onPick={(id) => {
            setActiveSchool(id);
            // A full reload, not a state flip: every screen already mounted has data for
            // no school or the previous one, and a half-switched dashboard is how someone
            // reads Bharath's numbers under another school's name.
            window.location.reload();
          }}
        />
      ) : blocked ? (
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
          <button key={s.id} className="card" style={{ textAlign: "left" }} onClick={() => onPick(s.id)}>
            <h3 style={{ margin: 0 }}>{s.name}</h3>
            <p className="cardnote" style={{ margin: "4px 0 0" }}>
              {s.students} student{s.students === 1 ? "" : "s"}
            </p>
          </button>
        ))}
      </div>

      <p className="small muted" style={{ marginTop: 18 }}>
        Creating a school, loading a book or issuing a key happens in the{" "}
        <Link href="/platform">console</Link>.
      </p>
    </main>
  );
}