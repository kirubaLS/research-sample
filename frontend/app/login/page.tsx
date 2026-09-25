"use client";

/**
 * §4 sign-in -- the reference design's own .auth/.authchoice/.stepper shell (gradient
 * icon tiles, box-shadows, stepper progress bar): step 1 picks Principal vs Teacher,
 * step 2 shows the real sign-in key form (both roles submit the same key; the backend
 * decides which one it is from GET /admin/me's `role`).
 *
 * No student PIN sign-in here -- a student attending an assessment goes through /attend
 * (tap a class, no login), and there is no other student-facing login on this screen.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  Eye,
  EyeOff,
  GraduationCap,
  KeyRound,
  PenLine,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { Mascot, Wordmark } from "@/components/Mascot";
import { EASE_OUT } from "@/components/motion";
import { homeFor, useAuth } from "@/lib/auth";
import { api, ApiError, ApiUnreachable } from "@/lib/api";
import { setApiKey, setRole } from "@/lib/session";

/** "principal" and "teacher" both submit the same single sign-in key (the backend
 * decides the role from the key itself, GET /admin/me), so they share one StaffSignIn
 * form -- this only changes which card and heading led there. */
type Choice = "principal" | "teacher";

const CHOICES: Array<{ choice: Choice; title: string; blurb: string; accent: string; icon: typeof GraduationCap }> = [
  {
    choice: "principal",
    title: "Principal sign-in",
    blurb: "For the school principal.",
    accent: "var(--brand-teal)",
    icon: Building2,
  },
  {
    choice: "teacher",
    title: "Teacher sign-in",
    blurb: "Your classes and your subjects, with the findings that matter.",
    accent: "var(--brand-blue)",
    icon: GraduationCap,
  },
];

function explainStaff(err: unknown): string {
  return err instanceof ApiUnreachable
    ? "Could not reach the server. Try again in a minute."
    : "That key was not recognised. Check it and try again.";
}

export default function LoginPage() {
  const [choice, setChoice] = useState<Choice | null>(null);

  const chosen = CHOICES.find((c) => c.choice === choice) ?? null;

  return (
    <div className="auth">
      <section className="auth__aside" style={{ alignItems: "center", justifyContent: "center", textAlign: "center" }}>
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: EASE_OUT }}
          style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", gap: 20, alignItems: "center" }}
        >
          <Wordmark height={52} onDark />

          <Mascot pose="hello" size={170} float />

          <h1
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "clamp(24px, 2.8vw, 34px)",
              fontWeight: 500,
              lineHeight: 1.25,
              maxWidth: 380,
            }}
          >
            Every opportunity belongs to every student.
          </h1>
        </motion.div>
      </section>

      <section className="auth__panel">
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="stepper" aria-hidden="true">
            <div className="stepper__bar" style={{ "--progress": choice ? "75%" : "25%" } as React.CSSProperties} />
            <div className="stepper__step" data-state={choice ? "done" : "current"}>
              <span className="stepper__dot">1</span>
              Who are you
            </div>
            <div className="stepper__step" data-state={choice ? "current" : "todo"}>
              <span className="stepper__dot">2</span>
              Sign in
            </div>
          </div>

          <AnimatePresence mode="wait" initial={false}>
            {!chosen ? (
              <motion.div
                key="choose"
                initial={{ opacity: 0, x: -14 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -14 }}
                transition={{ duration: 0.32, ease: EASE_OUT }}
                style={{ display: "flex", flexDirection: "column", gap: 16 }}
              >
                <div>
                  <h2 style={{ fontSize: 23 }}>
                    Sign in to <span className="gradient-text">AVAI</span>
                  </h2>
                  <p className="muted small" style={{ marginTop: 4 }}>
                    Pick the one that&rsquo;s you: the sign-in fields are different for each.
                  </p>
                </div>

                <div className="authchoice-list">
                  {CHOICES.map((c, i) => {
                    const Icon = c.icon;
                    return (
                      <motion.button
                        key={c.choice}
                        type="button"
                        className="authchoice"
                        style={{ "--accent": c.accent } as React.CSSProperties}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4, delay: 0.06 + i * 0.08, ease: EASE_OUT }}
                        onClick={() => setChoice(c.choice)}
                      >
                        <span className="authchoice__icon">
                          <Icon size={21} />
                        </span>
                        <div>
                          <strong>{c.title}</strong>
                          <small>{c.blurb}</small>
                        </div>
                        <ArrowRight size={17} style={{ marginLeft: "auto", color: "var(--muted)", flex: "0 0 auto" }} />
                      </motion.button>
                    );
                  })}
                </div>

                <div style={{ height: 1, background: "var(--line)", margin: "4px 0" }} />

                <Link
                  href="/attend"
                  className="surface surface--tinted hoverlift"
                  style={
                    {
                      "--accent": "var(--brand-gold)",
                      display: "flex",
                      alignItems: "center",
                      gap: 13,
                      padding: "13px 15px",
                      textDecoration: "none",
                      color: "inherit",
                    } as React.CSSProperties
                  }
                >
                  <span
                    style={{
                      width: 36,
                      height: 36,
                      flex: "0 0 36px",
                      borderRadius: 11,
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "#fff",
                      background: "linear-gradient(160deg, #eab949, var(--brand-gold))",
                      boxShadow: "0 8px 16px -8px rgba(224,166,42,.9), inset 0 1px 0 rgba(255,255,255,.4)",
                    }}
                  >
                    <PenLine size={17} />
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <strong style={{ display: "block", fontSize: 13.5, fontWeight: 650 }}>
                      Attending an AVAI assessment? Start here
                    </strong>
                    <small className="muted" style={{ display: "block", fontSize: 12, lineHeight: 1.35 }}>
                      For students taking the interest test. This is not a staff login.
                    </small>
                  </div>
                  <ArrowRight size={17} style={{ marginLeft: "auto", color: "var(--brand-gold)", flex: "0 0 auto" }} />
                </Link>
              </motion.div>
            ) : (
              <motion.div
                key={chosen.choice}
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 16 }}
                transition={{ duration: 0.32, ease: EASE_OUT }}
                style={{ display: "flex", flexDirection: "column", gap: 16 }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <button type="button" className="btn btn--ghost btn--sm" onClick={() => setChoice(null)} aria-label="Back">
                    <ArrowLeft size={15} />
                  </button>
                  <span
                    className="authchoice__icon"
                    style={{ "--accent": chosen.accent, width: 38, height: 38, flexBasis: 38, borderRadius: 12 } as React.CSSProperties}
                  >
                    <chosen.icon size={18} />
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <h2 style={{ fontSize: 19 }}>{chosen.title}</h2>
                    <p className="muted small">{chosen.blurb}</p>
                  </div>
                </div>

                <StaffSignIn />
              </motion.div>
            )}
          </AnimatePresence>

          <div style={{ height: 1, background: "var(--line)", margin: "2px 0" }} />

          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.2, ease: EASE_OUT }}>
            {chosen && (
              <p className="small muted" style={{ marginBottom: 14 }}>
                Trouble signing in? Ask your school office for your key or PIN.
              </p>
            )}

            <Link
              href="/admin"
              className="small muted"
              style={{ display: "inline-flex", alignItems: "center", gap: 6, textDecoration: "none" }}
            >
              <ShieldCheck size={13} /> AVAI staff console
            </Link>
          </motion.div>
        </div>
      </section>
    </div>
  );
}

