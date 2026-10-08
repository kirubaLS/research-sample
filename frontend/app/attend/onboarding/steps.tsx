"use client";

import { Brain, Compass, IdCard, Sparkles, Target } from "lucide-react";
import type { WizardAnswers } from "@/lib/attendState";
import { rules } from "@/lib/onboarding";
import {
  careersKnownOptions,
  class11GroupOptions,
  confidenceOptions,
  decisionHelperOptions,
  futureConcernOptions,
  genderOptions,
  groupReasonOptions,
  interestOptions,
  learningTypeOptions,
  livesInOptions,
  newLearningOptions,
  responsibilitiesOptions,
  subjectOptions,
  workInterestOptions,
} from "../options";
import { ChipGroup, FieldError, LockedField, PillGroup, Question, StepCard } from "./ui";

export const STEP_META = [
  { title: "Basic Info", icon: IdCard, accent: "var(--brand-teal)" },
  { title: "Your Background", icon: Compass, accent: "var(--brand-orange)" },
  { title: "Your Learning Profile", icon: Brain, accent: "var(--brand-blue, #2b6fd1)" },
  { title: "Your Interests", icon: Sparkles, accent: "var(--brand-green)" },
  { title: "Your Future Plans", icon: Target, accent: "var(--brand-gold)" },
] as const;

type Patch = (patch: WizardAnswers) => void;

export interface ClassContext {
  schoolName: string;
  classLabel: string;
  section: string;
  board: string;
}

// ---------------------------------------------------------------------------
// Step 1: Basic Info
// ---------------------------------------------------------------------------
export function isBasicInfoValid(a: WizardAnswers): boolean {
  return Object.keys(basicInfoErrors(a)).length === 0 && Boolean(a.gender);
}

/** Every Basic Info field that breaks its rule, with the message to show. */
export function basicInfoErrors(a: WizardAnswers): Record<string, string> {
  const e: Record<string, string> = {};
  const name = rules.personName(a.name ?? "");
  if (name) e.name = name;
  const roll = rules.rollNo(a.roll_no ?? "");
  if (roll) e.roll_no = roll;
  const dob = rules.dob(a.dob ?? "");
  if (dob) e.dob = dob;
  return e;
}

export function StepBasicInfo({
  ctx,
  answers,
  patch,
  showErrors,
}: {
  ctx: ClassContext;
  answers: WizardAnswers;
  patch: Patch;
  showErrors: boolean;
}) {
  const age = answers.dob ? ageFromDob(answers.dob) : answers.age;
  const err = basicInfoErrors(answers);
  const today = new Date().toISOString().slice(0, 10);
  return (
    <StepCard icon={IdCard} eyebrow="STEP 1 OF 6" title="Basic Info" accent={STEP_META[0].accent}>
      <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))" }}>
        <LockedField label="Class / Standard" value={ctx.classLabel} />
        <LockedField label="Section" value={ctx.section} />
        <LockedField label="School Name" value={ctx.schoolName} />
        <LockedField label="Board / Medium" value={ctx.board} />
      </div>

      <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        <div className="field">
          <label htmlFor="p-name">Full Name</label>
          <input
            id="p-name"
            className="input"
            autoComplete="name"
            value={answers.name ?? ""}
            aria-invalid={(showErrors || !!answers.name) && !!err.name}
            onChange={(e) => patch({ name: e.target.value })}
          />
          <FieldError show={(showErrors || !!answers.name) && !!err.name}>{err.name}</FieldError>
        </div>
        <div className="field">
          <label htmlFor="p-roll">Roll Number</label>
          <input
            id="p-roll"
            className="input"
            inputMode="numeric"
            value={answers.roll_no ?? ""}
            aria-invalid={(showErrors || !!answers.roll_no) && !!err.roll_no}
            maxLength={16}
            onChange={(e) => patch({ roll_no: e.target.value })}
          />
          <FieldError show={(showErrors || !!answers.roll_no) && !!err.roll_no}>{err.roll_no}</FieldError>
        </div>
        <div className="field">
          <label htmlFor="p-dob">Date of Birth</label>
          <input
            id="p-dob"
            className="input"
            type="date"
            max={today}
            value={answers.dob ?? ""}
            aria-invalid={(showErrors || !!answers.dob) && !!err.dob}
            onChange={(e) => {
              const dob = e.target.value;
              patch({ dob, age: dob ? ageFromDob(dob) : answers.age });
            }}
          />
          <FieldError show={(showErrors || !!answers.dob) && !!err.dob}>{err.dob}</FieldError>
        </div>
        <LockedField label="Age" value={age ? String(age) : "—"} />
      </div>

      <Question label="Gender">
        <PillGroup
          groupLabel="Gender"
          options={genderOptions}
          selected={answers.gender ? [answers.gender] : []}
          accent={STEP_META[0].accent}
          onChange={([gender]) => patch({ gender: gender as WizardAnswers["gender"] })}
        />
        <FieldError show={showErrors && !answers.gender}>Choose one.</FieldError>
      </Question>
    </StepCard>
  );
}

