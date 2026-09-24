"use client";

/**
 * One student, one paper: where they are strong, where to work, and the proof.
 *
 * Two rules run through the whole layout.
 *
 * Every figure shows its denominator and the questions it came from. A rate with no
 * questions behind it is an assertion, and a teacher who cannot check a number by hand
 * against the mark sheet has been asked to trust us instead.
 *
 * Nothing the paper cannot support is stated. A topic under the evidence floor says so
 * instead of showing a percentage, an unattempted alternative is absence of evidence
 * rather than weakness, and a board unit the paper never tested is a coverage gap rather
 * than a silence.
 *
 * It prints. The browser's own print-to-PDF is the whole feature: no server rendering, no
 * second layout to keep in step with this one, and what a parent receives is what the
 * teacher saw on screen.
 */

import { useState } from "react";
import type { Finding, Proof, StudentDiagnosis } from "@/lib/api";

const AXIS_LABEL: Record<string, string> = {
  concept_family: "Concept",
  subtopic: "Sub-topic",
  chapter: "Chapter",
};

const TIER_LABEL: Record<string, string> = {
  "R&U": "Recall and understanding",
  AP: "Application",
  AEC: "Analysis, evaluation and creation",
};

function pct(rate: number | null): string {
  return rate === null ? "not scored" : `${Math.round(rate * 100)}%`;
}

function confClass(confidence: Finding["confidence"]): string {
  if (confidence === "HIGH") return "conf--high";
  if (confidence === "MEDIUM") return "conf--medium";
  return "conf--emerging";
}

function urgClass(tier: string | null | undefined): string {
  if (tier === "VERY HIGH") return "urg--very_high";
  if (tier === "HIGH") return "urg--high";
  if (tier === "MEDIUM") return "urg--medium";
  return "urg--low";
}

/** Plain words for what a Wilson interval is really saying -- a teacher or a parent has
 *  no reason to know what "95% interval" or "Wilson" means, and shouldn't need to. Only
 *  ever called where `finding.sufficient` is true, so confidence is always HIGH or MEDIUM
 *  here (EMERGING only happens when insufficient, a different branch entirely). */
function reliabilityNote(confidence: Finding["confidence"], questions: number): string {
  if (confidence === "HIGH") {
    return `Based on enough questions in this paper (${questions}) to trust this number.`;
  }
  return `Based on only ${questions} question${questions === 1 ? "" : "s"} in this paper -- ` +
    "treat this as a rough signal, not an exact score.";
}

/** Tier keys are short codes with no label of their own; everything else arrives named. */
function readable(f: Finding): string {
  return TIER_LABEL[f.key] ?? f.label ?? f.key;
}