function StaffSignIn() {
  const router = useRouter();
  const { refresh } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showKey, setShowKey] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    const key = String(new FormData(event.currentTarget).get("key") ?? "").trim();
    try {
      const me = await api.whoami(key);
      setApiKey(key, me.name);
      setRole({ role: me.role, can: me.can, scope: me.scope, assignments: me.assignments, exam_cell: me.exam_cell });
      // router.push is a client-side route change -- it never remounts the root
      // AuthProvider, so without this its `user` stays whatever it was before sign-in
      // (usually null) and the destination's RoleGuard bounces straight back to /login.
      refresh();
      const examsOnly = me.role === "teacher" && me.exam_cell === true;
      router.push(
        me.role === "teacher"
          ? homeFor({ role: "teacher", id: key, name: me.name, assignments: me.assignments ?? [], can: me.can, examsOnly })
          : "/principal/classes",
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        // Valid admin key, no school picked yet -- let /principal/classes resolve it.
        setApiKey(key, "");
        refresh();
        router.push("/principal/classes");
        return;
      }
      setError(explainStaff(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="login__form" onSubmit={submit}>
      <div className="field">
        <label htmlFor="key">Sign-in key</label>
        <div style={{ position: "relative" }}>
          <KeyRound size={15} style={{ position: "absolute", left: 11, top: 12, color: "var(--muted)" }} />
          <input
            id="key"
            name="key"
            className="input"
            style={{ paddingLeft: 34, paddingRight: 40 }}
            type={showKey ? "text" : "password"}
            autoComplete="current-password"
            required
            placeholder="Your personal AVAI sign-in key"
          />
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => setShowKey((v) => !v)}
            aria-label={showKey ? "Hide sign-in key" : "Show sign-in key"}
            style={{ position: "absolute", right: 5, top: 5, padding: 6 }}
          >
            {showKey ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        </div>
        <p className="small muted">
          The key you were personally issued: a principal&rsquo;s school key, or a teacher&rsquo;s own sign-in key.
        </p>
      </div>

      <button type="submit" className="btn btn--primary" disabled={busy} style={{ justifyContent: "center", padding: 11 }}>
        {busy ? "Checking…" : "Continue"} {!busy && <ArrowRight size={15} />}
      </button>

      {error && (
        <motion.div
          className="evidence evidence--gold"
          role="status"
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: EASE_OUT }}
        >
          <ShieldAlert size={16} />
          <div>{error}</div>
        </motion.div>
      )}
    </form>
  );
}

