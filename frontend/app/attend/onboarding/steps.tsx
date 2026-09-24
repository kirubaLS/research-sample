"use client";

import { motion } from "framer-motion";
import { Compass, Heart, IdCard, Sparkles, Target } from "lucide-react";
import { EASE_OUT } from "@/components/motion";
import { school } from "@/lib/avai-mock-data";
import { ageFrom, type AttendDraft } from "@/lib/attendState";
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
import { ChipGroup, LockedField, Question, StepCard } from "./ui";

const MAX_INTERESTS = 3;
const MAX_GROUP_REASONS = 2;

export interface StepProps {
  draft: AttendDraft;
  patch: (patch: Partial<AttendDraft>) => void;
  showErrors: boolean;
}

function FieldError({ show, children }: { show: boolean; children: React.ReactNode }) {
  if (!show) return null;
  return (
    <motion.div
      role="alert"
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: EASE_OUT }}
      style={{ fontSize: 12.5, fontWeight: 600, color: "var(--risk)" }}
    >
      {children}
    </motion.div>
  );
}

// ---------------------------------------------------------------- Basic Information

export function StepBasicInfo({ draft, patch, showErrors }: StepProps) {
  const id = draft.identity;
  if (!id) return null;
  const age = ageFrom(draft.dob);

  return (
    <StepCard icon={IdCard} eyebrow="Step 1 of 6" title="Basic Information">
      <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        <LockedField label="Full Name" value={id.name} />
        <LockedField label="Roll Number" value={id.rollNo} />
        <LockedField label="Class / Standard" value="Class 10" />
        <LockedField label="Section" value={id.section} />
        <LockedField label="School Name" value={school.name} />
        <LockedField label="Board / Medium" value={school.board} />
      </div>

      <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        <div className="field">
          <label htmlFor="dob">Date of Birth</label>
          <input
            id="dob"
            className="input"
            type="date"
            min="2006-01-01"
            max="2014-12-31"
            value={draft.dob}
            aria-invalid={showErrors && !draft.dob}
            onChange={(e) => patch({ dob: e.target.value })}
          />
          <FieldError show={showErrors && !draft.dob}>Enter your date of birth.</FieldError>
        </div>
        <LockedField label="Age" value={age !== null ? String(age) : "-"} />
      </div>

      <Question label="Gender">
        <ChipGroup groupLabel="Gender" options={genderOptions} selected={draft.gender ? [draft.gender] : []} onChange={([gender]) => patch({ gender })} />
        <FieldError show={showErrors && !draft.gender}>Choose one.</FieldError>
      </Question>
    </StepCard>
  );
}

// ---------------------------------------------------------------- Section 1, Your Background

export function StepBackground({ draft, patch, showErrors }: StepProps) {
  return (
    <StepCard icon={Compass} eyebrow="Step 2 of 6" title="Section 1, Your Background" accent="var(--brand-orange)">
      <Question label="Where do you live?">
        <ChipGroup
          groupLabel="Where you live"
          options={livesInOptions}
          selected={draft.livesIn ? [draft.livesIn] : []}
          accent="var(--brand-orange)"
          onChange={([livesIn]) => patch({ livesIn })}
        />
        <FieldError show={showErrors && !draft.livesIn}>Choose one.</FieldError>
      </Question>

      <Question label="Who usually helps you make important study decisions?">
        <ChipGroup
          groupLabel="Who helps with study decisions"
          options={decisionHelperOptions}
          selected={draft.decisionHelper ? [draft.decisionHelper] : []}
          accent="var(--brand-teal)"
          onChange={([decisionHelper]) => patch({ decisionHelper })}
        />
        <FieldError show={showErrors && !draft.decisionHelper}>Choose one.</FieldError>
      </Question>

      <Question label="Do you have any responsibilities outside school that affect your study plans?">
        <ChipGroup
          groupLabel="Responsibilities outside school"
          options={responsibilitiesOptions}
          selected={draft.hasResponsibilities ? [draft.hasResponsibilities] : []}
          accent="var(--brand-gold)"
          onChange={([hasResponsibilities]) => patch({ hasResponsibilities })}
        />
        <FieldError show={showErrors && !draft.hasResponsibilities}>Choose one.</FieldError>
      </Question>
    </StepCard>
  );
}

// ---------------------------------------------------------------- Section 2, Your Learning Profile

