"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  clearActiveSchool,
  getApiKey,
  getRole,
  getSchoolName,
  signOut as sessionSignOut,
  type StaffRole,
  type TeacherAssignment,
} from "@/lib/session";

/**
 * Real auth, backed by lib/session.ts (which app/login/page.tsx already writes to with a
 * real api.whoami() call). This replaces the wholesale clone's dev-only role switcher:
 * there is no more signIn()/mock user table here, only a read of whatever the real sign-in
 * already stored. `ready` flips true once localStorage has been checked (client-only), so
 * a route guard never has to guess whether "no user yet" means "signed out" or "still
 * reading storage".
 */

export type CurrentUser =
  | { role: "principal"; id: string; name: string }
  | { role: "admin"; id: string; name: string }
  | {
      role: "teacher";
      id: string;
      name: string;
      assignments: TeacherAssignment[];
      can: StaffRole["can"];
      /** The exam cell: papers-and-marks rights across every subject, no teaching
       * assignment of their own -- StaffRole.exam_cell, the server's own fact. */
      examsOnly: boolean;
    };

interface AuthState {
  user: CurrentUser | null;
  ready: boolean;
  signOut: () => void;
  /** Re-reads the signed-in session from storage. AuthProvider only reads it once, on
   * first mount -- a client-side route change (router.push, no reload) after signing in
   * never remounts it, so without this the freshly-written key/role never reaches `user`
   * and RoleGuard bounces straight back to /login, seeing a still-null user. login/page.tsx
   * calls this right after writing the session, before navigating away. */
  refresh: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

function readUser(): CurrentUser | null {
  const key = getApiKey();
  const role = getRole();
  if (!key || !role) return null;
  const name = getSchoolName() || "";
  if (role.role === "teacher") {
    const assignments = role.assignments ?? [];
    return {
      role: "teacher",
      id: key,
      name,
      assignments,
      can: role.can,
      examsOnly: role.exam_cell === true,
    };
  }
  // A principal key resolves server-side two different real ways: a per-person key
  // stored with role "principal", or the legacy school-wide api_key, which the backend
  // always resolves as role "admin" scoped to one school (deps.py's current_staff, the
  // School.api_key branch) -- both are a real principal, not a true cross-school operator,
  // which only ever has scope "all_schools". Treating only the literal "principal" string
  // as a principal was the bug: a school's own api_key -- very possibly what was just
  // tested -- resolved as role "admin" and got stuck outside RoleGuard's "principal" gate
  // forever, with no error, because nothing there was wrong enough to reject outright.
  if (role.role === "principal" || (role.role === "admin" && role.scope === "one_school")) {
    return { role: "principal", id: key, name };
  }
  return { role: "admin", id: key, name };
}

/** Where a signed-in user's home page is. */
export function homeFor(user: CurrentUser | CurrentUser["role"]) {
  const role = typeof user === "string" ? user : user.role;
  if (role === "teacher" && typeof user !== "string" && user.role === "teacher" && user.examsOnly) return "/teacher/papers";
  return role === "teacher" ? "/teacher/home" : "/principal/classes";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setUser(readUser());
    setReady(true);
  }, []);

  const signOut = () => {
    sessionSignOut();
    clearActiveSchool();
    setUser(null);
  };

  const refresh = () => setUser(readUser());

  const value = useMemo(() => ({ user, ready, signOut, refresh }), [user, ready]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

export function initials(name: string) {
  return name
    .replace(/^(Mrs?|Ms|Dr)\.\s*/i, "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}
