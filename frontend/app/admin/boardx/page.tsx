"use client";

/**
 * AVAI BoardX -- the principal's primary lens (design spec §5). Structure follows §5.1-5.9:
 * a sticky assessment/filter header (§5.2), an internal Overview|Sections|Subjects|Students|
 * Interventions nav, an 11-section overview scroll (§5.3) built from the one reusable
 * finding unit (§5.4) and a right-side Finding Details drawer (§5.5), the Student
 * Intelligence tab (§5.6), first-class empty states (§5.7), and the three-dimension status
 * system (§5.8) used everywhere instead of a flat badge.
 *
 * Real data: GET /reports/paper/{id} (diagnostic strength), GET /reports/cohort/{id}
 * (bands, subject/section bars, top_losses) and GET /board-frequency (years_appeared/
 * years_eligible, best-effort enrichment). Where a section depends on backend
 * aggregation that does not exist yet (Dependency Index #3-#6), it is built against
 * clearly marked mock data with an inline TODO -- see OverviewTab.tsx and
 * components/boardx/mock.ts.
 *
 * No mascot anywhere on this page or its sub-components, per §5.10 (independently
 * confirmed by the brand's own mascot-placement rule in §0).
 */

import { useEffect, useMemo, useState } from "react";
import {
  api, ApiError, ApiUnreachable, type BoardFrequencyRow, type CohortReport, type Overview,
  type PaperReport,
} from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { FindingDrawer } from "@/components/boardx/FindingDrawer";
import type { BoardXFinding } from "@/components/boardx/types";
import { findingsFromTopLosses } from "@/components/boardx/findings";
import { OverviewTab } from "./OverviewTab";
import { StudentsTab } from "./StudentsTab";
import { SectionsTab, SubjectsTab, InterventionsTab } from "./SimpleTabs";

type TabKey = "overview" | "sections" | "subjects" | "students" | "interventions";
const TABS: { key: TabKey; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "sections", label: "Sections" },
  { key: "subjects", label: "Subjects" },
  { key: "students", label: "Students" },
  { key: "interventions", label: "Interventions" },
];

