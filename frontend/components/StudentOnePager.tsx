"use client";

import type { BoardXChapterRow, BoardXLine, BoardXReport } from "@/lib/api";
import { scoreColor } from "@/lib/bandColors";
import { Reveal } from "@/components/motion";

function isChapter(e: BoardXChapterRow | { lines: BoardXLine[] }): e is BoardXChapterRow {
  return "domain" in e;
}

function num(n: number) {
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function Block({ n, title, lead, children, delay = 0 }: { n: number; title: string; lead?: string; children: React.ReactNode; delay?: number }) {
  return (
    <Reveal delay={delay}>
      <section className="bx-block">
        <header className="bx-block__head">
          <span className="bx-block__num" aria-hidden="true">
            {n}
          </span>
          <div>
            <h3>{title}</h3>
            {lead && <p className="small muted">{lead}</p>}
          </div>
        </header>
        <div className="bx-block__body">{children}</div>
      </section>
    </Reveal>
  );
}

/** The BoardX one-page report, inline -- rendered straight from GET
 * /reports/student/{id}/boardx (compose_boardx_report's own dict, the same one the
 * PDF prints). Every sentence shown is one of that report's frozen lines; the
 * practice recommendations are the approved remediation catalogue's own text, shown
 * as-is. Nothing here adds a number or an exercise reference the report does not carry. */
export function StudentOnePager({ report }: { report: BoardXReport }) {
  const chapters = report.section1.filter(isChapter);
  const disclaimers = report.section1.filter((e) => !isChapter(e)).flatMap((e) => e.lines);
  const cross = report.section2.crosstab;
  const tiers = Array.from(new Set(cross.map((c) => c.tier).filter((t): t is string => !!t)));
  const skills = Array.from(new Set(cross.map((c) => c.skill_label)));
  const cell = (skill: string, tier: string) => cross.find((c) => c.skill_label === skill && c.tier === tier);
  const tierLabel = (tier: string) => cross.find((c) => c.tier === tier)?.question_type ?? tier;
  const actions = report.section5.actions;

  return (
    <div className="bx-report">
      <Block n={1} title="Where you stand" lead={`${report.subject_label} · ${report.assessment_title}`}>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Chapter</th>
                <th className="num">You scored</th>
                <th className="num">Not scored</th>
                <th className="num">Board importance</th>
              </tr>
            </thead>
            <tbody>
              {chapters.map((c) => (
                <tr key={c.domain_code}>
                  <td className="strong">
                    {c.domain}
                    {!c.diagnosable && <div className="small muted">Too few questions to diagnose</div>}
                  </td>
                  <td className="num">
                    {num(c.scored)} / {num(c.available)}
                  </td>
                  <td className="num">{num(c.not_scored)}</td>
                  <td className="num">{c.board_exposure_verified && c.board_exposure !== null ? `${c.board_exposure} of ${c.board_total}` : <span className="muted">Not yet calibrated</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {disclaimers.map((l) => (
          <p key={l.id} className="small muted" style={{ marginTop: 10 }}>
            {l.text}
          </p>
        ))}
      </Block>

      <Block n={2} title="How you're handling questions" lead={report.section2.caption.text} delay={0.05}>
        {cross.length === 0 ? (
          <p className="small muted">No skill-level evidence on this paper.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Skill</th>
                  {tiers.map((t) => (
                    <th key={t} className="num" style={{ textTransform: "none" }}>
                      {tierLabel(t)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {skills.map((sk) => (
                  <tr key={sk}>
                    <td className="strong">{sk}</td>
                    {tiers.map((t) => {
                      const c = cell(sk, t);
                      if (!c) return <td key={t} className="num muted">-</td>;
                      return (
                        <td key={t} className="num" title={c.sufficient ? undefined : c.message}>
                          {num(c.earned)} / {num(c.available)}
                          {c.sufficient && c.rate !== null ? (
                            <span className="pillnum" style={{ "--accent": scoreColor(c.rate * 100), marginLeft: 6 } as React.CSSProperties}>
                              {Math.round(c.rate * 100)}%
                            </span>
                          ) : (
                            <span className="small muted" style={{ marginLeft: 6 }}>
                              low evidence
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Block>

      <Block n={3} title="Where the marks went" delay={0.1}>
        {report.section4.length === 0 ? (
          <p className="small muted">{report.section3[0]?.text ?? "No chapter lost enough marks to single out."}</p>
        ) : (
          <div className="bx-cards">
            {report.section4.map((card, i) => {
              const row = chapters.find((c) => c.domain === card.domain);
              const pct = row && row.available ? (row.scored / row.available) * 100 : null;
              const pattern = report.section3.find((l) => l.text.includes(card.domain));
              return (
                <div key={`${card.domain}-${i}`} className="bx-card" style={{ "--accent": pct !== null ? scoreColor(pct) : "var(--muted)" } as React.CSSProperties}>
                  <div className="bx-card__top">
                    <span className="strong">{card.domain}</span>
                    {row && (
                      <span className="small muted">
                        {num(row.scored)} / {num(row.available)}
                      </span>
                    )}
                  </div>
                  {pct !== null && (
                    <div className="bar" style={{ marginTop: 8 }}>
                      <div className="bar__fill" style={{ width: `${pct}%`, background: "var(--accent)" }} />
                    </div>
                  )}
                  {pattern && <p className="small" style={{ marginTop: 10 }}>{pattern.text}</p>}
                  {card.lines
                    .filter((l) => l.id !== "S4_ACTION")
                    .map((l) => (
                      <p key={l.id} className="small muted" style={{ marginTop: 6 }}>
                        {l.text}
                      </p>
                    ))}
                </div>
              );
            })}
          </div>
        )}
      </Block>

      <Block n={4} title="What you should do next" delay={0.15}>
        {actions.length === 0 ? (
          <p className="small muted">No approved practice recommendation matches these findings yet; your teacher will review them with you.</p>
        ) : (
          <ol className="bx-actions">
            {actions.map((a, i) => (
              <li key={a.remediation_ref + i} className="bx-action">
                <span className="bx-action__step">{i === 0 ? "Start with" : "Then"}</span>
                <span>{a.text}</span>
              </li>
            ))}
          </ol>
        )}
        {report.section6.map((l) => (
          <p key={l.id} className="small muted" style={{ marginTop: 10 }}>
            {l.text}
          </p>
        ))}
      </Block>
    </div>
  );
}
