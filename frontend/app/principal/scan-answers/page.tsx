"use client";

import { MarksGridPanel } from "@/components/teacher/MarksGridPanel";

/**
 * Principal's twin of teacher/gridsheet -- same real pipeline, school-wide instead of
 * scoped to a teacher's own assignments. Shares lib/useGridSheet.ts and
 * components/teacher/MarksGridPanel.tsx with the teacher and subject-scoped screens.
 */
export default function PrincipalScanAnswersPage() {
  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <p className="eyebrow">Mark-entry sheet</p>
      <h1 className="page-title">Read marks off a photo -- a whole class, or one script</h1>
      <p className="page-sub" style={{ maxWidth: "68ch" }}>
        A whole class&rsquo;s mark-entry sheet in one photo -- one row per roll number, one
        column per question -- or one student&rsquo;s own script, its name and roll read
        straight off the page rather than picked from a list first. A roll already on the
        roster is picked up automatically; anything that doesn&rsquo;t match cleanly,
        including a student missed off the roster entirely, is shown here for a person to
        settle before it counts.
      </p>
      <MarksGridPanel role="principal" />
    </div>
  );
}
