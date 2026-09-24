"use client";

import { PaperPanel } from "@/components/teacher/PaperPanel";
import { api } from "@/lib/api";

/**
 * The principal's twin of app/teacher/paper/page.tsx -- same real scan/confirm/map/
 * classify pipeline (lib/usePaperScan.ts) and the same accordion/modal/drawer panel
 * (components/teacher/PaperPanel.tsx), just backed by the school-wide listPapers/subjects
 * endpoints instead of the teacher-scoped ones.
 */
export default function PrincipalPapersPage() {
  return (
    <>
      <div>
        <p className="eyebrow">Question papers</p>
        <h1 className="page-title" style={{ marginTop: 4 }}>Read a paper, and map it onto the book</h1>
        <p className="page-sub" style={{ maxWidth: "70ch" }}>
          Every question is matched to a chapter, a section and a concept family, all of
          them from the textbook loaded, none of them from memory. A question that cannot
          be matched keeps its place here and says why.
        </p>
      </div>

      <div style={{ marginTop: 18 }}>
        <PaperPanel
          listPapers={(key) => api.listPapers(key)}
          listSubjects={(key) => api.subjects(key).then((r) => r.subjects)}
        />
      </div>
    </>
  );
}
