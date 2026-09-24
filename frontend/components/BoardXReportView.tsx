"use client";

import { ClipboardCheck, Search } from "lucide-react";
import { motion } from "framer-motion";
import { Mascot, type MascotPose } from "@/components/Mascot";
import type { BoardXStudentReport } from "@/lib/avai-mock-data";

const poseForTrend: Record<string, MascotPose> = { up: "achieve", down: "improve", flat: "improve" };

/** The one-page BoardX report body, shared by the student-facing report
 * page and the principal's per-student, test-wise report view. */
export function BoardXReportView({ report: r, studentName, section }: { report: BoardXStudentReport; studentName: string; section?: string }) {
  const pose = poseForTrend[r.trend] ?? "neutral";

  return (
    <motion.div className="feedback" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <div className="feedback__hero">
        <Mascot pose={pose} size={100} />
        <div>
          <div className="eyebrow">AVAI BoardX · One-page assessment report</div>
          <div className="feedback__score">{r.score}</div>
          <p style={{ marginTop: 6, fontSize: 15 }}>{r.encouragingLine}</p>
        </div>
      </div>
      <div className="feedback__body">
        <div className="small muted">
          <span className="strong" style={{ color: "var(--text)" }}>
            {studentName}
          </span>{" "}
          · {[section, r.assessmentName, r.subject].filter(Boolean).join(" · ")}
        </div>

        <section className="section" style={{ marginTop: 20 }}>
          <h2 className="section-q">
            <span className="section-q__num">1</span>Where you stand
          </h2>
          <div className="table-wrap" style={{ marginTop: 12 }}>
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
                {r.standing.map((s) => (
                  <tr key={s.chapter}>
                    <td className="strong">{s.chapter}</td>
                    <td className="num">
                      {s.scored} / {s.outOf}
                    </td>
                    <td className="num">{s.notScored}</td>
                    <td className="num">{s.boardImportance}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="grid grid--2" style={{ marginTop: 14 }}>
            <div className="metric">
              <div className="metric__label">Board exposure</div>
              <div className="metric__value" style={{ fontSize: 15, fontWeight: 500 }}>
                Affected chapters carry {r.boardExposureMarks} of {r.totalBoardMarks} Board marks.
              </div>
            </div>
            <div className="metric">
              <div className="metric__label">Estimated Board-score impact</div>
              <div className="metric__value">{r.boardScoreImpact === "NOT_CALIBRATED" ? "Not yet calibrated" : r.boardScoreImpact}</div>
            </div>
          </div>
        </section>

        <section className="section">
          <h2 className="section-q">
            <span className="section-q__num">2</span>How you are handling questions
          </h2>
          <div className="grid grid--2" style={{ marginTop: 12 }}>
            <div className="evidence evidence--neutral">
              <Search size={16} />
              <div>
                <div className="evidence__title">Reading &amp; Understanding</div>
                <div>No score is invented here, this needs more answer-level data than one assessment provides.</div>
              </div>
            </div>
            <div className="card card--soft">
              <div className="card__body">
                <span className="tag tag--teal">{r.patternLabel}</span>
                <p style={{ marginTop: 10, fontWeight: 600 }}>{r.patternHeadline}</p>
                <p className="small muted" style={{ marginTop: 6 }}>
                  {r.patternBody}
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="section">
          <h2 className="section-q">
            <span className="section-q__num">3</span>Where the marks went
          </h2>
          <div className="grid grid--2" style={{ marginTop: 12 }}>
            {r.marksLost.map((m) => (
              <div className="card" key={m.chapter}>
                <div className="card__body">
                  <div className="strong">{m.chapter}</div>
                  <div className="bar-row" style={{ gridTemplateColumns: "1fr 56px", padding: "8px 0 2px" }}>
                    <div className="bar">
                      <div className="bar__fill bar__fill--gold" style={{ width: `${(m.scored / m.outOf) * 100}%` }} />
                    </div>
                    <div className="bar-row__val">{m.scoreLabel}</div>
                  </div>
                  <div className="small muted">{m.subLabel}</div>
                  <p className="small" style={{ marginTop: 8 }}>
                    {m.insight}
                  </p>
                </div>
              </div>
            ))}
            {r.noPatternNote && (
              <div className="card card--flat card--soft">
                <div className="card__body">
                  <div className="strong">
                    {r.noPatternNote.chapter} <span className="muted" style={{ fontWeight: 400 }}>| {r.noPatternNote.scoreLabel}</span>
                  </div>
                  <p className="small muted" style={{ marginTop: 8 }}>
                    {r.noPatternNote.note}
                  </p>
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="section">
          <h2 className="section-q">
            <span className="section-q__num">4</span>What you should do next
          </h2>
          <div style={{ marginTop: 12, display: "grid", gap: 14 }}>
            {r.actionPlan.map((g) => (
              <div className="card card--soft" key={g.heading}>
                <div className="card__body">
                  <div className="strong" style={{ color: "var(--brand-teal)" }}>
                    {g.heading}
                  </div>
                  <ul className="list-plain" style={{ marginTop: 8 }}>
                    {g.items.map((it) => (
                      <li key={it}>{it}</li>
                    ))}
                  </ul>
                </div>
              </div>
            ))}
            <div className="evidence evidence--gold">
              <ClipboardCheck size={16} />
              <div>
                <div className="evidence__title">Practice rule</div>
                <div>{r.practiceRule}</div>
              </div>
            </div>
          </div>
        </section>

        <p className="small muted" style={{ marginTop: 4 }}>
          {r.takeaway} <br />
          {r.evidenceNote}
        </p>
      </div>
    </motion.div>
  );
}
