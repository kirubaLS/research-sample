"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, CheckCircle2, FileUp, Loader2 } from "lucide-react";
import { api, ApiError, ApiUnreachable, type JobProgress, type PaperSummary } from "@/lib/api";
import { clearJob, setJob } from "@/lib/jobStore";
import { getApiKey } from "@/lib/session";
import { FilePickButtons } from "@/components/FilePickButtons";

export type UploadPhase = "reading" | "matching" | "classifying" | "done" | "held" | "error";
export type UploadState = {
  phase: UploadPhase;
  /** a person-readable line; for "error" what went wrong */
  message?: string;
  /** for "error": the stage that failed */
  at?: UploadPhase;
  done?: number | null;
  total?: number | null;
};

/** Words for an API failure, the same ones usePaperScan.explain uses. */
export function explainUploadError(err: unknown): string {
  if (err instanceof ApiUnreachable) return "Could not reach the API.";
  if (!(err instanceof ApiError)) return "Something went wrong.";
  try {
    const body = JSON.parse(err.message) as { detail?: string };
    if (typeof body.detail === "string" && body.detail) return body.detail;
  } catch {
    /* the body was not JSON; fall through to the status */
  }
  if (err.status === 404) return "That key was not recognised. Please sign in again.";
  return `The API returned ${err.status}.`;
}

const STEPS: { phase: UploadPhase; label: string }[] = [
  { phase: "reading", label: "Reading the paper" },
  { phase: "matching", label: "Matching to the book" },
  { phase: "classifying", label: "Classifying topics" },
];

/** Uploads a question paper straight into a paper row of the list, without leaving it:
 * the file is read, and the server's own pipeline (confirm, map, classify) is followed to
 * the end so the row fills in as it goes. One upload per paper at a time. A paper the
 * school already has is held by the server and shown with its own choice in the row
 * (DuplicateHold), not decided here. */
export function usePaperUploader(onChanged: () => void) {
  const [states, setStates] = useState<Record<string, UploadState>>({});
  const running = useRef(new Set<string>());
  const alive = useRef(true);
  const changed = useRef(onChanged);
  changed.current = onChanged;
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const set = useCallback((id: string, next: UploadState | null) => {
    if (!alive.current) return;
    setStates((prev) => {
      const copy = { ...prev };
      if (next) copy[id] = next;
      else delete copy[id];
      return copy;
    });
  }, []);

  const upload = useCallback(async (paper: PaperSummary, files: File[]) => {
    const key = getApiKey();
    if (files.length === 0 || running.current.has(paper.id)) return;
    if (!key) {
      set(paper.id, { phase: "error", message: "Sign in first." });
      return;
    }
    running.current.add(paper.id);
    let last: UploadPhase = "reading";
    const progress = (phase: UploadPhase) => (p: JobProgress) =>
      set(paper.id, { phase, done: p.progress_done, total: p.progress_total });
    set(paper.id, { phase: "reading" });
    try {
      const scanned = await api.scanPaper(key, paper.id, files, undefined, progress("reading"));
      changed.current();
      const mapJob = scanned.auto?.map_job_id ?? null;
      const placeJob = scanned.auto?.place_job_id ?? null;
      if (mapJob) setJob("paper-map", paper.id, mapJob);
      if (placeJob) setJob("paper-place", paper.id, placeJob);
      if (!mapJob && !placeJob) {
        // held as a possible duplicate, or the automatic pipeline is off: the row says which
        const held = (scanned.duplicates?.length ?? 0) > 0;
        set(paper.id, {
          phase: held ? "held" : "done",
          message: held
            ? "This looks like a paper you already have. Choose below what to do with it."
            : "Paper read. Open it to review and map.",
        });
        return;
      }
      if (mapJob) {
        last = "matching";
        set(paper.id, { phase: "matching" });
        await api.resumeMapJob(key, paper.id, mapJob, progress("matching"));
        clearJob("paper-map", paper.id);
        changed.current();
      }
      if (placeJob) {
        last = "classifying";
        set(paper.id, { phase: "classifying" });
        await api.resumePlacementJob(key, paper.id, placeJob, progress("classifying"));
        clearJob("paper-place", paper.id);
      }
      set(paper.id, { phase: "done", message: "Mapped and ready for answer sheets." });
      changed.current();
    } catch (err) {
      clearJob("paper-map", paper.id);
      clearJob("paper-place", paper.id);
      set(paper.id, { phase: "error", message: explainUploadError(err), at: last });
      changed.current();
    } finally {
      running.current.delete(paper.id);
    }
  }, [set]);

  const clear = useCallback((id: string) => set(id, null), [set]);
  return { states, upload, clear };
}

