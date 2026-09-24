"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import Link from "next/link";
import { Mascot } from "@/components/Mascot";
import {
  clearActiveSchool,
  getApiKey,
  getSchoolName,
  setActiveSchool,
  setRole,
  signOut,
  signOutPlatform,
  type StaffRole,
} from "@/lib/session";

/** A principal's key never opens the operator console, no matter what this same browser
 * signed into earlier -- a stale platform key from a prior operator session must not
 * carry forward onto a principal's own sign-in. */
function forgetPlatformAccessUnlessAdmin(role: string): void {
  if (role !== "admin") signOutPlatform();
}

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
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [staff, setStaff] = useState<StaffRole | null>(null);
  const [needsSchool, setNeedsSchool] = useState(false);
  const [stale, setStale] = useState<string | null>(null);
  const [school, setSchool] = useState<string | null>(null);
  // Set the moment a teacher key is caught here, so the sibling "not signed in -> /login"
  // effect below (keyed on the same ready/signedIn state) doesn't also fire and race the
  // /teacher redirect -- both would otherwise see ready=true, signedIn=false.
  const [redirectingRole, setRedirectingRole] = useState(false);

  useEffect(() => {
    const key = getApiKey();
    if (!key) {
      setReady(true);
      return;
    }
    api
      .whoami(key)
      .then((me) => {
        // /admin is the principal/school-admin dashboard -- BoardX, Manage Teachers,
        // Settings, the full roster. A teacher key resolving here (a stale session from
        // before the teacher role existed, a bookmarked URL, the back button) must not
        // render any of that; it gets exactly the same "which shell for this role" send-off
        // /login already gives a fresh sign-in.
        if (me.role === "teacher") {
          setRedirectingRole(true);
          router.replace("/teacher/home");
          return;
        }
        setSchool(me.name);
        setStaff({ role: me.role, can: me.can, scope: me.scope });
        setRole({ role: me.role, can: me.can, scope: me.scope });
        forgetPlatformAccessUnlessAdmin(me.role);
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

  // Not signed in: there is exactly one sign-in screen in the product, /login (§4 of the
  // brand spec -- "School Staff"/"Student" tabs). This component used to render a second,
  // differently-styled form of its own right here, which is the duplicate-login confusion
  // reported live -- landing on /admin with no session now hands off to /login instead of
  // drawing a competing form.
  useEffect(() => {
    if (ready && !signedIn && !redirectingRole) router.replace("/login");
  }, [ready, signedIn, redirectingRole, router]);

  if (!ready || !signedIn) {
    return (
      <main className="narrow">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={28} />
          <p className="muted" style={{ margin: 0 }}>
            {ready ? "Taking you to the right place…" : "Checking your session…"}
          </p>
        </div>
      </main>
    );
  }

  return (
    <>
      {staff?.scope === "all_schools" && !needsSchool && (
        <div style={{ display: "flex", justifyContent: "flex-end", padding: "10px 22px 0" }}>
          <button
            className="btn btn--ghost btn--sm"
            onClick={() => {
              clearActiveSchool();
              setNeedsSchool(true);
            }}
          >
            Switch school
          </button>
        </div>
      )}
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
          border: 1px solid var(--rule, #e3e3e6);
          cursor: pointer;
          animation: rise-in 0.4s var(--ease, ease) both;
        }
        .schoolpick:hover {
          border-color: var(--mark-2, #16324f);
          transform: translateY(-2px);
          box-shadow: var(--shadow);
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