"use client";

import { useCallback, useEffect, useState } from "react";
import { CameraCapture } from "@/components/CameraCapture";
import { Scanner } from "@/components/Scanner";
import { downloadBlob } from "@/lib/download";
import { newSessionId } from "@/lib/id";
import { pagesToFiles } from "@/lib/pageStore";
import {
  api,
  ApiError,
  ApiUnreachable,
  GridSheetReview,
  GridSheetRowView,
  PaperSummary,
  RosterRow,
  SectionSummary,
} from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { clearJob, getJob, setJob } from "@/lib/jobStore";

/**
 * Reading a class mark-entry sheet: one photograph, many students, read in a single call
 * and staged one row per roll number.
 *
 * A roll already on the roster, whose written name is not too far from the roster's own,
 * needs nothing further -- it is ready to confirm the moment the sheet is read. Anything
 * else -- a roll nobody recognises, a name that does not match -- is shown and left for a
 * person to settle, never guessed at and never silently dropped. Confirming moves every
 * clean row in one call; a flagged row stays exactly where it is until it is resolved.
 */

const STATUS_LABEL: Record<GridSheetRowView["status"], string> = {
  clean: "Ready",
  name_mismatch: "Name doesn't match the roster",
  unmatched: "No student with this roll",
};

type PhotoMode = "class" | "single";

