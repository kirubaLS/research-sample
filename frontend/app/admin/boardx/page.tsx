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
import { StatTile, StatTileRow } from "@/components/academics/StatTile";
import { PeopleIcon, ClipboardIcon, BookIcon, TargetIcon } from "@/components/academics/Icons";

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

  if (loadError) return <main className="content"><div className="evidence evidence--gold"><div>{loadError}</div></div></main>;
  if (!overview) return <main className="content"><p className="muted">Loading…</p></main>;

  const assessment = overview.assessments.find((a) => a.id === assessmentId);

  function goToStudents(filter?: { band?: string; section?: string }) {
    setStudentsFilter(filter);
    setTab("students");
  }

  return (
    <main className="content">
      <header className="bx-header">
        <h1 className="page-title">AVAI BoardX</h1>

        <div className="filterbar" style={{ position: "static" }}>
          <div className="filter">
            <label htmlFor="bx-assessment">Assessment</label>
            <select id="bx-assessment" className="select" value={assessmentId} onChange={(e) => setAssessmentId(e.target.value)}>
              {overview.assessments.map((a) => (
                <option key={a.id} value={a.id}>{a.title}</option>
              ))}
            </select>
          </div>
        </div>

        {assessment && cohort && (
          <StatTileRow>
            <StatTile icon={<PeopleIcon />} tone="info" value={cohort.students_analysed} label="Students Analysed" />
            <StatTile icon={<ClipboardIcon />} tone="violet" value={cohort.section_bars.length} label="Sections Analysed" />
            <StatTile icon={<BookIcon />} tone="gold" value={cohort.subject_bars.length} label="Subjects Analysed" />
            <StatTile
              icon={<TargetIcon />}
              tone={blueprintMappingEnabled ? "verify" : "neutral"}
              value={blueprintMappingEnabled ? "Enabled" : "Disabled"}
              label="Board Blueprint Mapping"
            />
            <StatTile icon={<ClipboardIcon />} tone="neutral" value={1} label="Assessment Evidence" />
          </StatTileRow>
        )}

        {assessment && showEarlyIntelligence && (
          <div className="evidence" style={{ marginBottom: 6 }}>
            <div><strong>ⓘ Early Intelligence:</strong> This analysis is based on {assessment.title}.
            Trend and multi-test insights become available once more assessments are analysed.</div>
          </div>
        )}
      </header>

      <nav className="tabs" style={{ marginBottom: 20 }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`tab ${tab === t.key ? "tab--active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {overview.assessments.length === 0 && (
        <div className="evidence evidence--neutral">
          <div>No assessments have been created for this school yet.</div>
        </div>
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
        .bx-header { margin-bottom: 4px; }
      `}</style>
    </main>
  );
}
