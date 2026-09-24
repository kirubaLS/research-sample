"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { AlertCircle, ArrowRight, CircleCheck, Clock3, Eye, EyeOff, IdCard, Lock, ShieldCheck, Sparkles } from "lucide-react";
import { Mascot, Wordmark } from "@/components/Mascot";
import { EASE_OUT } from "@/components/motion";
import { academicYear, school } from "@/lib/avai-mock-data";
import { DEMO_PASSWORD, demoLogins, onboardingCohort, resolveAttendLogin, startAttend, useAttend } from "@/lib/attendState";

const PROMISES: Array<{ icon: typeof Clock3; text: string }> = [
  { icon: Clock3, text: "About 6 minutes" },
  { icon: ShieldCheck, text: "No marks, no ranking" },
  { icon: Sparkles, text: "Your teacher builds on it" },
];

/**
 * §A1 Attend, the first screen of the whole product. A student opens the
 * school link, types the ID printed on their slip, and starts onboarding.
 * Credentials resolve against the real roster; nothing leaves the browser.
 */
export default function AttendEntryPage() {
  const router = useRouter();
  const { identity, submitted } = useAttend();
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<{ field: "loginId" | "password"; message: string } | null>(null);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const result = resolveAttendLogin(loginId, password);
    if (!result.ok) {
      setError({ field: result.field, message: result.message });
      return;
    }
    setError(null);
    startAttend(result.identity);
    router.push("/attend/onboarding");
  }

  function fillDemo(id: string) {
    setLoginId(id);
    setPassword(DEMO_PASSWORD);
    setError(null);
  }

  return (
    <div className="auth">
      <section className="auth__aside">
        <div style={{ display: "flex", alignItems: "center", gap: 12, position: "relative", zIndex: 1 }}>
          <Wordmark height={40} onDark />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: EASE_OUT }}
          style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", gap: 20, alignItems: "flex-start" }}
        >
          <Mascot pose="hello" size={168} float />
          <h1
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "clamp(28px, 3.4vw, 42px)",
              fontWeight: 500,
              lineHeight: 1.14,
              maxWidth: 480,
            }}
          >
            Hi! Before your first test, tell us who you are.
          </h1>
          <p style={{ color: "#b9c6ce", fontSize: 15.5, lineHeight: 1.55, maxWidth: 430 }}>
            Every student in Class X does this once. It takes a few minutes and there is nothing to revise, AVAI just needs to
            know how you learn before it starts reading your papers.
          </p>

          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {PROMISES.map((p, i) => (
              <motion.span
                key={p.text}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.32 + i * 0.08, ease: EASE_OUT }}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 7,
                  padding: "6px 12px",
                  borderRadius: 999,
                  fontSize: 12,
                  fontWeight: 600,
                  color: "#dbe6ec",
                  background: "rgba(255,255,255,.08)",
                  border: "1px solid rgba(255,255,255,.14)",
                  backdropFilter: "blur(8px)",
                  WebkitBackdropFilter: "blur(8px)",
                }}
              >
                <p.icon size={13} />
                {p.text}
              </motion.span>
            ))}
          </div>
        </motion.div>

        <div style={{ position: "relative", zIndex: 1, color: "#8b99a3", fontSize: 12.5 }}>
          {school.name} · Class X · {academicYear} · {onboardingCohort} students onboarding
        </div>
      </section>

      <section className="auth__panel">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: EASE_OUT }}
          style={{ display: "flex", flexDirection: "column", gap: 18 }}
        >
          <div>
            <h2 style={{ fontSize: 23 }}>
              Start your <span className="gradient-text">onboarding</span>
            </h2>
            <p className="muted small" style={{ marginTop: 4 }}>
              Use the student ID and password on the slip your class teacher gave you.
            </p>
          </div>

          {identity && (
            <Link
              href="/attend/onboarding"
              className="surface surface--tinted hoverlift"
              style={
                {
                  "--accent": "var(--brand-green)",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "13px 15px",
                  textDecoration: "none",
                  color: "inherit",
                } as React.CSSProperties
              }
            >
              {submitted ? (
                <CircleCheck size={18} style={{ color: "var(--brand-green)", flex: "0 0 auto" }} />
              ) : (
                <span className="pulse-dot" style={{ "--accent": "var(--brand-green)" } as React.CSSProperties} />
              )}
              <span style={{ minWidth: 0 }}>
                <strong style={{ display: "block", fontSize: 13.5, fontWeight: 650 }}>
                  {submitted ? "Onboarding already done, see your summary" : "Continue where you left off"}
                </strong>
                <small className="muted" style={{ display: "block", fontSize: 12 }}>
                  {identity.name} · {identity.section} · Roll {identity.rollNo}
                </small>
              </span>
              <ArrowRight size={17} style={{ marginLeft: "auto", color: "var(--brand-green)", flex: "0 0 auto" }} />
            </Link>
          )}

          <form className="login__form" onSubmit={onSubmit} noValidate>
            <div className="field">
              <label htmlFor="attendId">Student ID</label>
              <div style={{ position: "relative" }}>
                <IdCard size={15} style={{ position: "absolute", left: 11, top: 12, color: "var(--muted)" }} />
                <input
                  id="attendId"
                  className="input"
                  style={{ paddingLeft: 34, letterSpacing: ".06em", fontWeight: 600 }}
                  placeholder="AVAI-XA-01"
                  autoComplete="off"
                  autoCapitalize="characters"
                  spellCheck={false}
                  aria-invalid={error?.field === "loginId"}
                  aria-describedby={error?.field === "loginId" ? "attendError" : undefined}
                  value={loginId}
                  onChange={(e) => {
                    setLoginId(e.target.value);
                    setError(null);
                  }}
                />
              </div>
            </div>

            <div className="field">
              <label htmlFor="attendPassword">Password</label>
              <div style={{ position: "relative" }}>
                <Lock size={15} style={{ position: "absolute", left: 11, top: 12, color: "var(--muted)" }} />
                <input
                  id="attendPassword"
                  className="input"
                  style={{ paddingLeft: 34, paddingRight: 42 }}
                  type={showPassword ? "text" : "password"}
                  placeholder="The password on your slip"
                  autoComplete="off"
                  aria-invalid={error?.field === "password"}
                  aria-describedby={error?.field === "password" ? "attendError" : undefined}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setError(null);
                  }}
                />
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  style={{ position: "absolute", right: 5, top: 5, padding: 6 }}
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            {error && (
              <motion.div
                id="attendError"
                role="alert"
                className="evidence"
                style={{ background: "var(--risk-soft)", borderColor: "#eec2b9", color: "#8c2a1c" }}
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.28, ease: EASE_OUT }}
              >
                <AlertCircle size={16} />
                <div>{error.message}</div>
              </motion.div>
            )}

            <motion.button
              type="submit"
              className="btn btn--primary"
              style={{ justifyContent: "center", padding: "12px 14px", fontSize: 14.5 }}
              whileHover={{ y: -2 }}
              whileTap={{ y: 0 }}
            >
              Start onboarding <ArrowRight size={16} />
            </motion.button>
          </form>

          <div className="surface" style={{ padding: 14, background: "linear-gradient(180deg, #ffffff, #faf7f1)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 4 }}>
              <span className="tag tag--dev">DEMO</span>
              <strong style={{ fontSize: 13, fontWeight: 650 }}>Working student logins</strong>
            </div>
            <p className="muted small" style={{ marginBottom: 10 }}>
              Any roll in any section works, <b>AVAI-XA-01</b> through <b>AVAI-XE-48</b>. Password for everyone in the demo is{" "}
              <b>{DEMO_PASSWORD}</b>.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              {demoLogins.map((d, i) => (
                <motion.button
                  key={d.loginId}
                  type="button"
                  onClick={() => fillDemo(d.loginId)}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: 0.05 + i * 0.05, ease: EASE_OUT }}
                  whileHover={{ y: -2 }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 11,
                    width: "100%",
                    textAlign: "left",
                    padding: "9px 11px",
                    borderRadius: "var(--radius-md)",
                    border: "1px solid var(--line)",
                    background: "linear-gradient(180deg, #ffffff, #fdfbf7)",
                    boxShadow: "var(--shadow-xs)",
                    font: "inherit",
                    color: "inherit",
                    cursor: "pointer",
                  }}
                >
                  <span
                    className="mono"
                    style={{ fontSize: 12.5, fontWeight: 700, color: "var(--brand-teal)", letterSpacing: ".04em" }}
                  >
                    {d.loginId}
                  </span>
                  <span className="muted" style={{ fontSize: 12, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {d.name} · {d.section}
                  </span>
                  <ArrowRight size={14} style={{ marginLeft: "auto", color: "var(--muted)", flex: "0 0 auto" }} />
                </motion.button>
              ))}
            </div>
          </div>

          <div className="login__help">
            Teacher or principal? <Link href="/login" className="btn--link">Staff sign-in is here</Link>.
          </div>
        </motion.div>
      </section>
    </div>
  );
}
