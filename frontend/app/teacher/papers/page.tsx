"use client";

import { useState } from "react";
import { AlertTriangle, Camera, CheckCircle2, ChevronDown, Loader2, Sparkles, Trash2, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { usePaperScan } from "@/lib/usePaperScan";
import { useGridSheet } from "@/lib/useGridSheet";
import { FilePickButtons } from "@/components/FilePickButtons";
import { usePageHeader } from "@/lib/pageHeader";
import { MarksEntryGrid } from "@/components/MarksEntryGrid";

/** The exam-cell login: every subject, question papers and marks only, no dashboard, no
 * insights, no per-section views -- wired to the real usePaperScan/useGridSheet pipelines
 * (the same hooks the subject-scoped Papers/Marks tabs use), just without a subject or
 * section fixed in advance. */
export default function TeacherPapersPage() {
  usePageHeader({ title: "Question Papers & Marks" });
  const [tab, setTab] = useState<"papers" | "marks">("papers");

  const scan = usePaperScan({
    listPapers: (key) => api.teacherPapers(key),
    listSubjects: (key) => api.subjects(key).then((r) => r.subjects),
  });
  const grid = useGridSheet({ role: "teacher" });

  const [newTitle, setNewTitle] = useState("Cycle Test I");

  return (
    <>
      <p className="page-sub" style={{ marginTop: 0 }}>
        Every subject, question papers and marks only.
      </p>

      <div className="tabs" role="tablist" style={{ marginTop: 18 }}>
        <button role="tab" aria-selected={tab === "papers"} className={`tab ${tab === "papers" ? "tab--active" : ""}`} onClick={() => setTab("papers")}>
          Question papers
        </button>
        <button role="tab" aria-selected={tab === "marks"} className={`tab ${tab === "marks" ? "tab--active" : ""}`} onClick={() => setTab("marks")}>
          Enter marks
        </button>
      </div>

      {tab === "papers" ? (
        <div style={{ marginTop: 18 }}>
          {scan.error && (
            <div className="evidence evidence--gold" style={{ marginBottom: 12 }}>
              <AlertTriangle size={16} />
              <div>{scan.error}</div>
            </div>
          )}

          {!scan.assessmentId ? (
            <>
              <div className="card">
                <div className="card__body" style={{ display: "grid", gap: 12 }}>
                  <div className="filterbar">
                    <div className="filter">
                      <label htmlFor="new-subject">Subject</label>
                      <select id="new-subject" className="select" value={scan.subject} onChange={(e) => scan.setSubject(e.target.value)}>
                        {scan.subjects.map((s) => (
                          <option key={s.subject_code} value={s.subject_code}>
                            {s.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="field">
                      <label htmlFor="new-title">Title</label>
                      <input id="new-title" className="input" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      className="btn btn--primary"
                      onClick={() => {
                        scan.setTitle(newTitle || "Cycle Test I");
                        scan.fileInput.current?.click();
                      }}
                    >
                      <Upload size={14} /> Upload paper file
                    </button>
                    <button
                      className="btn"
                      onClick={() => {
                        scan.setTitle(newTitle || "Cycle Test I");
                        scan.setShowCamera(true);
                      }}
                    >
                      <Camera size={14} /> Photograph paper
                    </button>
                  </div>
                  <input
                    ref={scan.fileInput}
                    type="file"
                    accept=".pdf,image/*"
                    multiple
                    hidden
                    onChange={(e) => {
                      const files = Array.from(e.target.files ?? []);
                      if (files.length) void scan.onFiles(files);
                    }}
                  />
                  {scan.showCamera && (
                    <FilePickButtons
                      accept="image/*"
                      fileLabel="Choose photo"
                      onPick={(file) => {
                        scan.setShowCamera(false);
                        void scan.onFiles([file]);
                      }}
                    />
                  )}
                </div>
              </div>

              <div style={{ display: "grid", gap: 14, marginTop: 14 }}>
                {scan.papers.map((p) => (
                  <div className="card" key={p.id}>
                    <button
                      onClick={() => scan.openPaper(p)}
                      style={{ width: "100%", textAlign: "left", background: "none", border: "none", padding: 0, cursor: "pointer" }}
                    >
                      <div className="card__head">
                        <div>
                          <div className="strong" style={{ fontSize: 15 }}>
                            {p.title}
                          </div>
                          <div className="small muted" style={{ marginTop: 2 }}>
                            {p.subject_label} · {p.questions} question{p.questions === 1 ? "" : "s"} · {p.mapped_questions} mapped ·{" "}
                            {p.students_with_marks} student{p.students_with_marks === 1 ? "" : "s"} marked
                          </div>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <span className={`tag ${p.stage === "mapped" ? "tag--green" : p.stage === "confirmed" ? "tag--gold" : ""}`}>{p.stage}</span>
                          <ChevronDown size={16} className="muted" />
                        </div>
                      </div>
                    </button>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="card">
              <div className="card__head">
                <div>
                  <div className="strong" style={{ fontSize: 15 }}>
                    {scan.title}
                  </div>
                  <div className="small muted" style={{ marginTop: 2 }}>
                    {scan.subject} · {scan.stage}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn btn--sm" onClick={() => scan.onRename()}>
                    Rename
                  </button>
                  <button className="btn btn--sm" onClick={() => scan.onDelete()}>
                    <Trash2 size={13} /> Delete
                  </button>
                  <button className="btn btn--sm" onClick={() => scan.loadPapers().then(() => scan.setError(null))}>
                    Back to list
                  </button>
                </div>
              </div>
              <div className="card__body" style={{ display: "grid", gap: 14 }}>
                {scan.busy && (
                  <div className="small muted" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Loader2 size={14} className="spin" /> {scan.busy}
                  </div>
                )}
                {!scan.scan && !scan.documentId && (
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="btn btn--primary" onClick={() => scan.fileInput.current?.click()}>
                      <Upload size={14} /> Upload scanned pages
                    </button>
                    <button className="btn" onClick={() => scan.setShowCamera(true)}>
                      <Camera size={14} /> Photograph pages
                    </button>
                    <input
                      ref={scan.fileInput}
                      type="file"
                      accept=".pdf,image/*"
                      multiple
                      hidden
                      onChange={(e) => {
                        const files = Array.from(e.target.files ?? []);
                        if (files.length) void scan.onFiles(files);
                      }}
                    />
                  </div>
                )}
                {scan.documentId && !scan.confirmed && (
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <input
                      className="input"
                      style={{ maxWidth: 220 }}
                      placeholder="Your name"
                      value={scan.confirmedBy}
                      onChange={(e) => scan.setConfirmedBy(e.target.value)}
                    />
                    <button className="btn btn--primary btn--sm" onClick={() => scan.onConfirm()}>
                      <CheckCircle2 size={13} /> Confirm reading &amp; map
                    </button>
                  </div>
                )}
                {scan.mapped && scan.mapped.blocked === 0 && !scan.placed && !scan.alreadyClassified && (
                  <button className="btn btn--primary btn--sm" onClick={() => scan.onClassify()}>
                    <Sparkles size={13} /> Read &amp; classify every question
                  </button>
                )}
                {(scan.placed || scan.alreadyClassified) && (
                  <div className="tag tag--green" style={{ width: "fit-content" }}>
                    <CheckCircle2 size={12} /> Classified
                  </div>
                )}
              </div>
            </div>
          )}

          <p className="small muted" style={{ marginTop: 14 }}>
            Real scan, mapping and classification against the backend -- nothing here is simulated.
          </p>
        </div>
      ) : (
        <div style={{ marginTop: 18 }}>
          <div className="filterbar">
            <div className="filter">
              <label htmlFor="marks-paper">Paper</label>
              <select id="marks-paper" className="select" value={grid.paperId} onChange={(e) => grid.pickPaper(e.target.value)}>
                <option value="">Choose a paper…</option>
                {grid.ready.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title} · {p.subject_label}
                  </option>
                ))}
              </select>
            </div>
            <div className="filter">
              <label htmlFor="marks-section">Section</label>
              <select id="marks-section" className="select" value={grid.sectionId} onChange={(e) => grid.pickSection(e.target.value)}>
                <option value="">Choose a class…</option>
                {grid.sections.map((s) => (
                  <option key={s.section_id} value={s.section_id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {grid.paperId && grid.sectionId && (
            <MarksEntryGrid
              key={`${grid.paperId}-${grid.sectionId}`}
              subject={grid.ready.find((p) => p.id === grid.paperId)?.subject_code ?? ""}
              section={grid.sectionId}
              paperId={grid.paperId}
            />
          )}
        </div>
      )}
    </>
  );
}
