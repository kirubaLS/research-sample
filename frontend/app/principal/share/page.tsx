"use client";

/**
 * Share reports -- the bulk version of the "Share ⋮" button already on every class
 * roster (ShareWithStudentModal), for a whole class and one test at once instead of one
 * student at a time.
 *
 * What this cannot be, and does not pretend to be: an actual send. There is no WhatsApp
 * integration in this deployment, and inventing one here -- a phone number field with
 * nowhere real to send to -- would be exactly the kind of thing this codebase refuses to
 * fake. What IS real: issuing a report (POST .../reports/{studentId}/issue, unchanged
 * from the single-student flow) and turning it into a live PIN
 * (POST .../reports/{id}/share, same endpoint ShareWithStudentModal already calls). This
 * screen is that, run over a whole class, with the PIN handed to a person to pass along
 * however their school actually reaches parents -- same "shown once" rule a single share
 * already follows, just gathered into one table instead of one modal at a time.
 *
 * A report already issued for this exact test is reused rather than re-issued: issuing
 * always creates a fresh StudentReport snapshot (by design -- see reports.py's own
 * issue_student_report), so re-issuing on every visit to this screen would pile up
 * duplicate snapshots of marks that have not changed.
 */

import { useEffect, useState } from "react";
import { api, type ClassStudentRow, type IssuedReportRow, type SectionSummary } from "@/lib/api";
import { getApiKey } from "@/lib/session";

type RowStatus = "checking" | "not_issued" | "issued" | "shared";

interface Row {
  student: ClassStudentRow;
  status: RowStatus;
  reportId: string | null;
  pin: string | null;
  error: string | null;
}

