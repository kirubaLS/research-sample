"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { FileUp, Users } from "lucide-react";
import type { PaperSummary } from "@/lib/api";
import { ConfirmedMarksGrid } from "@/components/ConfirmedMarksGrid";
import { MarksEntryGrid } from "@/components/MarksEntryGrid";

export type SectionOption = { section_id: string; label: string };

/** The drawer under a paper in Enter marks: pick the class, then upload its answer sheets
 * (a photographed answer card, a single script, or a spreadsheet) and confirm the marks --
 * MarksEntryGrid is the real pipeline for that. A class whose marks are already confirmed
 * shows them read-only (ConfirmedMarksGrid), with a button to upload more. */
export function AnswerSheetPanel({
  paper, sections, onChanged, mode = "upload",
}: {
  paper: PaperSummary;
  /** the classes that hold this paper's subject */
  sections: SectionOption[];
  /** called when a class's marks may have changed, so the list's counts refresh */
  onChanged: () => void;
  /** "view": only what has been scanned and confirmed, read-only -- nothing to upload */
  mode?: "upload" | "view";
}) {
  const reduce = useReducedMotion();
  const [sectionId, setSectionId] = useState(sections.length === 1 ? sections[0].section_id : "");
  // classes whose paper has no confirmed marks yet (or that the teacher chose to add to)
  const [entry, setEntry] = useState<Set<string>>(new Set());
  // classes with nothing confirmed yet, in "view" mode
  const [empty, setEmpty] = useState<Set<string>>(new Set());
  const key = `${paper.id}:${sectionId}`;

  // a list that arrives after the panel opened, with a single class in it, selects it
  useEffect(() => {
    if (!sectionId && sections.length === 1) setSectionId(sections[0].section_id);
  }, [sections, sectionId]);

  return (
    <div className="as">
      <div className="as__head">
        <div>
          <div className="strong">{mode === "view" ? "Scanned answer sheets" : "Answer sheets"} · {paper.title}</div>
          <div className="small muted">
            {mode === "view"
              ? "Pick a class to see the marks read from its answer sheets."
              : "Pick the class, then upload its answer sheets. Marks are read and shown for you to confirm."}
          </div>
        </div>
      </div>

      {sections.length === 0 ? (
        <p className="small muted" style={{ margin: 0 }}>
          No class holds this subject yet, so there is nobody to enter marks for.
        </p>
      ) : (
        <div className="as__sections" role="radiogroup" aria-label="Class">
          {sections.map((s, i) => (
            <motion.button
              key={s.section_id}
              type="button"
              role="radio"
              aria-checked={sectionId === s.section_id}
              className={`as__chip ${sectionId === s.section_id ? "as__chip--on" : ""}`}
              onClick={() => setSectionId(s.section_id)}
              initial={reduce ? false : { opacity: 0, y: 8, rotateX: -35 }}
              animate={{ opacity: 1, y: 0, rotateX: 0 }}
              transition={{ duration: 0.32, delay: i * 0.04, ease: [0.22, 1, 0.36, 1] }}
              style={{ transformPerspective: 600 }}
            >
              <Users size={13} /> {s.label}
            </motion.button>
          ))}
        </div>
      )}

      <AnimatePresence mode="wait" initial={false}>
        {sectionId && (
          <motion.div
            key={key}
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
            style={{ marginTop: 14 }}
          >
            {mode === "view" ? (
              empty.has(key) ? (
                <p className="small muted" style={{ margin: 0 }}>
                  No answer sheets have been confirmed for this class yet. Upload them from Answer sheets.
                </p>
              ) : (
                <ConfirmedMarksGrid
                  section={sectionId}
                  assessmentId={paper.id}
                  onNotReady={() => setEmpty((prev) => new Set(prev).add(key))}
                />
              )
            ) : entry.has(key) ? (
              <MarksEntryGrid subject={paper.subject_code} section={sectionId} paperId={paper.id} />
            ) : (
              <>
                <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
                  <button
                    type="button"
                    className="btn btn--sm btn--primary"
                    onClick={() => setEntry((prev) => new Set(prev).add(key))}
                  >
                    <FileUp size={13} /> Upload answer sheets
                  </button>
                </div>
                <ConfirmedMarksGrid
                  section={sectionId}
                  assessmentId={paper.id}
                  onNotReady={() => {
                    setEntry((prev) => new Set(prev).add(key));
                    onChanged();
                  }}
                />
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
