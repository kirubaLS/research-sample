"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Clock3, School as SchoolIcon, ShieldCheck, Sparkles } from "lucide-react";
import { api, ClassOption } from "@/lib/api";
import { GrowthIllustration } from "@/components/GrowthIllustration";

const EASE_OUT = [0.22, 0.68, 0.36, 1] as const;

const PROMISES = [
  { icon: Clock3, text: "About eight minutes" },
  { icon: ShieldCheck, text: "No right or wrong answers" },
  { icon: Sparkles, text: "Your teacher builds on it" },
];

/**
 * The student front door -- structurally adapted from the reference design's
 * /attend entry screen (split hero + promise chips), but this app has no student
 * login step: a class code is not a secret, so classes are listed here and each
 * one is a real link straight to /t/[classCode] instead of an ID+password form.
 */
export default function ClassPicker() {
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

  return (
    <div className="auth">
      <section className="auth__aside">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: EASE_OUT }}
          style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", gap: 20, alignItems: "flex-start" }}
        >
          <div style={{ maxWidth: 220 }}>
            <GrowthIllustration />
          </div>
          <h1
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "clamp(26px, 3vw, 38px)",
              fontWeight: 500,
              lineHeight: 1.18,
              maxWidth: 440,
            }}
          >
            Tap your class to begin.
          </h1>
          <p style={{ color: "#b9c6ce", fontSize: 15, lineHeight: 1.55, maxWidth: 420 }}>
            36 short questions, in English, தமிழ் or हिन्दी. There is nothing to revise.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {PROMISES.map((p, i) => (
              <motion.span
                key={p.text}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.28 + i * 0.08, ease: EASE_OUT }}
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
        <div style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 620 }}>
          <div>
            <p className="eyebrow">Interest test</p>
            <h2 style={{ fontSize: 23, marginTop: 4 }}>Find your class</h2>
            <p className="muted small" style={{ marginTop: 4 }}>
              No login. Pick your class below and start straight away.
            </p>
          </div>

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
                <h3 className="section-q" style={{ fontSize: 14 }}>
                  {school}
                </h3>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {options.map((option) => (
                  <Link key={option.class_code} href={`/t/${option.class_code}`} className="card card--hover">
                    <div className="card__body" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                      <span style={{ fontSize: 15, fontWeight: 650 }}>{option.label}</span>
                      <span className="btn--link">Start →</span>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          ))}

          <div className="login__help">
            Teacher or principal? <Link href="/login" className="btn--link">Staff sign-in is here</Link>.
          </div>
        </div>
      </section>
    </div>
  );
}
