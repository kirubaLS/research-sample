"use client";

/**
 * Reading a student's marks out of a file, and checking them before they count.
 *
 * The order is the point. A file is read into proposals; a person sees every one against
 * the paper's own questions, with the cell it came from and the text that was in it; only
 * then does anything become a mark. Retyping marks is where they get transposed, and a
 * transposed number looks exactly like a read one afterwards -- so the machine proposes
 * and a person disposes.
 *
 * Nothing here repairs anything quietly. A value that could not be read, a mark above what
 * the question is worth, a question the paper does not have: each is shown, each blocks
 * confirmation, and each has to be settled by somebody who saw the paper.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type ReadingSheet, type ReadResult, type ReadRow } from "@/lib/api";
import { getApiKey } from "@/lib/session";

const STATES = [
  ["awarded", "Awarded"],
  ["absent", "Absent"],
  ["not_offered", "Not offered"],
] as const;

export function MarksReader({
  assessmentId,
  studentId,
  by,
  onConfirmed,
}: {
  assessmentId: string;
  studentId: string;
  by: string;
  onConfirmed: () => void;
}) {
  const [sheet, setSheet] = useState<ReadingSheet | null>(null);
  const [result, setResult] = useState<ReadResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  function explain(err: unknown, fallback: string): string {
    if (err instanceof ApiError) {
      try {
        const body = JSON.parse(err.message) as { detail?: string };
        if (body.detail) return body.detail;
      } catch {
        /* not JSON */
      }
    }
    return fallback;
  }

  const refresh = useCallback(async () => {
    const key = getApiKey();
    if (!key) return;
    try {
      const body = await api.reading(key, assessmentId, studentId);
      setSheet(body.read > 0 ? body : null);
    } catch {
      setSheet(null);
    }
  }, [assessmentId, studentId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function send(files: FileList | null) {
    const key = getApiKey();
    if (!key || !files || files.length === 0) return;
    setBusy(files.length > 1 ? `Reading ${files.length} pages` : "Reading the file");
    setError(null);
    try {
      setResult(await api.readMarksFile(key, assessmentId, studentId, Array.from(files)));
      await refresh();
    } catch (err) {
      setResult(null);
      setError(explain(err, "That file could not be read. Nothing was changed."));
    } finally {
      setBusy(null);
      if (input.current) input.current.value = "";
    }
  }

  async function edit(row: ReadRow, marks: string, state: string) {
    const key = getApiKey();
    if (!key) return;
    setError(null);
    try {
      setSheet(
        await api.editReading(key, assessmentId, studentId, row.address, {
          marks: state === "awarded" ? Number(marks) : null,
          state,
          by: by || "unnamed",
        }),
      );
    } catch (err) {
      setError(explain(err, "That correction was not accepted."));
    }
  }

  async function confirm() {
    const key = getApiKey();
    if (!key || !sheet) return;
    if (!by.trim()) {
      setError("Put your name to these marks before confirming them.");
      return;
    }
    setBusy("Confirming");
    try {
      await api.confirmReading(key, assessmentId, studentId, by);
      setSheet(null);
      setResult(null);
      onConfirmed();
    } catch (err) {
      setError(explain(err, "Those marks were not confirmed."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="panel reader">
      <div className="head">
        <div>
          <strong>Read the marks from a file</strong>
          <p className="muted">
            A spreadsheet, a CSV, a PDF, or photographs of the sheet, one or many pages in
            the order you add them. Nothing is recorded until you have checked it below.
            Anything read by text recognition is held until you have looked at it, because
            a recognised number and a read one must never look alike.
          </p>
        </div>
        <input
          ref={input}
          type="file"
          multiple
          accept=".csv,.tsv,.txt,.xlsx,.xlsm,.pdf,image/*"
          onChange={(e) => send(e.target.files)}
          disabled={!!busy}
        />
      </div>

      {busy && <p className="muted">{busy}…</p>}
      {error && <p className="error">{error}</p>}

      {result && (
        <div className="summary">
          <p>
            <strong>{result.read}</strong> of {result.questions_on_paper} questions read
            from <span className="mono">{result.source}</span>.
            {result.used_ocr && " Read by text recognition, so every one needs checking."}
          </p>
          {result.note && <p className="warnish">{result.note}</p>}
          {result.problems.map((p) => (
            <p className="warnish" key={p}>
              {p}
            </p>
          ))}
          {result.unmatched.length > 0 && (
            <>
              <p className="warnish">
                {result.unmatched.length} row
                {result.unmatched.length === 1 ? "" : "s"} in the file could not be matched
                to a question on this paper. They were left out rather than guessed at.
              </p>
              <ul className="unmatched">
                {result.unmatched.map((u, i) => (
                  <li key={`${u.raw_address}-${i}`}>
                    <span className="mono">{u.raw_address || "(blank)"}</span>
                    {u.raw_value ? ` = ${u.raw_value}` : ""} · {u.reason}
                    <span className="muted"> · {u.origin}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {sheet && (
        <>
          <div className="tally">
            <span>
              {sheet.read} read · {sheet.missing} not in the file
              {sheet.blocked > 0 && (
                <>
                  {" "}
                  · <strong className="bad">{sheet.blocked} to settle</strong>
                </>
              )}
            </span>
            <button onClick={confirm} disabled={!sheet.can_confirm || !!busy}>
              Confirm the marks read from the file
            </button>
          </div>
          {!sheet.can_confirm && sheet.blocked > 0 && (
            <p className="warnish">
              Every row with a problem has to be settled first. Nothing is corrected for
              you: a mark nobody checked is a mark nobody can defend.
            </p>
          )}

          <ul className="rows">
            {sheet.questions.map((row) => (
              <ReadingRow key={row.address} row={row} onEdit={edit} />
            ))}
          </ul>
        </>
      )}

      <style jsx>{`
        /* The card styling lives here, not on the page. styled-jsx is scoped per
           component, so borrowing the page's .panel class gave this a class with no rules
           behind it -- a dashed line with no padding, cutting through its own text. */
        .reader {
          border: 1px dashed #c7ccd2;
          border-radius: 12px;
          padding: 14px;
          margin-bottom: 16px;
          background: #fff;
        }
        .head { display: flex; gap: 14px; justify-content: space-between; flex-wrap: wrap; align-items: flex-start; }
        .muted { color: #666; margin: 4px 0 0; font-size: 13px; max-width: 62ch; }
        .error { color: #a11; }
        .warnish { color: #8a5b00; font-size: 13px; }
        .bad { color: #a11; }
        .summary { margin-top: 12px; font-size: 14px; }
        .unmatched { font-size: 13px; padding-left: 18px; color: #444; }
        .tally { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin: 14px 0 8px; font-size: 14px; }
        button { padding: 9px 15px; border-radius: 8px; border: 0; background: #16324f; color: #fff; font-size: 15px; }
        button[disabled] { opacity: 0.5; }
        .rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
        .mono { font-family: ui-monospace, monospace; font-size: 12px; }
      `}</style>
    </section>
  );
}

function ReadingRow({
  row,
  onEdit,
}: {
  row: ReadRow;
  onEdit: (row: ReadRow, marks: string, state: string) => void;
}) {
  const [marks, setMarks] = useState(row.marks == null ? "" : String(row.marks));
  const [state, setState] = useState(row.state ?? "awarded");

  useEffect(() => {
    setMarks(row.marks == null ? "" : String(row.marks));
    setState(row.state ?? "awarded");
  }, [row.marks, row.state]);

  const tone = row.problem ? "bad" : row.read ? "" : "missing";

  return (
    <li className={`row ${tone}`}>
      <div className="top">
        <span className="no">
          {row.section ? `${row.section} · ` : ""}
          {row.question_no}
          {row.choice_alt === "b" ? " (or)" : ""}
        </span>
        <span className="worth">out of {row.max_marks}</span>
      </div>

      <div className="entry">
        <input
          type="number"
          inputMode="decimal"
          min={0}
          max={row.max_marks}
          step={0.5}
          value={marks}
          disabled={state !== "awarded"}
          placeholder={row.read ? "marks" : "not in the file"}
          onChange={(e) => setMarks(e.target.value)}
          onBlur={() => {
            if (state === "awarded" && marks.trim() === "") return;
            onEdit(row, marks, state);
          }}
        />
        <select
          value={state}
          onChange={(e) => {
            setState(e.target.value);
            onEdit(row, marks, e.target.value);
          }}
        >
          {STATES.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {/* Where the number came from, in the file's own words. A disputed mark is asked
          about months later and "which cell was this?" is the first question. */}
      {row.read && (
        <p className="from">
          {row.edited_by
            ? `Corrected by ${row.edited_by}.`
            : `Read “${row.raw_value}” from ${row.origin}${
                row.source_name ? ` in ${row.source_name}` : ""
              }.`}
        </p>
      )}
      {!row.read && <p className="from">This question was not in the file.</p>}
      {row.problem && (
        <p className="problem">
          {row.problem}
          {/* One click for a value that is already right. Retyping a number you can see is
              correct is how a person stops reading them and starts clicking through. */}
          {row.marks != null && (
            <button className="accept" onClick={() => onEdit(row, String(row.marks), state)}>
              It is right, accept {row.marks}
            </button>
          )}
        </p>
      )}

      <style jsx>{`
        li { border: 1px solid #e3e3e6; border-left: 4px solid #16324f; border-radius: 10px; padding: 10px 12px; background: #fff; }
        li.bad { border-left-color: #a11; background: #fff7f7; }
        li.missing { border-left-color: #d9a441; }
        .top { display: flex; justify-content: space-between; gap: 10px; font-size: 15px; }
        .no { font-weight: 600; }
        .worth { color: #666; font-size: 13px; }
        .entry { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
        input { width: 120px; padding: 9px; border: 1px solid #ccc; border-radius: 8px; font-size: 16px; }
        input[disabled] { background: #f4f4f5; color: #999; }
        select { flex: 1 1 160px; padding: 9px; border: 1px solid #ccc; border-radius: 8px; font-size: 16px; background: #fff; }
        .from { margin: 8px 0 0; font-size: 12px; color: #666; }
        .problem { margin: 4px 0 0; font-size: 13px; color: #a11; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .accept {
          background: #fff; border: 1px solid #a11; color: #a11; border-radius: 999px;
          padding: 3px 12px; font-size: 12px; cursor: pointer;
        }
        .accept:hover { background: #a11; color: #fff; }
      `}</style>
    </li>
  );
}
