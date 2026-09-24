"use client";

import { MarksGridPanel } from "@/components/teacher/MarksGridPanel";

/**
 * Reading a class mark-entry sheet: one photograph, many students, read in a single call
 * and staged one row per roll number, shown as a pinned-column grid once each row is
 * resolved to a real student. All state and API calls live in lib/useGridSheet.ts,
 * shared with the principal's twin screen and the subject-scoped "Enter marks" panel.
 */
export default function GridSheetPage() {
  return (
    <>
      <p className="eyebrow">Mark-entry sheet</p>
      <h1 className="page-title" style={{ marginTop: 4 }}>Read marks off a photo -- a whole class, or one script</h1>
      <p className="page-sub" style={{ maxWidth: "68ch" }}>
        A whole class&rsquo;s mark-entry sheet in one photo -- one row per roll number, one
        column per question -- or one student&rsquo;s own script, its name and roll read
        straight off the page rather than picked from a list first. A roll already on the
        roster is picked up automatically; anything that doesn&rsquo;t match cleanly,
        including a student missed off the roster entirely, is shown here for a person to
        settle before it counts.
      </p>
      <MarksGridPanel role="teacher" />
    </>
  );
}
