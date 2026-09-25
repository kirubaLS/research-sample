"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion, type Variants } from "framer-motion";
import { ArrowLeft, ArrowRight, Check, CloudCheck, IdCard, Loader2 } from "lucide-react";
import { EASE_OUT } from "@/components/motion";
import { api, ApiError } from "@/lib/api";
import { patchAnswers, patchAttend, useAttend } from "@/lib/attendState";
import { StepDone } from "./done";
import {
  isBackgroundValid,
  isBasicInfoValid,
  isFuturePlansValid,
  isInterestsValid,
  isLearningProfileValid,
  STEP_META,
  StepBackground,
  StepBasicInfo,
  StepFuturePlans,
  StepInterests,
  StepLearningProfile,
} from "./steps";

const VALIDATORS = [isBasicInfoValid, isBackgroundValid, isLearningProfileValid, isInterestsValid, isFuturePlansValid];

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
 * §A2 Onboarding: the real 6-step wizard, backed by POST /t/{classCode}/onboard.
 * Steps 1..5 collect the answers, step 6 is the confirmation screen after a
 * single submit -- there is no per-screen server round trip the way the old
 * 36-item Likert flow had (every screen there posted its own responses); here
 * autosave means "not lost on reload" (sessionStorage, via lib/attendState.ts),
 * not "already on the server".
 */
export default function OnboardingPage() {
  const router = useRouter();
  const draft = useAttend();
  const reduce = useReducedMotion();
  const slide = useMemo(() => slideFor(reduce ? 0 : 34), [reduce]);
  const [ready, setReady] = useState(false);
  const [direction, setDirection] = useState(1);
  const [showErrors, setShowErrors] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setReady(true), []);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [draft.step]);

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

  const step = draft.step;
  const done = draft.submitted;
  const ctx = {
    schoolName: draft.schoolName ?? "",
    classLabel: draft.classLabel ?? "",
    section: draft.classSection ?? "A",
    board: draft.classBoard ?? "CBSE",
  };

  function next() {
    const valid = VALIDATORS[step]?.(draft.answers) ?? true;
    if (!valid) {
      setShowErrors(true);
      return;
    }
    setShowErrors(false);
    setDirection(1);
    if (step < 4) {
      patchAttend({ step: step + 1 });
    } else {
      submit();
    }
  }

  function back() {
    setDirection(-1);
    setShowErrors(false);
    patchAttend({ step: Math.max(0, step - 1) });
  }

  async function submit() {
    if (!draft.classCode) return;
    setError(null);
    setSubmitting(true);
    try {
      const res = await api.onboard(draft.classCode, {
        name: draft.answers.name!,
        roll_no: draft.answers.roll_no!,
        age: draft.answers.age,
        gender: draft.answers.gender,
        dob: draft.answers.dob,
        board: ctx.board,
        lives_in: draft.answers.lives_in,
        decision_helper: draft.answers.decision_helper,
        responsibilities: draft.answers.responsibilities,
        subject_enjoy: draft.answers.subject_enjoy,
        subject_comfortable: draft.answers.subject_comfortable,
        learning_type: draft.answers.learning_type,
        interests: draft.answers.interests ?? [],
        work_interest: draft.answers.work_interest,
        new_learning_style: draft.answers.new_learning_style,
        future_career: draft.answers.future_career,
        class11_group: draft.answers.class11_group,
        group_reason: draft.answers.group_reason ?? [],
        confidence: draft.answers.confidence,
        careers_known: draft.answers.careers_known ?? [],
        future_concern: draft.answers.future_concern ?? [],
      });
      patchAttend({ studentId: res.student_id, submitted: true, step: 5 });
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 404
          ? "That class link is not recognised. Please pick your class again."
          : err instanceof ApiError && err.status === 422
            ? "Some answers look invalid. Please check the form and try again."
            : "Could not save your answers. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div className="surface" style={{ padding: "16px 16px 14px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <span style={{ fontSize: 13, fontWeight: 650 }}>
            {ctx.schoolName}
            {draft.answers.name ? ` · ${draft.answers.name}` : ""}
            {ctx.section ? ` · Section ${ctx.section}` : ""}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <SaveBadge rev={draft.rev} />
            <Link href="/attend" className="btn--link" style={{ fontSize: 12.5 }}>
              Exit
            </Link>
          </div>
        </div>
        <div className="stepper">
          <div className="stepper__bar" style={{ "--progress": `${(Math.min(step, 5) / 5) * 100}%` } as React.CSSProperties} />
          {STEP_META.map((meta, i) => (
            <div key={meta.title} className="stepper__step" data-state={i < step || done ? "done" : i === step ? "current" : "upcoming"}>
              <span className="stepper__dot">{i < step || done ? <Check size={13} /> : i + 1}</span>
              {meta.title}
            </div>
          ))}
        </div>
      </div>

      {error && (
        <div className="evidence evidence--gold">
          <div>{error}</div>
        </div>
      )}

      <AnimatePresence mode="wait" custom={direction} initial={false}>
        <motion.div key={done ? "done" : step} custom={direction} variants={slide} initial="enter" animate="center" exit="exit" transition={{ duration: 0.34, ease: EASE_OUT }}>
          {done && <StepDone draft={draft} />}
          {!done && step === 0 && <StepBasicInfo ctx={ctx} answers={draft.answers} patch={patchAnswers} showErrors={showErrors} />}
          {!done && step === 1 && <StepBackground answers={draft.answers} patch={patchAnswers} showErrors={showErrors} />}
          {!done && step === 2 && <StepLearningProfile answers={draft.answers} patch={patchAnswers} showErrors={showErrors} />}
          {!done && step === 3 && <StepInterests answers={draft.answers} patch={patchAnswers} showErrors={showErrors} />}
          {!done && step === 4 && <StepFuturePlans answers={draft.answers} patch={patchAnswers} showErrors={showErrors} />}
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
          <button type="button" className="btn" onClick={step === 0 ? () => router.push("/attend") : back}>
            <ArrowLeft size={15} /> {step === 0 ? "Change class" : "Back"}
          </button>
          <motion.button
            type="button"
            className="btn btn--primary"
            style={{ marginLeft: "auto", padding: "10px 18px", fontSize: 14 }}
            onClick={next}
            disabled={submitting}
            whileHover={{ y: -2 }}
            whileTap={{ y: 0 }}
          >
            {submitting ? (
              "Saving…"
            ) : (
              <>
                {step < 4 ? "Continue" : "Finish"} <ArrowRight size={15} />
              </>
            )}
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
