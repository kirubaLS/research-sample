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
    <section className="diag">
      <header className="diaghead">
        <div>
          <h2>{report.assessment_title}</h2>
          <p className="who">
            {student.name} · roll {student.roll_no}
          </p>
        </div>
        <div className="score">
          <strong>
            {total.earned} / {total.available}
          </strong>
          <span className="muted">
            {pct(total.rate)} across {total.questions} question
            {total.questions === 1 ? "" : "s"}
          </span>
        </div>
        <button className="secondary printbtn" onClick={() => window.print()}>
          Print or save as PDF
        </button>
      </header>

      <p className="axisnote">
        Grouped by {axis.toLowerCase()}, the finest grouping this paper supports. Every
        figure below shows the marks it was computed from, and any topic with too little
        in this paper says so rather than showing a percentage.
      </p>

      <Band
        title="Strengths"
        empty="No topic in this paper cleared the bar for a strength."
        findings={report.strengths}
        tone="good"
      />
      <Band
        title="Where to work next"
        empty="Nothing in this paper stands out as needing attention first."
        findings={report.focus}
        tone="focus"
      />

      {report.tier_summary.length > 0 && (
        <>
          <h3>By what the question asked for</h3>
          <p className="note">
            High recall with low application on the same material is the &ldquo;knows the
            formula, cannot apply it&rdquo; signature. It is only visible when the paper
            contains both, which is why each row carries its own question count.
          </p>
          <div className="rows">
            {report.tier_summary.map((f) => (
              <Row key={f.key} finding={f} label={readable(f)} />
            ))}
          </div>
        </>
      )}

      <h3>Every {axis.toLowerCase()} in this paper</h3>
      <div className="rows">
        {report.topics.map((f) => (
          <Row key={f.key} finding={f} label={readable(f)} compact />
        ))}
      </div>

      {report.coverage_gaps.length > 0 && (
        <>
          <h3>What this paper did not test</h3>
          <p className="note">
            These carry marks in the board&rsquo;s own weighting, so a result here says
            nothing about them either way.
          </p>
          <ul className="gaps">
            {report.coverage_gaps.map((g) => (
              <li key={g.board_unit}>
                {/* board_weight is already a percentage. Multiplying by 100 here printed
                    "600% of board marks" for a unit worth 6%. */}
                <strong>{g.label}</strong> · {Math.round(g.board_weight)}% of board marks.{" "}
                {g.message}
              </li>
            ))}
          </ul>
        </>
      )}

      {report.not_offered.length > 0 && (
        <p className="note">
          {report.not_offered.length} question
          {report.not_offered.length === 1 ? " was" : "s were"} the unattempted half of a
          choice. Those are left out of every figure above: choosing not to answer one of
          two alternatives is not evidence of weakness, and scoring it zero would mark this
          student weak in whichever topic they chose to avoid.
        </p>
      )}

      <style jsx>{`
        .diag { margin-top: 26px; }
        .diaghead {
          display: flex; align-items: flex-start; justify-content: space-between;
          gap: 14px; flex-wrap: wrap; padding-bottom: 12px;
          border-bottom: 2px solid var(--ink, #16324f);
        }
        .diaghead h2 { margin: 0; font-size: 22px; }
        .who { margin: 2px 0 0; color: #555; }
        .score { text-align: right; }
        .score strong { display: block; font-size: 26px; }
        .score span { font-size: 13px; }
        .axisnote, .note { color: #555; font-size: 14px; max-width: 68ch; }
        h3 { margin: 26px 0 6px; font-size: 17px; }
        .rows { display: grid; gap: 8px; }
        .gaps { padding-left: 18px; color: #444; font-size: 14px; }
        .gaps li { margin-bottom: 4px; }
        .printbtn { align-self: center; }
        @media print {
          .printbtn { display: none; }
          .diag { margin-top: 0; }
          h3 { break-after: avoid; }
        }
      `}</style>
    </section>
  );
}

