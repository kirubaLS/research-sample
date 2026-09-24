"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion, type Variants } from "framer-motion";
import { ArrowLeft, ArrowRight, Check, CloudCheck, IdCard, Loader2 } from "lucide-react";
import { EASE_OUT } from "@/components/motion";
import { patchAttend, submitAttend, useAttend } from "@/lib/attendState";
import { StepDone } from "./done";
import { isStepValid, StepBackground, StepBasicInfo, StepFuturePlans, StepInterests, StepLearningProfile } from "./steps";

const STEPS = ["Basic Info", "Background", "Learning Profile", "Interests", "Future Plans", "Done"];
const LAST = STEPS.length - 1;

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
 * §A2 Onboarding wizard, five screens, one per topic, with the answers
 * autosaved to localStorage after every change so a phone that reloads
 * mid-way picks up where it stopped.
 */
export default function OnboardingPage() {
  const draft = useAttend();
  const reduce = useReducedMotion();
  const slide = useMemo(() => slideFor(reduce ? 0 : 34), [reduce]);
  const [ready, setReady] = useState(false);
  const [direction, setDirection] = useState(1);
  const [showErrors, setShowErrors] = useState(false);

  useEffect(() => setReady(true), []);

  const step = Math.min(draft.step, LAST);
  const valid = isStepValid(step, draft);

  useEffect(() => {
    if (step === LAST && !draft.submitted) submitAttend();
  }, [step, draft.submitted]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [step]);

  function go(next: number) {
    setDirection(next > step ? 1 : -1);
    setShowErrors(false);
    patchAttend({ step: Math.max(0, Math.min(LAST, next)) });
  }

  function onContinue() {
    if (!valid) {
      setShowErrors(true);
      return;
    }
    go(step + 1);
  }

  if (!ready) {
    return (
      <div style={{ display: "grid", gap: 14 }}>
        <div className="shimmer" style={{ height: 44, borderRadius: "var(--radius-md)" }} />
        <div className="shimmer" style={{ height: 320, borderRadius: "var(--radius-lg)" }} />
      </div>
    );
  }

  if (!draft.identity) {
    return (
      <motion.div
        className="surface surface--raised"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: EASE_OUT }}
        style={{ padding: "clamp(22px, 5vw, 32px)", textAlign: "center", display: "grid", gap: 12, justifyItems: "center" }}
      >
        <IdCard size={26} style={{ color: "var(--brand-teal)" }} />
        <h2 style={{ fontSize: 20 }}>Sign in with your student ID first</h2>
        <p className="muted" style={{ fontSize: 13.5, maxWidth: 380, lineHeight: 1.5 }}>
          Onboarding is personal to you, so we need the ID on the slip your class teacher handed out before we can start.
        </p>
        <Link href="/attend" className="btn btn--primary">
          Go to sign-in <ArrowRight size={15} />
        </Link>
      </motion.div>
    );
  }

  const stepProps = { draft, patch: patchAttend, showErrors };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div className="surface" style={{ padding: "16px 16px 14px" }}>
        <div className="stepper">
          <div className="stepper__bar" style={{ "--progress": `${(step / LAST) * 100}%` } as React.CSSProperties} />
          {STEPS.map((label, i) => (
            <div key={label} className="stepper__step" data-state={i < step ? "done" : i === step ? "current" : "todo"}>
              <span className="stepper__dot">{i < step ? <Check size={13} /> : i + 1}</span>
              {label}
            </div>
          ))}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, marginTop: 14 }}>
          <span className="muted" style={{ fontSize: 12 }}>
            Step {step + 1} of {STEPS.length}
          </span>
          <SaveBadge rev={draft.rev} />
        </div>
      </div>

      <AnimatePresence mode="wait" custom={direction} initial={false}>
        <motion.div
          key={step}
          custom={direction}
          variants={slide}
          initial="enter"
          animate="center"
          exit="exit"
          transition={{ duration: 0.34, ease: EASE_OUT }}
        >
          {step === 0 && <StepBasicInfo {...stepProps} />}
          {step === 1 && <StepBackground {...stepProps} />}
          {step === 2 && <StepLearningProfile {...stepProps} />}
          {step === 3 && <StepInterests {...stepProps} />}
          {step === 4 && <StepFuturePlans {...stepProps} />}
          {step === LAST && <StepDone draft={draft} />}
        </motion.div>
      </AnimatePresence>

      {step < LAST && (
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
          <button type="button" className="btn" onClick={() => go(step - 1)} disabled={step === 0}>
            <ArrowLeft size={15} /> Back
          </button>
          {!valid && showErrors && (
            <span className="muted" style={{ fontSize: 12, lineHeight: 1.3, minWidth: 0 }}>
              Fill the highlighted answers.
            </span>
          )}
          <motion.button
            type="button"
            className="btn btn--primary"
            style={{ marginLeft: "auto", padding: "10px 18px", fontSize: 14, opacity: valid ? 1 : 0.75 }}
            onClick={onContinue}
            aria-disabled={!valid}
            whileHover={{ y: -2 }}
            whileTap={{ y: 0 }}
          >
            {step === LAST - 1 ? "Finish" : "Continue"} <ArrowRight size={15} />
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
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 12,
        fontWeight: 600,
        color: state === "saving" ? "var(--muted)" : "var(--brand-green)",
      }}
      aria-live="polite"
    >
      {state === "saving" ? (
        <Loader2 size={13} className="spin" />
      ) : (
        <CloudCheck size={13} />
      )}
      {state === "saving" ? "Saving…" : state === "saved" ? "Saved" : "Autosave on"}
    </span>
  );
}
