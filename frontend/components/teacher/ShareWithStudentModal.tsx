"use client";

/**
 * §6.4 -- "Share with student": real PIN issuance against POST
 * /admin/teacher/reports/{id}/share. Three states: pick which issued report to share
 * (skipped when there is exactly one), confirm, then the PIN shown once -- same "shown
 * once" pattern as CopySecret.tsx uses for every other credential this deployment
 * issues, but now a real one, checked by a real student login.
 *
 * The same endpoint doubles as "Reset PIN": sharing an already-shared report replaces
 * its PIN server-side (the old one stops verifying immediately), so picking an
 * already-shared report here and confirming is a reset, not a second share -- no
 * separate endpoint needed, just different copy for that state.
 */

import { useEffect, useState } from "react";
import { CopySecret } from "@/components/CopySecret";
import { api, type IssuedReportRow, type SharedReportView } from "@/lib/api";
import { getApiKey } from "@/lib/session";

export function ShareWithStudentModal({
  studentId,
  studentName,
  onClose,
}: {
  studentId: string;
  studentName: string;
  onClose: () => void;
}) {
  const [reports, setReports] = useState<IssuedReportRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<IssuedReportRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [shared, setShared] = useState<SharedReportView | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .studentIssuedReports(key, studentId)
      .then((res) => {
        setReports(res.reports);
        if (res.reports.length === 1) setPicked(res.reports[0]);
      })
      .catch(() => setError("Could not load this student's reports."));
  }, [studentId]);

  async function share() {
    const key = getApiKey();
    if (!key || !picked) return;
    setBusy(true);
    setError(null);
    try {
      setShared(await api.shareReport(key, picked.report_id, ""));
    } catch {
      setError("Could not share this report.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        {shared ? (
          <>
            <div className="modal__head">
              <h3 style={{ margin: 0 }}>{picked?.shared ? "New PIN issued" : "Report shared"}</h3>
            </div>
            <div className="modal__body">
              <p className="muted">
                Give this {picked?.shared ? "new " : ""}PIN to {studentName} (or their parent), along
                with the class code <strong>{shared.class_code}</strong> and roll number{" "}
                <strong>{shared.roll_no}</strong>. {shared.pin_notice}
              </p>
              <CopySecret value={shared.pin} />
            </div>
            <div className="modal__foot">
              <button type="button" className="btn btn--ghost" onClick={onClose}>
                Done
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="modal__head">
              <h3 style={{ margin: 0 }}>
                {picked?.shared ? `Reset ${studentName}'s PIN?` : `Share a report with ${studentName}?`}
              </h3>
            </div>
            <div className="modal__body">
              {error && (
                <div className="evidence">
                  <p>{error}</p>
                </div>
              )}
              {!reports && !error && <p className="muted">Loading…</p>}
              {reports && reports.length === 0 && (
                <p className="muted">
                  No report has been issued for {studentName} yet -- a principal issues one
                  from the student's own page before it can be shared.
                </p>
              )}
              {reports && reports.length > 1 && (
                <div className="field">
                  <label htmlFor="reportPick">Which report?</label>
                  <select
                    id="reportPick"
                    className="select"
                    value={picked?.report_id ?? ""}
                    onChange={(e) => setPicked(reports.find((r) => r.report_id === e.target.value) ?? null)}
                  >
                    <option value="" disabled>Choose a report</option>
                    {reports.map((r) => (
                      <option key={r.report_id} value={r.report_id}>
                        {r.assessment_title ?? "Report"}: {r.earned}/{r.available}
                        {r.shared ? " (already shared)" : ""}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              {picked && (
                <p className="muted">
                  {picked.shared
                    ? `This gives ${studentName} a fresh PIN for “${picked.assessment_title ?? "this report"}” -- the PIN already handed out stops working the moment this issues.`
                    : `This lets ${studentName} sign in and see “${picked.assessment_title ?? "this report"}”.`}
                </p>
              )}
            </div>
            <div className="modal__foot">
              <button type="button" className="btn btn--ghost" onClick={onClose}>Cancel</button>
              <button type="button" className="btn btn--primary" disabled={!picked || busy} onClick={share}>
                {busy ? "Working…" : picked?.shared ? "Reset PIN" : "Share with student"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
