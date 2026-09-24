"use client";

import { motion } from "framer-motion";
import { FileText, PartyPopper } from "lucide-react";
import { Mascot } from "@/components/Mascot";
import { EASE_OUT, Reveal } from "@/components/motion";
import type { AttendDraft } from "@/lib/attendState";

/** Final screen, after POST /t/session/{id}/complete answers. The reference
 * design's summary echoed back a whole fake profile (background, learning
 * style, future plans); the real payload carries only what the student
 * typed on the profile step plus how many of the 36 items were answered, so
 * that is all this screen can honestly show. */
export function StepDone({ draft }: { draft: AttendDraft }) {
  const profile = draft.profile;
  if (!profile) return null;
  const first = profile.name.split(" ")[0];
  const answered = Object.keys(draft.answers).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <motion.div
        className="surface surface--raised"
        initial={{ opacity: 0, y: 14, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: EASE_OUT }}
        style={{
          padding: "clamp(22px, 5vw, 32px) clamp(18px, 4vw, 28px)",
          display: "flex",
          alignItems: "center",
          gap: "clamp(14px, 4vw, 26px)",
          flexWrap: "wrap",
          background:
            "radial-gradient(520px 320px at 88% -10%, rgba(58,157,106,.16), transparent 66%), radial-gradient(420px 300px at -6% 110%, rgba(224,166,42,.16), transparent 64%), linear-gradient(180deg, #ffffff, #fdfbf7)",
        }}
      >
        <Mascot pose="achieve" size={132} float />
        <div style={{ minWidth: 200, flex: "1 1 240px" }}>
          <span className="tag tag--green" style={{ marginBottom: 8 }}>
            <PartyPopper size={12} /> Onboarding complete
          </span>
          <h2 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(25px, 6vw, 34px)", fontWeight: 500, lineHeight: 1.15 }}>
            You&apos;re all set, {first}.
          </h2>
          <p className="muted" style={{ fontSize: 14, lineHeight: 1.5, marginTop: 7 }}>
            You can close this page, you won&apos;t have to do it again.
          </p>
        </div>
      </motion.div>

      <Reveal delay={0.12}>
        <div className="surface" style={{ padding: "clamp(16px, 4vw, 22px) clamp(16px, 4vw, 24px)" }}>
          <div className="eyebrow" style={{ marginBottom: 6 }}>
            What was sent
          </div>
          <div>
            {(
              [
                ["Name", `${profile.name} · Section ${profile.section} · Roll ${profile.roll_no}`],
                ["Age", profile.age ? String(profile.age) : "-"],
                ["Questions answered", `${answered} of ${draft.payload?.total_items ?? answered}`],
              ] as [string, string][]
            ).map(([label, value], i) => (
              <motion.div
                key={label}
                className="metric-row"
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.16 + i * 0.035, ease: EASE_OUT }}
                style={{ alignItems: "flex-start", gap: 18 }}
              >
                <span className="muted" style={{ flex: "0 0 auto" }}>{label}</span>
                <b style={{ textAlign: "right", minWidth: 0, lineHeight: 1.4 }}>{value}</b>
              </motion.div>
            ))}
          </div>
        </div>
      </Reveal>

      <Reveal delay={0.3}>
        <div
          className="surface surface--tinted"
          style={{ "--accent": "var(--brand-gold)", display: "flex", alignItems: "center", gap: 13, padding: "14px 16px" } as React.CSSProperties}
        >
          <FileText size={18} style={{ color: "#8a6410", flex: "0 0 auto" }} />
          <span style={{ minWidth: 0 }}>
            <strong style={{ display: "block", fontSize: 13.5, fontWeight: 650 }}>That is everything we need</strong>
            <small className="muted" style={{ display: "block", fontSize: 12, lineHeight: 1.35 }}>
              You can close this page. Your report goes to your class teacher.
            </small>
          </span>
        </div>
      </Reveal>
    </div>
  );
}