export function StepLearningProfile({ draft, patch, showErrors }: StepProps) {
  return (
    <StepCard icon={Heart} eyebrow="Step 3 of 6" title="Section 2, Your Learning Profile" accent="var(--brand-blue)">
      <Question label="Which subject do you enjoy learning the most?">
        <ChipGroup
          groupLabel="Subject you enjoy most"
          options={subjectOptions}
          selected={draft.favoriteSubject ? [draft.favoriteSubject] : []}
          accent="var(--brand-blue)"
          onChange={([favoriteSubject]) => patch({ favoriteSubject })}
        />
        <FieldError show={showErrors && !draft.favoriteSubject}>Choose one.</FieldError>
      </Question>

      <Question label="Which subject do you feel most comfortable with?">
        <ChipGroup
          groupLabel="Subject you feel most comfortable with"
          options={subjectOptions}
          selected={draft.comfortableSubject ? [draft.comfortableSubject] : []}
          accent="var(--brand-teal)"
          onChange={([comfortableSubject]) => patch({ comfortableSubject })}
        />
        <FieldError show={showErrors && !draft.comfortableSubject}>Choose one.</FieldError>
      </Question>

      <Question label="Which type of learning do you enjoy more?">
        <ChipGroup
          groupLabel="Type of learning you enjoy"
          options={learningTypeOptions}
          selected={draft.learningType ? [draft.learningType] : []}
          accent="var(--brand-gold)"
          onChange={([learningType]) => patch({ learningType })}
        />
        <FieldError show={showErrors && !draft.learningType}>Choose one.</FieldError>
      </Question>
    </StepCard>
  );
}

// ---------------------------------------------------------------- Section 3, Your Interests

export function StepInterests({ draft, patch, showErrors }: StepProps) {
  const atMax = draft.interests.length >= MAX_INTERESTS;

  return (
    <StepCard icon={Sparkles} eyebrow="Step 4 of 6" title="Section 3, Your Interests" accent="var(--brand-green)">
      <Question label="What do you enjoy doing outside studies?" hint={`Select up to ${MAX_INTERESTS}.`}>
        <ChipGroup
          groupLabel="Interests outside studies"
          options={interestOptions}
          selected={draft.interests}
          multi
          accent="var(--brand-green)"
          onChange={(next) => patch({ interests: next.length > MAX_INTERESTS ? next.slice(next.length - MAX_INTERESTS) : next })}
        />
        {atMax && (
          <div className="muted" style={{ fontSize: 12 }}>
            That&apos;s {MAX_INTERESTS}, picking another will replace the first.
          </div>
        )}
        <FieldError show={showErrors && draft.interests.length === 0}>Pick at least one.</FieldError>
      </Question>

      <Question label="Which kind of work sounds interesting to you?">
        <ChipGroup
          groupLabel="Kind of work that sounds interesting"
          options={workInterestOptions}
          selected={draft.workInterest ? [draft.workInterest] : []}
          accent="var(--brand-blue)"
          onChange={([workInterest]) => patch({ workInterest })}
        />
        <FieldError show={showErrors && !draft.workInterest}>Choose one.</FieldError>
      </Question>

      <Question label="When you learn something new, what do you enjoy most?">
        <ChipGroup
          groupLabel="What you enjoy most when learning something new"
          options={newLearningOptions}
          selected={draft.newLearning ? [draft.newLearning] : []}
          accent="var(--brand-teal)"
          onChange={([newLearning]) => patch({ newLearning })}
        />
        <FieldError show={showErrors && !draft.newLearning}>Choose one.</FieldError>
      </Question>
    </StepCard>
  );
}

// ---------------------------------------------------------------- Section 4, Your Future Plans

