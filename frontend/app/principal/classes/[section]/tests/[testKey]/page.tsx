"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Send } from "lucide-react";
import { analysedTests, attentionFor, classAveragePct, classRosterFull, sectionComparison, subjects, testsConducted, topGapFor } from "@/lib/avai-mock-data";
import { markReportShared, useReportShared } from "@/lib/shareState";
import { usePageHeader } from "@/lib/pageHeader";
import { EvidenceState } from "@/components/EvidenceState";
import { DeltaCell, StudentRosterTable } from "@/components/StudentRosterTable";

/** Principal → Classes → section → one test. Scrolls normally like every
 * other page now, a compact KPI + subject strip up top, then the full
 * student roster underneath with its own sticky header, the same pattern
 * as the Class detail page. */
export default function ClassTestPage() {
  const { section, testKey } = useParams<{ section: string; testKey: string }>();

  const summary = sectionComparison.find((s) => s.section === section);
  const roster = useMemo(() => classRosterFull[section] ?? [], [section]);
  const test = testsConducted.find((t) => t.key === testKey);
  usePageHeader({ title: test ? `${section} · ${test.name}` : section, backHref: `/principal/classes/${section}` });
  const alreadyShared = useReportShared(section, testKey);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2800);
    return () => clearTimeout(t);
  }, [toast]);

  function shareReport() {
    markReportShared(section, testKey);
    setToast(`Report sent to ${roster.length} students in ${section} via WhatsApp (demo only) · ${test?.name ?? testKey}.`);
  }

  // The test before this one, so every figure on this sheet can show
  // movement rather than a standing number with nothing to compare to.
  const prevTestKey = useMemo(() => {
    const i = analysedTests.findIndex((t) => t.key === testKey);
    return i > 0 ? analysedTests[i - 1].key : null;
  }, [testKey]);

  const subjectAvgFor = useMemo(
    () => (key: string, subj: string) =>
      roster.length ? Math.round((roster.reduce((sum, s) => sum + (s.scores[key]?.[subj] ? s.scores[key][subj].scored / s.scores[key][subj].outOf : 0), 0) / roster.length) * 100) : 0,
    [roster]
  );

  const subjectAverages = useMemo(() => {
    if (!test || test.status !== "Analysed" || roster.length === 0) return [];
    return subjects.map((subj) => ({
      subject: subj,
      pct: subjectAvgFor(testKey, subj),
      delta: prevTestKey ? subjectAvgFor(testKey, subj) - subjectAvgFor(prevTestKey, subj) : null,
    }));
  }, [roster, test, testKey, prevTestKey, subjectAvgFor]);

  const overallAvg = test?.status === "Analysed" ? Math.round(classAveragePct(section, testKey)) : null;
  const overallDelta = prevTestKey ? Math.round(classAveragePct(section, testKey) - classAveragePct(section, prevTestKey)) : null;
  const needAttentionCount = roster.filter((s) => attentionFor(s, testKey) !== "On Track").length;
  const criticalCount = roster.filter((s) => attentionFor(s, testKey) === "Intervention").length;
  const weakest = [...subjectAverages].sort((a, b) => a.pct - b.pct)[0];

  if (!summary || !test) {
    return <EvidenceState kind="early">No such test for {section} in this demo dataset.</EvidenceState>;
  }

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16, flexWrap: "wrap" }}>
        <p className="page-sub" style={{ marginTop: 0 }}>
          Conducted {test.date} {test.status === "Analysed" ? <span className="tag tag--green" style={{ marginLeft: 8 }}>Analysed</span> : <span className="tag" style={{ marginLeft: 8 }}>Scheduled</span>}
        </p>
        {test.status === "Analysed" && (
          <button className="btn btn--sm btn--primary" disabled={alreadyShared} onClick={shareReport}>
            {alreadyShared ? <Check size={13} /> : <Send size={13} />} {alreadyShared ? "Shared" : "Share report"}
          </button>
        )}
      </div>

      {test.status !== "Analysed" ? (
        <div style={{ marginTop: 20 }}>
          <EvidenceState kind="early">{test.name} hasn&apos;t been conducted yet for {section}, no marks to show.</EvidenceState>
        </div>
      ) : (
        <>
          <div className="grid grid--4" style={{ marginTop: 20 }}>
            <div className="stat">
              <div className="stat__label">Class average</div>
              <div className="stat__value" style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                {overallAvg}%
                <DeltaCell delta={overallDelta} />
              </div>
            </div>
            <div className="stat">
              <div className="stat__label">Students</div>
              <div className="stat__value">{roster.length}</div>
            </div>
            <div className="stat">
              <div className="stat__label">Need attention</div>
              <div className="stat__value">{needAttentionCount}</div>
            </div>
            <div className="stat">
              <div className="stat__label">Critical</div>
              <div className="stat__value">{criticalCount}</div>
            </div>
          </div>

          <section className="section">
            <div className="section__head">
              <h2 className="section-q">Subject-wise average</h2>
            </div>
            <div className="grid grid--5">
              {subjectAverages.map((s) => (
                <div className="stat" key={s.subject}>
                  <div className="stat__label">{s.subject}</div>
                  <div className="stat__value stat__value--sm" style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                    {s.pct}%
                    <DeltaCell delta={s.delta} />
                  </div>
                  <div className="bar" style={{ marginTop: 6 }}>
                    <div className={`bar__fill ${s.pct >= 78 ? "bar__fill--green" : s.pct >= 65 ? "bar__fill--gold" : "bar__fill--risk"}`} style={{ width: `${s.pct}%` }} />
                  </div>
                </div>
              ))}
            </div>
            {weakest && (
              <p className="small muted" style={{ marginTop: 12 }}>
                Weakest subject in this paper: <strong>{weakest.subject}</strong> at {weakest.pct}%. Biggest gap across the class:{" "}
                <strong>{topGapFor(section, testKey)}</strong>.
              </p>
            )}
          </section>

          <section className="section">
            <StudentRosterTable
              roster={roster}
              testKey={testKey}
              section={section}
              testStatus="Analysed"
              testName={test.name}
              heading={
                <div className="section__head">
                  <h2 className="section-q">Students in {section}</h2>
                </div>
              }
            />
          </section>
        </>
      )}

      <AnimatePresence>
        {toast && (
          <motion.div className="toast" role="status" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}>
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
