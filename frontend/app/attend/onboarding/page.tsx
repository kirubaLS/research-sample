"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion, type Variants } from "framer-motion";
import { ArrowLeft, ArrowRight, CloudCheck, IdCard, Loader2 } from "lucide-react";
import { EASE_OUT } from "@/components/motion";
import { api, ApiError } from "@/lib/api";
import { patchAttend, useAttend, type AttendProfile } from "@/lib/attendState";
import { StepDone } from "./done";
import { isProfileValid, StepBasicInfo, StepLikertScreen } from "./steps";

/** Direction-aware slide: AnimatePresence passes the *current* direction to
 * the exiting screen, so back really does read as going back. */
function slideFor(offset: number): Variants {
  return {
    enter: (d: number) => ({ opacity: 0, x: d * offset }),
    center: { opacity: 1, x: 0 },
    exit: (d: number) => ({ opacity: 0, x: d * -offset }),
  };
}

/**
 * §A2 Onboarding: the real interest test. Step 0 collects the profile POST
 * /t/{classCode}/start needs and starts the session; every screen after
 * that is one of the real SessionPayload.screens (6 Likert items each,
 * saved to the server the moment a screen is completed via
 * POST /t/session/{id}/responses); the last screen calls
 * POST /t/session/{id}/complete. The reference design's five-topic
 * personality/background/future-plans wizard is not reproduced -- see the
 * gap note in the wiring report.
 */
