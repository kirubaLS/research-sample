"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, CalendarCheck, CalendarClock, ChevronDown } from "lucide-react";
import { analysedTests, assessmentContext, classRosterFull, latestTest, markingProgress, sections, subjects, subjectsByAverage, testsConducted } from "@/lib/avai-mock-data";
import { usePageHeader } from "@/lib/pageHeader";
import { DeltaCell } from "@/components/StudentRosterTable";

function sectionSubjectPct(section: string, testKey: string, subject: string): number | null {
  const roster = classRosterFull[section] ?? [];
  if (!roster.length) return null;
  const scored = roster.map((s) => s.scores[testKey]?.[subject]).filter((x): x is { scored: number; outOf: number } => !!x);
  if (!scored.length) return null;
  return Math.round((scored.reduce((sum, x) => sum + x.scored / x.outOf, 0) / scored.length) * 100);
}

function sectionOverallPct(section: string, testKey: string): number {
  const vals = subjects.map((subj) => sectionSubjectPct(section, testKey, subj)).filter((v): v is number => v !== null);
  return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : 0;
}

function daysUntil(dateStr: string): number {
  const today = new Date(assessmentContext.today);
  const target = new Date(dateStr);
  return Math.round((target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

/** Principal → Exams. A read-only calendar of every test: conducted, with
 * a full section × subject breakdown (every number labeled, no bare
 * percentages), and upcoming. Papers and marks are entered by subject
 * teachers now, this is where the principal sees the assessment calendar
 * and opens a test's own class-by-class report. */
export default function ExamsPage() {
  usePageHeader({ title: "Exams" });
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set([latestTest.key]));

  const conducted = [...testsConducted.filter((t) => t.status === "Analysed")].reverse(); // most recent first
  const upcoming = testsConducted.filter((t) => t.status === "Scheduled");
  const nextExam = upcoming[0];

  const prevTestKey = analysedTests.length > 1 ? analysedTests[analysedTests.length - 2].key : null;
  const latestSchoolAvg = Math.round(sections.reduce((sum, s) => sum + sectionOverallPct(s, latestTest.key), 0) / sections.length);
  const prevSchoolAvg = prevTestKey ? Math.round(sections.reduce((sum, s) => sum + sectionOverallPct(s, prevTestKey), 0) / sections.length) : null;
  const weakestSubject = subjectsByAverage(latestTest.key)[0];

  function toggle(key: string) {
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <>
      <p className="page-sub" style={{ marginTop: 0 }}>
        Every test on the calendar. Open one to see how each section did, subject by subject.
      </p>

      <div className="grid grid--3" style={{ marginTop: 20 }}>
        <div className="stat">
          <div className="stat__label">{latestTest.name}, school average</div>
          <div className="stat__value" style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            {latestSchoolAvg}%
            {prevSchoolAvg !== null && <DeltaCell delta={latestSchoolAvg - prevSchoolAvg} />}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">Weakest subject this term</div>
          <div className="stat__value stat__value--sm">
            {weakestSubject?.subject}
            <span className="small muted" style={{ fontWeight: 400 }}> · {weakestSubject?.avgPct}% school average</span>
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">Next exam</div>
          <div className="stat__value stat__value--sm">
            {nextExam ? nextExam.name : "None scheduled"}
            {nextExam && (
              <span className="small muted" style={{ fontWeight: 400 }}>
                {" "}
                · {nextExam.date} ({daysUntil(nextExam.date)} day{daysUntil(nextExam.date) === 1 ? "" : "s"} away)
              </span>
            )}
          </div>
        </div>
      </div>

      <section className="section">
        <div className="section__head">
          <div>
            <h2 className="section-q">
              <CalendarCheck size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} /> Conducted
            </h2>
            <p className="section__lead">
              Percentages below are each section&apos;s average score in that subject for that test, e.g. &quot;X-A · Mathematics · 82%&quot; means
              X-A&apos;s students scored 82% of the marks on average in the Mathematics paper.
            </p>
          </div>
        </div>
        <div style={{ display: "grid", gap: 12 }}>
          {conducted.map((t) => {
            const isOpen = expanded.has(t.key);
            const avg = Math.round(sections.reduce((sum, s) => sum + sectionOverallPct(s, t.key), 0) / sections.length);
            return (
              <div className="card" key={t.key}>
                <button
                  onClick={() => toggle(t.key)}
                  style={{ width: "100%", textAlign: "left", background: "none", border: "none", padding: 0, cursor: "pointer" }}
                  aria-expanded={isOpen}
                >
                  <div className="card__head">
                    <div>
                      <div className="strong" style={{ fontSize: 15 }}>
                        {t.name}
                      </div>
                      <div className="small muted" style={{ marginTop: 2 }}>
                        {t.date}
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                      <div style={{ textAlign: "right" }}>
                        <div className="stat__label">All-subjects school average</div>
                        <div className="strong">{avg}%</div>
                      </div>
                      <ChevronDown size={16} className="muted" style={{ transform: isOpen ? "rotate(180deg)" : undefined, transition: "transform .15s" }} />
                    </div>
                  </div>
                </button>
                {isOpen && (
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Section</th>
                          {subjects.map((s) => (
                            <th key={s} className="num">
                              {s}
                            </th>
                          ))}
                          <th className="num">Overall</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {sections.map((s) => (
                          <tr key={s}>
                            <td className="strong">{s}</td>
                            {subjects.map((subj) => (
                              <td key={subj} className="num">
                                {sectionSubjectPct(s, t.key, subj) === null ? "-" : `${sectionSubjectPct(s, t.key, subj)}%`}
                              </td>
                            ))}
                            <td className="num strong">{sectionOverallPct(s, t.key)}%</td>
                            <td style={{ textAlign: "right" }}>
                              <Link href={`/principal/classes/${s}/tests/${t.key}`} className="btn--link" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                                Full report <ArrowRight size={12} />
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
          {conducted.length === 0 && <p className="small muted">No tests conducted yet.</p>}
        </div>
      </section>

      <section className="section">
        <div className="section__head">
          <h2 className="section-q">
            <CalendarClock size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} /> Upcoming
          </h2>
        </div>
        <div style={{ display: "grid", gap: 12 }}>
          {upcoming.map((t) => (
            <div className="card" key={t.key}>
              <div className="card__head">
                <div>
                  <div className="strong" style={{ fontSize: 15 }}>
                    {t.name}
                  </div>
                  <div className="small muted" style={{ marginTop: 2 }}>
                    {t.date} · {daysUntil(t.date)} day{daysUntil(t.date) === 1 ? "" : "s"} away
                  </div>
                </div>
                {(() => {
                  const p = markingProgress(t.key);
                  return p.done > 0 ? (
                    <span className="tag tag--gold">
                      Marking {p.done} of {p.total}
                    </span>
                  ) : (
                    <span className="tag">Scheduled</span>
                  );
                })()}
              </div>
            </div>
          ))}
          {upcoming.length === 0 && <p className="small muted">Nothing scheduled.</p>}
        </div>
      </section>
    </>
  );
}
