"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { analysedTests, findings, latestTest, rosterFor, subjectSnapshotFor, testsConducted } from "@/lib/avai-mock-data";
import { useLiveVersion } from "@/lib/liveData";
import { usePageHeader } from "@/lib/pageHeader";
import { EvidenceState } from "@/components/EvidenceState";
import { FindingCard } from "@/components/FindingCard";
import { MarksEntryGrid } from "@/components/MarksEntryGrid";
import { QuestionPaperPanel } from "@/components/QuestionPaperPanel";
import { SubjectRoster } from "@/components/SubjectRoster";

/** §6.3 Subject view, one subject, one section, with Question Paper and
 * Enter Marks tabs (both moved here from the principal's nav, a subject's
 * paper and marks are a subject teacher's job, not the principal's). */
export default function SubjectView() {
  const params = useParams<{ subject: string; section: string }>();
  const subject = decodeURIComponent(params.subject);
  const section = params.section;
  usePageHeader({ title: `${subject} · ${section}`, backHref: "/teacher/home" });
  const [tab, setTab] = useState<"insights" | "paper" | "marks">("insights");
  const [testKey, setTestKey] = useState(latestTest.key);
  const [marksTestKey, setMarksTestKey] = useState(latestTest.key);
  const { user } = useAuth();
  useLiveVersion();

  const allowed = user?.role === "teacher" && user.assignments.some((a) => a.type === "subject" && a.subject === subject && a.sections.includes(section));
  if (!allowed) return <EvidenceState kind="cause">You are not assigned to {subject} for {section}.</EvidenceState>;

  const test = analysedTests.find((t) => t.key === testKey) ?? latestTest;
  const snap = subjectSnapshotFor(subject, section, testKey);
  const subjectFindings = findings.filter((f) => f.subject === subject);
  const roster = rosterFor(section, latestTest.key);

  return (
    <>
      <p className="page-sub" style={{ marginTop: 0 }}>
        After {test.name} · top gap: {snap.topGap}
      </p>

      <div className="tabs" role="tablist" style={{ marginTop: 18 }}>
        <button role="tab" aria-selected={tab === "insights"} className={`tab ${tab === "insights" ? "tab--active" : ""}`} onClick={() => setTab("insights")}>
          Insights
        </button>
        <button role="tab" aria-selected={tab === "paper"} className={`tab ${tab === "paper" ? "tab--active" : ""}`} onClick={() => setTab("paper")}>
          Question paper
        </button>
        <button role="tab" aria-selected={tab === "marks"} className={`tab ${tab === "marks" ? "tab--active" : ""}`} onClick={() => setTab("marks")}>
          Enter marks
        </button>
      </div>

      {tab === "insights" ? (
        <>
          <div className="grid grid--3" style={{ marginTop: 18 }}>
            <div className="stat">
              <div className="stat__label">Marks tested</div>
              <div className="stat__value">{snap.marksTested}</div>
            </div>
            <div className="stat">
              <div className="stat__label">Avg attainment</div>
              <div className="stat__value">
                {snap.avgAttainment} <span className="small muted" style={{ fontWeight: 500 }}>/ {snap.marksTested}</span>
              </div>
            </div>
            <div className="stat">
              <div className="stat__label">At expected level</div>
              <div className="stat__value">
                {snap.atExpectedLevelPct}%
                <span className="small muted" style={{ fontWeight: 400 }}> of {roster.length}</span>
              </div>
            </div>
          </div>

          <section className="section">
            <div className="section__head">
              <h2 className="section-q">Findings in {subject}</h2>
            </div>
            {subjectFindings.length ? (
              <div className="grid grid--2">
                {subjectFindings.map((f) => (
                  <FindingCard key={f.id} finding={f} compact />
                ))}
              </div>
            ) : (
              <EvidenceState kind="early">No findings in {subject} rise above the evidence threshold from a single test.</EvidenceState>
            )}
          </section>

          <section className="section">
            <div className="section__head">
              <h2 className="section-q">
                {section} students in {subject}
              </h2>
              <div className="filter">
                <label htmlFor="roster-test">Assessment</label>
                <select id="roster-test" className="select" value={testKey} onChange={(e) => setTestKey(e.target.value)}>
                  {analysedTests.map((t) => (
                    <option key={t.key} value={t.key}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <SubjectRoster subject={subject} section={section} testKey={testKey} />
          </section>
        </>
      ) : tab === "paper" ? (
        <div style={{ marginTop: 18 }}>
          <QuestionPaperPanel subject={subject} section={section} />
        </div>
      ) : (
        <div style={{ marginTop: 18 }}>
          <div className="filter" style={{ maxWidth: 280 }}>
            <label htmlFor="marks-test">Assessment</label>
            <select id="marks-test" className="select" value={marksTestKey} onChange={(e) => setMarksTestKey(e.target.value)}>
              {testsConducted
                .filter((t) => (t.subjects ?? [subject]).includes(subject))
                .map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.name}
                    {t.status === "Analysed" ? "" : " (not yet analysed)"}
                  </option>
                ))}
            </select>
          </div>
          <MarksEntryGrid
            key={`${subject}-${section}-${marksTestKey}`}
            subject={subject}
            roster={roster}
            scopeLabel={`${subject} · ${section} · ${testsConducted.find((t) => t.key === marksTestKey)?.name ?? ""}`}
            testKey={marksTestKey}
          />
        </div>
      )}
    </>
  );
}