export function Diagnosis({
  report,
  student,
}: {
  report: StudentDiagnosis;
  student: { name: string; roll_no: string };
}) {
  const axis = AXIS_LABEL[report.topic_axis] ?? "Topic";
  const total = report.total;

  return (
    <section className="section">
      <div className="card" style={{ marginBottom: 20 }}>
        <div
          className="card__body"
          style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 14, flexWrap: "wrap" }}
        >
          <div>
            <h2 className="page-title" style={{ fontSize: 20 }}>{report.assessment_title}</h2>
            <p className="muted" style={{ marginTop: 4 }}>
              {student.name} · roll {student.roll_no}
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="stat__value">
              {total.earned} / {total.available}
            </div>
            <div className="stat__label" style={{ textTransform: "none" }}>
              {pct(total.rate)} across {total.questions} question
              {total.questions === 1 ? "" : "s"}
            </div>
          </div>
          <button className="btn btn--ghost btn--sm printbtn" onClick={() => window.print()}>
            Print or save as PDF
          </button>
        </div>
      </div>

      <p className="muted" style={{ fontSize: 13.5, maxWidth: "68ch" }}>
        Grouped by {axis.toLowerCase()}, the finest grouping this paper supports. Every
        figure below shows the marks it was computed from, and any topic with too little
        in this paper says so rather than showing a percentage.
      </p>

      <Band
        title="Strengths"
        empty="No topic in this paper cleared the bar for a strength."
        findings={report.strengths}
      />
      <Band
        title="Where to work next"
        empty="Nothing in this paper stands out as needing attention first."
        findings={report.focus}
      />

      {report.tier_summary.length > 0 && (
        <>
          <h3 className="section-q" style={{ marginTop: 26, marginBottom: 6 }}>By what the question asked for</h3>
          <p className="muted" style={{ fontSize: 13.5, maxWidth: "68ch" }}>
            High recall with low application on the same material is the &ldquo;knows the
            formula, cannot apply it&rdquo; signature. It is only visible when the paper
            contains both, which is why each row carries its own question count.
          </p>
          <div className="grid" style={{ gap: 8, marginTop: 10 }}>
            {report.tier_summary.map((f) => (
              <Row key={f.key} finding={f} label={readable(f)} />
            ))}
          </div>
        </>
      )}

      <h3 className="section-q" style={{ marginTop: 26, marginBottom: 6 }}>Every {axis.toLowerCase()} in this paper</h3>
      <div className="grid" style={{ gap: 8 }}>
        {report.topics.map((f) => (
          <Row key={f.key} finding={f} label={readable(f)} compact />
        ))}
      </div>

      {report.coverage_gaps.length > 0 && (
        <>
          <h3 className="section-q" style={{ marginTop: 26, marginBottom: 6 }}>What this paper did not test</h3>
          <p className="muted" style={{ fontSize: 13.5, maxWidth: "68ch" }}>
            These carry marks in the board&rsquo;s own weighting, so a result here says
            nothing about them either way.
          </p>
          <ul className="list-plain muted" style={{ fontSize: 13.5 }}>
            {report.coverage_gaps.map((g) => (
              <li key={g.board_unit}>
                {/* board_weight is already a percentage. Multiplying by 100 here printed
                    "600% of board marks" for a unit worth 6%. */}
                <strong className="text">{g.label}</strong> · {Math.round(g.board_weight)}% of board marks.{" "}
                {g.message}
              </li>
            ))}
          </ul>
        </>
      )}

      {report.not_offered.length > 0 && (
        <p className="muted" style={{ fontSize: 13.5, maxWidth: "68ch", marginTop: 14 }}>
          {report.not_offered.length} question
          {report.not_offered.length === 1 ? " was" : "s were"} the unattempted half of a
          choice. Those are left out of every figure above: choosing not to answer one of
          two alternatives is not evidence of weakness, and scoring it zero would mark this
          student weak in whichever topic they chose to avoid.
        </p>
      )}

      <style jsx>{`
        @media print {
          .printbtn { display: none; }
        }
      `}</style>
    </section>
  );
}

function Band({
  title,
  findings,
  empty,
}: {
  title: string;
  findings: Finding[];
  empty: string;
}) {
  return (
    <>
      <h3 className="section-q" style={{ marginTop: 26, marginBottom: 6 }}>{title}</h3>
      {findings.length === 0 ? (
        <p className="muted" style={{ fontSize: 13.5, maxWidth: "68ch" }}>{empty}</p>
      ) : (
        <div className="grid" style={{ gap: 8 }}>
          {findings.map((f) => (
            <Row key={`${f.scope}-${f.key}`} finding={f} label={readable(f)} />
          ))}
        </div>
      )}
    </>
  );
}