function ageFromDob(dob: string): number | undefined {
  const d = new Date(dob);
  if (Number.isNaN(d.getTime())) return undefined;
  const now = new Date();
  let age = now.getFullYear() - d.getFullYear();
  const m = now.getMonth() - d.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < d.getDate())) age--;
  return age;
}

// ---------------------------------------------------------------------------
// Step 2: Background
// ---------------------------------------------------------------------------
export function isBackgroundValid(a: WizardAnswers): boolean {
  return Boolean(a.lives_in) && Boolean(a.decision_helper) && Boolean(a.responsibilities);
}

export function StepBackground({ answers, patch, showErrors }: { answers: WizardAnswers; patch: Patch; showErrors: boolean }) {
  return (
    <StepCard icon={Compass} eyebrow="STEP 2 OF 6" title="Section 1 · Your Background" accent={STEP_META[1].accent}>
      <Question label="Where do you live?">
        <PillGroup groupLabel="Where do you live" options={livesInOptions} selected={answers.lives_in ? [answers.lives_in] : []} accent={STEP_META[1].accent} onChange={([v]) => patch({ lives_in: v })} />
        <FieldError show={showErrors && !answers.lives_in}>Choose one.</FieldError>
      </Question>
      <Question label="Who usually helps you make important study decisions?">
        <PillGroup groupLabel="Who helps you decide" options={decisionHelperOptions} selected={answers.decision_helper ? [answers.decision_helper] : []} accent={STEP_META[1].accent} onChange={([v]) => patch({ decision_helper: v })} />
        <FieldError show={showErrors && !answers.decision_helper}>Choose one.</FieldError>
      </Question>
      <Question label="Do you have any responsibilities outside school that affect your study plans?">
        <PillGroup groupLabel="Responsibilities" options={responsibilitiesOptions} selected={answers.responsibilities ? [answers.responsibilities] : []} accent={STEP_META[1].accent} onChange={([v]) => patch({ responsibilities: v })} />
        <FieldError show={showErrors && !answers.responsibilities}>Choose one.</FieldError>
      </Question>
    </StepCard>
  );
}

// ---------------------------------------------------------------------------
// Step 3: Learning Profile
// ---------------------------------------------------------------------------
export function isLearningProfileValid(a: WizardAnswers): boolean {
  return Boolean(a.subject_enjoy) && Boolean(a.subject_comfortable) && Boolean(a.learning_type);
}

export function StepLearningProfile({ answers, patch, showErrors }: { answers: WizardAnswers; patch: Patch; showErrors: boolean }) {
  return (
    <StepCard icon={Brain} eyebrow="STEP 3 OF 6" title="Section 2 · Your Learning Profile" accent={STEP_META[2].accent}>
      <Question label="Which subject do you enjoy learning the most?">
        <PillGroup groupLabel="Subject you enjoy" options={subjectOptions} selected={answers.subject_enjoy ? [answers.subject_enjoy] : []} accent={STEP_META[2].accent} onChange={([v]) => patch({ subject_enjoy: v })} />
        <FieldError show={showErrors && !answers.subject_enjoy}>Choose one.</FieldError>
      </Question>
      <Question label="Which subject do you feel most comfortable with?">
        <PillGroup groupLabel="Subject you're comfortable with" options={subjectOptions} selected={answers.subject_comfortable ? [answers.subject_comfortable] : []} accent={STEP_META[2].accent} onChange={([v]) => patch({ subject_comfortable: v })} />
        <FieldError show={showErrors && !answers.subject_comfortable}>Choose one.</FieldError>
      </Question>
      <Question label="Which type of learning do you enjoy more?">
        <PillGroup groupLabel="Type of learning" options={learningTypeOptions} selected={answers.learning_type ? [answers.learning_type] : []} accent={STEP_META[2].accent} onChange={([v]) => patch({ learning_type: v })} />
        <FieldError show={showErrors && !answers.learning_type}>Choose one.</FieldError>
      </Question>
    </StepCard>
  );
}

// ---------------------------------------------------------------------------
// Step 4: Interests
// ---------------------------------------------------------------------------
export function isInterestsValid(a: WizardAnswers): boolean {
  return Boolean(a.interests?.length) && Boolean(a.work_interest) && Boolean(a.new_learning_style);
}

