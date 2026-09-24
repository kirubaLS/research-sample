"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  ChevronRight,
  Eye,
  EyeOff,
  GraduationCap,
  KeyRound,
  PenLine,
  School,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { Mascot, Wordmark } from "@/components/Mascot";
import { EASE_OUT } from "@/components/motion";
import { homeFor, initials, useAuth } from "@/lib/auth";
import { devLoginOptions, mockPrincipal, mockTeachers, type TeacherAssignment } from "@/lib/avai-mock-data";

type StaffRole = "principal" | "teacher";

const ROLES: Array<{
  role: StaffRole;
  title: string;
  blurb: string;
  accent: string;
  icon: typeof Building2;
}> = [
  {
    role: "principal",
    title: "Principal sign-in",
    blurb: "For the school principal.",
    accent: "var(--brand-teal)",
    icon: Building2,
  },
  {
    role: "teacher",
    title: "Teacher sign-in",
    blurb: "Your classes and your subjects, with the findings that matter.",
    accent: "var(--brand-blue)",
    icon: GraduationCap,
  },
];

/** "X-A class teacher · Mathematics · X-A, X-B", what a demo account will
 *  actually see. Subjects taught to the same sections are grouped so the line
 *  stays one or two rows on a phone. */
function describeAssignments(assignments: TeacherAssignment[]) {
  const parts: string[] = [];
  const bySections = new Map<string, string[]>();

  for (const a of assignments) {
    if (a.type === "class") parts.push(`${a.section} class teacher`);
    else {
      const key = a.sections.join(", ");
      bySections.set(key, [...(bySections.get(key) ?? []), a.subject]);
    }
  }
  for (const [sectionList, subjectList] of bySections) {
    parts.push(`${subjectList.join(", ")} · ${sectionList}`);
  }
  return parts.join(" · ");
}

const principalDemo = devLoginOptions.find((o) => o.role === "principal");

/**
 * §4 Sign in. Step 1 picks a staff role, step 2 shows that role's credential
 * form. The form is design only, the demo accounts beneath it are what
 * actually call signIn(). Students never sign in here; they go to /attend.
 */
export default function LoginPage() {
  const [role, setRole] = useState<StaffRole | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const { signIn } = useAuth();
  const router = useRouter();

  const chosen = ROLES.find((r) => r.role === role) ?? null;

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setNotice("Sign-in is not connected in this preview build. Use a demo account below.");
  }

  function enter(r: StaffRole, userId: string) {
    const u = signIn(r, userId);
    if (u) router.push(homeFor(u));
  }

  function back() {
    setRole(null);
    setNotice(null);
    setShowPassword(false);
  }

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
            <div className="stepper__bar" style={{ "--progress": role ? "75%" : "25%" } as React.CSSProperties} />
            <div className="stepper__step" data-state={role ? "done" : "current"}>
              <span className="stepper__dot">1</span>
              Choose role
            </div>
            <div className="stepper__step" data-state={role ? "current" : "todo"}>
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
                    Sign in with your school code and access key.
                  </p>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {ROLES.map((r, i) => {
                    const Icon = r.icon;
                    return (
                      <motion.button
                        key={r.role}
                        type="button"
                        className="authchoice"
                        style={{ "--accent": r.accent } as React.CSSProperties}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4, delay: 0.06 + i * 0.08, ease: EASE_OUT }}
                        onClick={() => setRole(r.role)}
                      >
                        <span className="authchoice__icon">
                          <Icon size={21} />
                        </span>
                        <div>
                          <strong>{r.title}</strong>
                          <small>{r.blurb}</small>
                        </div>
                        <ChevronRight size={17} style={{ marginLeft: "auto", color: "var(--muted)", flex: "0 0 auto" }} />
                      </motion.button>
                    );
                  })}
                </div>
              </motion.div>
            ) : (
              <motion.div
                key={chosen.role}
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 16 }}
                transition={{ duration: 0.32, ease: EASE_OUT }}
                style={{ display: "flex", flexDirection: "column", gap: 16 }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <button type="button" className="btn btn--ghost btn--sm" onClick={back} aria-label="Back to role selection">
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

                <form className="login__form" onSubmit={onSubmit}>
                  <div className="field">
                    <label htmlFor="schoolCode">School code</label>
                    <div style={{ position: "relative" }}>
                      <School size={15} style={{ position: "absolute", left: 11, top: 12, color: "var(--muted)" }} />
                      <input id="schoolCode" className="input" style={{ paddingLeft: 34 }} placeholder="e.g. BIS-TN-001" autoComplete="off" />
                    </div>
                  </div>

                  <div className="field">
                    <label htmlFor="accessKey">Access key</label>
                    <div style={{ position: "relative" }}>
                      <KeyRound size={15} style={{ position: "absolute", left: 11, top: 12, color: "var(--muted)" }} />
                      <input
                        id="accessKey"
                        className="input"
                        style={{ paddingLeft: 34, paddingRight: 40 }}
                        type={showPassword ? "text" : "password"}
                        placeholder="Your personal AVAI access key"
                        autoComplete="current-password"
                      />
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        onClick={() => setShowPassword((v) => !v)}
                        aria-label={showPassword ? "Hide access key" : "Show access key"}
                        style={{ position: "absolute", right: 5, top: 5, padding: 6 }}
                      >
                        {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                      </button>
                    </div>
                  </div>

                  <button
                    type="submit"
                    className={`btn ${chosen.role === "principal" ? "btn--primary" : "btn--blue"}`}
                    style={{ justifyContent: "center", padding: 11 }}
                  >
                    Continue <ArrowRight size={15} />
                  </button>

                  {notice && (
                    <motion.div
                      className="evidence evidence--gold"
                      role="status"
                      initial={{ opacity: 0, y: -6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.3, ease: EASE_OUT }}
                    >
                      <ShieldAlert size={16} />
                      <div>{notice}</div>
                    </motion.div>
                  )}
                </form>


                <DemoAccounts role={chosen.role} accent={chosen.accent} onPick={enter} />
              </motion.div>
            )}
          </AnimatePresence>

          <div style={{ height: 1, background: "var(--line)", margin: "2px 0" }} />

          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.2, ease: EASE_OUT }}>
            <Link
              href="/attend"
              className="surface surface--tinted hoverlift"
              style={{
                "--accent": "var(--brand-gold)",
                display: "flex",
                alignItems: "center",
                gap: 13,
                padding: "13px 15px",
                textDecoration: "none",
                color: "inherit",
              } as React.CSSProperties}
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
                <strong style={{ display: "block", fontSize: 13.5, fontWeight: 650 }}>Attending an AVAI assessment? Start here</strong>
                <small className="muted" style={{ display: "block", fontSize: 12, lineHeight: 1.35 }}>
                  For students with a test ID. This is not a staff login.
                </small>
              </div>
              <ArrowRight size={17} style={{ marginLeft: "auto", color: "#8a6410", flex: "0 0 auto" }} />
            </Link>

            {/* AVAI's own staff console, deliberately quiet, and not a school login. */}
            <Link
              href="/admin"
              className="small muted"
              style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 14, textDecoration: "none" }}
            >
              <ShieldCheck size={13} /> AVAI staff console
            </Link>
          </motion.div>
        </div>
      </section>
    </div>
  );
}

