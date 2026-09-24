"use client";

import { IdCard } from "lucide-react";
import type { Screen } from "@/lib/api";
import type { AttendDraft, AttendProfile } from "@/lib/attendState";
import { ChipGroup, FieldError, LockedField, Question, StepCard } from "./ui";

/**
 * Step 1: the real profile POST /t/{classCode}/start takes -- name, roll
 * number, section, age, gender, language. The reference design's Basic
 * Information step also showed a locked "Class / Standard" and "Board /
 * Medium" pulled from a hardcoded fake school; this deployment does not
 * carry a school's board on GET /t/classes, so that row is left off rather
 * than shown from nothing (see the gap note in the wiring report).
 */

const GENDER_OPTIONS = [
  { id: "female", label: "Female" },
  { id: "male", label: "Male" },
  { id: "other", label: "Other" },
  { id: "prefer_not_to_say", label: "Prefer not to say" },
];

const LOCALE_OPTIONS = [
  { id: "en", label: "English" },
  { id: "ta", label: "தமிழ்" },
  { id: "hi", label: "हिन्दी" },
];

export interface ProfileStepProps {
  classLabel: string;
  schoolName: string;
  profile: Partial<AttendProfile>;
  patch: (patch: Partial<AttendProfile>) => void;
  showErrors: boolean;
}

export function isProfileValid(profile: Partial<AttendProfile>): boolean {
  return Boolean(profile.name?.trim()) && Boolean(profile.roll_no?.trim()) && Boolean(profile.section?.trim());
}

export function StepBasicInfo({ classLabel, schoolName, profile, patch, showErrors }: ProfileStepProps) {
  return (
    <StepCard icon={IdCard} eyebrow="Before you start" title="Tell us who you are">
      <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        <LockedField label="School" value={schoolName} />
        <LockedField label="Class" value={classLabel} />
      </div>

      <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        <div className="field">
          <label htmlFor="p-name">Your name</label>
          <input
            id="p-name"
            className="input"
            autoComplete="name"
            value={profile.name ?? ""}
            aria-invalid={showErrors && !profile.name?.trim()}
            onChange={(e) => patch({ name: e.target.value })}
          />
          <FieldError show={showErrors && !profile.name?.trim()}>Enter your name.</FieldError>
        </div>
        <div className="field">
          <label htmlFor="p-roll">Roll number</label>
          <input
            id="p-roll"
            className="input"
            inputMode="numeric"
            value={profile.roll_no ?? ""}
            aria-invalid={showErrors && !profile.roll_no?.trim()}
            onChange={(e) => patch({ roll_no: e.target.value })}
          />
          <FieldError show={showErrors && !profile.roll_no?.trim()}>Enter your roll number.</FieldError>
        </div>
        <div className="field">
          <label htmlFor="p-section">Section</label>
          <input
            id="p-section"
            className="input"
            value={profile.section ?? ""}
            aria-invalid={showErrors && !profile.section?.trim()}
            onChange={(e) => patch({ section: e.target.value })}
            placeholder="A"
          />
          <FieldError show={showErrors && !profile.section?.trim()}>Enter your section.</FieldError>
        </div>
        <div className="field">
          <label htmlFor="p-age">Age</label>
          <input
            id="p-age"
            className="input"
            type="number"
            min={8}
            max={25}
            value={profile.age ?? ""}
            onChange={(e) => patch({ age: e.target.value ? Number(e.target.value) : undefined })}
          />
        </div>
      </div>

      <Question label="Gender">
        <ChipGroup
          groupLabel="Gender"
          options={GENDER_OPTIONS}
          selected={profile.gender ? [profile.gender] : []}
          onChange={([gender]) => patch({ gender: gender as AttendProfile["gender"] })}
        />
      </Question>

      <Question label="Language for the questionnaire">
        <ChipGroup
          groupLabel="Language"
          options={LOCALE_OPTIONS}
          selected={profile.locale ? [profile.locale] : ["en"]}
          accent="var(--brand-orange)"
          onChange={([locale]) => patch({ locale: locale as AttendProfile["locale"] })}
        />
      </Question>
    </StepCard>
  );
}

/**
 * Steps 2..N-1: the real 36-item questionnaire, six items to a screen (see
 * SessionPayload.screens from POST /t/{classCode}/start). Every answer is a
 * 1..5 Likert choice against the item's own `options` labels -- there is no
 * fixed option list to import, the server sends them per item.
 */
export function StepLikertScreen({
  screen,
  index,
  total,
  answers,
  onChoose,
}: {
  screen: Screen[];
  index: number;
  total: number;
  answers: AttendDraft["answers"];
  onChoose: (itemId: string, value: number) => void;
}) {
  return (
    <StepCard
      icon={IdCard}
      eyebrow={`Screen ${index + 1} of ${total}`}
      title="How much would you enjoy doing this?"
      lead="There are no right or wrong answers."
    >
      {screen.map((item) => (
        <Question key={item.item_id} label={item.text}>
          <div className="chipset" role="group" aria-label={item.text}>
            {item.options.map((label, i) => {
              const value = i + 1;
              const on = answers[item.item_id]?.value === value;
              return (
                <button
                  key={label}
                  type="button"
                  className={`chip${on ? " chip--on" : ""}`}
                  aria-pressed={on}
                  onClick={() => onChoose(item.item_id, value)}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </Question>
      ))}
    </StepCard>
  );
}
