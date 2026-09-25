"use client";

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BookX, CalendarDays, ChevronRight, Sparkles, TrendingDown, TrendingUp, Trophy } from "lucide-react";
import {
  api,
  type AcademicsOverview,
  type AcademicTestRow,
  type ClassAcademicSummary,
  type ClassStudentRow,
  type CohortReport,
} from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { usePageHeader } from "@/lib/pageHeader";
import { TOTAL_BAND_COLORS } from "@/lib/bandColors";
import { Reveal, Stagger, StaggerItem } from "@/components/motion";
import { OverviewKpis, type AttentionBreakdown } from "@/components/overview/OverviewKpis";
import { BandDistribution } from "@/components/overview/BandDistribution";
import { SubjectPerformance } from "@/components/overview/SubjectPerformance";
import { StudentDrawer, StudentRow, type DrillDown, type DrillStudent } from "@/components/overview/StudentDrawer";
import { AnomalyGrid } from "@/components/overview/AnomalyGrid";
import { MarksDonuts } from "@/components/overview/MarksDonuts";
import { StudentRosterTable } from "@/components/StudentRosterTable";

type IntelPanel = "toppers" | "climbers" | "weakestClass" | "weakestSubject" | null;

interface Climber {
  student: DrillStudent;
  delta: number;
  now: number | null;
}

function toDrill(rows: ClassStudentRow[], sectionId: string, sectionLabel: string): DrillStudent[] {
  return rows.map((r) => ({ student_id: r.student_id, name: r.name, roll_no: r.roll_no, section_id: sectionId, section_label: sectionLabel }));
}

/** The Class X overview, or one section's version of it -- real data from
 * GET /admin/academics (per-class summary), GET /admin/academics/tests (which
 * assessment to show), and GET /reports/cohort/{id} (band distribution, subject
 * averages, section comparison, top concept losses) for the selected assessment.
 * Every number here comes straight from those three calls; nothing is derived from
 * fake per-test deltas the backend has no concept of. */
