"use client";

/**
 * §6.4 -- "Share with student" confirmation + one-time PIN, mocked (Dependency Index #2:
 * no real PIN issuance / `shared_with_student` flag exists yet). Styled after the
 * existing "shown once" StaffKey pattern (see CopySecret.tsx), same confirmation-then-
 * reveal shape, but generating a mock PIN rather than a real credential.
 */

import { useState } from "react";
import { CopySecret } from "@/components/CopySecret";

function mockPin(): string {
  return String(Math.floor(1000 + Math.random() * 9000));
}

export function ShareWithStudentModal({
  studentName,
  onClose,
}: {
  studentName: string;
  onClose: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [pin] = useState(mockPin);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="card sharemodal" onClick={(e) => e.stopPropagation()}>
        {!confirmed ? (
          <>
            <h3 style={{ marginTop: 0 }}>Share this report?</h3>
            <p className="cardnote">
              This lets {studentName} sign in and see this report. Continue?
            </p>
            <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
              <button type="button" className="secondary" onClick={onClose}>Cancel</button>
              <button type="button" onClick={() => setConfirmed(true)}>Share with student</button>
            </div>
          </>
        ) : (
          <>
            <h3 style={{ marginTop: 0 }}>Report shared</h3>
            <p className="cardnote">
              Give this PIN to {studentName} (or their parent) along with the school code and
              roll number. It is shown once and cannot be retrieved again.
            </p>
            <CopySecret value={pin} />
            <p className="small muted" style={{ marginTop: 10 }}>
              TODO(backend): Dependency Index #2 — this PIN is generated in the browser
              only and unlocks nothing real; no backend PIN-issuance endpoint exists yet.
            </p>
            <button type="button" className="secondary" style={{ marginTop: 10 }} onClick={onClose}>
              Done
            </button>
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