export default function GridSheetPage() {
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [sections, setSections] = useState<SectionSummary[]>([]);
  const [students, setStudents] = useState<RosterRow[]>([]);
  const [paperId, setPaperId] = useState("");
  const [sectionId, setSectionId] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [review, setReview] = useState<GridSheetReview | null>(null);
  const [uploadSummary, setUploadSummary] = useState<string | null>(null);
  const [by, setBy] = useState("");
  const [confirmResult, setConfirmResult] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCamera, setShowCamera] = useState(false);
  const [photoMode, setPhotoMode] = useState<PhotoMode>("class");
  const [sessionId] = useState(() => newSessionId());

  function explain(err: unknown): string {
    if (err instanceof ApiUnreachable) return "Could not reach the API.";
    if (!(err instanceof ApiError)) return "Something went wrong.";
    try {
      const body = JSON.parse(err.message) as { detail?: string };
      if (body.detail) return body.detail;
    } catch {
      /* not JSON */
    }
    return `Request failed (${err.status}).`;
  }

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    (async () => {
      try {
        const [list, overview] = await Promise.all([api.listPapers(key), api.overview(key)]);
        setPapers(list.assessments);
        setSections(overview.sections);
      } catch (err) {
        setError(explain(err));
      }
    })();
  }, []);

  useEffect(() => {
    const key = getApiKey();
    if (!key || !sectionId) {
      setStudents([]);
      return;
    }
    (async () => {
      try {
        setStudents((await api.roster(key, sectionId)).students);
      } catch (err) {
        setError(explain(err));
      }
    })();
  }, [sectionId]);

  const loadReview = useCallback(async (docId: string) => {
    const key = getApiKey();
    if (!key || !paperId || !docId) return;
    try {
      setReview(await api.gridSheet(key, paperId, docId));
    } catch (err) {
      setError(explain(err));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paperId]);

  function gridJobKey(paper: string, section: string): string {
    return `${paper}:${section}`;
  }

  async function uploadPhoto(files: File[]) {
    const key = getApiKey();
    if (!key || !paperId || !sectionId || files.length === 0) return;
    setShowCamera(false);
    setBusy(photoMode === "class" ? "Reading the sheet" : "Reading the script");
    setError(null);
    setUploadSummary(null);
    setConfirmResult(null);
    const scope = gridJobKey(paperId, sectionId);
    const onJobQueued = (jobId: string) => {
      // Persisted the instant the server has queued the vision read, so switching tabs,
      // minimising, or reloading mid-read still resumes the same job server-side rather
      // than looking like nothing was ever uploaded.
      setJob("gridsheet", scope, jobId);
    };
    try {
      const out = photoMode === "class"
        ? await api.uploadGridSheet(key, paperId, sectionId, files, onJobQueued)
        : await api.uploadSingleScript(key, paperId, sectionId, files, onJobQueued);
      clearJob("gridsheet", scope);
      setDocumentId(out.document_id);
      setUploadSummary(
        `${out.rows} row${out.rows === 1 ? "" : "s"} read: ${out.clean} ready, ` +
          `${out.name_mismatch} with a name to check, ${out.unmatched} with no matching student.`,
      );
      await loadReview(out.document_id);
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  // A photo/script read left in flight from an earlier visit to this paper+class -- resume
  // watching it instead of showing an empty upload form as though nothing had started.
  useEffect(() => {
    const key = getApiKey();
    if (!key || !paperId || !sectionId || documentId) return;
    const scope = gridJobKey(paperId, sectionId);
    const jobId = getJob("gridsheet", scope);
    if (!jobId) return;
    let cancelled = false;
    setBusy("Reading the sheet");
    setError(null);
    (async () => {
      try {
        const out = await api.resumeGridSheetJob(key, paperId, jobId);
        if (cancelled) return;
        clearJob("gridsheet", scope);
        setDocumentId(out.document_id);
        setUploadSummary(
          `${out.rows} row${out.rows === 1 ? "" : "s"} read: ${out.clean} ready, ` +
            `${out.name_mismatch} with a name to check, ${out.unmatched} with no matching student.`,
        );
        await loadReview(out.document_id);
      } catch (err) {
        if (cancelled) return;
        clearJob("gridsheet", scope);
        setError(explain(err));
      } finally {
        if (!cancelled) setBusy(null);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paperId, sectionId]);

  async function uploadSpreadsheet(files: FileList | null) {
    const key = getApiKey();
    if (!key || !paperId || !sectionId || !files || files.length === 0) return;
    setBusy("Reading the file");
    setError(null);
    setUploadSummary(null);
    setConfirmResult(null);
    try {
      const out = await api.uploadGridSheetFile(key, paperId, sectionId, Array.from(files));
      setDocumentId(out.document_id);
      setUploadSummary(
        `${out.rows} row${out.rows === 1 ? "" : "s"} read: ${out.clean} ready, ` +
          `${out.unmatched} with no matching student.` +
          (out.problems.length ? ` ${out.problems.join(" ")}` : ""),
      );
      await loadReview(out.document_id);
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  async function downloadAnswerCard() {
    const key = getApiKey();
    if (!key || !paperId || !sectionId) return;
    setBusy("Preparing the answer card");
    setError(null);
    try {
      const blob = await api.answerCardPdf(key, paperId, sectionId);
      const paper = ready.find((p) => p.id === paperId);
      const section = sections.find((s) => s.section_id === sectionId);
      downloadBlob(blob, `${paper?.title ?? "paper"}-${section?.label ?? "class"}-answer-card.pdf`);
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  async function resolveWithStudent(row: GridSheetRowView, studentId: string) {
    const key = getApiKey();
    if (!key || !documentId) return;
    setBusy(`Resolving roll ${row.roll_no}`);
    setError(null);
    try {
      await api.resolveGridRow(key, paperId, documentId, row.row_id, { student_id: studentId });
      await loadReview(documentId);
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  async function resolveWithNewStudent(row: GridSheetRowView, name: string, rollNo: string) {
    const key = getApiKey();
    if (!key || !documentId) return;
    setBusy(`Creating a student for roll ${row.roll_no}`);
    setError(null);
    try {
      await api.resolveGridRow(key, paperId, documentId, row.row_id, {
        create: { name, roll_no: rollNo },
      });
      await loadReview(documentId);
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  async function editMark(
    row: GridSheetRowView, address: string, marks: number | null, state: string,
  ) {
    const key = getApiKey();
    if (!key || !row.student) return;
    if (!by.trim()) {
      setError("Put your name in the box above before editing a mark -- a correction is recorded against who made it.");
      return;
    }
    setBusy(`Saving ${address}`);
    setError(null);
    try {
      await api.editReading(key, paperId, row.student.id, address, { marks, state, by });
      await loadReview(documentId);
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  async function confirmAll() {
    const key = getApiKey();
    if (!key || !documentId) return;
    if (!by.trim()) {
      setError("Put your name to these marks before confirming them.");
      return;
    }
    setBusy("Confirming");
    setError(null);
    try {
      const out = await api.confirmGridSheet(key, paperId, documentId, by);
      await loadReview(documentId);
      const skippedText = out.skipped.length
        ? ` ${out.skipped.length} row${out.skipped.length === 1 ? "" : "s"} skipped: ` +
          out.skipped.map((s) => `roll ${s.roll_no} (${s.reason})`).join(", ") + "."
        : " Nothing was skipped.";
      setConfirmResult(
        `${out.confirmed.length} student${out.confirmed.length === 1 ? "" : "s"} confirmed.` +
          skippedText,
      );
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  const ready = papers.filter((p) => p.ready_for_answer_sheets);

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

      <section className="card" style={{ marginTop: 18 }}>
        <div className="card__body">
        <div className="tabs" style={{ marginBottom: 14, border: "none", boxShadow: "none" }}>
          <button
            type="button"
            className={`tab${photoMode === "class" ? " tab--active" : ""}`}
            onClick={() => setPhotoMode("class")}
          >
            Whole class
          </button>
          <button
            type="button"
            className={`tab${photoMode === "single" ? " tab--active" : ""}`}
            onClick={() => setPhotoMode("single")}
          >
            One student&rsquo;s script
          </button>
        </div>
        <div className="grid grid--2">
          <div className="field">
            <label>Paper</label>
            <select className="select" value={paperId} onChange={(e) => { setPaperId(e.target.value); setDocumentId(""); setReview(null); }}>
              <option value="">Choose a paper…</option>
              {ready.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title} · {p.subject_label} · {p.questions} questions
                  {p.stage === "mapped" ? "" : " (not linked to the book yet)"}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Class</label>
            <select className="select" value={sectionId} onChange={(e) => { setSectionId(e.target.value); setDocumentId(""); setReview(null); }}>
              <option value="">Choose a class…</option>
              {sections.map((s) => (
                <option key={s.section_id} value={s.section_id}>
                  {s.label} · {s.students} students
                </option>
              ))}
            </select>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
          <button
            type="button"
            className="btn btn--ghost"
            disabled={!paperId || !sectionId || !!busy}
            onClick={() => void downloadAnswerCard()}
          >
            Generate blank answer card
          </button>
          <span className="small muted">
            One row per student, one column per question -- print it, hand it out, then
            scan the filled-in sheet back in below.
          </span>
        </div>

        <div className="grid grid--2" style={{ marginTop: 14 }}>
          <div className="field">
            <label>{photoMode === "class" ? "Photograph" : "Photo(s) of the script"}</label>
            <input
              type="file"
              multiple
              accept="image/*"
              disabled={!paperId || !sectionId || !!busy}
              onChange={(e) => void uploadPhoto(Array.from(e.target.files ?? []))}
            />
            {photoMode === "single" && (
              <span className="small muted">
                Select every page of this student&rsquo;s script at once -- they&rsquo;re stored and read together as one script.
              </span>
            )}
          </div>
          <div className="field">
            <label>Spreadsheet or PDF</label>
            <input
              type="file"
              accept=".csv,.tsv,.txt,.xlsx,.xlsm,.pdf"
              disabled={!paperId || !sectionId || !!busy}
              onChange={(e) => void uploadSpreadsheet(e.target.files)}
            />
            <span className="small muted">One row per student, one column per question -- a CSV, an Excel file, or a printed PDF.</span>
          </div>
        </div>

        <div style={{ marginTop: 12 }}>
          <button
            type="button"
            className="btn btn--ghost"
            disabled={!paperId || !sectionId || !!busy}
            onClick={() => setShowCamera((v) => !v)}
          >
            {showCamera ? "Close camera" : "Use camera instead"}
          </button>
        </div>
        {showCamera && photoMode === "class" && (
          <CameraCapture onCapture={(file) => void uploadPhoto([file])} onCancel={() => setShowCamera(false)} />
        )}
        {showCamera && photoMode === "single" && (
          <div style={{ marginTop: 12 }}>
            <p className="muted">Capture each page of the script in order. Retake replaces a single page and keeps its position.</p>
            <Scanner sessionId={sessionId} mode="script" onComplete={(pages) => uploadPhoto(pagesToFiles(pages))} />
          </div>
        )}

        {papers.length > 0 && ready.length === 0 && (
          <p className="small" style={{ color: "var(--brand-gold)", marginTop: 12 }}>
            No paper has been read yet. Scan and confirm one on the Question paper screen
            first. Marks have nothing to attach to until then.
          </p>
        )}
        {uploadSummary && <p className="small" style={{ color: "var(--brand-green)", marginTop: 8 }}>{uploadSummary}</p>}
        </div>
      </section>

      {error && <p style={{ color: "var(--risk)", fontSize: 13.5, marginTop: 12 }}>{error}</p>}
      {busy && <p className="muted" style={{ marginTop: 12 }}>{busy}…</p>}

      {review && (
        <>
          <section className="card" style={{ marginTop: 16, position: "sticky", top: 0, zIndex: 5 }}>
            <div className="card__body">
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", fontSize: 16 }}>
              <div>
                <strong>{review.assessment.title}</strong>
              </div>
              <div>
                <strong>{review.ready_to_confirm}</strong>
                <span className="muted"> of {review.rows.length} ready to confirm</span>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
              <div className="field" style={{ flex: "1 1 180px" }}>
                <label className="small" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0,0,0,0)" }}>Your name</label>
                <input
                  className="input"
                  value={by}
                  onChange={(e) => setBy(e.target.value)}
                  placeholder="Your name"
                  autoComplete="name"
                />
              </div>
              <button className="btn btn--primary" onClick={confirmAll} disabled={!!busy || review.ready_to_confirm === 0}>
                Confirm all ready rows
              </button>
            </div>
            {confirmResult && <p className="small" style={{ color: "var(--brand-green)", marginTop: 8 }}>{confirmResult}</p>}
            </div>
          </section>

          <ol style={{ listStyle: "none", margin: "16px 0 0", padding: 0, display: "grid", gap: 10 }}>
            {review.rows.map((row) => (
              <GridRow
                key={row.row_id}
                row={row}
                students={students}
                busy={!!busy}
                onPick={(studentId) => void resolveWithStudent(row, studentId)}
                onCreate={(name, rollNo) => void resolveWithNewStudent(row, name, rollNo)}
                onEditMark={(address, marks, state) => void editMark(row, address, marks, state)}
              />
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

function GridRow({
  row,
  students,
  busy,
  onPick,
  onCreate,
  onEditMark,
}: {
  row: GridSheetRowView;
  students: RosterRow[];
  busy: boolean;
  onPick: (studentId: string) => void;
  onCreate: (name: string, rollNo: string) => void;
  onEditMark: (address: string, marks: number | null, state: string) => void;
}) {
  const [picked, setPicked] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState(row.name_as_written);
  // Which mark is mid-edit, if any -- one at a time, so a half-typed correction on one
  // cell is never lost by tapping into another before saving it.
  const [editing, setEditing] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const blocked = row.marks.filter((m) => m.problem);
  const borderColor = row.status === "name_mismatch" ? "var(--brand-gold)" : row.status === "unmatched" ? "var(--risk)" : "var(--brand-ink)";

  return (
    <li className="card" style={{ borderLeft: `4px solid ${borderColor}`, background: row.status === "unmatched" ? "var(--risk-soft)" : undefined }}>
      <div className="card__body" style={{ padding: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <span className="strong">
          Roll {row.roll_no}
          {row.student ? ` · ${row.student.name}` : row.name_as_written ? ` · written as “${row.name_as_written}”` : ""}
        </span>
        <span className={`attn ${row.status === "clean" ? "attn--low" : row.status === "name_mismatch" ? "attn--medium" : "attn--high"}`}>{STATUS_LABEL[row.status]}</span>
      </div>

      {row.status === "name_mismatch" && row.student && (
        <p className="small" style={{ margin: "8px 0 0" }}>
          The sheet reads &ldquo;{row.name_as_written}&rdquo; but roll {row.roll_no} on the
          roster is {row.student.name}. If that&rsquo;s the same student, say so below;
          otherwise pick or create the right one.
        </p>
      )}

      {row.marks.length > 0 && (
        <div className="chipset" style={{ margin: "8px 0 0" }}>
          {row.marks.map((m) =>
            editing === m.address ? (
              <span key={m.address} className="chip" style={{ paddingRight: 4 }}>
                <input
                  className="input"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  placeholder="marks"
                  inputMode="decimal"
                  autoFocus
                  style={{ width: 56, padding: "3px 6px", fontSize: 12 }}
                />
                <button
                  type="button"
                  className="btn btn--sm btn--primary"
                  disabled={busy}
                  onClick={() => {
                    const trimmed = editValue.trim();
                    onEditMark(m.address, trimmed === "" ? null : Number(trimmed), trimmed === "" ? "not_offered" : "awarded");
                    setEditing(null);
                  }}
                >
                  Save
                </button>
                <button type="button" className="btn btn--sm btn--ghost" disabled={busy} onClick={() => setEditing(null)}>
                  Cancel
                </button>
              </span>
            ) : (
              <span
                key={m.address}
                className={m.problem ? "tag" : "tag"}
                style={m.problem ? { background: "var(--risk-soft)", color: "var(--risk)", borderColor: "transparent" } : undefined}
                title={row.student ? "Tap to correct this mark" : "Resolve this row to a student before editing its marks"}
              >
                {m.address}: {m.marks ?? (m.raw_value || "N/A")}
                {row.student && (
                  <button
                    type="button"
                    aria-label={`Edit ${m.address}`}
                    disabled={busy}
                    style={{ border: "none", background: "none", cursor: "pointer", padding: 0, opacity: 0.7 }}
                    onClick={() => {
                      setEditValue(m.marks != null ? String(m.marks) : "");
                      setEditing(m.address);
                    }}
                  >
                    ✎
                  </button>
                )}
              </span>
            ),
          )}
        </div>
      )}
      {blocked.length > 0 && (
        <p className="small" style={{ color: "var(--risk)", margin: "8px 0 0" }}>
          {blocked.length} cell{blocked.length === 1 ? "" : "s"} need a look: {blocked.map((m) => `${m.address} (${m.problem})`).join("; ")}
        </p>
      )}

      {row.status !== "clean" && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10, alignItems: "center" }}>
          {row.status === "name_mismatch" && row.student && (
            <button type="button" className="btn btn--primary" onClick={() => onPick(row.student!.id)} disabled={busy}>
              This is {row.student.name}
            </button>
          )}
          {!creating && (
            <>
              <select
                className="select"
                value={picked}
                onChange={(e) => setPicked(e.target.value)}
                disabled={busy || !students.length}
              >
                <option value="">Pick a different student…</option>
                {students.map((s) => (
                  <option key={s.student_id} value={s.student_id}>
                    {s.roll_no}. {s.name}
                  </option>
                ))}
              </select>
              <button type="button" className="btn btn--primary" onClick={() => picked && onPick(picked)} disabled={busy || !picked}>
                Use this student
              </button>
              <button type="button" className="btn btn--ghost" onClick={() => setCreating(true)} disabled={busy}>
                Create a new student
              </button>
            </>
          )}
          {creating && (
            <>
              <input
                className="input"
                style={{ width: "auto" }}
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Student's name"
              />
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => newName.trim() && onCreate(newName.trim(), row.roll_no)}
                disabled={busy || !newName.trim()}
              >
                Create roll {row.roll_no}
              </button>
              <button type="button" className="btn btn--ghost" onClick={() => setCreating(false)} disabled={busy}>
                Cancel
              </button>
            </>
          )}
        </div>
      )}
      </div>
    </li>
  );
}