function DemoAccounts({
  role,
  accent,
  onPick,
}: {
  role: StaffRole;
  accent: string;
  onPick: (role: StaffRole, userId: string) => void;
}) {
  const rows =
    role === "principal"
      ? [
          {
            id: principalDemo?.userId ?? mockPrincipal.id,
            name: principalDemo?.sub ?? mockPrincipal.name,
            sub: "Principal · every section, every subject",
          },
        ]
      : mockTeachers.map((t) => ({
          id: t.id,
          name: t.name,
          sub: t.examsOnly ? "Question papers & marks · every subject" : describeAssignments(t.assignments),
        }));

  return (
    <div className="surface" style={{ padding: 14, background: "linear-gradient(180deg, #ffffff, #faf7f1)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 4 }}>
        <span className="tag tag--dev">DEMO</span>
        <strong style={{ fontSize: 13, fontWeight: 650 }}>Demo accounts</strong>
      </div>
      <p className="muted small" style={{ marginBottom: 10 }}>
        {role === "principal"
          ? "Signs you straight in as the principal with mock school data."
          : `Each teacher sees only their own classes and subjects. Pick one of the ${rows.length}.`}
      </p>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 7,
          maxHeight: role === "teacher" ? 268 : undefined,
          overflowY: role === "teacher" ? "auto" : undefined,
          paddingRight: role === "teacher" ? 4 : undefined,
        }}
      >
        {rows.map((r, i) => (
          <motion.button
            key={r.id}
            type="button"
            onClick={() => onPick(role, r.id)}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.04 + i * 0.035, ease: EASE_OUT }}
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
              aria-hidden="true"
              style={{
                width: 32,
                height: 32,
                flex: "0 0 32px",
                borderRadius: "50%",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 11.5,
                fontWeight: 700,
                color: "#fff",
                background: `linear-gradient(160deg, color-mix(in srgb, ${accent} 68%, #fff), ${accent})`,
                boxShadow: `0 6px 14px -7px ${accent}`,
              }}
            >
              {initials(r.name)}
            </span>
            <span style={{ minWidth: 0 }}>
              <span style={{ display: "block", fontSize: 13.5, fontWeight: 620 }}>{r.name}</span>
              <span className="muted" style={{ display: "block", fontSize: 11.5, lineHeight: 1.35 }}>
                {r.sub}
              </span>
            </span>
            <ArrowRight size={15} style={{ marginLeft: "auto", color: "var(--muted)", flex: "0 0 auto" }} />
          </motion.button>
        ))}
      </div>
    </div>
  );
}
