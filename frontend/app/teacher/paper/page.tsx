"use client";

import { useSearchParams } from "next/navigation";
import { PaperPanel } from "@/components/teacher/PaperPanel";
import { api } from "@/lib/api";

/**
 * Reading a question paper, and watching the book make sense of it -- the real
 * scan/confirm/map/classify pipeline (lib/usePaperScan.ts), presented as the reference
 * design's accordion-card / upload-modal / mapping-drawer shape (components/teacher/PaperPanel.tsx)
 * instead of the old single-wizard stepper. Every card here is a real paper (api.teacherPapers,
 * scoped server-side to this teacher's own subject assignments); nothing is simulated.
 */
export default function PaperPage() {
  const searchParams = useSearchParams();
  const prefillSubject = searchParams.get("subject");

  return (
    <>
      <div>
        <p className="eyebrow">Question paper</p>
        <h1 className="page-title" style={{ marginTop: 4 }}>Read a paper, and map it onto the book</h1>
        <p className="page-sub" style={{ maxWidth: "70ch" }}>
          Every question is matched to a chapter, a section and a concept family, all of
          them from the textbook you loaded, none of them from memory. A question that
          cannot be matched keeps its place here and says why.
        </p>
      </div>

      <div style={{ marginTop: 18 }}>
        <PaperPanel
          listPapers={(key) => api.teacherPapers(key)}
          listSubjects={async (key) => {
            const [{ subjects: allSubjects }, { sections }] = await Promise.all([
              api.subjects(key),
              api.teacherSections(key),
            ]);
            const held = new Set(sections.flatMap((s) => s.subjects));
            return allSubjects.filter((s) => held.has(s.subject_code));
          }}
          prefillSubject={prefillSubject}
        />
      </div>
    </>
  );
}
