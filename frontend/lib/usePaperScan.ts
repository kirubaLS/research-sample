"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  ApiUnreachable,
  ConfirmResult,
  MapResult,
  PaperSummary,
  PlaceResult,
  ScanResult,
  ScanReview,
  type Subject,
} from "@/lib/api";
import {
  clearPending,
  clearSession,
  getPending,
  listAllPending,
  listPages,
  setPending,
  type PendingSubmission,
  type ScannedPage,
} from "@/lib/pageStore";
import { getApiKey } from "@/lib/session";
import { newSessionId } from "@/lib/id";
import { clearJob, getJob, setJob } from "@/lib/jobStore";

/** The same conversion the single-student script scanner already uses: a captured page's
 * blob, in capture order, as a real File -- nothing downstream needs to know a camera was
 * involved rather than a file picker. */
export function toFiles(pages: ScannedPage[]): File[] {
  return pages
    .slice()
    .sort((a, b) => a.index - b.index)
    .map((p, i) => new File([p.blob], `page-${i + 1}.jpg`, { type: p.blob.type || "image/jpeg" }));
}

export type Stage = "start" | "scanned" | "confirmed" | "mapped" | "classified";

/**
 * Everything a screen needs to read a question paper and watch the book make sense of
 * it: every real state transition and API call that used to live inside
 * app/teacher/paper/page.tsx's component body, moved here unchanged so it can be shared
 * by that page, app/principal/papers/page.tsx, and a subject-scoped embedded panel,
 * instead of three separately-maintained copies of the same business logic.
 *
 * This hook is pure state/logic -- it renders nothing. `listPapers` and `listSubjects`
 * are passed in because the teacher and principal screens call different, differently
 * scoped endpoints (api.teacherPapers/api.teacherSections vs api.listPapers/api.subjects)
 * for the same shapes.
 */
