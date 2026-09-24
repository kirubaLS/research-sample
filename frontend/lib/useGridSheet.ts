"use client";

import { useCallback, useEffect, useState } from "react";
import { downloadBlob } from "@/lib/download";
import { newSessionId } from "@/lib/id";
import {
  api,
  ApiError,
  ApiUnreachable,
  GridSheetReview,
  GridSheetRowView,
  PaperSummary,
  RosterRow,
} from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { clearJob, getJob, setJob } from "@/lib/jobStore";

/**
 * Every real piece of state and behaviour behind the class mark-entry-sheet pipeline
 * (one photograph, many students, read in a single call and staged one row per roll
 * number), extracted so it can be shared between the standalone teacher/principal
 * screens and the subject-scoped "Enter marks" panel without duplicating a single real
 * API call or state transition. Nothing here is simulated: every read comes from the
 * real gridsheet endpoints in lib/api.ts, and every write (resolve, edit, confirm) is a
 * real call against the real backend.
 *
 * `role` picks the real endpoints this account is allowed to call (a teacher's calls are
 * scoped to the sections/subjects they are assigned; a principal's are school-wide).
 * `fixed` optionally pins the paper/section pickers, for the subject-scoped embed, where
 * the section is already chosen by the page around it and the paper choice should be
 * narrowed to one subject.
 */

export type PhotoMode = "class" | "single";

export interface GridSectionOption {
  section_id: string;
  label: string;
}

export interface UseGridSheetOptions {
  role: "teacher" | "principal";
  /** Restrict the paper picker to this subject's papers (subject-scoped embed). */
  subjectCode?: string;
  /** Pin the class picker to this section (subject-scoped embed) -- the picker is not
   * shown at all and every load is scoped to this section from the start. */
  fixedSectionId?: string;
}

export function useGridSheet({ role, subjectCode, fixedSectionId }: UseGridSheetOptions) {
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [sections, setSections] = useState<GridSectionOption[]>([]);
  const [students, setStudents] = useState<RosterRow[]>([]);
  const [paperId, setPaperId] = useState("");
  const [sectionId, setSectionId] = useState(fixedSectionId ?? "");
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

  // Load the real paper list and section list for this role. A teacher's section list
  // carries which subjects each section holds, so it is filtered client-side to the
  // paper's own subject; a principal's overview already lists every section in the
  // school with no subject to filter by.
  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    (async () => {
      try {
        if (role === "teacher") {
          const [list, teacherSections] = await Promise.all([api.teacherPapers(key), api.teacherSections(key)]);
          setPapers(list.assessments);
          setAllTeacherSections(teacherSections.sections);
        } else {
          const [list, overview] = await Promise.all([api.listPapers(key), api.overview(key)]);
          setPapers(list.assessments);
          setSections(overview.sections.map((s) => ({ section_id: s.section_id, label: s.label })));
        }
      } catch (err) {
        setError(explain(err));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role]);

  // Kept separate from `sections` for the teacher role only, since it carries the real
  // subjects each section holds and must be re-filtered whenever the chosen paper's
  // subject changes.
  const [allTeacherSections, setAllTeacherSections] = useState<{ section_id: string; label: string | null; subjects: string[] }[]>([]);

  const currentSubject = subjectCode ?? papers.find((p) => p.id === paperId)?.subject_code;

  useEffect(() => {
    if (role !== "teacher") return;
    setSections(
      allTeacherSections
        .filter((s) => !!currentSubject && s.subjects.includes(currentSubject))
        .map((s) => ({ section_id: s.section_id, label: s.label ?? s.section_id })),
    );
  }, [role, allTeacherSections, currentSubject]);

  useEffect(() => {
    const key = getApiKey();
    if (!key || !sectionId) {
      setStudents([]);
      return;
    }
    (async () => {
      try {
        const out = role === "teacher" ? await api.teacherRoster(key, sectionId) : await api.roster(key, sectionId);
        setStudents(out.students);
      } catch (err) {
        setError(explain(err));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionId, role]);

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

  // A mis-scanned or wrong-class upload had no way out except picking a different paper
  // and back again, which does nothing (the same document loads right back via the
  // review fetch above) -- there was no real "start over" for this class's answer sheet,
  // unlike the question-paper flow's own "Remove scan". DELETE /documents/{id} already
  // supports this (see documents.py's own docstring); this just wires a button to it.
  const [removingScan, setRemovingScan] = useState(false);

  async function removeScan() {
    const key = getApiKey();
    if (!key || !documentId) return;
    if (!window.confirm(
      "Remove this scan? The uploaded pages cannot be brought back -- you would need to " +
        "photograph or upload the sheet again. Any student already confirmed from it keeps " +
        "their marks; only the raw scan and its still-unresolved rows go.",
    )) return;
    setRemovingScan(true);
    setError(null);
    try {
      await api.deleteDocument(key, documentId);
      setDocumentId("");
      setReview(null);
      setUploadSummary(null);
      setConfirmResult(null);
    } catch (err) {
      setError(explain(err));
    } finally {
      setRemovingScan(false);
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

  async function editMark(row: GridSheetRowView, address: string, marks: number | null, state: string) {
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
        `${out.confirmed.length} student${out.confirmed.length === 1 ? "" : "s"} confirmed.` + skippedText,
      );
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  function pickPaper(id: string) {
    setPaperId(id);
    if (!fixedSectionId) setSectionId("");
    setDocumentId("");
    setReview(null);
  }

  function pickSection(id: string) {
    setSectionId(id);
    setDocumentId("");
    setReview(null);
  }

  const ready = papers.filter((p) => p.ready_for_answer_sheets && (!subjectCode || p.subject_code === subjectCode));

  return {
    papers,
    ready,
    sections,
    students,
    paperId,
    sectionId,
    documentId,
    review,
    uploadSummary,
    by,
    setBy,
    confirmResult,
    busy,
    error,
    showCamera,
    setShowCamera,
    photoMode,
    setPhotoMode,
    sessionId,
    pickPaper,
    pickSection,
    uploadPhoto,
    uploadSpreadsheet,
    removeScan,
    removingScan,
    downloadAnswerCard,
    resolveWithStudent,
    resolveWithNewStudent,
    editMark,
    confirmAll,
  };
}

export type GridSheetHook = ReturnType<typeof useGridSheet>;