export function ClassOverview({ section }: { section?: string }) {
  const isAll = !section;
  const key = getApiKey() ?? "";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overview, setOverview] = useState<AcademicsOverview | null>(null);
  const [tests, setTests] = useState<AcademicTestRow[]>([]);
  const [testKey, setTestKey] = useState<string>("");
  const [cohort, setCohort] = useState<CohortReport | null>(null);
  const [drill, setDrill] = useState<DrillDown | null>(null);
  const [intelPanel, setIntelPanel] = useState<IntelPanel>(null);
  const [toppers, setToppers] = useState<DrillStudent[]>([]);
  /** Students whose score on the selected test rose against their own previous
   * same-subject test -- GET /admin/academics/{id}/students' real delta_pct, per section. */
  const [climbers, setClimbers] = useState<Climber[] | null>(null);
  const [previousTitle, setPreviousTitle] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [ov, t] = await Promise.all([api.academicsOverview(key), api.academicsTests(key)]);
        if (cancelled) return;
        setOverview(ov);
        setTests(t.tests);
        // GET /admin/academics/tests is newest first; open on the latest test.
        if (t.tests.length) setTestKey((prev) => prev || t.tests[0].assessment_id);
      } catch {
        if (!cancelled) setError("Could not load the class overview.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!testKey) return;
    let cancelled = false;
    (async () => {
      try {
        const c = await api.cohortReport(key, testKey, isAll ? undefined : section);
        if (!cancelled) setCohort(c);
      } catch {
        if (!cancelled) setCohort(null);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testKey, section]);

  const classes = overview?.classes ?? [];
  const thisClass = useMemo(() => classes.find((c) => c.section_id === section), [classes, section]);
  const sectionLabelFor = (id: string) => classes.find((c) => c.section_id === id)?.label ?? id;
  const label = isAll ? (overview?.school.name ?? "Class X") : (thisClass?.label ?? section ?? "");
  const test = tests.find((t) => t.assessment_id === testKey);

  usePageHeader({
    title: label,
    subtitle: isAll
      ? `Overall · as of ${test?.title ?? "-"} · ${classes.reduce((s, c) => s + c.student_count, 0)} students · ${classes.length} sections`
      : `Overall · as of ${test?.title ?? "-"} · ${thisClass?.student_count ?? 0} students`,
    backHref: isAll ? undefined : "/principal/classes",
  });

  const breakdown: AttentionBreakdown = useMemo(() => {
    const rows = isAll ? classes : thisClass ? [thisClass] : [];
    return rows.reduce(
      (acc, c: ClassAcademicSummary) => ({
        total: acc.total + c.student_count,
        onTrack: acc.onTrack + c.status_counts.on_track,
        watch: acc.watch + c.status_counts.needs_attention,
        intervention: acc.intervention + c.status_counts.requires_review,
      }),
      { total: 0, onTrack: 0, watch: 0, intervention: 0 },
    );
  }, [isAll, classes, thisClass]);

  const totalSegments = useMemo(() => {
    if (!cohort) return [];
    const order: (keyof CohortReport["band_counts"])[] = ["full_mastery", "band_80_89", "band_60_79", "below_60"];
    const labels = ["90-100", "80-89", "60-79", "Below 60"];
    return order.map((k, i) => ({ label: labels[i], count: cohort.band_counts[k], share: Math.round(cohort.band_pct[k]), color: TOTAL_BAND_COLORS[i] }));
  }, [cohort]);

  const subjectRows = useMemo(
    () =>
      (cohort?.subject_bars ?? []).map((s) => ({
        subject: s.subject_label,
        avgPct: s.pct,
        counts: [s.band_counts.full_mastery, s.band_counts.band_80_89, s.band_counts.band_60_79, s.band_counts.below_60],
      })),
    [cohort],
  );

  // Score bands implied by GET /reports/cohort/{id}'s own field names.
  const BAND_RANGES: [number, number][] = [
    [90, 100],
    [80, 89.999],
    [60, 79.999],
    [0, 59.999],
  ];

  async function studentsFor(filters: { status?: ClassStudentRow["status"]; subjectCode?: string; assessmentId?: string }): Promise<{ rows: ClassStudentRow[]; sectionId: string; sectionLabel: string; previousTitle: string | null }[]> {
    const targets = isAll ? classes : thisClass ? [thisClass] : [];
    const results = await Promise.all(
      targets.map(async (c) => {
        try {
          const view = await api.classStudents(key, c.section_id, { assessmentId: testKey, ...filters });
          return { rows: view.students, sectionId: c.section_id, sectionLabel: c.label, previousTitle: view.previous_test?.title ?? null };
        } catch {
          return { rows: [] as ClassStudentRow[], sectionId: c.section_id, sectionLabel: c.label, previousTitle: null };
        }
      }),
    );
    return results;
  }

  async function openTier(tierKey: string, tileLabel: string) {
    if (tierKey === "total") {
      const groups = await studentsFor({});
      setDrill({ title: `${label}, ${tileLabel}`, subtitle: `Based on ${test?.title ?? "the selected assessment"}.`, students: groups.flatMap((g) => toDrill(g.rows, g.sectionId, g.sectionLabel)) });
      return;
    }
    const status = tierKey === "ontrack" ? "on_track" : tierKey === "support" ? "needs_attention" : "requires_review";
    const groups = await studentsFor({ status });
    setDrill({
      title: `${label}, ${tileLabel}`,
      subtitle: `Based on ${test?.title ?? "the selected assessment"}.`,
      students: groups.flatMap((g) => toDrill(g.rows, g.sectionId, g.sectionLabel)),
      metaFor: (s) => {
        const row = groups.flatMap((g) => g.rows).find((r) => r.student_id === s.student_id);
        return row?.avg_score_pct === null || row?.avg_score_pct === undefined ? "-" : `${Math.round(row.avg_score_pct)}%`;
      },
    });
  }

  async function openTotalBand(index: number) {
    const [min, max] = BAND_RANGES[index];
    const groups = await studentsFor({});
    const inBand = groups.flatMap((g) => g.rows.filter((r) => r.avg_score_pct !== null && r.avg_score_pct >= min && r.avg_score_pct <= max).map((r) => ({ r, sectionId: g.sectionId, sectionLabel: g.sectionLabel })));
    setDrill({
      title: `${label} overall, ${totalSegments[index]?.label ?? ""}`,
      subtitle: `Score band, based on ${test?.title ?? "the selected assessment"}.`,
      students: inBand.map(({ r, sectionId, sectionLabel }) => ({ student_id: r.student_id, name: r.name, roll_no: r.roll_no, section_id: sectionId, section_label: sectionLabel })),
      metaFor: (s) => {
        const found = inBand.find((x) => x.r.student_id === s.student_id);
        return found?.r.avg_score_pct === null || found?.r.avg_score_pct === undefined ? "-" : `${Math.round(found.r.avg_score_pct)}%`;
      },
    });
  }

  async function openSubjectBand(subjectLabel: string, index: number) {
    const subjectBar = cohort?.subject_bars.find((s) => s.subject_label === subjectLabel);
    if (!subjectBar) return;
    const [min, max] = BAND_RANGES[index] ?? [0, 100];
    // Each subject's band counts come from that subject's own paper (subject_bars'
    // assessment_id), so the drill-down reads the same paper -- not the selected test.
    const groups = await studentsFor({ subjectCode: subjectBar.subject_code, assessmentId: subjectBar.assessment_id });
    const inBand = groups.flatMap((g) => g.rows.filter((r) => r.avg_score_pct !== null && r.avg_score_pct >= min && r.avg_score_pct <= max).map((r) => ({ r, sectionId: g.sectionId, sectionLabel: g.sectionLabel })));
    setDrill({
      title: `${subjectLabel}, ${["90-100", "80-89", "60-79", "Below 60"][index] ?? ""}`,
      subtitle: `Based on ${test?.title ?? "the selected assessment"}.`,
      students: inBand.map(({ r, sectionId, sectionLabel }) => ({ student_id: r.student_id, name: r.name, roll_no: r.roll_no, section_id: sectionId, section_label: sectionLabel })),
      metaFor: (s) => {
        const found = inBand.find((x) => x.r.student_id === s.student_id);
        return found?.r.avg_score_pct === null || found?.r.avg_score_pct === undefined ? "-" : `${Math.round(found.r.avg_score_pct)}%`;
      },
    });
  }

  async function openToppers() {
    const groups = await studentsFor({});
    const merged = groups.flatMap((g) => g.rows.map((r) => ({ r, sectionId: g.sectionId, sectionLabel: g.sectionLabel })));
    merged.sort((a, b) => (b.r.avg_score_pct ?? -1) - (a.r.avg_score_pct ?? -1));
    setToppers(merged.slice(0, 10).map(({ r, sectionId, sectionLabel }) => ({ student_id: r.student_id, name: r.name, roll_no: r.roll_no, section_id: sectionId, section_label: sectionLabel })));
    setIntelPanel("toppers");
  }

  useEffect(() => {
    if (!testKey || !classes.length) return;
    let cancelled = false;
    setClimbers(null);
    (async () => {
      const groups = await studentsFor({});
      if (cancelled) return;
      const list: Climber[] = groups
        .flatMap((g) =>
          g.rows
            .filter((r) => r.delta_pct !== null && r.delta_pct > 0)
            .map((r) => ({
              student: { student_id: r.student_id, name: r.name, roll_no: r.roll_no, section_id: g.sectionId, section_label: g.sectionLabel },
              delta: r.delta_pct as number,
              now: r.avg_score_pct,
            })),
        )
        .sort((a, b) => b.delta - a.delta);
      setClimbers(list);
      setPreviousTitle(groups.find((g) => g.previousTitle)?.previousTitle ?? null);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testKey, classes, section]);

  const weakestSection = isAll ? [...classes].sort((a, b) => (a.avg_score_pct ?? 0) - (b.avg_score_pct ?? 0))[0] : undefined;
  const rankedSections = isAll ? [...classes].sort((a, b) => (b.avg_score_pct ?? 0) - (a.avg_score_pct ?? 0)) : [];
  const ownRank = !isAll ? rankedSections.findIndex((c) => c.section_id === section) + 1 : 0;
  const subjectStandings = useMemo(() => [...(cohort?.subject_bars ?? [])].sort((a, b) => a.pct - b.pct), [cohort]);
  const losses = cohort?.top_losses ?? [];

  if (loading) {
    return <p className="muted">Loading…</p>;
  }
  if (error) {
    return <p className="muted">{error}</p>;
  }

  return (
    <>
      <Reveal>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h2 className="page-title" style={{ fontSize: 30, lineHeight: 1.15 }}>
              {label} <span className="gradient-text">Overview</span>
            </h2>
            <p className="page-sub" style={{ fontSize: 14 }}>
              Performance snapshot based on {test?.title ?? "the selected assessment"}.
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="tag">
              <CalendarDays size={12} /> {tests.length} analysed test{tests.length === 1 ? "" : "s"}
            </span>
            {tests.length > 1 && (
              <select className="select" value={testKey} onChange={(e) => setTestKey(e.target.value)}>
                {tests.map((t) => (
                  <option key={t.assessment_id} value={t.assessment_id}>
                    {t.title}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
      </Reveal>

      <OverviewKpis breakdown={breakdown} totalSub={isAll ? `Across ${classes.length} sections` : `In ${label}`} onOpen={openTier} />

      {cohort && (
        <Reveal delay={0.1} style={{ marginTop: 20 }}>
          <BandDistribution
            title="Score band distribution"
            subtitle={`Based on ${test?.title ?? "the selected assessment"}. Click a band to see who's in it.`}
            segments={totalSegments}
            onSelect={openTotalBand}
          />
        </Reveal>
      )}

      {testKey && classes.length > 0 && (
        <Reveal delay={0.13} style={{ marginTop: 20 }}>
          <MarksDonuts
            assessmentId={testKey}
            testTitle={test?.title ?? "the selected assessment"}
            wholeLabel={overview?.school.name ?? "the class"}
            sections={classes.map((c) => ({ section_id: c.section_id, label: c.label }))}
            defaultSectionId={isAll ? undefined : section}
            onSelectWhole={isAll ? openTotalBand : undefined}
          />
        </Reveal>
      )}

      {cohort && (
        <Reveal delay={0.16} style={{ marginTop: 20 }}>
          <SubjectPerformance
            title="Subject-wise performance"
            subtitle={`Each subject's latest paper for ${isAll ? "these sections" : label}: its average, and how many students land in each band.`}
            bandLabels={["90-100", "80-89", "60-79", "Below 60"]}
            bandColors={TOTAL_BAND_COLORS}
            rows={subjectRows}
            onOpen={openSubjectBand}
          />
        </Reveal>
      )}

      <section className="section">
        <div className="section__head">
          <div>
            <h2 className="section-q">
              <Sparkles size={17} style={{ verticalAlign: "-3px", marginRight: 6 }} /> Intelligence layer
            </h2>
            <p className="section__lead">Live, drawn from the same real data as everything above.</p>
          </div>
        </div>

        <Reveal>
          <div className="card intel-band">
            <button className="intel-band__seg" style={{ "--accent": "var(--brand-gold)" } as React.CSSProperties} onClick={openToppers}>
              <span className="intel-band__icon">
                <Trophy size={15} />
              </span>
              <div className="stat__label">Toppers</div>
              <div className="strong" style={{ fontSize: 16, marginTop: 6 }}>
                Top 10
              </div>
              <div className="small muted" style={{ marginTop: 2 }}>
                By score on {test?.title ?? "the selected assessment"}
              </div>
              <ChevronRight size={15} className="intel-band__arrow" />
            </button>

            <button
              className="intel-band__seg"
              style={{ "--accent": "var(--brand-blue)" } as React.CSSProperties}
              onClick={() => setIntelPanel("climbers")}
              disabled={!climbers || climbers.length === 0}
            >
              <span className="intel-band__icon">
                <TrendingUp size={15} />
              </span>
              <div className="stat__label">Late bloomers</div>
              <div className="strong" style={{ fontSize: 16, marginTop: 6 }}>
                {climbers === null ? "…" : previousTitle === null ? "No earlier test" : `${climbers.length} climbing`}
              </div>
              <div className="small muted" style={{ marginTop: 2 }}>
                {climbers && climbers.length > 0
                  ? `Led by ${climbers[0].student.name}, +${climbers[0].delta}pt since the previous test`
                  : previousTitle === null
                    ? "Needs a previous test of the same subject to compare"
                    : "Nobody rose since the previous test"}
              </div>
              {climbers && climbers.length > 0 && <ChevronRight size={15} className="intel-band__arrow" />}
            </button>

            <button className="intel-band__seg" style={{ "--accent": "var(--risk)" } as React.CSSProperties} onClick={() => setIntelPanel("weakestClass")}>
              <span className="intel-band__icon">
                <TrendingDown size={15} />
              </span>
              <div className="stat__label">{isAll ? "Weakest class" : "Against other sections"}</div>
              <div className="strong" style={{ fontSize: 16, marginTop: 6 }}>
                {isAll ? (weakestSection?.label ?? "-") : `${thisClass?.avg_score_pct ?? 0}% overall`}
              </div>
              <div className="small muted" style={{ marginTop: 2 }}>
                {isAll
                  ? `${weakestSection?.avg_score_pct ?? 0}% avg score, lowest of ${classes.length} sections`
                  : `Ranked ${ownRank} of ${rankedSections.length} sections`}
              </div>
              <ChevronRight size={15} className="intel-band__arrow" />
            </button>

            <button className="intel-band__seg" style={{ "--accent": "var(--info)" } as React.CSSProperties} onClick={() => setIntelPanel("weakestSubject")} disabled={!cohort}>
              <span className="intel-band__icon">
                <BookX size={15} />
              </span>
              <div className="stat__label">Weakest subject</div>
              <div className="strong" style={{ fontSize: 16, marginTop: 6 }}>
                {subjectStandings[0]?.subject_label ?? "-"}
              </div>
              <div className="small muted" style={{ marginTop: 2 }}>
                {subjectStandings[0] ? `${subjectStandings[0].pct}% average, lowest of ${subjectStandings.length} subjects` : "No data yet"}
              </div>
              <ChevronRight size={15} className="intel-band__arrow" />
            </button>
          </div>
        </Reveal>

        <div className="section__head" style={{ marginTop: 28 }}>
          <div>
            <h3 className="section-q" style={{ fontSize: 16 }}>
              Concept losses worth a look
            </h3>
            <p className="section__lead">Real, numbers-backed concept losses from this assessment&apos;s cohort report.</p>
          </div>
        </div>
        <AnomalyGrid losses={losses.slice(0, 8)} />
      </section>

      {!isAll && thisClass && (
        <SectionRoster sectionId={thisClass.section_id} sectionLabel={thisClass.label} defaultTestKey={testKey} />
      )}

      <StudentDrawer drill={drill} onClose={() => setDrill(null)} />

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
                  {intelPanel === "climbers" && "Late bloomers"}
                  {intelPanel === "weakestClass" && "Sections, weakest first"}
                  {intelPanel === "weakestSubject" && "Subjects, weakest first"}
                </h3>
                <button className="iconbtn" onClick={() => setIntelPanel(null)} aria-label="Close">
                  <ChevronRight size={0} />
                </button>
              </div>
              <div className="drawer__body">
                {intelPanel === "toppers" && (
                  <div className="drawer__section" style={{ marginTop: 0 }}>
                    <h4>{isAll ? "School-wide top 10" : `Top 10 in ${label}`}</h4>
                    <div style={{ display: "grid", gap: 8 }}>
                      {toppers.map((s, i) => (
                        <StudentRow key={s.student_id} student={s} showSection meta={`#${i + 1}`} />
                      ))}
                    </div>
                  </div>
                )}
                {intelPanel === "climbers" && climbers && (
                  <div className="drawer__section" style={{ marginTop: 0 }}>
                    <h4>
                      Score rose on {test?.title ?? "this test"} vs {previousTitle ?? "the previous test"}
                    </h4>
                    <div style={{ display: "grid", gap: 8 }}>
                      {climbers.map((c) => (
                        <StudentRow key={c.student.student_id} student={c.student} showSection={isAll} meta={`+${c.delta}pt${c.now !== null ? ` · now ${Math.round(c.now)}%` : ""}`} />
                      ))}
                    </div>
                  </div>
                )}
                {intelPanel === "weakestClass" && (
                  <div className="drawer__section" style={{ marginTop: 0 }}>
                    <h4>Average score, {test?.title ?? "the selected assessment"}</h4>
                    <div style={{ display: "grid", gap: 14 }}>
                      {[...classes]
                        .sort((a, b) => (a.avg_score_pct ?? 0) - (b.avg_score_pct ?? 0))
                        .map((c) => (
                          <div key={c.section_id}>
                            <div className="bar-row" style={{ gridTemplateColumns: "70px 1fr 50px" }}>
                              <div className="bar-row__label strong">{c.label}</div>
                              <div className="bar">
                                <div
                                  className={`bar__fill ${(c.avg_score_pct ?? 0) >= 78 ? "bar__fill--green" : (c.avg_score_pct ?? 0) >= 70 ? "bar__fill--gold" : "bar__fill--risk"}`}
                                  style={{ width: `${c.avg_score_pct ?? 0}%` }}
                                />
                              </div>
                              <div className="bar-row__val">{c.avg_score_pct ?? 0}%</div>
                            </div>
                            <div className="small muted" style={{ marginTop: 2 }}>
                              {c.status_counts.needs_attention + c.status_counts.requires_review} of {c.student_count} need attention
                              {c.status_counts.requires_review > 0 ? ` (${c.status_counts.requires_review} at risk)` : ""}.
                            </div>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
                {intelPanel === "weakestSubject" && (
                  <div className="drawer__section" style={{ marginTop: 0 }}>
                    <h4>{isAll ? "School" : label} average per subject, {test?.title ?? "the selected assessment"}</h4>
                    <div style={{ display: "grid", gap: 6 }}>
                      {subjectStandings.map((s) => (
                        <div className="bar-row" key={s.subject_code} style={{ gridTemplateColumns: "140px 1fr 50px" }}>
                          <div className="bar-row__label strong">{s.subject_label}</div>
                          <div className="bar">
                            <div className={`bar__fill ${s.pct >= 78 ? "bar__fill--green" : s.pct >= 70 ? "bar__fill--gold" : "bar__fill--risk"}`} style={{ width: `${s.pct}%` }} />
                          </div>
                          <div className="bar-row__val">{s.pct}%</div>
                        </div>
                      ))}
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

/** The searchable roster for one section, its own subject/status filters driving a
 * real refetch of GET /admin/academics/{sectionId}/students. */
function SectionRoster({ sectionId, sectionLabel, defaultTestKey }: { sectionId: string; sectionLabel: string; defaultTestKey: string }) {
  const key = getApiKey() ?? "";
  const [subjects, setSubjects] = useState<{ subject_code: string; label: string }[]>([]);
  const [subjectCode, setSubjectCode] = useState<string>("");
  const [rows, setRows] = useState<ClassStudentRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const view = await api.classStudents(key, sectionId, { assessmentId: defaultTestKey || undefined, subjectCode: subjectCode || undefined });
        if (cancelled) return;
        setRows(view.students);
        setSubjects(view.filters.subjects);
      } catch {
        if (!cancelled) setRows([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionId, defaultTestKey, subjectCode]);

  return (
    <section className="section">
      <StudentRosterTable
        rows={rows}
        sectionId={sectionId}
        loading={loading}
        heading={
          <div className="section__head">
            <div>
              <h2 className="section-q">Students in {sectionLabel}</h2>
              <p className="section__lead">Search by name, or tap a student to open their test-wise report.</p>
            </div>
          </div>
        }
        leadingFilters={
          <div className="filter">
            <label htmlFor="roster-subject">Subject</label>
            <select id="roster-subject" className="select" value={subjectCode} onChange={(e) => setSubjectCode(e.target.value)}>
              <option value="">All subjects</option>
              {subjects.map((s) => (
                <option key={s.subject_code} value={s.subject_code}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        }
      />
    </section>
  );
}