export function StepInterests({ answers, patch, showErrors }: { answers: WizardAnswers; patch: Patch; showErrors: boolean }) {
  return (
    <StepCard icon={Sparkles} eyebrow="STEP 4 OF 6" title="Section 3 · Your Interests" accent={STEP_META[3].accent}>
      <Question label="What do you enjoy doing outside studies?" hint="Select up to 3">
        <PillGroup
          groupLabel="Outside-studies interests"
          options={interestOptions}
          selected={answers.interests ?? []}
          multi
          max={3}
          accent={STEP_META[3].accent}
          onChange={(v) => patch({ interests: v })}
        />
        <FieldError show={showErrors && !answers.interests?.length}>Choose at least one.</FieldError>
      </Question>
      <Question label="Which kind of work sounds interesting to you?">
        <PillGroup groupLabel="Kind of work" options={workInterestOptions} selected={answers.work_interest ? [answers.work_interest] : []} accent={STEP_META[3].accent} onChange={([v]) => patch({ work_interest: v })} />
        <FieldError show={showErrors && !answers.work_interest}>Choose one.</FieldError>
      </Question>
      <Question label="When you learn something new, what do you enjoy most?">
        <PillGroup groupLabel="Learning something new" options={newLearningOptions} selected={answers.new_learning_style ? [answers.new_learning_style] : []} accent={STEP_META[3].accent} onChange={([v]) => patch({ new_learning_style: v })} />
        <FieldError show={showErrors && !answers.new_learning_style}>Choose one.</FieldError>
      </Question>
    </StepCard>
  );
}

// ---------------------------------------------------------------------------
// Step 5: Future Plans
// ---------------------------------------------------------------------------
export function isFuturePlansValid(a: WizardAnswers): boolean {
  return !rules.career(a.future_career ?? "") && Boolean(a.class11_group) && Boolean(a.group_reason?.length) && Boolean(a.confidence);
}

export function StepFuturePlans({ answers, patch, showErrors }: { answers: WizardAnswers; patch: Patch; showErrors: boolean }) {
  const notSure = answers.future_career === "Not sure yet";
  return (
    <StepCard icon={Target} eyebrow="STEP 5 OF 6" title="Section 4 · Your Future Plans" accent={STEP_META[4].accent}>
      <Question label="What would you like to become or explore in the future?">
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <input
            className="input"
            style={{ flex: "1 1 220px" }}
            value={notSure ? "Not sure yet" : answers.future_career ?? ""}
            disabled={notSure}
            placeholder="e.g. Software engineer, Doctor, Designer…"
            aria-invalid={(showErrors || !!answers.future_career) && !!rules.career(answers.future_career ?? "")}
            onChange={(e) => patch({ future_career: e.target.value })}
          />
          <button
            type="button"
            className={`pillchoice${notSure ? " pillchoice--on" : ""}`}
            style={{ "--accent": STEP_META[4].accent } as React.CSSProperties}
            onClick={() => patch({ future_career: notSure ? "" : "Not sure yet" })}
          >
            Not sure yet
          </button>
        </div>
        <FieldError show={(showErrors || !!answers.future_career) && !!rules.career(answers.future_career ?? "")}>{rules.career(answers.future_career ?? "")}</FieldError>
      </Question>

      <Question label="Which Class 11 group are you thinking about?">
        <PillGroup groupLabel="Class 11 group" options={class11GroupOptions} selected={answers.class11_group ? [answers.class11_group] : []} accent={STEP_META[4].accent} onChange={([v]) => patch({ class11_group: v })} />
        <FieldError show={showErrors && !answers.class11_group}>Choose one.</FieldError>
      </Question>

      <Question label="Why are you considering this group?" hint="Select up to 2">
        <PillGroup
          groupLabel="Why this group"
          options={groupReasonOptions}
          selected={answers.group_reason ?? []}
          multi
          max={2}
          accent={STEP_META[4].accent}
          onChange={(v) => patch({ group_reason: v })}
        />
        <FieldError show={showErrors && !answers.group_reason?.length}>Choose at least one.</FieldError>
      </Question>

      <Question label="How sure are you about this choice?">
        <ChipGroup
          groupLabel="Confidence"
          options={confidenceOptions.map((o) => ({ id: o.id, label: o.label }))}
          selected={answers.confidence ? [String(answers.confidence)] : []}
          accent={STEP_META[4].accent}
          onChange={([v]) => patch({ confidence: Number(v) })}
        />
        <FieldError show={showErrors && !answers.confidence}>Choose one.</FieldError>
      </Question>

      <Question label="Which careers or exams have you heard about?">
        <PillGroup
          groupLabel="Careers or exams heard about"
          options={careersKnownOptions}
          selected={answers.careers_known ?? []}
          multi
          accent={STEP_META[4].accent}
          onChange={(v) => patch({ careers_known: v })}
        />
      </Question>

      <Question label="Is there anything that may affect your future study choice?">
        <PillGroup
          groupLabel="What may affect your future study choice"
          options={futureConcernOptions}
          selected={answers.future_concern ?? []}
          multi
          accent={STEP_META[4].accent}
          onChange={(v) => patch({ future_concern: v })}
        />
      </Question>
    </StepCard>
  );
}