export function StepFuturePlans({ draft, patch, showErrors }: StepProps) {
  const atMaxReasons = draft.groupReasons.length >= MAX_GROUP_REASONS;

  return (
    <StepCard icon={Target} eyebrow="Step 5 of 6" title="Section 4, Your Future Plans" accent="var(--brand-gold)">
      <Question label="What would you like to become or explore in the future?" htmlFor="future-plan">
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <input
            id="future-plan"
            className="input"
            style={{ flex: "1 1 220px" }}
            placeholder="Type your answer"
            value={draft.futurePlan}
            disabled={draft.futurePlanUnsure}
            onChange={(e) => patch({ futurePlan: e.target.value })}
          />
          <button
            type="button"
            className={`chip${draft.futurePlanUnsure ? " chip--on" : ""}`}
            style={{ "--accent": "var(--brand-gold)" } as React.CSSProperties}
            aria-pressed={draft.futurePlanUnsure}
            onClick={() => patch({ futurePlanUnsure: !draft.futurePlanUnsure, futurePlan: draft.futurePlanUnsure ? draft.futurePlan : "" })}
          >
            Not sure yet
          </button>
        </div>
        <FieldError show={showErrors && !draft.futurePlanUnsure && !draft.futurePlan.trim()}>Type an answer, or choose &quot;Not sure yet&quot;.</FieldError>
      </Question>

      <Question label="Which Class 11 group are you thinking about?">
        <ChipGroup
          groupLabel="Class 11 group"
          options={class11GroupOptions}
          selected={draft.class11Group ? [draft.class11Group] : []}
          accent="var(--brand-blue)"
          onChange={([class11Group]) => patch({ class11Group })}
        />
        <FieldError show={showErrors && !draft.class11Group}>Choose one.</FieldError>
      </Question>

      <Question label="Why are you considering this group?" hint={`Select up to ${MAX_GROUP_REASONS}.`}>
        <ChipGroup
          groupLabel="Why you are considering this group"
          options={groupReasonOptions}
          selected={draft.groupReasons}
          multi
          accent="var(--brand-teal)"
          onChange={(next) => patch({ groupReasons: next.length > MAX_GROUP_REASONS ? next.slice(next.length - MAX_GROUP_REASONS) : next })}
        />
        {atMaxReasons && (
          <div className="muted" style={{ fontSize: 12 }}>
            That&apos;s {MAX_GROUP_REASONS}, picking another will replace the first.
          </div>
        )}
        <FieldError show={showErrors && draft.groupReasons.length === 0}>Pick at least one.</FieldError>
      </Question>

      <Question label="How sure are you about this choice?">
        <ChipGroup
          groupLabel="How sure you are about this choice"
          options={confidenceOptions}
          selected={draft.groupConfidence ? [draft.groupConfidence] : []}
          accent="var(--brand-green)"
          onChange={([groupConfidence]) => patch({ groupConfidence })}
        />
        <FieldError show={showErrors && !draft.groupConfidence}>Choose one.</FieldError>
      </Question>

      <Question label="Which careers or exams have you heard about?">
        <ChipGroup
          groupLabel="Careers or exams you have heard about"
          options={careersKnownOptions}
          selected={draft.careersKnown}
          multi
          accent="var(--brand-orange)"
          onChange={(careersKnown) => patch({ careersKnown })}
        />
        <FieldError show={showErrors && draft.careersKnown.length === 0}>Pick at least one.</FieldError>
      </Question>

      <Question label="Is there anything that may affect your future study choice?">
        <ChipGroup
          groupLabel="What may affect your future study choice"
          options={futureConcernOptions}
          selected={draft.futureConcerns}
          multi
          accent="var(--brand-gold)"
          onChange={(futureConcerns) => patch({ futureConcerns })}
        />
        <FieldError show={showErrors && draft.futureConcerns.length === 0}>Pick at least one.</FieldError>
      </Question>
    </StepCard>
  );
}

// ---------------------------------------------------------------- gating

export function isStepValid(step: number, draft: AttendDraft): boolean {
  if (step === 0) return Boolean(draft.identity) && Boolean(draft.dob) && Boolean(draft.gender);
  if (step === 1) return Boolean(draft.livesIn) && Boolean(draft.decisionHelper) && Boolean(draft.hasResponsibilities);
  if (step === 2) return Boolean(draft.favoriteSubject) && Boolean(draft.comfortableSubject) && Boolean(draft.learningType);
  if (step === 3) return draft.interests.length > 0 && Boolean(draft.workInterest) && Boolean(draft.newLearning);
  if (step === 4)
    return (
      (draft.futurePlanUnsure || draft.futurePlan.trim().length > 0) &&
      Boolean(draft.class11Group) &&
      draft.groupReasons.length > 0 &&
      Boolean(draft.groupConfidence) &&
      draft.careersKnown.length > 0 &&
      draft.futureConcerns.length > 0
    );
  return true;
}