export default function BoardXPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [assessmentId, setAssessmentId] = useState<string>("");
  const [report, setReport] = useState<PaperReport | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [cohort, setCohort] = useState<CohortReport | null>(null);
  const [cohortNote, setCohortNote] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [freq, setFreq] = useState<BoardFrequencyRow[]>([]);

  const [tab, setTab] = useState<TabKey>("overview");
  const [studentsFilter, setStudentsFilter] = useState<{ band?: string; section?: string } | undefined>();
  const [drawerFinding, setDrawerFinding] = useState<BoardXFinding | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api.overview(key).then(setOverview).catch(() => setLoadError("Could not load your assessments."));
  }, []);

  useEffect(() => {
    if (!overview) return;
    if (!assessmentId && overview.assessments.length > 0) {
      setAssessmentId(overview.assessments[0].id);
    }
  }, [overview, assessmentId]);

  useEffect(() => {
    const key = getApiKey();
    if (!key || !assessmentId) return;
    setReport(null);
    setReportError(null);
    api.paperReport(key, assessmentId).then(setReport).catch((err: unknown) => {
      if (err instanceof ApiError && err.status === 404) {
        setReportError("No marks have been entered for this assessment yet.");
      } else if (err instanceof ApiUnreachable) {
        setReportError("Could not reach the API.");
      } else {
        setReportError("Could not load this assessment's diagnostic report.");
      }
    });
    setCohort(null);
    setCohortNote(null);
    setFreq([]);
    api.cohortReport(key, assessmentId).then((c) => {
      setCohort(c);
      const subject = overview?.assessments.find((a) => a.id === assessmentId)?.subject_code;
      if (subject) api.boardFrequency(key, subject).then(setFreq);
    }).catch((err: unknown) => {
      setCohortNote(
        err instanceof ApiError && err.status === 404
          ? "No marks have been entered for this assessment yet, so there is nothing to aggregate across students."
          : "Could not load the class-wide read of this assessment.",
      );
    });
  }, [assessmentId, overview]);

  const findings = useMemo(
    () => (cohort ? findingsFromTopLosses(cohort, freq) : []),
    [cohort, freq],
  );

  // §5.2 -- the Early Intelligence strip disappears on its own once this school has more
  // than one analysed assessment. Real data: Overview.assessments (every assessment the
  // school has actually created).
  const showEarlyIntelligence = (overview?.assessments.length ?? 0) <= 1;

  // §5.2 -- "Board Blueprint Mapping: Enabled/Disabled" -- real signal: whether any
  // top_loss on this paper resolved a board urgency tier at all (i.e. board frequency
  // data has been mapped for this subject).
  const blueprintMappingEnabled = findings.some((f) => f.urgencyTier != null);

  if (loadError) return <main className="wrap"><p className="error">{loadError}</p></main>;
  if (!overview) return <main className="wrap"><p className="muted">Loading…</p></main>;

  const assessment = overview.assessments.find((a) => a.id === assessmentId);

  function goToStudents(filter?: { band?: string; section?: string }) {
    setStudentsFilter(filter);
    setTab("students");
  }

  return (
    <main className="wrap">
      <header className="bx-header">
        <h1>AVAI BoardX</h1>

        <div className="bx-filterbar">
          <label>
            Assessment
            <select value={assessmentId} onChange={(e) => setAssessmentId(e.target.value)}>
              {overview.assessments.map((a) => (
                <option key={a.id} value={a.id}>{a.title}</option>
              ))}
            </select>
          </label>
        </div>

        {assessment && cohort && (
          <div className="bx-context">
            <span><strong>{cohort.students_analysed}</strong> Students Analysed</span>
            <span><strong>{cohort.section_bars.length}</strong> Sections Analysed</span>
            <span><strong>{cohort.subject_bars.length}</strong> Subjects Analysed</span>
            <span>Board Blueprint Mapping: <strong>{blueprintMappingEnabled ? "Enabled" : "Disabled"}</strong></span>
            <span>Assessment Evidence: <strong>1</strong></span>
          </div>
        )}

        {assessment && showEarlyIntelligence && (
          <div className="bx-earlyintel">
            <strong>ⓘ Early Intelligence:</strong> This analysis is based on {assessment.title}.
            Trend and multi-test insights become available once more assessments are analysed.
          </div>
        )}
      </header>

      <nav className="bx-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`bx-tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {overview.assessments.length === 0 && (
        <p className="notice mark">No assessments have been created for this school yet.</p>
      )}

      {assessment && (
        <div className="bx-content">
          {tab === "overview" && (
            <OverviewTab
              cohort={cohort} report={report} cohortNote={cohortNote} reportError={reportError}
              freq={freq} onOpenDrawer={setDrawerFinding} onGoToStudents={goToStudents}
            />
          )}
          {tab === "sections" && (
            <SectionsTab cohort={cohort} onGoToStudents={(section) => goToStudents({ section })} />
          )}
          {tab === "subjects" && <SubjectsTab cohort={cohort} />}
          {tab === "students" && (
            <StudentsTab
              overview={overview} assessmentId={assessmentId}
              initialBandFilter={studentsFilter?.band ?? studentsFilter?.section}
            />
          )}
          {tab === "interventions" && (
            <InterventionsTab findings={findings} onOpenDrawer={setDrawerFinding} onGoToStudents={() => goToStudents()} />
          )}
        </div>
      )}

      <FindingDrawer finding={drawerFinding} onClose={() => setDrawerFinding(null)} onViewStudents={() => { setDrawerFinding(null); goToStudents(); }} />

      <style jsx>{`
        .wrap { max-width: 1180px; margin: 0 auto; padding: 22px 0 60px; }
        .bx-header h1 {
          font-family: var(--font-display), sans-serif; font-size: 24px; font-weight: 800;
          color: var(--brand-ink); margin: 0 0 14px;
        }
        .bx-filterbar { margin-bottom: 12px; }
        .bx-filterbar label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; max-width: 360px; }
        .bx-filterbar select { padding: 8px 10px; font-size: 15px; }
        .bx-context { display: flex; flex-wrap: wrap; gap: 18px; font-size: 13.5px; color: var(--ink-2); margin-bottom: 12px; }
        .bx-earlyintel {
          background: var(--info-soft); border-radius: var(--radius, 12px); padding: 12px 16px;
          font-size: 13.5px; color: var(--ink-2); margin-bottom: 6px;
        }
        .bx-tabs {
          position: sticky; top: 0; z-index: 5; background: var(--paper); display: flex; gap: 4px;
          border-bottom: 1px solid var(--rule); padding: 14px 0 0; margin-bottom: 20px; flex-wrap: wrap;
        }
        .bx-tab {
          background: none; border: none; padding: 10px 16px; font-size: 14px; font-weight: 700;
          color: var(--ink-3); cursor: pointer; border-bottom: 3px solid transparent; font-family: inherit;
        }
        .bx-tab.active { color: var(--brand-ink); border-bottom-color: var(--brand-ink); }
        .error { color: var(--risk); }
      `}</style>
    </main>
  );
}
