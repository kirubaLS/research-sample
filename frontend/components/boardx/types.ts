import type { ConfidenceTier, UrgencyTier } from "./Status";

/**
 * §5.4 -- the one reusable finding unit, used by every BoardX section that shows a
 * finding (Marks Loss, Urgency-vs-Impact, Anomalies, Interventions). Never render a bare
 * stat outside <FindingCard/> on BoardX.
 */
export interface BoardXFinding {
  id: string;
  /** e.g. ["Mathematics", "Quadratic Equations", "Application"] */
  topicPath: string[];
  studentsAffected: number;
  avgMarksLost: number;
  urgencyTier: UrgencyTier;
  yearsAppeared?: number | null;
  yearsEligible?: number | null;
  confidence: ConfidenceTier;
  /** "What BoardX Observed" -- one interpretation sentence, never a bare percentage. */
  interpretation: string;
  /** false only for the deliberately-marked demo of Dependency Index #3 (§5.7) -- never
   *  invented against a real finding the backend has not actually flagged this way. */
  causeLocalized: boolean;
  mostAffectedSections?: { label: string; pct: number }[];
  recommendedAction?: string;
  studentsHref?: string;
}
