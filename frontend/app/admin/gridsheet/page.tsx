"use client";

import { useCallback, useEffect, useState } from "react";
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

  async function upload(files: FileList | null) {
    const key = getApiKey();
    if (!key || !paperId || !sectionId || !files || files.length === 0) return;
    setBusy("Reading the sheet");
    setError(null);
    setUploadSummary(null);
    setConfirmResult(null);
    try {
      const out = await api.uploadGridSheet(key, paperId, sectionId, Array.from(files));
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
    <main className="wrap">
      <p className="eyebrow">Mark-entry sheet</p>
      <h1>Read a class sheet, one photo for many students</h1>
      <p className="lede">
        Upload a single mark-entry sheet for a whole class -- one row per roll number, one
        column per question. A roll already on the roster is picked up automatically;
        anything that doesn&rsquo;t match cleanly is shown here for a person to settle
        before it counts.
      </p>

      <section className="panel">
        <div className="picks">
          <label>
            <span>Paper</span>
            <select value={paperId} onChange={(e) => { setPaperId(e.target.value); setDocumentId(""); setReview(null); }}>
              <option value="">Choose a paper…</option>
              {ready.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title} · {p.subject_code} · {p.questions} questions
                  {p.stage === "mapped" ? "" : " (not linked to the book yet)"}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Class</span>
            <select value={sectionId} onChange={(e) => { setSectionId(e.target.value); setDocumentId(""); setReview(null); }}>
              <option value="">Choose a class…</option>
              {sections.map((s) => (
                <option key={s.section_id} value={s.section_id}>
                  {s.label} · {s.students} students
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Photograph</span>
            <input
              type="file"
              multiple
              accept="image/*"
              disabled={!paperId || !sectionId || !!busy}
              onChange={(e) => void upload(e.target.files)}
            />
          </label>
        </div>

        {papers.length > 0 && ready.length === 0 && (
          <p className="warnish">
            No paper has been read yet. Scan and confirm one on the Question paper screen
            first. Marks have nothing to attach to until then.
          </p>
        )}
        {uploadSummary && <p className="ok">{uploadSummary}</p>}
      </section>

      {error && <p className="error">{error}</p>}
      {busy && <p className="muted">{busy}…</p>}

      {review && (
        <>
          <section className="panel sticky">
            <div className="tally">
              <div>
                <strong>{review.assessment.title}</strong>
              </div>
              <div>
                <strong>{review.ready_to_confirm}</strong>
                <span className="muted"> of {review.rows.length} ready to confirm</span>
              </div>
            </div>
            <div className="confirmrow">
              <label>
                <span className="sr">Your name</span>
                <input
                  value={by}
                  onChange={(e) => setBy(e.target.value)}
                  placeholder="Your name"
                  autoComplete="name"
                />
              </label>
              <button onClick={confirmAll} disabled={!!busy || review.ready_to_confirm === 0}>
                Confirm all ready rows
              </button>
            </div>
            {confirmResult && <p className="ok">{confirmResult}</p>}
          </section>

          <ol className="rows">
            {review.rows.map((row) => (
              <GridRow
                key={row.row_id}
                row={row}
                students={students}
                busy={!!busy}
                onPick={(studentId) => void resolveWithStudent(row, studentId)}
                onCreate={(name, rollNo) => void resolveWithNewStudent(row, name, rollNo)}
              />
            ))}
          </ol>
        </>
      )}

      <style jsx>{`
        .wrap { max-width: 900px; margin: 0 auto; padding: 20px 16px 64px; }
        h1 { margin: 0 0 4px; font-size: 26px; }
        .lede { color: #555; margin: 0 0 20px; max-width: 68ch; }
        .panel { border: 1px solid #e3e3e6; border-radius: 12px; padding: 14px; margin-bottom: 16px; background: #fff; }
        .sticky { position: sticky; top: 0; z-index: 5; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
        .picks { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
        .picks label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: #555; }
        select, input { padding: 10px; border: 1px solid #ccc; border-radius: 8px; font-size: 16px; background: #fff; }
        .tally { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; font-size: 16px; }
        .confirmrow { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
        .confirmrow label { flex: 1 1 180px; display: flex; }
        .confirmrow input { width: 100%; }
        button { padding: 10px 16px; border-radius: 8px; border: 0; background: #16324f; color: #fff; font-size: 15px; }
        button[disabled] { opacity: .5; }
        .rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
        .muted { color: #666; }
        .error { color: #a11; }
        .ok { color: #196b2c; margin: 8px 0 0; }
        .warnish { color: #8a5b00; }
        .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
        @media (max-width: 560px) {
          .picks { grid-template-columns: 1fr; }
          .sticky { position: static; }
        }
      `}</style>
    </main>
  );
}

function GridRow({
  row,
  students,
  busy,
  onPick,
  onCreate,
}: {
  row: GridSheetRowView;
  students: RosterRow[];
  busy: boolean;
  onPick: (studentId: string) => void;
  onCreate: (name: string, rollNo: string) => void;
}) {
  const [picked, setPicked] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState(row.name_as_written);

  const blocked = row.marks.filter((m) => m.problem);

  return (
    <li className={`row row-${row.status}`}>
      <div className="head">
        <span className="who">
          Roll {row.roll_no}
          {row.student ? ` · ${row.student.name}` : row.name_as_written ? ` · written as “${row.name_as_written}”` : ""}
        </span>
        <span className={`badge badge-${row.status}`}>{STATUS_LABEL[row.status]}</span>
      </div>

      {row.status === "name_mismatch" && row.student && (
        <p className="note">
          The sheet reads &ldquo;{row.name_as_written}&rdquo; but roll {row.roll_no} on the
          roster is {row.student.name}. If that&rsquo;s the same student, say so below;
          otherwise pick or create the right one.
        </p>
      )}

      {row.marks.length > 0 && (
        <div className="marks">
          {row.marks.map((m) => (
            <span key={m.address} className={m.problem ? "mark mark-bad" : "mark"} title={m.problem ?? undefined}>
              {m.address}: {m.marks ?? (m.raw_value || "—")}
            </span>
          ))}
        </div>
      )}
      {blocked.length > 0 && (
        <p className="note bad">
          {blocked.length} cell{blocked.length === 1 ? "" : "s"} need a look: {blocked.map((m) => `${m.address} (${m.problem})`).join("; ")}
        </p>
      )}

      {row.status !== "clean" && (
        <div className="resolve">
          {row.status === "name_mismatch" && row.student && (
            <button type="button" onClick={() => onPick(row.student!.id)} disabled={busy}>
              This is {row.student.name}
            </button>
          )}
          {!creating && (
            <>
              <select
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
              <button type="button" onClick={() => picked && onPick(picked)} disabled={busy || !picked}>
                Use this student
              </button>
              <button type="button" className="ghost" onClick={() => setCreating(true)} disabled={busy}>
                Create a new student
              </button>
            </>
          )}
          {creating && (
            <>
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Student's name"
              />
              <button
                type="button"
                onClick={() => newName.trim() && onCreate(newName.trim(), row.roll_no)}
                disabled={busy || !newName.trim()}
              >
                Create roll {row.roll_no}
              </button>
              <button type="button" className="ghost" onClick={() => setCreating(false)} disabled={busy}>
                Cancel
              </button>
            </>
          )}
        </div>
      )}

      <style jsx>{`
        .row { border: 1px solid #e3e3e6; border-left: 4px solid #16324f; border-radius: 10px; padding: 12px; background: #fff; }
        .row-name_mismatch { border-left-color: #d9a441; }
        .row-unmatched { border-left-color: #a11; background: #fff7f7; }
        .head { display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; align-items: center; }
        .who { font-weight: 600; }
        .badge { font-size: 12px; padding: 3px 10px; border-radius: 999px; background: #eaf4ec; color: #196b2c; }
        .badge-name_mismatch { background: #fdf1de; color: #8a5b00; }
        .badge-unmatched { background: #fbe9e9; color: #a11; }
        .note { font-size: 13px; color: #555; margin: 8px 0 0; }
        .note.bad { color: #a11; }
        .marks { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 0; }
        .mark { font-size: 12px; background: #f1f2f4; border-radius: 999px; padding: 3px 10px; color: #444; }
        .mark-bad { background: #fbe9e9; color: #a11; }
        .resolve { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; align-items: center; }
        select, input { padding: 8px 10px; border: 1px solid #ccc; border-radius: 8px; font-size: 14px; background: #fff; }
        button { padding: 8px 14px; border-radius: 8px; border: 0; background: #16324f; color: #fff; font-size: 14px; }
        button.ghost { background: transparent; color: #16324f; border: 1px solid #16324f; }
        button[disabled] { opacity: .5; }
      `}</style>
    </li>
  );
}
