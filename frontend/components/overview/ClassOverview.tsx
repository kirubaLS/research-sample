"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BookX, CalendarDays, ChevronRight, Download, Sparkles, TrendingDown, TrendingUp, Trophy, X } from "lucide-react";
import {
  allStudents,
  attentionFor,
  analysedTests,
  anomaliesFor,
  attentionBreakdown,
  classRosterFull,
  latestTest,
  lateBloomersFor,
  overallPctFor,
  pctFor,
  percentShares,
  projectedSubjectMarks,
  projectedTotalMarks,
  schoolSnapshot,
  sectionLabel,
  sectionStandings,
  sections,
  studentsInSubjectBand,
  studentsInTotalBand,
  subjectBandCounts,
  subjectMarkBands,
  subjects,
  subjectsByAverage,
  topGapFor,
  topStudents,
  totalBandCounts,
  totalMarkBands,
} from "@/lib/avai-mock-data";
import { downloadSectionsComparisonReport } from "@/lib/downloadReport";
import { HeaderActions, usePageHeader } from "@/lib/pageHeader";
import { SUBJECT_BAND_COLORS, TOTAL_BAND_COLORS } from "@/lib/bandColors";
import { BandPie } from "@/components/BandPie";
import { Reveal, Stagger, StaggerItem } from "@/components/motion";
import { OverviewKpis } from "@/components/overview/OverviewKpis";
import { BandDistribution } from "@/components/overview/BandDistribution";
import { SubjectPerformance } from "@/components/overview/SubjectPerformance";
import { StudentDrawer, StudentRow, type DrillDown } from "@/components/overview/StudentDrawer";
import { AnomalyGrid } from "@/components/overview/AnomalyGrid";
import { StudentRosterTable } from "@/components/StudentRosterTable";

type IntelPanel = "toppers" | "lateBloomers" | "weakestClass" | "weakestSubject" | null;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Dates are fixed mock strings, so they're formatted by hand rather than
 * with a locale-dependent formatter that could render differently. */
function longDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${Number(d)} ${MONTHS[Number(m) - 1]} ${y}`;
}

/** The Class X overview, or one section's version of it (same analysis,
 * scoped to that section, no anomalies, plus the searchable student list). Board-mark
 * distribution for the whole grade and by subject with student-level
 * drill-down, section/subject-filterable pies, and the intelligence layer
 * (toppers, late bloomers, weakest class/subject, anomalies). Every number
 * follows the assessment picked in the header, and all of them read from
 * the same roster every other screen reads, so nothing shown here can
 * disagree with a class or student page. */
export function ClassOverview({ section = "All" }: { section?: string }) {
  // Overall standing, as of the latest analysed test, not a per-assessment
  // breakdown (that lives on the Exams page).
  const testKey = latestTest.key;
  const test = latestTest;
  const isAll = section === "All";
  const scope = section;
  const label = isAll ? "Class X" : sectionLabel(section);
  const pool = useMemo(() => (isAll ? allStudents : (classRosterFull[section] ?? [])), [isAll, section]);
  const [drill, setDrill] = useState<DrillDown | null>(null);
  const [intelPanel, setIntelPanel] = useState<IntelPanel>(null);
  const [pieSubject, setPieSubject] = useState<string>("All");
  const [pieSection, setPieSection] = useState<string>(isAll ? sections[0] : section);

  usePageHeader({
    title: label,
    subtitle: isAll
      ? `Overall · as of ${test.name} · ${schoolSnapshot.students} students · ${sections.length} sections`
      : `Overall · as of ${test.name} · ${pool.length} students`,
    backHref: isAll ? undefined : "/principal/classes",
  });

  // ---------- Headline figures ----------
  const breakdown = useMemo(() => attentionBreakdown(testKey, scope), [testKey, scope]);

  const totalSegments = useMemo(() => {
    const counts = totalBandCounts(scope, testKey).map((c) => c.count);
    const shares = percentShares(counts);
    return totalMarkBands.map((band, i) => ({ label: band.label, count: counts[i], share: shares[i], color: TOTAL_BAND_COLORS[i] }));
  }, [testKey, scope]);

  // The subject-wise table has its own test filter, "All tests" averages a
  // student's % in a subject across every analysed test before banding it,
  // separate from the page's own "overall, as of the latest test" framing.
  const [subjectTestKey, setSubjectTestKey] = useState<string>("all");
  const [rosterTestKey, setRosterTestKey] = useState<string>(latestTest.key);

  function avgSubjectPctAcrossTests(student: (typeof allStudents)[number], subject: string): number {
    return analysedTests.reduce((sum, t) => sum + pctFor(student, t.key, subject), 0) / analysedTests.length;
  }

  const subjectRows = useMemo(() => {
    if (subjectTestKey === "all") {
      return subjects.map((subject) => {
        const avgs = pool.map((s) => avgSubjectPctAcrossTests(s, subject));
        const avgPct = avgs.reduce((a, b) => a + b, 0) / avgs.length;
        const counts = subjectMarkBands.map((band) => avgs.filter((v) => v >= band.min && v <= band.max).length);
        return { subject, avgPct, counts };
      });
    }
    return subjects.map((subject) => ({
      subject,
      avgPct: pool.length ? pool.reduce((sum, st) => sum + pctFor(st, subjectTestKey, subject), 0) / pool.length : 0,
      counts: subjectBandCounts(scope, subjectTestKey, subject).map((c) => c.count),
    }));
  }, [subjectTestKey, pool, scope]);

  function openTier(key: string, tileLabel: string) {
    const tier = key === "ontrack" ? "On Track" : key === "support" ? "Watch" : key === "risk" ? "Intervention" : null;
    setDrill({
      title: `${label}, ${tileLabel}`,
      subtitle: `Based on ${test.name}.`,
      students: [...pool]
        .filter((s) => tier === null || attentionFor(s, testKey) === tier)
        .sort((a, b) => projectedTotalMarks(b, testKey) - projectedTotalMarks(a, testKey)),
      metaFor: (s) => `${projectedTotalMarks(s, testKey)} / 500`,
    });
  }

  function openTotalBand(index: number) {
    const band = totalMarkBands[index];
    setDrill({
      title: `${label} overall, ${band.label}`,
      subtitle: `Projected Board total out of 500, based on ${test.name}.`,
      students: studentsInTotalBand(scope, testKey, band),
      metaFor: (s) => `${projectedTotalMarks(s, testKey)} / 500`,
    });
  }
  function openSubjectBand(subject: string, index: number) {
    const band = subjectMarkBands[index];
    if (subjectTestKey === "all") {
      const inBand = [...pool]
        .filter((s) => {
          const avg = avgSubjectPctAcrossTests(s, subject);
          return avg >= band.min && avg <= band.max;
        })
        .sort((a, b) => avgSubjectPctAcrossTests(b, subject) - avgSubjectPctAcrossTests(a, subject));
      setDrill({
        title: `${subject}, ${band.label}`,
        subtitle: `Projected Board marks out of 100, averaged across all ${analysedTests.length} analysed tests.`,
        students: inBand,
        metaFor: (s) => `${Math.round(avgSubjectPctAcrossTests(s, subject))} / 100`,
      });
      return;
    }
    setDrill({
      title: `${subject}, ${band.label}`,
      subtitle: `Projected Board marks out of 100, based on ${analysedTests.find((t) => t.key === subjectTestKey)?.name ?? test.name}.`,
      students: studentsInSubjectBand(scope, subjectTestKey, subject, band),
      metaFor: (s) => `${projectedSubjectMarks(s, subjectTestKey, subject)} / 100`,
    });
  }

  // ---------- Filters + pies ----------
  const pieBands = pieSubject === "All" ? totalMarkBands : subjectMarkBands;
  const pieColors = pieSubject === "All" ? TOTAL_BAND_COLORS : SUBJECT_BAND_COLORS;
  const overallCounts = pieSubject === "All" ? totalBandCounts("All", testKey) : subjectBandCounts("All", testKey, pieSubject);
  const comparedSection = isAll ? pieSection : section;
  const sectionCounts = pieSubject === "All" ? totalBandCounts(comparedSection, testKey) : subjectBandCounts(comparedSection, testKey, pieSubject);

  // ---------- Intelligence layer ----------
  const standings = useMemo(() => sectionStandings(testKey), [testKey]);
  const schoolToppers = useMemo(() => topStudents(10, testKey, scope), [testKey, scope]);
  const bloomers = useMemo(() => lateBloomersFor(10, testKey, scope), [testKey, scope]);
  const subjectStandings = useMemo(
    () =>
      isAll
        ? subjectsByAverage(testKey)
        : subjects
            .map((subject) => ({
              subject,
              avgPct: Math.round((pool.reduce((sum, st) => sum + pctFor(st, testKey, subject), 0) / Math.max(1, pool.length)) * 10) / 10,
            }))
            .sort((a, b) => a.avgPct - b.avgPct),
    [testKey, isAll, pool],
  );
  const anomalies = useMemo(() => (isAll ? anomaliesFor(testKey) : []), [testKey, isAll]);
  const weakestSection = [...standings].sort((a, b) => a.overallAttainment - b.overallAttainment)[0];
  const weakestSubject = subjectStandings[0];
  const ranked = [...standings].sort((a, b) => b.overallAttainment - a.overallAttainment);
  const ownStanding = standings.find((s) => s.section === section);
  const ownRank = ranked.findIndex((s) => s.section === section) + 1;

  return (
    <>
      <HeaderActions>
        {isAll && (
          <button className="btn btn--sm" onClick={() => downloadSectionsComparisonReport(testKey)}>
            <Download size={13} /> Download report
          </button>
        )}
      </HeaderActions>

      {/* Title block */}
      <Reveal>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h2 className="page-title" style={{ fontSize: 30, lineHeight: 1.15 }}>
              {label} <span className="gradient-text">Overview</span>
            </h2>
            <p className="page-sub" style={{ fontSize: 14 }}>
              Performance snapshot based on {test.name}. Projected onto Board scale (out of 500).
            </p>
          </div>
          <span className="tag">
            <CalendarDays size={12} /> Analysed {longDate(test.date)}
          </span>
        </div>
      </Reveal>

      <OverviewKpis breakdown={breakdown} totalSub={isAll ? `Across ${sections.length} sections` : `In ${label}`} onOpen={openTier} />

      <Reveal delay={0.1} style={{ marginTop: 20 }}>
        <BandDistribution
          title="Projected Board mark distribution"
          subtitle={`Out of 500 (based on ${test.name}). Click a band to see who's in it.`}
          segments={totalSegments}
          onSelect={openTotalBand}
        />
      </Reveal>

      <Reveal delay={0.16} style={{ marginTop: 20 }}>
        <SubjectPerformance
          title="Subject-wise performance"
          subtitle={`Out of 100 (${
            subjectTestKey === "all" ? `averaged across all ${analysedTests.length} analysed tests` : analysedTests.find((t) => t.key === subjectTestKey)?.name ?? test.name
          }). Click a count to see those students.`}
          bandLabels={subjectMarkBands.map((b) => b.label)}
          bandColors={SUBJECT_BAND_COLORS}
          rows={subjectRows}
          onOpen={openSubjectBand}
          controls={
            <div className="filter" style={{ marginBottom: 0 }}>
              <label htmlFor="subject-table-test">Assessment</label>
              <select id="subject-table-test" className="select" value={subjectTestKey} onChange={(e) => setSubjectTestKey(e.target.value)}>
                <option value="all">All tests</option>
                {analysedTests.map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
          }
        />
      </Reveal>

      {/* Filters + pies */}
      <section className="section">
        <div className="section__head">
          <div>
            <h2 className="section-q">Where the marks land</h2>
            <p className="section__lead">
              {isAll ? "Compare one section against the whole of Class X, overall or in a single subject." : `How ${label} compares with the whole of Class X, overall or in a single subject.`}
            </p>
          </div>
        </div>
        <div className="filterbar">
          <div className="filter">
            <label htmlFor="pie-subject">Subject</label>
            <select id="pie-subject" className="select" value={pieSubject} onChange={(e) => setPieSubject(e.target.value)}>
              <option value="All">All subjects (overall)</option>
              {subjects.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </div>
          {isAll && (
          <div className="filter">
            <label htmlFor="pie-section">Compare section</label>
            <select id="pie-section" className="select" value={pieSection} onChange={(e) => setPieSection(e.target.value)}>
              {sections.map((s) => (
                <option key={s} value={s}>
                  {sectionLabel(s)}
                </option>
              ))}
            </select>
          </div>
          )}
        </div>

        <Stagger className="grid grid--2" gap={0.08} style={{ marginTop: 16, alignItems: "start" }}>
          <StaggerItem>
            <div className="card hoverlift" style={{ height: "100%" }}>
              <div className="card__head">
                <h3 style={{ fontSize: 15 }}>Class X overall</h3>
                <span className="small muted">{pieSubject === "All" ? "All subjects" : pieSubject}</span>
              </div>
              <div className="card__body">
                <BandPie slices={pieBands.map((b, i) => ({ label: b.label, value: overallCounts[i].count, color: pieColors[i] }))} />
              </div>
            </div>
          </StaggerItem>
          <StaggerItem>
            <div className="card hoverlift" style={{ height: "100%" }}>
              <div className="card__head">
                <h3 style={{ fontSize: 15 }}>{sectionLabel(comparedSection)}</h3>
                <span className="small muted">{pieSubject === "All" ? "All subjects" : pieSubject}</span>
              </div>
              <div className="card__body">
                <BandPie slices={pieBands.map((b, i) => ({ label: b.label, value: sectionCounts[i].count, color: pieColors[i] }))} />
              </div>
            </div>
          </StaggerItem>
        </Stagger>
      </section>

      {/* Intelligence layer */}
      <section className="section">
        <div className="section__head">
          <div>
            <h2 className="section-q">
              <Sparkles size={17} style={{ verticalAlign: "-3px", marginRight: 6 }} /> Intelligence layer
            </h2>
            <p className="section__lead">Live, drawn from the same roster as everything above, not separate claims.</p>
          </div>
        </div>

        <Reveal>
          <div className="card intel-band">
            <button className="intel-band__seg" style={{ "--accent": "var(--brand-gold)" } as React.CSSProperties} onClick={() => setIntelPanel("toppers")}>
              <span className="intel-band__icon">
                <Trophy size={15} />
              </span>
              <div className="stat__label">Toppers</div>
              <div className="strong" style={{ fontSize: 16, marginTop: 6 }}>
                {schoolToppers[0]?.name ?? "-"}
              </div>
              <div className="small muted" style={{ marginTop: 2 }}>
                {schoolToppers[0] ? `${Math.round(overallPctFor(schoolToppers[0], testKey))}% overall, highest in ${label}` : "Not enough data"}
              </div>
              <ChevronRight size={15} className="intel-band__arrow" />
            </button>

            <button
              className="intel-band__seg"
              style={{ "--accent": "var(--brand-green)" } as React.CSSProperties}
              disabled={bloomers.length === 0}
              onClick={() => setIntelPanel("lateBloomers")}
            >
              <span className="intel-band__icon">
                <TrendingUp size={15} />
              </span>
              <div className="stat__label">Late bloomers</div>
              <div className="strong" style={{ fontSize: 16, marginTop: 6 }}>
                {bloomers.length > 0 ? `${bloomers.length} climbing` : "None this term"}
              </div>
              <div className="small muted" style={{ marginTop: 2 }}>
                {bloomers[0] ? `Led by ${bloomers[0].student.name}, +${bloomers[0].gain}pt since the previous test` : "Needs an earlier analysed test"}
              </div>
              <ChevronRight size={15} className="intel-band__arrow" />
            </button>

            <button className="intel-band__seg" style={{ "--accent": "var(--risk)" } as React.CSSProperties} onClick={() => setIntelPanel("weakestClass")}>
              <span className="intel-band__icon">
                <TrendingDown size={15} />
              </span>
              <div className="stat__label">{isAll ? "Weakest class" : "Against other sections"}</div>
              <div className="strong" style={{ fontSize: 16, marginTop: 6 }}>
                {isAll ? sectionLabel(weakestSection?.section ?? "") : `${ownStanding?.overallAttainment ?? 0}% overall`}
              </div>
              <div className="small muted" style={{ marginTop: 2 }}>
                {isAll
                  ? `${weakestSection?.overallAttainment}% overall attainment, lowest of ${sections.length} sections`
                  : `Ranked ${ownRank} of ${sections.length} sections in Class X`}
              </div>
              <ChevronRight size={15} className="intel-band__arrow" />
            </button>

            <button className="intel-band__seg" style={{ "--accent": "var(--info)" } as React.CSSProperties} onClick={() => setIntelPanel("weakestSubject")}>
              <span className="intel-band__icon">
                <BookX size={15} />
              </span>
              <div className="stat__label">Weakest subject</div>
              <div className="strong" style={{ fontSize: 16, marginTop: 6 }}>
                {weakestSubject?.subject}
              </div>
              <div className="small muted" style={{ marginTop: 2 }}>
                {weakestSubject?.avgPct}% {isAll ? "school" : "class"} average, lowest of {subjects.length} subjects
              </div>
              <ChevronRight size={15} className="intel-band__arrow" />
            </button>
          </div>
        </Reveal>

        {isAll && (
          <>
        {/* Anomalies */}
        <div className="section__head" style={{ marginTop: 28 }}>
          <div>
            <h3 className="section-q" style={{ fontSize: 16 }}>
              Anomalies worth a look
            </h3>
            <p className="section__lead">Real, numbers-backed surprises the averages above don&apos;t show on their own.</p>
          </div>
        </div>
        <AnomalyGrid anomalies={anomalies.slice(0, 8)} />
          </>
        )}
      </section>

      {!isAll && (
        <section className="section">
          <StudentRosterTable
            roster={pool}
            testKey={rosterTestKey}
            section={section}
            testStatus="Analysed"
            heading={
              <div className="section__head">
                <div>
                  <h2 className="section-q">Students in {label}</h2>
                  <p className="section__lead">Search by name, or tap a student to open their test-wise report.</p>
                </div>
              </div>
            }
            leadingFilters={
              <div className="filter">
                <label htmlFor="roster-test">Test</label>
                <select id="roster-test" className="select" value={rosterTestKey} onChange={(e) => setRosterTestKey(e.target.value)}>
                  {analysedTests.map((t) => (
                    <option key={t.key} value={t.key}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>
            }
          />
        </section>
      )}

      <StudentDrawer drill={drill} onClose={() => setDrill(null)} />

      {/* Intelligence layer drawer */}
      <AnimatePresence>
        {intelPanel && (
          <>
            <motion.div className="drawer-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setIntelPanel(null)} />
            <motion.aside
              className="drawer"
              role="dialog"
              aria-modal="true"
              initial={{ x: 40, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 40, opacity: 0 }}
              transition={{ type: "spring", stiffness: 380, damping: 34 }}
            >
              <div className="drawer__head">
                <h3 style={{ fontSize: 18 }}>
                  {intelPanel === "toppers" && "Toppers"}
                  {intelPanel === "lateBloomers" && "Late bloomers"}
                  {intelPanel === "weakestClass" && "Sections, weakest first"}
                  {intelPanel === "weakestSubject" && "Subjects, weakest first"}
                </h3>
                <button className="iconbtn" onClick={() => setIntelPanel(null)} aria-label="Close">
                  <X size={18} />
                </button>
              </div>
              <div className="drawer__body">
                {intelPanel === "toppers" && (
                  <>
                    <p className="small muted" style={{ marginTop: 0 }}>
                      Ranked by overall % across all {subjects.length} subjects, {test.name}.
                    </p>
                    <div className="drawer__section" style={{ marginTop: 0 }}>
                      <h4>{isAll ? "School-wide top 10" : `Top 10 in ${label}`}</h4>
                      <div style={{ display: "grid", gap: 8 }}>
                        {schoolToppers.map((s, i) => (
                          <StudentRow key={s.id} student={s} showSection meta={`#${i + 1} · ${Math.round(overallPctFor(s, testKey))}%`} />
                        ))}
                      </div>
                    </div>
                    {(isAll ? sections : []).map((sec) => (
                      <div className="drawer__section" key={sec}>
                        <h4>Top 3 in {sectionLabel(sec)}</h4>
                        <div style={{ display: "grid", gap: 8 }}>
                          {topStudents(3, testKey, sec).map((s, i) => (
                            <StudentRow key={s.id} student={s} showSection={false} meta={`#${i + 1}`} />
                          ))}
                        </div>
                      </div>
                    ))}
                  </>
                )}
                {intelPanel === "lateBloomers" && (
                  <div className="drawer__section" style={{ marginTop: 0 }}>
                    <h4>
                      {bloomers.length} student{bloomers.length === 1 ? "" : "s"} gained ground between {test.name} and the test before it
                    </h4>
                    <div style={{ display: "grid", gap: 8 }}>
                      {bloomers.map((b) => (
                        <StudentRow key={b.student.id} student={b.student} showSection meta={`${b.prevPct}% → ${b.nowPct}% (+${b.gain}pt)`} />
                      ))}
                      {bloomers.length === 0 && <p className="small muted">Needs an earlier analysed test to show movement.</p>}
                    </div>
                  </div>
                )}
                {intelPanel === "weakestClass" && (
                  <div className="drawer__section" style={{ marginTop: 0 }}>
                    <h4>Overall attainment, average % across all {subjects.length} subjects, {test.name}</h4>
                    <div style={{ display: "grid", gap: 14 }}>
                      {[...standings]
                        .sort((a, b) => a.overallAttainment - b.overallAttainment)
                        .map((s) => (
                          <div key={s.section}>
                            <div className="bar-row" style={{ gridTemplateColumns: "70px 1fr 50px" }}>
                              <div className="bar-row__label strong">{sectionLabel(s.section)}</div>
                              <div className="bar">
                                <div
                                  className={`bar__fill ${s.overallAttainment >= 78 ? "bar__fill--green" : s.overallAttainment >= 70 ? "bar__fill--gold" : "bar__fill--risk"}`}
                                  style={{ width: `${s.overallAttainment}%` }}
                                />
                              </div>
                              <div className="bar-row__val">{s.overallAttainment}%</div>
                            </div>
                            <div className="small muted" style={{ marginTop: 2 }}>
                              Biggest gap: <strong>{topGapFor(s.section, testKey)}</strong> · {s.needAttention} of {s.students} need attention
                              {s.critical > 0 ? ` (${s.critical} critical)` : ""}.
                            </div>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
                {intelPanel === "weakestSubject" && (
                  <div className="drawer__section" style={{ marginTop: 0 }}>
                    <h4>{isAll ? "School" : label} average per subject, {test.name}</h4>
                    <div style={{ display: "grid", gap: 6 }}>
                      {subjectStandings.map((s) => (
                        <div className="bar-row" key={s.subject} style={{ gridTemplateColumns: "140px 1fr 50px" }}>
                          <div className="bar-row__label strong">{s.subject}</div>
                          <div className="bar">
                            <div
                              className={`bar__fill ${s.avgPct >= 78 ? "bar__fill--green" : s.avgPct >= 70 ? "bar__fill--gold" : "bar__fill--risk"}`}
                              style={{ width: `${s.avgPct}%` }}
                            />
                          </div>
                          <div className="bar-row__val">{s.avgPct}%</div>
                        </div>
                      ))}
                    </div>
                    <h4 style={{ marginTop: 22 }}>Where, each subject, broken down by section</h4>
                    <p className="small muted" style={{ marginTop: -4, marginBottom: 10 }}>
                      Every subject&apos;s weakest section is highlighted, so a low school average never hides which class is actually pulling it down.
                    </p>
                    <div className="table-wrap">
                      <table className="table">
                        <thead>
                          <tr>
                            <th>Subject</th>
                            {sections.map((sec) => (
                              <th key={sec} className="num">
                                {sectionLabel(sec)}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {subjectStandings.map((s) => {
                            const bySection = sections.map((sec) => {
                              const roster = classRosterFull[sec] ?? [];
                              const avg = roster.length ? roster.reduce((sum, st) => sum + pctFor(st, testKey, s.subject), 0) / roster.length : 0;
                              return { section: sec, pct: Math.round(avg) };
                            });
                            const min = Math.min(...bySection.map((b) => b.pct));
                            return (
                              <tr key={s.subject}>
                                <td className="strong">{s.subject}</td>
                                {bySection.map((b) => (
                                  <td key={b.section} className="num" style={b.pct === min ? { color: "var(--risk)", fontWeight: 700 } : undefined}>
                                    {b.pct}%
                                  </td>
                                ))}
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