export function usePaperScan(opts: {
  listPapers: (key: string) => Promise<{ assessments: PaperSummary[] }>;
  listSubjects: (key: string) => Promise<Subject[]>;
  /** Preselects a subject (e.g. deep-linked from a subject-scoped screen) and, once this
   * subject's real papers are in, opens the most recent one automatically. Never
   * fabricates a paper -- with none yet, the subject is simply preselected for creating
   * a new one. */
  prefillSubject?: string | null;
}) {
  const { listPapers: fetchPapers, listSubjects: fetchSubjects, prefillSubject } = opts;

  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subject, setSubject] = useState<string>("");
  const [title, setTitle] = useState("Cycle Test I");
  const [assessmentId, setAssessmentId] = useState<string | null>(null);
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [review, setReview] = useState<ScanReview | null>(null);
  const [mapped, setMapped] = useState<MapResult | null>(null);
  const [placed, setPlaced] = useState<PlaceResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "mapped" | "blocked">("all");
  const [confirmedBy, setConfirmedBy] = useState("");
  const [confirmation, setConfirmation] = useState<ConfirmResult | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [deleted, setDeleted] = useState(false);
  // The scanned document itself (the uploaded pages), separate from the assessment it
  // belongs to -- so a bad scan (wrong file, blurred cover) can be discarded and re-shot
  // without also destroying every question, mapping and mark already recorded against
  // this paper, which is what "Delete paper" does instead.
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [removingScan, setRemovingScan] = useState(false);
  // Every paper already created for this school/teacher, so an existing one can be
  // opened rather than this screen only ever being able to start a new one.
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  // Seeded from an opened paper's own already-known stage (PaperSummary.stage), so the
  // wizard resumes near the right step instead of dropping back to "start" and offering
  // to upload a duplicate scan. Real actions taken in this session (scan/mapped/placed
  // below) still take priority once they happen.
  const [openedStage, setOpenedStage] = useState<Stage | null>(null);
  // Real fact from the DB (see ScanReview.classified), not the run's own spend/summary --
  // those were never persisted, so refresh() does not fabricate a PlaceResult to match.
  const [alreadyClassified, setAlreadyClassified] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const [showCamera, setShowCamera] = useState(false);
  // One id per paper, not per mount: switching subject/paper before Complete would
  // otherwise lose a half-shot paper's pages to a fresh, disconnected session.
  const [scanSessionId] = useState(() => newSessionId());
  // A capture whose pages reached this device but never reached the server -- the
  // backend was unreachable, not that anything was wrong with the scan. Checked for on
  // mount (any tab's leftover, not just this one's) and set the moment an upload fails
  // that way; cleared the moment a retry lands.
  const [pendingResume, setPendingResume] = useState<PendingSubmission | null>(null);
  const [pendingPageCount, setPendingPageCount] = useState(0);
  const [retrying, setRetrying] = useState(false);

  const loadPapers = useCallback(async () => {
    const key = getApiKey();
    if (!key) return;
    try {
      const { assessments } = await fetchPapers(key);
      setPapers(assessments);
    } catch {
      /* the rest of the screen still works; an existing-papers list that failed to load
         just means starting a new one is the only option shown */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    fetchSubjects(key)
      .then((found) => {
        setSubjects(found);
        setSubject((current) =>
          current
          || (prefillSubject && found.some((s) => s.subject_code === prefillSubject) ? prefillSubject : "")
          || found.find((s) => s.book_loaded)?.subject_code
          || found[0]?.subject_code || "",
        );
      })
      .catch(() => setSubjects([]));
    void loadPapers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadPapers, prefillSubject]);

  // Once this subject's real papers are in, open the most recent one automatically so a
  // deep link lands on the paper itself rather than an empty "start" screen when one
  // already exists -- still just a normal openPaper(), no fabricated state.
  useEffect(() => {
    if (!prefillSubject || assessmentId || papers.length === 0) return;
    const match = papers.find((p) => p.subject_code === prefillSubject);
    if (match) void openPaper(match);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillSubject, papers]);

  async function openPaper(p: PaperSummary) {
    const key = getApiKey();
    if (!key) return;
    setError(null);
    setDeleted(false);
    setScan(null);
    setMapped(null);
    setPlaced(null);
    setAlreadyClassified(false);
    setConfirmation(null);
    setDocumentId(null);
    setAssessmentId(p.id);
    setSubject(p.subject_code);
    setTitle(p.title);
    setOpenedStage(p.stage === "empty" ? "start" : p.stage);
    try {
      await refresh(p.id);
    } catch (err) {
      setError(explain(err));
    }
  }

  const confirmed = !!(confirmation || review?.confirmed_at);
  const stage: Stage = placed || alreadyClassified
    ? "classified"
    : mapped
      ? "mapped"
      : confirmed
        ? "confirmed"
        : scan
          ? "scanned"
          : openedStage ?? "start";

  function explain(err: unknown): string {
    if (err instanceof ApiUnreachable) return "Could not reach the API.";
    if (!(err instanceof ApiError)) return "Something went wrong.";
    try {
      const body = JSON.parse(err.message) as { detail?: string };
      if (body.detail) return body.detail;
    } catch {
      /* the body was not JSON; fall through to the status */
    }
    if (err.status === 404) return "That key was not recognised. Please sign in again.";
    return `The API returned ${err.status}.`;
  }

  async function onRename(id?: string, currentTitle?: string) {
    const key = getApiKey();
    const targetId = id ?? assessmentId;
    if (!key || !targetId) return;
    const next = window.prompt("Rename this paper", currentTitle ?? title);
    if (next === null || next.trim() === "" || next === (currentTitle ?? title)) return;
    setRenaming(true);
    setError(null);
    try {
      await api.editAssessment(key, targetId, { title: next.trim() });
      if (targetId === assessmentId) setTitle(next.trim());
      await loadPapers();
    } catch (err) {
      setError(explain(err));
    } finally {
      setRenaming(false);
    }
  }

  async function onDelete(id?: string) {
    const key = getApiKey();
    const targetId = id ?? assessmentId;
    if (!key || !targetId) return;
    if (!window.confirm(
      "Delete this paper? Every scanned question, mapping and mark recorded against it " +
        "goes with it, and none of it can be brought back.",
    )) return;
    setBusy("Deleting the paper…");
    setError(null);
    try {
      await api.deleteAssessment(key, targetId);
      if (targetId === assessmentId) {
        setDeleted(true);
        setAssessmentId(null);
        setScan(null);
        setReview(null);
        setMapped(null);
        setPlaced(null);
        setAlreadyClassified(false);
        setConfirmation(null);
        setDocumentId(null);
        setTitle("Cycle Test I");
      }
      await loadPapers();
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  async function onRemoveScan() {
    const key = getApiKey();
    if (!key || !documentId) return;
    if (!window.confirm(
      "Remove this scan? The uploaded pages cannot be brought back -- you would need to " +
        "photograph or upload the paper again. Nothing already mapped or confirmed on " +
        "this paper is touched; only the original scanned pages go.",
    )) return;
    setRemovingScan(true);
    setError(null);
    try {
      await api.deleteDocument(key, documentId);
      setDocumentId(null);
      setScan(null);
      setReview(null);
      setMapped(null);
      setPlaced(null);
      setAlreadyClassified(false);
      setConfirmation(null);
    } catch (err) {
      setError(explain(err));
    } finally {
      setRemovingScan(false);
    }
  }

  const refresh = useCallback(async (id: string) => {
    const key = getApiKey();
    if (!key) return;
    const data = await api.readScan(key, id);
    setReview(data);

    if (data.staged > 0) {
      const pages = new Set(
        data.questions.map((q) => q.page).filter((p): p is number => p != null),
      );
      setScan({
        route: data.route === "vision" ? "vision" : "text",
        pages: pages.size,
        questions: new Set(data.questions.map((q) => `${q.section ?? ""}|${q.question_no}`)).size,
        sub_parts: data.questions.filter((q) => q.sub_part).length,
        choice_alternatives: data.questions.filter((q) => q.choice_alt).length,
        context_stems: data.questions.filter((q) => q.is_context).length,
        total_marks: data.marks.read,
        staged: data.staged,
        already_promoted: data.mapped,
        declared: data.declared,
        problems: [],
      });
    } else {
      setScan(null);
    }

    const mappingAttempted = data.mapped > 0 || data.questions.some((q) => q.blocked_reason);
    if (mappingAttempted) {
      const blockedRows = data.questions.filter((q) => !q.is_context && q.blocked_reason);
      setMapped({
        retrieval: "lexical",
        mapped: data.mapped,
        blocked: blockedRows.length,
        blocked_addresses: blockedRows.map((q) => q.address),
        needs_review: data.questions.filter((q) => q.mapped_to?.needs_review).length,
        with_topic: data.questions.filter((q) => q.mapped_to?.topic).length,
        context_stems: data.questions.filter((q) => q.is_context).length,
      });
    } else {
      setMapped(null);
    }

    setAlreadyClassified(data.classified);

    try {
      const { documents } = await api.listDocuments(key, id);
      setDocumentId(documents.find((d) => d.kind === "question_paper")?.document_id ?? null);
    } catch {
      setDocumentId(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submitScan(
    scanSubject: string,
    scanTitle: string,
    existingId: string | null,
    files: File[],
    sessionId: string | null,
    resumeJobId?: string,
  ) {
    const key = getApiKey();
    if (!key) {
      setError("Sign in first.");
      return;
    }
    setError(null);
    setBusy(sessionId && pendingResume ? "Retrying…" : "Reading the paper…");
    let id = existingId;
    try {
      if (resumeJobId && id) {
        setScan(await api.resumeScanJob(key, id, resumeJobId));
      } else {
        if (!id) {
          const created = await api.createAssessment(key, { subject_code: scanSubject, title: scanTitle });
          id = created.assessment_id;
          setAssessmentId(id);
        }
        const capturedId = id;
        setScan(await api.scanPaper(key, id, files, (jobId) => {
          if (sessionId) {
            void setPending({
              sessionId, subject: scanSubject, title: scanTitle, assessmentId: capturedId,
              savedAt: Date.now(), jobId,
            });
            setPendingResume((prev) =>
              prev && prev.sessionId === sessionId ? { ...prev, assessmentId: capturedId, jobId } : prev,
            );
          }
        }));
      }
      setMapped(null);
      setConfirmation(null);
      await refresh(id);
      if (sessionId) {
        await clearPending(sessionId);
        setPendingResume(null);
      }
    } catch (err) {
      if (err instanceof ApiUnreachable && sessionId) {
        const existing = await getPending(sessionId);
        const pending: PendingSubmission = {
          sessionId, subject: scanSubject, title: scanTitle, assessmentId: id,
          savedAt: Date.now(), lastError: explain(err), jobId: existing?.jobId ?? resumeJobId,
        };
        await setPending(pending);
        setPendingResume(pending);
        setPendingPageCount(files.length);
      } else {
        if (sessionId) {
          await clearPending(sessionId);
          setPendingResume(null);
        }
        setError(explain(err));
      }
    } finally {
      setBusy(null);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function onFiles(files: File[]) {
    if (!subject) {
      setError("Choose a subject before reading the paper.");
      return;
    }
    await submitScan(subject, title, assessmentId, files, null);
  }

  // On mount, pick up any capture left waiting from a previous visit -- a tab closed, a
  // page reload, the same "the backend was down" reason -- not only one from this
  // session. Runs once; the pages themselves are still exactly where Scanner put them.
  useEffect(() => {
    (async () => {
      const [pending] = await listAllPending();
      if (!pending) return;
      const pages = await listPages(pending.sessionId);
      if (!pages.length) {
        await clearPending(pending.sessionId);
        return;
      }
      setPendingResume(pending);
      setPendingPageCount(pages.length);
    })();
  }, []);

  // Retried automatically, not just offered.
  useEffect(() => {
    if (!pendingResume) return;
    const sessionId = pendingResume.sessionId;
    const timer = window.setInterval(() => {
      void (async () => {
        const current = await getPending(sessionId);
        if (!current) return;
        const pages = await listPages(sessionId);
        if (!pages.length) {
          await clearPending(sessionId);
          setPendingResume(null);
          return;
        }
        setRetrying(true);
        try {
          await submitScan(
            current.subject, current.title, current.assessmentId, toFiles(pages), sessionId,
            current.jobId,
          );
        } finally {
          setRetrying(false);
        }
      })();
    }, 20000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingResume?.sessionId]);

  async function retryPendingNow() {
    if (!pendingResume) return;
    const current = await getPending(pendingResume.sessionId);
    if (!current) return;
    const pages = await listPages(pendingResume.sessionId);
    setRetrying(true);
    try {
      await submitScan(
        current.subject, current.title, current.assessmentId,
        toFiles(pages), current.sessionId, current.jobId,
      );
    } finally {
      setRetrying(false);
    }
  }

  async function discardPending() {
    if (!pendingResume) return;
    if (!window.confirm(`Discard the ${pendingPageCount} captured page(s)? They cannot be brought back.`)) return;
    await clearSession(pendingResume.sessionId);
    setPendingResume(null);
  }

  async function onEdit(address: string, patch: Record<string, unknown>) {
    const key = getApiKey();
    if (!key || !assessmentId) return;
    setError(null);
    try {
      await api.editScanned(key, assessmentId, address, { ...patch, by: confirmedBy || "teacher" });
      await refresh(assessmentId);
    } catch (err) {
      setError(explain(err));
    }
  }

  async function onConfirm() {
    const key = getApiKey();
    if (!key || !assessmentId) return;
    setError(null);
    // Confirm, map and classify chained into one wait: once a teacher has attested to the
    // reading, there is no further human decision needed unless mapping turns up a question
    // it could not place -- so run straight through to the final result instead of making
    // them press three separate buttons and watch three separate stages.
    setBusy("Recording your confirmation…");
    try {
      setConfirmation(await api.confirmScan(key, assessmentId, confirmedBy || "teacher"));
      await refresh(assessmentId);
    } catch (err) {
      setError(explain(err));
      setBusy(null);
      return;
    }
    await onMap();
  }

  async function onMap() {
    const key = getApiKey();
    if (!key || !assessmentId) return;
    setError(null);
    setBusy("Matching every question against the book…");
    try {
      const result = await api.mapPaper(key, assessmentId);
      setMapped(result);
      setPlaced(null);
      await refresh(assessmentId);
      // Only auto-advance to classify when nothing needs a human decision first -- a
      // question mapping could not place is exactly the case where stopping and showing
      // the review table (not the stepper) is the right outcome, not racing past it.
      if (result.blocked === 0) {
        await onClassify();
        return;
      }
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  async function onClassify() {
    const key = getApiKey();
    if (!key || !assessmentId) return;
    setError(null);
    setBusy("Reading each question against the passages it matched (this can take a minute or two)…");
    try {
      setPlaced(await api.placePaper(key, assessmentId, (jobId) => {
        setJob("paper-place", assessmentId, jobId);
      }));
      clearJob("paper-place", assessmentId);
      await refresh(assessmentId);
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(null);
    }
  }

  // A classify run left in flight from an earlier visit -- resume watching it instead of
  // showing the "Read and classify" button as though the paper were untouched.
  useEffect(() => {
    if (!assessmentId) return;
    const jobId = getJob("paper-place", assessmentId);
    if (!jobId || placed || alreadyClassified) return;
    const key = getApiKey();
    if (!key) return;
    let cancelled = false;
    setBusy("Reading each question against the passages it matched (this can take a minute or two)…");
    (async () => {
      try {
        const result = await api.resumePlacementJob(key, assessmentId, jobId);
        if (cancelled) return;
        setPlaced(result);
        clearJob("paper-place", assessmentId);
        await refresh(assessmentId);
      } catch (err) {
        if (cancelled) return;
        clearJob("paper-place", assessmentId);
        setError(explain(err));
      } finally {
        if (!cancelled) setBusy(null);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assessmentId]);

  const rows = (review?.questions ?? []).filter((q) =>
    filter === "all" ? true : filter === "mapped" ? !!q.mapped_to : !q.mapped_to,
  );
  const blockedCount = (review?.questions ?? []).filter((q) => !q.mapped_to).length;

  return {
    // data
    subjects, subject, setSubject, title, setTitle, assessmentId,
    scan, review, mapped, placed, busy, error, setError, filter, setFilter,
    confirmedBy, setConfirmedBy, confirmation, renaming, deleted,
    documentId, removingScan, papers, alreadyClassified, fileInput, showCamera, setShowCamera,
    scanSessionId, pendingResume, pendingPageCount, retrying,
    confirmed, stage, rows, blockedCount,
    // actions
    openPaper, onRename, onDelete, onRemoveScan, onFiles, submitScan,
    onEdit, onConfirm, onMap, onClassify, retryPendingNow, discardPending,
    loadPapers, explain,
  };
}

export type PaperScan = ReturnType<typeof usePaperScan>;
