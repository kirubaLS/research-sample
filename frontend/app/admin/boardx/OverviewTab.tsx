"use client";

import type { CohortReport, PaperReport, BoardFrequencyRow } from "@/lib/api";
import { AttentionPill, attentionFromRate } from "@/components/boardx/Status";
import { FindingCard } from "@/components/boardx/FindingCard";
import { TrendNotAvailable, EarlySignal } from "@/components/boardx/EmptyStates";
import type { BoardXFinding } from "@/components/boardx/types";
import { findingsFromTopLosses } from "@/components/boardx/findings";
import {
  MOCK_POTENTIAL_LADDER, MOCK_BAND_OPPORTUNITY, mockPatternLabelFor, INTERVENTION_PRIORITY_NOTE,
} from "@/components/boardx/mock";
import { StatTile, StatTileRow } from "@/components/academics/StatTile";
import {
  ClipboardIcon, BarChartIcon, TargetIcon, PuzzleIcon, BrainIcon, PeopleIcon,
} from "@/components/academics/Icons";

const STRENGTH_COPY: Record<PaperReport["diagnostic_strength"], string> = {
  STRONG: "This paper is a solid basis for the findings below.",
  MODERATE:
    "This paper provides reasonable evidence, but interpret findings in under-tested areas with caution.",
  LIMITED:
    "This paper's tier balance or item consistency is weak enough that findings here should be treated as a starting signal, not a conclusion.",
};

function pct(n: number | null | undefined): string {
  return n == null ? "—" : `${Math.round(n * 100)}%`;
}

