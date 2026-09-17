"use client";

/**
 * §6.4 -- "Share with student": real PIN issuance against POST
 * /admin/teacher/reports/{id}/share. Three states: pick which issued report to share
 * (skipped when there is exactly one), confirm, then the PIN shown once -- same "shown
 * once" pattern as CopySecret.tsx uses for every other credential this deployment
 * issues, but now a real one, checked by a real student login.
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
    <div className="modal-overlay" onClick={onClose}>
      <div className="card sharemodal" onClick={(e) => e.stopPropagation()}>
        {shared ? (
          <>
            <h3 style={{ marginTop: 0 }}>Report shared</h3>
            <p className="cardnote">
              Give this PIN to {studentName} (or their parent), along with the class code{" "}
              <strong>{shared.class_code}</strong> and roll number{" "}
              <strong>{shared.roll_no}</strong>. {shared.pin_notice}
            </p>
            <CopySecret value={shared.pin} />
            <button type="button" className="secondary" style={{ marginTop: 10 }} onClick={onClose}>
              Done
            </button>
          </>
        ) : (
          <>
            <h3 style={{ marginTop: 0 }}>Share a report with {studentName}?</h3>
            {error && <p className="error">{error}</p>}
            {!reports && !error && <p className="muted">Loading…</p>}
            {reports && reports.length === 0 && (
              <p className="cardnote">
                No report has been issued for {studentName} yet -- a principal issues one
                from the student's own page before it can be shared.
              </p>
            )}
            {reports && reports.length > 1 && (
              <div className="field">
                <label htmlFor="reportPick">Which report?</label>
                <select
                  id="reportPick"
                  value={picked?.report_id ?? ""}
                  onChange={(e) => setPicked(reports.find((r) => r.report_id === e.target.value) ?? null)}
                >
                  <option value="" disabled>Choose a report</option>
                  {reports.map((r) => (
                    <option key={r.report_id} value={r.report_id}>
                      {r.assessment_title ?? "Report"} — {r.earned}/{r.available}
                      {r.shared ? " (already shared)" : ""}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {picked && (
              <p className="cardnote">
                This lets {studentName} sign in and see &ldquo;{picked.assessment_title ?? "this report"}&rdquo;.
                {picked.shared && " Sharing again replaces the PIN already handed out -- the old one stops working."}
              </p>
            )}
            <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
              <button type="button" className="secondary" onClick={onClose}>Cancel</button>
              <button type="button" disabled={!picked || busy} onClick={share}>
                {busy ? "Sharing…" : "Share with student"}
              </button>
            </div>
          </>
        )}
      </div>
      <style jsx>{`
        .modal-overlay {
          position: fixed; inset: 0; background: rgba(20, 33, 61, 0.45);
          display: flex; align-items: flex-start; justify-content: center;
          padding: 10vh 16px 0; z-index: 60;
        }
        .sharemodal { max-width: 420px; width: 100%; margin: 0; }
      `}</style>
    </div>
  );
}
