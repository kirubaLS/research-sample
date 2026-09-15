"use client";

/**
 * §5.7 -- four empty/limited-evidence states, first-class UI treatments, never styled as
 * an error/failure. Used wherever real data is too thin to support a finding -- these
 * reuse the backend's own evidence-floor/confidence signals (Finding.sufficient,
 * Finding.confidence, CohortReport.top_losses[].confidence) rather than inventing new
 * thresholds on the frontend.
 */

export function TrendNotAvailable() {
  return (
    <div className="bx-empty bx-empty-info">
      <p className="bx-empty-title">Trend not available yet</p>
      <p className="bx-empty-body">
        Trend and consistency insights require at least one additional analysed assessment.
      </p>
      <style jsx>{emptyCss}</style>
    </div>
  );
}

export function EarlySignal() {
  return (
    <div className="bx-empty bx-empty-info">
      <p className="bx-empty-title">Early signal</p>
      <p className="bx-empty-body">
        A possible pattern is visible, but there is not yet enough evidence for a strong
        conclusion.
      </p>
      <style jsx>{emptyCss}</style>
    </div>
  );
}

/**
 * Dependency Index #3 -- "Cause Could Not Be Localized" is not a state the backend names
 * anywhere today. This component renders the neutral/investigative treatment the spec
 * calls for; whether it appears for a given finding is driven by a mock flag a caller
 * passes in, never inferred from real data as if the backend already flags it.
 */
export function CauseNotLocalized({ onReview }: { onReview?: () => void }) {
  return (
    <div className="bx-empty bx-empty-investigate">
      <p className="bx-empty-title">Cause could not be localized</p>
      <p className="bx-empty-body">
        A problem is confirmed here, but BoardX could not localize a single cause with
        enough confidence to name it. Manual answer-script review recommended.
      </p>
      <button type="button" className="bx-empty-cta" onClick={onReview}>
        Review Evidence →
      </button>
      <style jsx>{emptyCss}</style>
    </div>
  );
}

export function PaperUnderTests({ competency = "application readiness" }: { competency?: string }) {
  return (
    <div className="bx-empty bx-empty-info">
      <p className="bx-empty-title">Paper under-tests a competency</p>
      <p className="bx-empty-body">
        This assessment included too few application questions to confidently assess {competency}.
      </p>
      <style jsx>{emptyCss}</style>
    </div>
  );
}

const emptyCss = `
  .bx-empty {
    border-radius: var(--radius-sm, 10px); padding: 14px 16px; margin: 8px 0;
  }
  .bx-empty-info { background: var(--info-soft); }
  /* Deliberately NOT --risk-soft: a confirmed-but-unexplained problem must never read as
     the same "Immediate Attention" red used elsewhere on BoardX -- it is a different kind
     of finding, investigative rather than alarming. */
  .bx-empty-investigate { background: #efe7f7; border: 1px dashed #b7a4d6; }
  .bx-empty-title { margin: 0 0 4px; font-weight: 700; font-size: 14px; color: var(--ink); }
  .bx-empty-body { margin: 0; font-size: 13.5px; color: var(--ink-2); }
  .bx-empty-cta {
    margin-top: 10px; background: none; border: 1.5px solid #6b4fa0; color: #6b4fa0;
    border-radius: 8px; padding: 6px 12px; font-size: 13px; font-weight: 700; cursor: pointer;
  }
`;
