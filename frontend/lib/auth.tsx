"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  mockPrincipal,
  mockStudentUser,
  mockTeachers,
  type Role,
  type TeacherAssignment,
} from "./avai-mock-data";
import "./opsDirectory";

/**
 * Mock auth. 🔧 BACKEND REQUIRED, this is a dev-only role switcher, not real
 * sign-in. The "current user" lives in React state and is mirrored to
 * localStorage so reloads keep the chosen shell.
 */

export type CurrentUser =
  | { role: "principal"; id: string; name: string }
  | { role: "teacher"; id: string; name: string; assignments: TeacherAssignment[]; examsOnly?: boolean }
  | { role: "student"; id: string; name: string; rollNo: string; section: string };

interface AuthState {
  user: CurrentUser | null;
  ready: boolean;
  signIn: (role: Role, userId: string) => CurrentUser | null;
  signOut: () => void;
}

const STORAGE_KEY = "avai.devUser";

const AuthContext = createContext<AuthState | null>(null);

export function resolveUser(role: Role, userId: string): CurrentUser | null {
  if (role === "principal") return { role, id: mockPrincipal.id, name: mockPrincipal.name };
  if (role === "teacher") {
    const t = mockTeachers.find((x) => x.id === userId);
    return t ? { role, id: t.id, name: t.name, assignments: t.assignments, examsOnly: t.examsOnly } : null;
  }
  if (role === "student") return { role, ...mockStudentUser };
  return null;
}

export function homeFor(user: CurrentUser | Role) {
  const role = typeof user === "string" ? user : user.role;
  if (role === "teacher" && typeof user !== "string" && user.role === "teacher" && user.examsOnly) return "/teacher/papers";
  // Students never sign in, their only visit is the onboarding assessment.
  return role === "principal" ? "/principal/classes" : role === "teacher" ? "/teacher/home" : "/attend";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const { role, id } = JSON.parse(raw) as { role: Role; id: string };
        setUser(resolveUser(role, id));
      }
    } catch {
      /* storage unavailable, stay signed out */
    }
    setReady(true);
  }, []);

  const signIn = useCallback((role: Role, userId: string) => {
    const u = resolveUser(role, userId);
    setUser(u);
    try {
      if (u) window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ role: u.role, id: u.id }));
    } catch {}
    return u;
  }, []);

  const signOut = useCallback(() => {
    setUser(null);
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {}
  }, []);

  const value = useMemo(() => ({ user, ready, signIn, signOut }), [user, ready, signIn, signOut]);
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