/** The upload panel that opens under a paper's row: drop files or pick them, watch the
 * three real stages go by. Plain buttons and inputs inside -- no 3D context here, since
 * perspective on a surface that holds a file input is what once swallowed its clicks. */
export function PaperUploadDrawer({
  paper, state, onFiles, onRetry, onClose,
}: {
  paper: PaperSummary;
  state: UploadState | undefined;
  onFiles: (files: File[]) => void;
  /** forget a failed attempt, so the drop zone is offered again */
  onRetry: () => void;
  onClose: () => void;
}) {
  const reduce = useReducedMotion();
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const working = state?.phase === "reading" || state?.phase === "matching" || state?.phase === "classifying";
  const stepIndex = state
    ? STEPS.findIndex((s) => s.phase === (state.phase === "error" ? state.at ?? "reading" : state.phase))
    : -1;
  const finished = state?.phase === "done" || state?.phase === "held";

  function pick(list: FileList | File[] | null) {
    const files = Array.from(list ?? []);
    if (files.length && !working) onFiles(files);
  }

  return (
    <div className="pu">
      <div className="pu__head">
        <div>
          <div className="strong">Upload the question paper</div>
          <div className="small muted">{paper.title} · {paper.subject_label}</div>
        </div>
        <button type="button" className="btn btn--sm" onClick={onClose} disabled={working}>
          {finished ? "Done" : "Close"}
        </button>
      </div>

      {!working && !finished && state?.phase !== "error" && (
        <div
          className={`pu__drop ${over ? "pu__drop--over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files); }}
        >
          <motion.span
            className="pu__icon"
            animate={reduce ? undefined : { y: [0, -5, 0], rotateX: [0, 14, 0] }}
            transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
          >
            <FileUp size={26} />
          </motion.span>
          <div className="pu__title">Drop the paper here</div>
          <div className="small muted">A PDF or photos of its pages. Several files are read as one paper.</div>
          <div className="pu__actions">
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,image/*"
              multiple
              hidden
              onChange={(e) => { pick(e.target.files); e.target.value = ""; }}
            />
            <button type="button" className="btn btn--primary" onClick={() => inputRef.current?.click()}>
              <FileUp size={14} /> Choose file(s)
            </button>
            <FilePickButtons accept="image/*" fileLabel="Choose photo" onPick={(f) => pick([f])} />
          </div>
        </div>
      )}

      {state && (
        <div className="pu__steps" aria-live="polite">
          {STEPS.map((s, i) => {
            const failed = state.phase === "error" && i === Math.max(stepIndex, 0);
            const isDone = finished || (!failed && i < stepIndex);
            const active = working && i === stepIndex;
            return (
              <motion.div
                key={s.phase}
                className={`pu__step ${isDone ? "pu__step--done" : ""} ${active ? "pu__step--active" : ""} ${failed ? "pu__step--failed" : ""}`}
                initial={reduce ? false : { opacity: 0, rotateX: -50, y: 8 }}
                animate={{ opacity: 1, rotateX: 0, y: 0 }}
                transition={{ duration: 0.4, delay: i * 0.08, ease: [0.22, 1, 0.36, 1] }}
                style={{ transformPerspective: 700 }}
              >
                <span className="pu__dot">
                  {active ? <Loader2 size={14} className="spin" /> : isDone ? <CheckCircle2 size={14} /> : failed ? <AlertTriangle size={14} /> : i + 1}
                </span>
                <span>
                  {s.label}
                  {active && state.total != null && (
                    <span className="small muted"> · {state.done ?? "…"} of {state.total}</span>
                  )}
                </span>
              </motion.div>
            );
          })}
        </div>
      )}

      {working && (
        <p className="small muted" style={{ margin: "10px 0 0" }}>
          This runs on the server, so you can keep working. Closing the tab does not stop it.
        </p>
      )}
      {state?.message && (
        <div className={`pu__note ${state.phase === "error" ? "pu__note--error" : ""}`}>
          {state.phase === "error" ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />} {state.message}
        </div>
      )}
      {state?.phase === "error" && (
        <button type="button" className="btn btn--sm" style={{ marginTop: 10 }} onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