export default function OnboardingPage() {
  const router = useRouter();
  const draft = useAttend();
  const reduce = useReducedMotion();
  const slide = useMemo(() => slideFor(reduce ? 0 : 34), [reduce]);
  const [ready, setReady] = useState(false);
  const [direction, setDirection] = useState(1);
  const [showErrors, setShowErrors] = useState(false);
  const [starting, setStarting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shownAt = useRef<Record<string, number>>({});

  useEffect(() => setReady(true), []);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [draft.screenIndex]);

  const step = draft.sessionId ? draft.screenIndex : -1;
  const screens = draft.payload?.screens ?? [];
  const screen = step >= 0 ? screens[step] : null;

  useEffect(() => {
    const now = Date.now() / 1000;
    for (const item of screen ?? []) {
      if (!(item.item_id in shownAt.current)) shownAt.current[item.item_id] = now;
    }
  }, [screen]);

  if (!ready) {
    return (
      <div style={{ display: "grid", gap: 14 }}>
        <div className="shimmer" style={{ height: 44, borderRadius: "var(--radius-md)" }} />
        <div className="shimmer" style={{ height: 320, borderRadius: "var(--radius-lg)" }} />
      </div>
    );
  }

  if (!draft.classCode) {
    return (
      <motion.div
        className="surface surface--raised"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: EASE_OUT }}
        style={{ padding: "clamp(22px, 5vw, 32px)", textAlign: "center", display: "grid", gap: 12, justifyItems: "center" }}
      >
        <IdCard size={26} style={{ color: "var(--brand-teal)" }} />
        <h2 style={{ fontSize: 20 }}>Pick your class first</h2>
        <p className="muted" style={{ fontSize: 13.5, maxWidth: 380, lineHeight: 1.5 }}>
          Onboarding is personal to your class, so we need that before we can start.
        </p>
        <Link href="/attend" className="btn btn--primary">
          Go to class picker <ArrowRight size={15} />
        </Link>
      </motion.div>
    );
  }

  const profile: Partial<AttendProfile> = draft.profile ?? { locale: "en" };

  async function startSession() {
    setShowErrors(true);
    if (!isProfileValid(profile) || !draft.classCode) return;
    setError(null);
    setStarting(true);
    try {
      const body: Record<string, unknown> = { name: profile.name, roll_no: profile.roll_no, section: profile.section, locale: profile.locale ?? "en" };
      if (profile.age) body.age = profile.age;
      if (profile.gender) body.gender = profile.gender;
      const session = await api.startSession(draft.classCode, body);
      patchAttend({
        profile: profile as AttendProfile,
        sessionId: session.session_id,
        payload: session,
        screenIndex: 0,
      });
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 404
          ? "That class link is not recognised. Please pick your class again."
          : "Could not start the test. Please try again.",
      );
    } finally {
      setStarting(false);
    }
  }

  async function nextScreen() {
    if (!screen || !draft.sessionId) return;
    const allAnswered = screen.every((i) => draft.answers[i.item_id]);
    if (!allAnswered) {
      setShowErrors(true);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.saveResponses(
        draft.sessionId,
        screen.map((i) => ({
          item_id: i.item_id,
          value: draft.answers[i.item_id].value,
          shown_at: draft.answers[i.item_id].shownAt,
          answered_at: draft.answers[i.item_id].answeredAt,
        })),
      );
      setDirection(1);
      setShowErrors(false);
      if (draft.screenIndex + 1 < screens.length) {
        patchAttend({ screenIndex: draft.screenIndex + 1 });
      } else {
        await api.complete(draft.sessionId);
        patchAttend({ submitted: true, screenIndex: screens.length });
      }
    } catch {
      setError("Could not save just now. Please try again, your answers are still here.");
    } finally {
      setSaving(false);
    }
  }

  function back() {
    setDirection(-1);
    setShowErrors(false);
    patchAttend({ screenIndex: Math.max(0, draft.screenIndex - 1) });
  }

  function choose(itemId: string, value: number) {
    patchAttend({
      answers: {
        ...draft.answers,
        [itemId]: { value, shownAt: shownAt.current[itemId] ?? Date.now() / 1000, answeredAt: Date.now() / 1000 },
      },
    });
  }

  const done = draft.submitted;
  const totalLabel = draft.sessionId ? screens.length + 1 : 1;
  const currentLabel = draft.sessionId ? Math.min(step, screens.length) + 1 : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div className="surface" style={{ padding: "16px 16px 14px" }}>
        <div className="stepper">
          <div className="stepper__bar" style={{ "--progress": `${(currentLabel / totalLabel) * 100}%` } as React.CSSProperties} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, marginTop: 14 }}>
          <span className="muted" style={{ fontSize: 12 }}>
            {done ? "Done" : draft.sessionId ? `Screen ${step + 1} of ${screens.length}` : "Your details"}
          </span>
          <SaveBadge rev={draft.rev} />
        </div>
      </div>

      {error && (
        <div className="evidence evidence--gold">
          <div>{error}</div>
        </div>
      )}

      <AnimatePresence mode="wait" custom={direction} initial={false}>
        <motion.div key={done ? "done" : draft.sessionId ? step : "profile"} custom={direction} variants={slide} initial="enter" animate="center" exit="exit" transition={{ duration: 0.34, ease: EASE_OUT }}>
          {done && <StepDone draft={draft} />}
          {!done && !draft.sessionId && (
            <StepBasicInfo
              classLabel={draft.classLabel ?? ""}
              schoolName={draft.schoolName ?? ""}
              profile={profile}
              patch={(p) => patchAttend({ profile: { ...profile, ...p } as AttendProfile })}
              showErrors={showErrors}
            />
          )}
          {!done && draft.sessionId && screen && (
            <StepLikertScreen screen={screen} index={step} total={screens.length} answers={draft.answers} onChoose={choose} />
          )}
        </motion.div>
      </AnimatePresence>

      {!done && (
        <div
          className="surface--glass"
          style={{
            position: "sticky",
            bottom: 0,
            zIndex: 15,
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "12px 14px",
            marginTop: 4,
            borderRadius: "var(--radius-lg)",
            border: "1px solid var(--line)",
          }}
        >
          {draft.sessionId ? (
            <button type="button" className="btn" onClick={back} disabled={step === 0}>
              <ArrowLeft size={15} /> Back
            </button>
          ) : (
            <button type="button" className="btn" onClick={() => router.push("/attend")}>
              <ArrowLeft size={15} /> Change class
            </button>
          )}
          <motion.button
            type="button"
            className="btn btn--primary"
            style={{ marginLeft: "auto", padding: "10px 18px", fontSize: 14 }}
            onClick={draft.sessionId ? nextScreen : startSession}
            disabled={starting || saving}
            whileHover={{ y: -2 }}
            whileTap={{ y: 0 }}
          >
            {starting || saving ? "Please wait…" : draft.sessionId ? (step + 1 < screens.length ? "Continue" : "Finish") : "Start the questionnaire"} <ArrowRight size={15} />
          </motion.button>
        </div>
      )}
    </div>
  );
}

/** "Saving… / Saved", the reassurance that nothing typed is lost. */
function SaveBadge({ rev }: { rev: number }) {
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");

  useEffect(() => {
    if (rev === 0) return;
    setState("saving");
    const t = setTimeout(() => setState("saved"), 600);
    return () => clearTimeout(t);
  }, [rev]);

  return (
    <span
      style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600, color: state === "saving" ? "var(--muted)" : "var(--brand-green)" }}
      aria-live="polite"
    >
      {state === "saving" ? <Loader2 size={13} className="spin" /> : <CloudCheck size={13} />}
      {state === "saving" ? "Saving…" : state === "saved" ? "Saved" : "Autosave on"}
    </span>
  );
}
