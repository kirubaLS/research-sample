"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight, CircleCheck, Clock3, School as SchoolIcon, ShieldCheck, Sparkles } from "lucide-react";
import { Mascot, Wordmark } from "@/components/Mascot";
import { EASE_OUT } from "@/components/motion";
import { api, ClassOption } from "@/lib/api";
import { pickClass, useAttend } from "@/lib/attendState";

const PROMISES: Array<{ icon: typeof Clock3; text: string }> = [
  { icon: Clock3, text: "About five minutes" },
  { icon: ShieldCheck, text: "No right or wrong answers" },
  { icon: Sparkles, text: "Your teacher builds on it" },
];

/**
 * §A1 Attend, the first screen of the whole product. Real: GET /t/classes
 * lists every class whose school has not hidden it from the public
 * directory, and a class code is not a secret -- there is no student
 * ID+password login to start the interest test (the reference design's
 * demo ID/password form and its "AVAI-XA-01" slip has no backend
 * counterpart at all). A student just taps their class and continues to
 * /attend/onboarding, which asks for their name and roll number itself.
 */
export default function AttendEntryPage() {
  const router = useRouter();
  const { classCode, classLabel, answers, submitted } = useAttend();
  const [classes, setClasses] = useState<ClassOption[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .classes()
      .then(setClasses)
      .catch(() => setError("Could not reach the server. Check your connection and reload."));
  }, []);

  const schools = new Map<string, ClassOption[]>();
  for (const c of classes ?? []) {
    schools.set(c.school, [...(schools.get(c.school) ?? []), c]);
  }

  function choose(option: ClassOption) {
    pickClass(option);
    router.push("/attend/onboarding");
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
            Six short steps, about five minutes. There is nothing to revise, AVAI just needs to know a bit about you
            before it starts reading your papers.
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
              Find your <span className="gradient-text">class</span>
            </h2>
            <p className="muted small" style={{ marginTop: 4 }}>
              No login. Tap your class below and start straight away.
            </p>
          </div>

          {classCode && (
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
                  {classLabel}{answers.name ? ` · ${answers.name}` : ""}
                </small>
              </span>
              <ArrowRight size={17} style={{ marginLeft: "auto", color: "var(--brand-green)", flex: "0 0 auto" }} />
            </Link>
          )}

          {error && (
            <div className="evidence evidence--gold">
              <div>{error}</div>
            </div>
          )}
          {!classes && !error && <p className="muted small">Loading classes…</p>}
          {classes?.length === 0 && (
            <div className="evidence evidence--neutral">No classes have been set up yet. Ask your teacher for the class link.</div>
          )}

          {[...schools.entries()].map(([school, options]) => (
            <div key={school}>
              <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 10 }}>
                <SchoolIcon size={14} className="muted" />
                <h3 className="section-q" style={{ fontSize: 14 }}>{school}</h3>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {options.map((option) => (
                  <button
                    key={option.class_code}
                    type="button"
                    className="card card--hover"
                    style={{ width: "100%", textAlign: "left", font: "inherit", color: "inherit", cursor: "pointer" }}
                    onClick={() => choose(option)}
                  >
                    <div className="card__body" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                      <span style={{ fontSize: 15, fontWeight: 650 }}>{option.label}</span>
                      <span className="btn--link">Start →</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))}

          <div className="login__help">
            Teacher or principal? <Link href="/login" className="btn--link">Staff sign-in is here</Link>.
          </div>
        </motion.div>
      </section>
    </div>
  );
}
