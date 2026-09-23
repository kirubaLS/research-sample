import type { AcademicStatus } from "@/lib/api";

const LABELS: Record<AcademicStatus, string> = {
  on_track: "On Track",
  needs_attention: "Needs Attention",
  requires_review: "Requires Review",
  not_assessed: "Not Yet Assessed",
};

/** attn is dimension 1 of the reference design's three-part status system -- a solid
 * pill, real colors (see globals.css's own note on why .attn reuses --verify/--warn/
 * --risk rather than the reference's own close-but-different tokens). "Not yet
 * assessed" gets no pill at all: it is an absence of evidence, not a fourth color on the
 * same scale as the other three, so a muted plain label reads more honestly. */
const TONES: Record<AcademicStatus, string> = {
  on_track: "attn--low",
  needs_attention: "attn--medium",
  requires_review: "attn--high",
  not_assessed: "",
};

/** The same on_track/needs_attention/requires_review/not_assessed status every
 * academics screen buckets a student or a test result into, rendered as one badge so
 * the four screens that show it never drift out of sync with each other. */
export function StatusBadge({ status }: { status: AcademicStatus }) {
  const tone = TONES[status];
  if (!tone) return <span className="muted small">{LABELS[status]}</span>;
  return <span className={`attn ${tone}`}>{LABELS[status]}</span>;
}

export function statusLabel(status: AcademicStatus): string {
  return LABELS[status];
}
