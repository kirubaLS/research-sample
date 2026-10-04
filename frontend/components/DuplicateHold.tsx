"use client";

import type { PaperSummary } from "@/lib/api";

/**
 * A paper the duplicate check is holding: it matched a paper the school already has, so
 * nothing has been mapped. Shown only while the hold lasts -- the server stops listing
 * the match once the teacher chooses or the paper is mapped -- with the same two choices
 * the scan's own dialog offers. Nothing is ever reused or deleted automatically.
 */
export function DuplicateHold({
  paper, onChoose,
}: {
  paper: PaperSummary;
  onChoose: (paper: PaperSummary, choice: "keep_new" | "open_existing") => void;
}) {
  const best = paper.duplicates_pending?.[0];
  if (!best) return null;
  return (
    <div
      className="small"
      style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 4 }}
      role="status"
    >
      <span className="tag tag--gold">
        Possible duplicate of {best.title} ({Math.round(best.overlap * 100)}%) — not mapped
      </span>
      <button
        type="button"
        className="btn btn--sm"
        onClick={(e) => { e.stopPropagation(); onChoose(paper, "open_existing"); }}
      >
        Open existing
      </button>
      <button
        type="button"
        className="btn btn--sm"
        onClick={(e) => { e.stopPropagation(); onChoose(paper, "keep_new"); }}
      >
        Keep as new
      </button>
    </div>
  );
}
