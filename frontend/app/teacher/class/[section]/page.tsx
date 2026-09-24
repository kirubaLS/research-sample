"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { useAuth } from "@/lib/auth";
import {
  analysedTests,
  attentionFromPct,
  classRosterFull,
  emptyStates,
  findings,
  latestTest,
  mainBlockerFor,
  pctFor,
  subjectSnapshotFor,
  subjects,
  type FullRosterStudent,
} from "@/lib/avai-mock-data";
import { usePageHeader } from "@/lib/pageHeader";
import { AttentionPill } from "@/components/Status";
import { EvidenceState } from "@/components/EvidenceState";
import { FindingCard } from "@/components/FindingCard";
import { DeltaCell } from "@/components/StudentRosterTable";

/** §6.2 Class view, a class teacher's own section, scoped to only the
 * subject(s) she actually teaches there. A class teacher oversees the
 * section, but the marks and findings shown here are still one subject
 * teacher's numbers, not a school-wide view across every subject. */
export default function ClassView() {
  const { section } = useParams<{ section: string }>();
  usePageHeader({ title: `Class ${section}`, backHref: "/teacher/home" });
  const { user } = useAuth();
  const fullRoster = classRosterFull[section] ?? [];
  const allowed = user?.role === "teacher" && user.assignments.some((a) => a.type === "class" && a.section === section);

  const mySubjects =
    user?.role === "teacher"
      ? subjects.filter((s) => user.assignments.some((a) => a.type === "subject" && a.subject === s && a.sections.includes(section)))
      : [];

  const scopedPct = (student: FullRosterStudent, testKey: string) =>
    mySubjects.length ? mySubjects.reduce((sum, s) => sum + pctFor(student, testKey, s), 0) / mySubjects.length : 0;

  const overallAttainment = fullRoster.length ? Math.round(fullRoster.reduce((sum, s) => sum + scopedPct(s, latestTest.key), 0) / fullRoster.length) : 0;
  const attention = attentionFromPct(overallAttainment);
  const snapshots = mySubjects.map((s) => subjectSnapshotFor(s, section, latestTest.key));
  const topFinding = snapshots.find((s) => s.topGap !== "No gap localized")?.topGap ?? snapshots[0]?.topGap ?? "No subject assigned";

  // Movement since the previous analysed test, at class and student level,
  // both scoped to mySubjects only.
  const trend = useMemo(() => {
    if (analysedTests.length < 2 || mySubjects.length === 0) return null;
    const prev = analysedTests[analysedTests.length - 2];
    let improved = 0;
    let declined = 0;
    for (const s of fullRoster) {
      const d = scopedPct(s, latestTest.key) - scopedPct(s, prev.key);
      if (d >= 2) improved += 1;
      else if (d <= -2) declined += 1;
    }
    const prevPct = fullRoster.length ? Math.round(fullRoster.reduce((sum, s) => sum + scopedPct(s, prev.key), 0) / fullRoster.length) : 0;
    return {
      prevName: prev.name,
      prevPct,
      nowPct: overallAttainment,
      delta: overallAttainment - prevPct,
      improved,
      declined,
      steady: fullRoster.length - improved - declined,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section, mySubjects.join("|")]);

  if (!allowed) return <EvidenceState kind="cause">You are not assigned as class teacher for {section}.</EvidenceState>;
  if (mySubjects.length === 0) {
    return <EvidenceState kind="early">You are the class teacher for {section}, but aren&apos;t assigned to teach any subject there, nothing subject-specific to show.</EvidenceState>;
  }

  const sectionFindings = findings.filter(
    (f) => (mySubjects as string[]).includes(f.subject) && (f.mostAffectedSections?.some((s) => s.section === section) || !f.mostAffectedSections)
  );

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16 }}>
        <p className="page-sub" style={{ marginTop: 0 }}>
          Class view · your subject{mySubjects.length > 1 ? "s" : ""}: {mySubjects.join(", ")}
        </p>
        <AttentionPill level={attention} label={`${attention} risk`} />
      </div>

      <div className="grid grid--3" style={{ marginTop: 18 }}>
        <div className="stat">
          <div className="stat__label">Students</div>
          <div className="stat__value">{fullRoster.length}</div>
        </div>
        <div className="stat">
          <div className="stat__label">{mySubjects.length > 1 ? "Your subjects, attainment" : `${mySubjects[0]} attainment`}</div>
          <div className="stat__value" style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            {overallAttainment}%
            <DeltaCell delta={trend?.delta ?? null} />
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">Top gap in your subject{mySubjects.length > 1 ? "s" : ""}</div>
          <div className="stat__value stat__value--sm">{topFinding}</div>
        </div>
      </div>

      <section className="section">
        <div className="section__head">
          <h2 className="section-q">Students in {section}</h2>
          <span className="small muted">
            All {fullRoster.length} students · {latestTest.name} · {mySubjects.join(", ")} only
          </span>
        </div>
        <div className="card">
          <div className="table-wrap table-wrap--scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Roll</th>
                  <th>Student</th>
                  {mySubjects.map((s) => (
                    <th key={s} className="num">
                      {s}
                    </th>
                  ))}
                  <th>Main blocker</th>
                  <th>Attention</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {fullRoster.map((s) => (
                  <tr key={s.id}>
                    <td className="muted">{s.rollNo}</td>
                    <td className="strong">{s.name}</td>
                    {mySubjects.map((sub) => (
                      <td key={sub} className="num">
                        {Math.round(pctFor(s, latestTest.key, sub))}
                      </td>
                    ))}
                    <td>{mainBlockerFor(s, latestTest.key)}</td>
                    <td>
                      <AttentionPill level={attentionFromPct(scopedPct(s, latestTest.key))} />
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <Link href={`/teacher/student/${s.id}`} className="btn btn--sm">
                        Report <ArrowRight size={12} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section__head">
          <div>
            <h2 className="section-q">Since {trend?.prevName ?? "the previous assessment"}</h2>
            <p className="section__lead">Movement in your subject{mySubjects.length > 1 ? "s" : ""} between the two analysed assessments.</p>
          </div>
        </div>
        {trend ? (
          <div className="grid grid--4">
            <div className="stat">
              <div className="stat__label">{trend.prevName}</div>
              <div className="stat__value stat__value--sm">{trend.prevPct}%</div>
            </div>
            <div className="stat">
              <div className="stat__label">{latestTest.name}</div>
              <div className="stat__value stat__value--sm" style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                {trend.nowPct}%
                <DeltaCell delta={trend.delta} />
              </div>
            </div>
            <div className="stat">
              <div className="stat__label">Improved</div>
              <div className="stat__value stat__value--sm">{trend.improved}</div>
            </div>
            <div className="stat">
              <div className="stat__label">Declined</div>
              <div className="stat__value stat__value--sm">{trend.declined}</div>
            </div>
          </div>
        ) : (
          <EvidenceState kind="trend">{emptyStates.trendNotAvailable}</EvidenceState>
        )}
        {trend && (
          <p className="small muted" style={{ marginTop: 10 }}>
            {emptyStates.trendTwoPoints}
          </p>
        )}
      </section>

      <section className="section">
        <div className="section__head">
          <div>
            <h2 className="section-q">Findings in your subject{mySubjects.length > 1 ? "s" : ""} that touch {section}</h2>
            <p className="section__lead">The same finding unit the principal sees, scoped to {mySubjects.join(" and ")}.</p>
          </div>
        </div>
        {sectionFindings.length ? (
          <div className="grid grid--2">
            {sectionFindings.map((f) => (
              <FindingCard key={f.id} finding={f} compact />
            ))}
          </div>
        ) : (
          <EvidenceState kind="early">No findings in {mySubjects.join(" or ")} rise above the evidence threshold for {section}.</EvidenceState>
        )}
      </section>
    </>
  );
}
