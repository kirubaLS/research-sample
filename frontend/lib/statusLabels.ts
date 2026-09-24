/** Shared mapping from the real backend's AcademicStatus enum to the labels/CSS
 * accent keys the principal UI already has stylesheet support for (.attn--ontrack /
 * .attn--watch / .attn--intervention). `not_assessed` has no dedicated pill colour in
 * the stylesheet, so it borrows the neutral "medium" accent rather than inventing one. */
import type { AcademicStatus } from "@/lib/api";

export const STATUS_LABEL: Record<AcademicStatus, string> = {
  on_track: "On Track",
  needs_attention: "Need Support",
  requires_review: "At Risk",
  not_assessed: "Not assessed",
};

export const STATUS_PILL_KEY: Record<AcademicStatus, string> = {
  on_track: "ontrack",
  needs_attention: "watch",
  requires_review: "intervention",
  not_assessed: "medium",
};
