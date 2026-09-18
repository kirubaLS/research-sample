/**
 * Everything in this file is mocked/stub data for BoardX sections whose underlying
 * aggregation does not exist in the backend yet -- see the Backend Dependency Index in
 * the design spec (§5.12). Each export names exactly which index item it stands in for.
 * None of this is wired to a real endpoint; every call site carries its own
 * `// TODO(backend): Dependency Index #N` comment as well.
 */

// TODO(backend): Dependency Index #4 -- "Recoverable Opportunity / Student Potential
// Ladder" needs a distance-to-next-band computation on top of existing student-report
// fields. No such computation exists yet; this is illustrative shape only.
export const MOCK_POTENTIAL_LADDER = {
  atPotential: 62,
  within1Mark: 41,
  within2Marks: 37,
  mostCommonBlocker: "Application-style questions in Quadratic Equations",
};

// TODO(backend): Dependency Index #4 -- "students near next band" + "common blocker" per
// band has no backend computation. Mocked band opportunity rows, shaped like what a real
// endpoint would return once the distance-to-next-band aggregation exists.
export const MOCK_BAND_OPPORTUNITY = [
  { band: "60-79%", studentsNearNextBand: 28, commonBlocker: "Application-tier numerical questions" },
  { band: "80-89%", studentsNearNextBand: 14, commonBlocker: "No dominant common blocker" },
  { band: "Below 60%", studentsNearNextBand: 19, commonBlocker: "Recall of core formulae" },
];

// TODO(backend): Dependency Index #6 -- "Subject Anomaly pattern labels" (Application
// failure / Concept gap / etc.) require a classification layer over tier_summary /
// all_crosstab that does not exist. This is a label lookup used only to *illustrate* the
// shape of a labelled pattern on top of a real per-subject heatmap value; it is never
// derived from the real number beside it.
export const MOCK_PATTERN_LABELS = [
  "Application failure", "Concept gap", "Careless/recall slip", "Time-pressure drop-off",
];

export function mockPatternLabelFor(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return MOCK_PATTERN_LABELS[h % MOCK_PATTERN_LABELS.length];
}

// TODO(backend): Dependency Index #5 -- the combined Intervention Priority score
// (Impact × Marks Exposure × Board Urgency × Confidence) is not computed anywhere yet;
// the founder's own spec keeps the formula unexposed in the UI. The Recommended
// Intervention Plan below therefore keeps the backend's real marks-lost × students-
// affected ordering (already returned sorted this way by GET /reports/cohort) as an
// honest interim proxy, and labels it as such rather than inventing a fake composite
// number.
export const INTERVENTION_PRIORITY_NOTE =
  "Ranked by marks lost × students affected (today's real ordering from the cohort " +
  "report). A combined Intervention Priority score (Impact × Exposure × Board Urgency × " +
  "Confidence) is planned backend work -- see Dependency Index #5.";