export function OverviewTab({
  cohort, report, cohortNote, reportError, freq,
  onOpenDrawer, onGoToStudents,
}: {
  cohort: CohortReport | null;
  report: PaperReport | null;
  cohortNote: string | null;
  reportError: string | null;
  freq: BoardFrequencyRow[];
  onOpenDrawer: (f: BoardXFinding) => void;
  onGoToStudents: (filter?: { band?: string }) => void;
}) {
  const findings = cohort ? findingsFromTopLosses(cohort, freq) : [];

  return (
    <div className="bx-scroll">
      {/* --- 1. Assessment Diagnostic Quality --- */}
      <section className="bx-section">
        <h2>Can I trust this test to tell me enough?</h2>
        {reportError && <TrendNotAvailable />}
        {report && (
          <div className="bx-panel">
            <div className={`bx-strength bx-strength-${report.diagnostic_strength.toLowerCase()}`}>
              <p className="bx-small bx-muted">Assessment Diagnostic Strength</p>
              <p className="bx-strength-v">{report.diagnostic_strength}</p>
            </div>
            <p className="bx-small">{STRENGTH_COPY[report.diagnostic_strength]}</p>
            <StatTileRow>
              <StatTile icon={<PuzzleIcon />} tone="info" value={pct(report.application_share)} label="Application Questions" />
              <StatTile icon={<BrainIcon />} tone="violet" value={pct(report.higher_order_share)} label="Higher-Order Questions" />
              <StatTile
                icon={<TargetIcon />}
                tone={report.cronbach_alpha == null ? "neutral" : report.cronbach_alpha >= 0.7 ? "verify" : "warn"}
                value={report.cronbach_alpha == null ? "—" : report.cronbach_alpha.toFixed(2)}
                label="Item Consistency (α)"
              />
              <StatTile
                icon={<ClipboardIcon />}
                tone={report.flagged_items.length > 0 ? "risk" : "verify"}
                value={report.flagged_items.length}
                label="Items Flagged"
              />
            </StatTileRow>
            <p className="bx-verdict">{report.typology_alignment.verdict}</p>
            {report.application_share != null && report.application_share < 0.15 && (
              <div style={{ marginTop: 10 }}>
                {/* Real signal (application_share is a real backend field) driving a real
                    §5.7 state -- not mocked. */}
                <p className="bx-empty-inline">This assessment included too few application
                  questions to confidently assess application readiness.</p>
              </div>
            )}
          </div>
        )}
      </section>

      {/* --- 2. Standard Performance Snapshot --- */}
      <section className="bx-section">
        <h2>How is my entire Class {"X"} performing?</h2>
        {cohortNote && <TrendNotAvailable />}
        {cohort && (
          <div className="bx-bandgrid">
            {([
              ["full_mastery", "Full Mastery (90%+)", "verify"],
              ["band_80_89", "80–89%", "gold"],
              ["band_60_79", "60–79%", "warn"],
              ["below_60", "Below 60%", "risk"],
            ] as const).map(([key, label, tone]) => (
              <button
                key={key}
                type="button"
                className={`bx-bandcard bx-bandcard-${tone}`}
                onClick={() => onGoToStudents({ band: key })}
              >
                <p className="bx-bandcard-n">{cohort.band_counts[key]}</p>
                <p className="bx-bandcard-l">{label}</p>
                <p className="bx-bandcard-pct">{cohort.band_pct[key]}% of cohort</p>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* --- 3. Subject Board Conversion --- */}
      <section className="bx-section">
        <h2>Across subjects, how much of the Board requirement are my students demonstrating?</h2>
        {cohort && (
          <>
            <p className="bx-small bx-muted">{cohort.subject_bars_note}</p>
            <div className="bx-table">
              <div className="bx-trow bx-thead">
                <span>Subject</span><span>Assessment</span><span>Avg. attainment</span>
              </div>
              {cohort.subject_bars.map((s) => (
                <div className="bx-trow" key={s.subject_code}>
                  <span className="bx-subject">{s.subject_label}</span>
                  <span className="bx-muted bx-small">{s.assessment_title}</span>
                  <span className="bx-pct">{s.pct.toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      {/* --- 4. Marks Loss Intelligence (hero) --- */}
      <section className="bx-section bx-hero">
        <h2>What is stopping students from scoring higher?</h2>
        <p className="bx-small bx-muted">Lost Marks = Lost Board Potential</p>
        {findings.length === 0 && cohortNote && <EarlySignal />}
        <div className="bx-findings">
          {findings.map((f) => (
            <FindingCard
              key={f.id}
              finding={f}
              onViewStudents={() => onGoToStudents()}
              onViewDetails={onOpenDrawer}
            />
          ))}
        </div>
      </section>

      {/* --- 5. Board Urgency vs Board Impact --- */}
      <section className="bx-section">
        <h2>Even if students are weak here, how much should I care for the Board?</h2>
        {findings.length > 0 && (
          <div className="bx-table">
            <div className="bx-trow bx-thead">
              <span>Topic</span><span>Marks exposure</span><span>Board recurrence</span>
              <span>Students affected</span><span>Urgency</span>
            </div>
            {findings.map((f) => (
              <button key={f.id} type="button" className="bx-trow bx-trow-click" onClick={() => onOpenDrawer(f)}>
                <span>{f.topicPath[f.topicPath.length - 1]}</span>
                <span>{f.avgMarksLost.toFixed(1)}</span>
                <span>{f.yearsEligible ? `${f.yearsAppeared}/${f.yearsEligible} yrs` : "—"}</span>
                <span>{f.studentsAffected}</span>
                <span>{f.urgencyTier ?? "—"}</span>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* --- 6. Student Potential Ladder --- */}
      <section className="bx-section">
        <h2>Who is close to the next level?</h2>
        {/* TODO(backend): Dependency Index #4 -- Potential Ladder / distance-to-next-band
            has no real computation yet. Mocked shape below. */}
        <div className="bx-ladder">
          <div className="bx-rung">
            <span className="bx-rung-n">{MOCK_POTENTIAL_LADDER.atPotential}</span>
            <span className="bx-rung-l">at potential</span>
          </div>
          <div className="bx-rung">
            <span className="bx-rung-n">{MOCK_POTENTIAL_LADDER.within1Mark}</span>
            <span className="bx-rung-l">within 1 mark of next band</span>
          </div>
          <div className="bx-rung">
            <span className="bx-rung-n">{MOCK_POTENTIAL_LADDER.within2Marks}</span>
            <span className="bx-rung-l">within 2 marks of next band</span>
          </div>
        </div>
        <p className="bx-small bx-muted">Most common blocker (mocked): {MOCK_POTENTIAL_LADDER.mostCommonBlocker}</p>
      </section>

      {/* --- 7. Performance Band Opportunity --- */}
      <section className="bx-section">
        <h2>What is stopping each band from moving higher?</h2>
        {/* TODO(backend): Dependency Index #4 -- "students near next band" per band and
            its common blocker are mocked; no real distance-to-next-band aggregation
            exists yet. */}
        <div className="bx-table">
          <div className="bx-trow bx-thead"><span>Band</span><span>Students near next band</span><span>Common blocker</span></div>
          {MOCK_BAND_OPPORTUNITY.map((r) => (
            <div className="bx-trow" key={r.band}>
              <span>{r.band}</span>
              <span>{r.studentsNearNextBand}</span>
              <span>{r.commonBlocker === "No dominant common blocker" ? <em>No dominant common blocker</em> : r.commonBlocker}</span>
            </div>
          ))}
        </div>
      </section>

      {/* --- 8. Risk Intelligence --- */}
      <section className="bx-section">
        <h2>Who requires intervention?</h2>
        {cohort && (
          <div className="bx-riskgrid">
            <div className="bx-riskcard">
              <span className="bx-riskcard-icon bx-riskcard-icon-risk"><PeopleIcon /></span>
              <div className="bx-riskcard-body">
                <p className="bx-riskcard-n">{cohort.band_counts.below_60}</p>
                <p className="bx-riskcard-l">High Academic Risk (below 60%)</p>
              </div>
              <AttentionPill state={attentionFromRate(0.4)} />
            </div>
            <div className="bx-riskcard">
              {/* TODO(backend): Dependency Index #4 -- "High Potential Gap" (near-band
                  students at real risk of falling) needs the same distance-to-next-band
                  computation as the Potential Ladder; mocked here. */}
              <span className="bx-riskcard-icon bx-riskcard-icon-warn"><TargetIcon /></span>
              <div className="bx-riskcard-body">
                <p className="bx-riskcard-n">{MOCK_POTENTIAL_LADDER.within1Mark}</p>
                <p className="bx-riskcard-l">High Potential Gap (mocked)</p>
              </div>
              <AttentionPill state="WATCH" />
            </div>
          </div>
        )}
      </section>

      {/* --- 9. Subject Anomaly Intelligence --- */}
      <section className="bx-section">
        <h2>Where is my batch struggling in an unusual or concentrated way?</h2>
        {findings.length > 0 && (
          <div className="bx-table">
            <div className="bx-trow bx-thead">
              <span>Topic</span><span>Pattern detected</span><span>% affected</span><span>Confidence</span>
            </div>
            {findings.map((f) => (
              <div className="bx-trow" key={f.id}>
                <span>{f.topicPath[f.topicPath.length - 1]}</span>
                {/* TODO(backend): Dependency Index #6 -- pattern label is a mocked
                    classification; the % affected and confidence beside it are real. */}
                <span className="bx-mocklabel">{mockPatternLabelFor(f.id)}</span>
                <span>{cohort ? Math.round((f.studentsAffected / cohort.students_analysed) * 100) : "—"}%</span>
                <span>{f.confidence}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* --- 10. Section Comparison --- */}
      <section className="bx-section">
        <h2>Are all my sections facing the same problem?</h2>
        {cohort && (
          <>
            <div className="bx-table">
              <div className="bx-trow bx-thead"><span>Section</span><span>Attainment</span><span>Attention</span></div>
              {cohort.section_bars.map((s) => (
                <div className="bx-trow" key={s.section_id}>
                  <span>{s.label}</span>
                  <span>{s.pct.toFixed(0)}%</span>
                  <span><AttentionPill state={attentionFromRate(s.pct / 100)} /></span>
                </div>
              ))}
            </div>
            <p className="bx-small bx-muted" style={{ marginTop: 8 }}>
              A section&rsquo;s attention level reflects attainment on this paper only -- it is
              never an implication about teacher quality.
            </p>
          </>
        )}
      </section>

      {/* --- 11. Recommended Intervention Plan --- */}
      <section className="bx-section bx-hero">
        <h2>What should my school act on now?</h2>
        <p className="bx-small bx-muted">{INTERVENTION_PRIORITY_NOTE}</p>
        <div className="bx-findings">
          {findings.map((f, i) => (
            <div key={f.id}>
              <p className="bx-priority-why">
                Why BoardX prioritised this: {f.studentsAffected} students affected ×
                {" "}{f.avgMarksLost.toFixed(1)} marks avg. exposure, {f.urgencyTier ?? "unscored"} Board
                urgency, {f.confidence.toLowerCase()} confidence. (Priority {i + 1} of {findings.length})
              </p>
              <FindingCard finding={f} onViewStudents={() => onGoToStudents()} onViewDetails={onOpenDrawer} />
            </div>
          ))}
        </div>
      </section>

      <style jsx>{`
        .bx-scroll { display: flex; flex-direction: column; gap: 30px; padding-bottom: 40px; }
        .bx-section h2 {
          font-family: var(--font-display), sans-serif; font-size: 19px; font-weight: 800;
          color: var(--brand-ink); margin: 0 0 12px;
        }
        .bx-hero { background: var(--surface-2); border-radius: var(--radius); padding: 18px 20px; }
        .bx-panel {
          background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius);
          padding: 18px 20px; box-shadow: var(--shadow-xs);
        }
        .bx-small { font-size: 13px; }
        .bx-muted { color: var(--ink-3); }
        .bx-strength { display: inline-flex; flex-direction: column; gap: 2px; padding: 6px 14px; border-radius: 8px; margin-bottom: 10px; }
        .bx-strength-strong { background: var(--verify-soft); }
        .bx-strength-moderate { background: var(--warn-soft); }
        .bx-strength-limited { background: var(--risk-soft); }
        .bx-strength-v { font-size: 20px; font-weight: 700; margin: 0; color: var(--brand-ink); }
        .bx-verdict { color: var(--ink-2); font-size: 14px; margin: 10px 0 0; }
        .bx-empty-inline { background: var(--info-soft); border-radius: 8px; padding: 10px 14px; margin: 0; font-size: 13.5px; }

        .bx-bandgrid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
        .bx-bandcard {
          text-align: left; background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius);
          padding: 14px 16px; cursor: pointer; font: inherit; border-left: 4px solid var(--rule-2);
          transition: border-color var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease);
        }
        .bx-bandcard:hover { border-color: var(--brand-ink-2); box-shadow: var(--shadow-sm); }
        .bx-bandcard-verify { border-left-color: var(--verify); }
        .bx-bandcard-gold { border-left-color: var(--brand-gold); }
        .bx-bandcard-warn { border-left-color: var(--warn); }
        .bx-bandcard-risk { border-left-color: var(--risk); }
        .bx-bandcard-n { margin: 0; font-size: 24px; font-weight: 800; font-family: var(--font-display), sans-serif; color: var(--ink); }
        .bx-bandcard-l { margin: 2px 0; font-size: 12.5px; color: var(--ink-2); font-weight: 600; }
        .bx-bandcard-pct { margin: 0; font-size: 12px; color: var(--ink-3); }

        .bx-table { display: flex; flex-direction: column; gap: 6px; overflow-x: auto; }
        .bx-trow {
          display: grid; grid-template-columns: repeat(auto-fit, minmax(90px, 1fr)); gap: 10px;
          padding: 12px 14px; align-items: center; background: var(--surface); border: 1px solid var(--rule);
          border-radius: var(--radius-sm, 10px); font-size: 13.5px;
          transition: border-color var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease);
        }
        .bx-thead { background: none; border: none; font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.05em; padding: 0 14px; font-weight: 700; }
        .bx-trow-click { text-align: left; font: inherit; cursor: pointer; width: 100%; }
        .bx-trow-click:hover, .bx-trow:not(.bx-thead):hover { border-color: var(--brand-ink-2); box-shadow: var(--shadow-xs); }
        .bx-mocklabel { font-style: italic; color: var(--ink-2); }
        .bx-subject { font-weight: 700; color: var(--ink); }
        .bx-pct { font-variant-numeric: tabular-nums; font-weight: 700; color: var(--brand-ink); }

        .bx-ladder { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 8px; }
        .bx-rung {
          background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius);
          padding: 14px 20px; text-align: center; min-width: 140px; box-shadow: var(--shadow-xs);
        }
        .bx-rung-n { display: block; font-size: 26px; font-weight: 800; font-family: var(--font-display), sans-serif; color: var(--brand-ink); }
        .bx-rung-l { display: block; font-size: 12.5px; color: var(--ink-3); margin-top: 4px; }

        .bx-riskgrid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
        .bx-riskcard {
          background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); padding: 16px 18px;
          display: flex; align-items: center; gap: 14px; flex-wrap: wrap; box-shadow: var(--shadow-xs);
        }
        .bx-riskcard-icon {
          flex: none; width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center;
        }
        .bx-riskcard-icon-risk { background: var(--risk-soft); color: var(--risk); }
        .bx-riskcard-icon-warn { background: var(--warn-soft); color: var(--warn); }
        .bx-riskcard-body { flex: 1; min-width: 120px; }
        .bx-riskcard-n { margin: 0; font-size: 24px; font-weight: 800; font-family: var(--font-display), sans-serif; color: var(--ink); }
        .bx-riskcard-l { margin: 0; font-size: 13px; color: var(--ink-2); }

        .bx-findings { display: grid; gap: 14px; }
        .bx-priority-why { font-size: 12.5px; color: var(--ink-3); margin: 0 0 6px; }
      `}</style>
    </div>
  );
}
