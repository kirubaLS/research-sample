"use client";

import type { DuplicateMatch } from "@/lib/api";

/**
 * A paper the duplicate check is holding: it matched a paper the school already has, so
 * nothing has been mapped and no model call has been spent. Shown only while the hold
 * lasts -- the server stops listing the match once the teacher chooses or the paper is
 * mapped -- with the two choices. Dismissing nothing decides nothing: the paper simply
 * stays held. Nothing is ever reused or deleted automatically.
 */
export function DuplicateHold({
  matches, onChoose,
}: {
  matches: DuplicateMatch[] | null | undefined;
  onChoose: (choice: "keep_new" | "open_existing") => void;
}) {
  const best = matches?.[0];
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
        onClick={(e) => { e.stopPropagation(); onChoose("open_existing"); }}
      >
        Open existing
      </button>
      <button
        type="button"
        className="btn btn--sm"
        onClick={(e) => { e.stopPropagation(); onChoose("keep_new"); }}
      >
        Keep as new
      </button>
    </div>
  );
}