function Row({
  finding,
  label,
  compact,
}: {
  finding: Finding;
  label: string;
  /** The full list repeats what the two bands above already showed. On paper its proof
      stays folded, so a printed sheet does not carry every question twice. */
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const width = finding.rate === null ? 0 : Math.round(finding.rate * 100);

  return (
    <div className={`finding${finding.sufficient ? "" : " finding--not-localized"}${compact ? " finding--compact" : ""}`}>
      <div className="finding__head">
        <div>
          {/* A concept or sub-topic name means little on its own -- "Finding the mean of
              ungrouped data" is unplaceable without "Statistics" in front of it. */}
          {finding.chapter && <div className="finding__subject">{finding.chapter}</div>}
          <div className="finding__title" style={{ fontSize: 15 }}>{label}</div>
        </div>
        <span>
          {finding.sufficient ? (
            <>
              <strong>{pct(finding.rate)}</strong>
              <span className="muted small">
                {" "}
                · {finding.earned} of {finding.available} marks over {finding.questions}{" "}
                question{finding.questions === 1 ? "" : "s"}
              </span>
            </>
          ) : (
            <span className="muted small" style={{ fontStyle: "italic" }}>
              {finding.message ?? "not enough in this paper to report a figure"}
            </span>
          )}
        </span>
      </div>

      {(finding.sufficient || finding.board?.urgency_tier) && (
        <div className="finding__status">
          {finding.sufficient && (
            <span className={`conf ${confClass(finding.confidence)}`}>
              <span className="conf__dots">
                <span className="conf__dot" />
                <span className="conf__dot" />
                <span className="conf__dot" />
              </span>
              {finding.confidence} confidence
            </span>
          )}
          {finding.board?.urgency_tier && (
            <span className={`urg ${urgClass(finding.board.urgency_tier)}`}>
              Board urgency: {finding.board.urgency_tier}
            </span>
          )}
          {finding.board?.board_weight_pct != null && (
            <span className="tag tag--info">
              {Math.round(finding.board.board_weight_pct)}% of board marks
            </span>
          )}
        </div>
      )}
      {finding.board?.note && <p className="finding__obs">{finding.board.note}</p>}

      {finding.sufficient && (
        <div style={{ padding: "10px 18px 0" }}>
          <div className="bar" aria-hidden>
            <div className="bar__fill" style={{ width: `${width}%` }} />
          </div>
          {finding.ci && (
            <p className="muted small" style={{ marginTop: 6 }}>{reliabilityNote(finding.confidence, finding.questions)}</p>
          )}
        </div>
      )}

      {finding.evidence.length > 0 && (
        <div className="finding__foot proofwrap">
          <button type="button" className="btn--link" onClick={() => setOpen(!open)}>
            {open ? "Hide" : "Show"} the {finding.evidence.length} question
            {finding.evidence.length === 1 ? "" : "s"} behind this
          </button>
          {/* Always in the DOM, hidden with CSS when collapsed. Rendering it only when
              open kept it out of the printed sheet entirely, and a printed report without
              the questions behind each figure is exactly the thing a parent cannot check. */}
          <ul className={`list-plain proof${open ? "" : " collapsed"}${compact ? " compact" : ""}`}>
            {finding.evidence.map((p, i) => (
              <ProofRow key={`${p.question_no}-${i}`} proof={p} />
            ))}
          </ul>
        </div>
      )}

      <style jsx>{`
        .proofwrap { display: block; }
        .proof { margin: 8px 0 0; }
        .proof.collapsed { display: none; }
        @media print {
          .proofwrap :global(.btn--link) { display: none; }
          .proof.collapsed { display: grid; }
          .proof.collapsed.compact { display: none; }
        }
      `}</style>
    </div>
  );
}

/**
 * One question, as it was read off the paper, and how it came to be counted here.
 *
 * A placement a person confirmed and one the model guessed at 0.41 produce the same
 * label. Showing only the label makes them indistinguishable, so both are shown.
 */
function ProofRow({ proof }: { proof: Proof }) {
  const p = proof.placement;
  return (
    <li className="p">
      <span className="q">
        {proof.section ? `${proof.section} · ` : ""}
        {proof.question_no}
        {proof.sub_part ? `(${proof.sub_part})` : ""}
        {proof.choice_alt === "b" ? " (or)" : ""}
      </span>
      <span className="sep" aria-hidden>
        ·
      </span>
      <span className="marks">
        {proof.state === "not_offered"
          ? "not offered"
          : `${proof.earned ?? 0} of ${proof.max_marks ?? 0}`}
      </span>
      {proof.stem_text && <p className="stem">{proof.stem_text}</p>}
      <p className="meta">
        {proof.curriculum_section_title || proof.curriculum_section ? (
          <>
            Book section {proof.curriculum_section}
            {proof.curriculum_section_title ? `, ${proof.curriculum_section_title}` : ""}.{" "}
          </>
        ) : null}
        {p?.needs_review
          ? "Placed automatically and still flagged for a person to check."
          : p?.source === "teacher"
            ? "Placed by a teacher."
            : p?.confidence != null
              ? `Placed automatically, confidence ${Math.round(p.confidence * 100)}%.`
              : "Placement not recorded."}
      </p>
      {p?.book_evidence?.length ? (
        <p className="meta">From the book: {p.book_evidence.join("; ")}</p>
      ) : null}

      <style jsx>{`
        .p { font-size: 13px; color: var(--brand-ink-soft); }
        .q { font-weight: 600; }
        .sep { color: var(--line-strong); margin: 0 6px; }
        .marks { color: var(--brand-ink-soft); }
        .stem { margin: 3px 0; color: var(--brand-ink-soft); }
        .meta { margin: 2px 0; color: var(--muted); font-size: 12px; }
      `}</style>
    </li>
  );
}