function Band({
  title,
  findings,
  empty,
  tone,
}: {
  title: string;
  findings: Finding[];
  empty: string;
  tone: "good" | "focus";
}) {
  return (
    <>
      <h3>{title}</h3>
      {findings.length === 0 ? (
        <p className="note">{empty}</p>
      ) : (
        <div className="rows">
          {findings.map((f) => (
            <Row key={`${f.scope}-${f.key}`} finding={f} label={readable(f)} tone={tone} />
          ))}
        </div>
      )}
      <style jsx>{`
        h3 { margin: 26px 0 6px; font-size: 17px; }
        .note { color: #555; font-size: 14px; max-width: 68ch; }
        .rows { display: grid; gap: 8px; }
      `}</style>
    </>
  );
}

function Row({
  finding,
  label,
  tone,
  compact,
}: {
  finding: Finding;
  label: string;
  tone?: "good" | "focus";
  /** The full list repeats what the two bands above already showed. On paper its proof
      stays folded, so a printed sheet does not carry every question twice. */
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const width = finding.rate === null ? 0 : Math.round(finding.rate * 100);

  return (
    <div className={`row ${tone ?? ""}${finding.sufficient ? "" : " thin"}`}>
      <div className="top">
        <span className="label">{label}</span>
        <span className="figure">
          {finding.sufficient ? (
            <>
              <strong>{pct(finding.rate)}</strong>
              <span className="muted">
                {" "}
                · {finding.earned} of {finding.available} marks over {finding.questions}{" "}
                question{finding.questions === 1 ? "" : "s"}
              </span>
            </>
          ) : (
            <span className="thintext">
              {finding.message ?? "not enough in this paper to report a figure"}
            </span>
          )}
        </span>
      </div>

      {finding.sufficient && (
        <>
          <div className="track" aria-hidden>
            <div className="fill" style={{ width: `${width}%` }} />
          </div>
          {finding.ci && (
            <p className="ci">
              95% interval {Math.round(finding.ci[0] * 100)}% to{" "}
              {Math.round(finding.ci[1] * 100)}%. Wide intervals are honest at this number
              of questions.
            </p>
          )}
        </>
      )}

      {finding.evidence.length > 0 && (
        <div className="proofwrap">
          <button className="link" onClick={() => setOpen(!open)}>
            {open ? "Hide" : "Show"} the {finding.evidence.length} question
            {finding.evidence.length === 1 ? "" : "s"} behind this
          </button>
          {/* Always in the DOM, hidden with CSS when collapsed. Rendering it only when
              open kept it out of the printed sheet entirely, and a printed report without
              the questions behind each figure is exactly the thing a parent cannot check. */}
          <ul className={`proof${open ? "" : " collapsed"}${compact ? " compact" : ""}`}>
            {finding.evidence.map((p, i) => (
              <ProofRow key={`${p.question_no}-${i}`} proof={p} />
            ))}
          </ul>
        </div>
      )}

      <style jsx>{`
        .row {
          border: 1px solid #e3e3e6; border-left: 4px solid #9aa3ad;
          border-radius: 10px; padding: 10px 12px; background: #fff;
        }
        .row.good { border-left-color: #196b2c; }
        .row.focus { border-left-color: #a8571b; }
        .row.thin { border-left-color: #c9cdd2; background: #fbfbfc; }
        .top { display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
        .label { font-weight: 600; }
        .figure { font-size: 14px; }
        .thintext { color: #6b6b6b; font-style: italic; }
        .track { height: 6px; background: #eceef1; border-radius: 999px; margin-top: 8px; }
        .fill { height: 6px; background: #16324f; border-radius: 999px; }
        .ci { margin: 6px 0 0; font-size: 12px; color: #666; }
        .proofwrap { margin-top: 8px; }
        .link {
          background: none; border: 0; padding: 0; color: #16324f;
          text-decoration: underline; font-size: 13px; cursor: pointer;
        }
        .proof { margin: 8px 0 0; padding-left: 16px; display: grid; gap: 8px; }
        .proof.collapsed { display: none; }
        @media print {
          .link { display: none; }
          .proof.collapsed { display: grid; }
          .proof.collapsed.compact { display: none; }
          .row { break-inside: avoid; }
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
        .p { font-size: 13px; color: #333; }
        .q { font-weight: 600; }
        .sep { color: #b8bcc2; margin: 0 6px; }
        .marks { color: #555; }
        .stem { margin: 3px 0; color: #444; }
        .meta { margin: 2px 0; color: #666; font-size: 12px; }
      `}</style>
    </li>
  );
}
