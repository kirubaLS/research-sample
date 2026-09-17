"use client";

/**
 * The BoardX v2 one-page student report, rendered from real composed data
 * (GET /reports/student/{id}/boardx) -- every sentence here is a frozen string the
 * backend chose and filled in, never written in this component. Same shape for every
 * student and every paper: nothing about a particular student is hardcoded.
 */

import type { BoardXChapterRow, BoardXReport } from "@/lib/api";

function isChapterRow(entry: BoardXReport["section1"][number]): entry is BoardXChapterRow {
  return "domain" in entry;
}

export function BoardXOnePager({
  report, className, rollNo,
}: {
  report: BoardXReport;
  className?: string | null;
  rollNo?: string;
}) {
  const chapterRows = report.section1.filter(isChapterRow);
  const exposureTotal = chapterRows
    .filter((r) => r.board_exposure_verified)
    .reduce((sum, r) => sum + (r.board_exposure ?? 0), 0);
  const boardTotal = chapterRows.find((r) => r.board_exposure_verified)?.board_total ?? null;
  // The real frozen-string sentence (S1_BOARD_IMPACT_NOT_CALIBRATED), not the bare status
  // code "NOT_CALIBRATED" -- that word means nothing to a teacher, principal or student
  // who was never told what it stands for.
  const impactLine = report.section1.find((e) => !("domain" in e))?.lines[0];

  // section3 is a flat line list built in the same order as section4's cards: one line
  // for a no-pattern card, two (pattern + scope) for a real one. Re-pairing them here
  // mirrors exactly how app.analysis.boardx_report composed them.
  let cursor = 0;
  const pairs = report.section4.map((card) => {
    if (card.topic === null) {
      const pattern = report.section3[cursor];
      cursor += 1;
      return { card, pattern, scope: null as BoardXReport["section3"][number] | null };
    }
    const pattern = report.section3[cursor];
    const scope = report.section3[cursor + 1];
    cursor += 2;
    return { card, pattern, scope };
  });
  const patternCards = pairs.filter((p) => p.card.topic !== null);

  return (
    <div className={`boardx-onepager${className ? ` ${className}` : ""}`}>
      <p className="bx-eyebrow">AVAI BoardX</p>
      <p className="bx-subtitle">{report.subject_code} &nbsp;|&nbsp; Your One-Page Assessment Report</p>
      <p className="bx-meta">
        {report.student_name}
        {rollNo ? ` (Roll ${rollNo})` : ""}
        {" · "}{report.assessment_title} · {report.subject_code}
      </p>

      <BxSection n={1} title="Where you stand">
        <div className="bx-table">
          <div className="bx-row bx-head">
            <span>Chapter</span><span>You scored</span><span>Not scored</span><span>Board importance</span>
          </div>
          {chapterRows.map((r) => (
            <div className="bx-row" key={r.domain_code}>
              <span className="strong">{r.domain}</span>
              <span>{r.diagnosable ? `${trim(r.scored)} / ${trim(r.available)}` : "Not enough evidence"}</span>
              <span>{r.diagnosable ? trim(r.not_scored) : "—"}</span>
              <span>
                {r.board_exposure_verified ? `${trim(r.board_exposure!)} / ${trim(r.board_total!)}` : "Not calibrated"}
              </span>
            </div>
          ))}
        </div>
        <p className="bx-note">
          <strong>BOARD EXPOSURE:</strong>{" "}
          {boardTotal
            ? `Affected chapters carry ${trim(exposureTotal)} of the ${trim(boardTotal)} Board marks.`
            : "Not calibrated for this subject yet."}
        </p>
        {impactLine && <p className="bx-note">{impactLine.text}</p>}
      </BxSection>

      <BxSection n={2} title="How you are handling questions">
        <p className="small muted">{report.section2.caption.text}</p>
        {patternCards.length === 0 ? (
          <p className="bx-note">This paper does not contain enough evidence to identify one repeated question pattern.</p>
        ) : (
          patternCards.map(({ card, pattern }) => (
            <div key={card.domain + (card.topic ?? "")} style={{ marginTop: 8 }}>
              <p className="bx-tag">PATTERN SEEN: {card.topic?.toUpperCase()}</p>
              <p className="small">{pattern.text}</p>
            </div>
          ))
        )}
      </BxSection>

      <BxSection n={3} title="Where the marks went">
        {report.section4.map((card) => (
          <div key={card.domain} style={{ marginBottom: 10 }}>
            <p className="strong" style={{ margin: "0 0 2px" }}>{card.domain}</p>
            {card.lines.map((l, i) => (
              <p className="small muted" style={{ margin: "0 0 2px" }} key={i}>{l.text}</p>
            ))}
          </div>
        ))}
      </BxSection>

      <BxSection n={4} title="What you should do next">
        {report.section5.actions.length === 0 ? (
          <p className="bx-note">Your answer script should be reviewed before a new practice task is selected.</p>
        ) : (
          report.section5.actions.map((a) => (
            <p className="bx-note" key={a.remediation_ref}>{a.line.text}</p>
          ))
        )}
      </BxSection>

      <div className="bx-footer">
        {report.section6.map((l, i) => <p key={i}>{l.text}</p>)}
      </div>

      <style jsx>{`
        .boardx-onepager {
          background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius);
          padding: 22px 24px; max-width: 720px;
        }
        .bx-eyebrow { margin: 0; font-weight: 800; font-size: 13px; letter-spacing: 0.04em; color: var(--brand-ink); }
        .bx-subtitle { margin: 2px 0 6px; color: var(--ink-2); font-size: 13.5px; }
        .bx-meta { margin: 0 0 16px; font-weight: 600; font-size: 13.5px; }
        .bx-table { border: 1px solid var(--rule); border-radius: var(--radius-sm); overflow: hidden; }
        .bx-row {
          display: grid; grid-template-columns: 2fr 1fr 1fr 1.3fr; gap: 8px;
          padding: 7px 10px; border-bottom: 1px solid var(--rule); font-size: 13px;
        }
        .bx-row:last-child { border-bottom: none; }
        .bx-row.bx-head { background: var(--surface-2); font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--ink-3); }
        .bx-note { font-size: 13px; margin: 8px 0 0; }
        .bx-tag { font-weight: 700; font-size: 11.5px; letter-spacing: 0.03em; color: var(--brand-ink); margin: 0 0 2px; }
        .bx-footer { margin-top: 18px; padding-top: 10px; border-top: 1px solid var(--rule); }
        .bx-footer p { font-size: 11.5px; color: var(--ink-3); font-style: italic; margin: 2px 0; }
      `}</style>
    </div>
  );
}

function BxSection({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: 18 }}>
      <div className="section-head" style={{ marginBottom: 8 }}>
        <h2 style={{ fontSize: 15 }}>{n}&ensp;{title}</h2>
      </div>
      {children}
    </div>
  );
}

function trim(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}
