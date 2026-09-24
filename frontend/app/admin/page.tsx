"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AlertCircle, ArrowRight, Lock, ShieldCheck } from "lucide-react";
import { Mascot, Wordmark } from "@/components/Mascot";
import { Reveal, Stagger, StaggerItem } from "@/components/motion";
import { DEMO_STAFF_PASSWORD, demoStaffLogins, signInStaff } from "@/lib/adminState";

/** AVAI staff sign-in. Mock: any listed staff email plus any password. */
export default function AdminSignInPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState(DEMO_STAFF_PASSWORD);
  const [error, setError] = useState<{ field: "email" | "password"; message: string } | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const result = signInStaff(email, password);
    if (!result.ok) {
      setError({ field: result.field, message: result.message });
      return;
    }
    router.push("/admin/schools");
  }

  return (
    <div className="auth">
      <aside className="auth__aside" style={{ alignItems: "center", justifyContent: "center", textAlign: "center" }}>
        <Reveal>
          <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", gap: 20, alignItems: "center" }}>
            <Wordmark height={52} onDark />
            <Mascot pose="hello" size={170} float />
            <h1 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(24px, 2.8vw, 34px)", fontWeight: 500, lineHeight: 1.25, maxWidth: 380 }}>
              Every opportunity belongs to every student.
            </h1>
          </div>
        </Reveal>
      </aside>

      <div className="auth__panel">
        <div>
          <Reveal>
            <div className="surface" style={{ padding: "26px 24px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 4 }}>
                <ShieldCheck size={18} style={{ color: "var(--brand-blue)" }} />
                <h2 style={{ fontSize: 21 }}>Staff sign-in</h2>
              </div>
              <p className="small muted" style={{ marginBottom: 20 }}>
                Use your AVAI address. Principals and teachers sign in at the school app, not here.
              </p>

              <form className="login__form" onSubmit={submit} noValidate>
                <div className="field">
                  <label htmlFor="staff-email">Work email</label>
                  <input
                    id="staff-email"
                    className="input"
                    type="email"
                    autoComplete="username"
                    placeholder="name@avai.school"
                    value={email}
                    aria-invalid={error?.field === "email"}
                    aria-describedby={error ? "staff-error" : undefined}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      setError(null);
                    }}
                  />
                </div>

                <div className="field">
                  <label htmlFor="staff-password">Password</label>
                  <input
                    id="staff-password"
                    className="input"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    aria-invalid={error?.field === "password"}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      setError(null);
                    }}
                  />
                  <span className="small muted" style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                    <Lock size={11} /> Demo build, any password works.
                  </span>
                </div>

                {error && (
                  <div id="staff-error" className="evidence" style={{ background: "var(--risk-soft)", borderColor: "#eec3bb", color: "#8f3226" }}>
                    <AlertCircle size={15} />
                    <span>{error.message}</span>
                  </div>
                )}

                <button type="submit" className="btn btn--blue" style={{ justifyContent: "center", padding: "10px 14px" }}>
                  Enter console <ArrowRight size={14} />
                </button>
              </form>
            </div>
          </Reveal>

          <Reveal delay={0.12}>
            <div className="devlogin" style={{ borderColor: "var(--brand-blue)", background: "rgba(29,95,208,.05)" }}>
              <div className="devlogin__head">
                <strong>Demo accounts</strong> · any password
              </div>
              <Stagger className="devlogin__grid" gap={0.05}>
                {demoStaffLogins.map((s) => (
                  <StaggerItem key={s.email}>
                    <button
                      type="button"
                      className="devlogin__btn"
                      style={{ width: "100%" }}
                      onClick={() => {
                        setEmail(s.email);
                        setError(null);
                      }}
                    >
                      <span>
                        <strong style={{ fontWeight: 650 }}>{s.email}</strong>
                        <small style={{ display: "block" }}>
                          {s.name} · {s.role}
                        </small>
                      </span>
                      <ArrowRight size={13} />
                    </button>
                  </StaggerItem>
                ))}
              </Stagger>
            </div>
          </Reveal>

          <p className="login__help">
            Looking for the school app? <Link href="/login" className="btn--link">Principal and teacher sign-in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
