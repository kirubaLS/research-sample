import type { AcademicStatus } from "@/lib/api";

const LABELS: Record<AcademicStatus, string> = {
  on_track: "On Track",
  needs_attention: "Needs Attention",
  requires_review: "Requires Review",
  not_assessed: "Not Yet Assessed",
};

const TONES: Record<AcademicStatus, string> = {
  on_track: "green",
  needs_attention: "amber",
  requires_review: "red",
  not_assessed: "",
};

/** The same on_track/needs_attention/requires_review/not_assessed status every
 * academics screen buckets a student or a test result into, rendered as one badge so
 * the four screens that show it never drift out of sync with each other. */
export function StatusBadge({ status }: { status: AcademicStatus }) {
  const tone = TONES[status];
  return <span className={`badge${tone ? ` ${tone}` : ""}`}>{LABELS[status]}</span>;
}

export function statusLabel(status: AcademicStatus): string {
  return LABELS[status];
}