export default function ShareReportsPage() {
  const [sections, setSections] = useState<SectionSummary[]>([]);
  const [sectionId, setSectionId] = useState("");
  const [tests, setTests] = useState<{ assessment_id: string; title: string }[]>([]);
  const [assessmentId, setAssessmentId] = useState("");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [by, setBy] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api.overview(key).then((res) => setSections(res.sections)).catch(() => setError("Could not load your classes."));
  }, []);

  useEffect(() => {
    const key = getApiKey();
    if (!key || !sectionId) {
      setTests([]);
      setAssessmentId("");
      return;
    }
    api
      .classStudents(key, sectionId, {})
      .then((res) => {
        setTests(res.filters.tests);
        setAssessmentId((current) => (res.filters.tests.some((t) => t.assessment_id === current) ? current : ""));
      })
      .catch(() => setError("Could not load this class's tests."));
  }, [sectionId]);

  // Every row starts "checking" and resolves independently -- one student's slow or
  // failed lookup must never block the rest of the class from showing its real status.
  useEffect(() => {
    const key = getApiKey();
    if (!key || !sectionId || !assessmentId) {
      setRows(null);
      return;
    }
    let cancelled = false;
    setError(null);
    api
      .classStudents(key, sectionId, { assessmentId })
      .then((res) => {
        if (cancelled) return;
        setRows(res.students.map((student) => ({ student, status: "checking", reportId: null, pin: null, error: null })));
        for (const student of res.students) {
          api
            .studentIssuedReports(key, student.student_id)
            .then((r) => {
              if (cancelled) return;
              const existing = r.reports.find((rep) => rep.assessment_id === assessmentId) ?? null;
              setRows((prev) =>
                prev?.map((row) =>
                  row.student.student_id === student.student_id
                    ? {
                        ...row,
                        status: existing ? (existing.shared ? "shared" : "issued") : "not_issued",
                        reportId: existing?.report_id ?? null,
                      }
                    : row,
                ) ?? null,
              );
            })
            .catch(() => {
              if (cancelled) return;
              setRows((prev) =>
                prev?.map((row) =>
                  row.student.student_id === student.student_id
                    ? { ...row, status: "not_issued", error: "Could not check this student's reports." }
                    : row,
                ) ?? null,
              );
            });
        }
      })
      .catch(() => setError("Could not load this class's roster for that test."));
    return () => {
      cancelled = true;
    };
  }, [sectionId, assessmentId]);

  async function shareOne(row: Row): Promise<void> {
    const key = getApiKey();
    if (!key || !by.trim()) return;
    setRows((prev) =>
      prev?.map((r) => (r.student.student_id === row.student.student_id ? { ...r, error: null } : r)) ?? null,
    );
    try {
      let reportId = row.reportId;
      if (!reportId) {
        const issued = await api.issueReport(key, row.student.student_id, assessmentId, by.trim());
        reportId = issued.report_id;
      }
      const shared = await api.shareReport(key, reportId, by.trim());
      setRows((prev) =>
        prev?.map((r) =>
          r.student.student_id === row.student.student_id
            ? { ...r, status: "shared", reportId, pin: shared.pin, error: null }
            : r,
        ) ?? null,
      );
    } catch {
      setRows((prev) =>
        prev?.map((r) =>
          r.student.student_id === row.student.student_id ? { ...r, error: "Could not share this report." } : r,
        ) ?? null,
      );
    }
  }

  async function shareAllUnsent() {
    if (!rows || !by.trim()) return;
    setBusy("Sharing with everyone not yet shared");
    for (const row of rows) {
      if (row.status === "shared" || row.status === "checking") continue;
      await shareOne(row);
    }
    setBusy(null);
  }

  const unsent = rows?.filter((r) => r.status === "not_issued" || r.status === "issued") ?? [];

  return (
    <div>
      <div>
        <p className="eyebrow">Share</p>
        <h1 className="page-title">Share reports</h1>
        <p className="page-sub">
          Issue and share a PIN for a whole class at once. There is no messaging service
          wired up here -- the PIN is shown once, for you to pass on however your school
          reaches parents.
        </p>
      </div>

      <div className="filterbar" style={{ marginTop: 18 }}>
        <div className="filter" style={{ minWidth: 180 }}>
          <label>Class</label>
          <select className="select" value={sectionId} onChange={(e) => setSectionId(e.target.value)}>
            <option value="">Choose a class…</option>
            {sections.map((s) => (
              <option key={s.section_id} value={s.section_id}>{s.label}</option>
            ))}
          </select>
        </div>
        <div className="filter" style={{ minWidth: 200 }}>
          <label>Test</label>
          <select className="select" value={assessmentId} onChange={(e) => setAssessmentId(e.target.value)} disabled={!sectionId}>
            <option value="">Choose a test…</option>
            {tests.map((t) => (
              <option key={t.assessment_id} value={t.assessment_id}>{t.title}</option>
            ))}
          </select>
        </div>
        <div className="filter" style={{ minWidth: 180 }}>
          <label>Your name</label>
          <input className="input" value={by} onChange={(e) => setBy(e.target.value)} placeholder="required before sharing" />
        </div>
      </div>

      {error && <p style={{ color: "var(--risk)", fontSize: 13.5 }}>{error}</p>}

      {rows && rows.length > 0 && (
        <div className="share-actions" style={{ display: "flex", marginBottom: 14 }}>
          <button
            type="button"
            className="btn btn--primary"
            disabled={!by.trim() || !!busy || unsent.length === 0}
            onClick={() => void shareAllUnsent()}
          >
            {busy ? "Working…" : `Share with everyone not yet shared (${unsent.length})`}
          </button>
        </div>
      )}

      {rows && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Roll</th>
                <th>Name</th>
                <th>Status</th>
                <th>PIN (this session only)</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.student.student_id}>
                  <td>{row.student.roll_no}</td>
                  <td className="strong">{row.student.name}</td>
                  <td>
                    {row.status === "checking" && <span className="muted">Checking…</span>}
                    {row.status === "not_issued" && <span className="muted">Not issued</span>}
                    {row.status === "issued" && <span className="attn attn--medium">Issued, not shared</span>}
                    {row.status === "shared" && <span className="attn attn--low">Shared</span>}
                    {row.error && <p className="small" style={{ color: "var(--risk)", margin: "4px 0 0" }}>{row.error}</p>}
                  </td>
                  <td className="mono">{row.pin ?? "—"}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      disabled={!by.trim() || row.status === "checking"}
                      onClick={() => void shareOne(row)}
                    >
                      {row.status === "shared" ? "Reset PIN" : "Share"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {sectionId && assessmentId && rows?.length === 0 && (
        <p className="muted">No students in this class.</p>
      )}
    </div>
  );
}
