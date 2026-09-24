"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Download } from "lucide-react";
import {
  analysedTests,
  attentionFor,
  buildStudentReport,
  classAveragePct,
  classRosterFull,
  latestTest,
  overallPctFor,
  studentIntelligenceFor,
  subjects,
} from "@/lib/avai-mock-data";
import { downloadStudentReport } from "@/lib/downloadReport";
import { usePageHeader } from "@/lib/pageHeader";
import { AttentionPill, ConfidenceMeter, UrgencyChip } from "@/components/Status";
import { EvidenceState } from "@/components/EvidenceState";
import { BoardXReportView } from "@/components/BoardXReportView";
import { DeltaCell } from "@/components/StudentRosterTable";

/** Principal → Classes → section → student. Pick an analysed assessment to
 * see where this student's marks went across every subject, then pick a
 * subject to read the same one-page BoardX report the student sees. */
export default function PrincipalStudentPage() {
  const { section, studentId } = useParams<{ section: string; studentId: string }>();
  const student = (classRosterFull[section] ?? []).find((s) => s.id === studentId);
  usePageHeader({ title: student?.name ?? studentId, backHref: `/principal/classes/${section}` });

  const [testKey, setTestKey] = useState(latestTest.key);
  const [subject, setSubject] = useState<string>(subjects[0]);

  const prevTestKey = useMemo(() => {
    const i = analysedTests.findIndex((t) => t.key === testKey);
    return i > 0 ? analysedTests[i - 1].key : null;
  }, [testKey]);

  const intel = student ? studentIntelligenceFor(student, testKey) : null;
  const report = student ? buildStudentReport(student, testKey, subject) : null;

  if (!student) {
    return <EvidenceState kind="early">No student with id {studentId} in {section}.</EvidenceState>;
  }

  const pct = Math.round(overallPctFor(student, testKey));
  const delta = prevTestKey ? pct - Math.round(overallPctFor(student, prevTestKey)) : null;
  const classPct = Math.round(classAveragePct(section, testKey));
  const totalMarks = subjects.reduce((sum, sub) => sum + (student.scores[testKey]?.[sub]?.outOf ?? 0), 0);

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16 }}>
        <p className="page-sub" style={{ marginTop: 0 }}>
          {section} · Roll {student.rollNo}
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button className="btn btn--sm" disabled={!report} onClick={() => downloadStudentReport(student.id, testKey, subject)}>
            <Download size={13} /> Download report
          </button>
          <AttentionPill level={attentionFor(student, testKey)} />
        </div>
      </div>

      <div className="filterbar" style={{ marginTop: 20 }}>
        <div className="filter">
          <label htmlFor="test-picker">Assessment</label>
          <select id="test-picker" className="select" value={testKey} onChange={(e) => setTestKey(e.target.value)}>
            {analysedTests.map((t) => (
              <option key={t.key} value={t.key}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
        <div className="filter">
          <label htmlFor="subject-picker">Subject report</label>
          <select id="subject-picker" className="select" value={subject} onChange={(e) => setSubject(e.target.value)}>
            {subjects.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid--4" style={{ marginTop: 16 }}>
        <div className="stat">
          <div className="stat__label">Overall</div>
          <div className="stat__value stat__value--sm" style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
            {pct}%
            <DeltaCell delta={delta} />
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">Against the class</div>
          <div className="stat__value stat__value--sm" style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
            <span className="delta" data-dir={pct >= classPct ? "up" : "down"} style={{ fontSize: "inherit" }}>
              {pct >= classPct ? "+" : "−"}
              {Math.abs(pct - classPct)}pt
            </span>
            <span className="small muted" style={{ fontWeight: 400 }}>class {classPct}%</span>
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">Marks lost</div>
          <div className="stat__value stat__value--sm">
            {intel?.marksLost ?? "-"}
            <span className="small muted" style={{ fontWeight: 400 }}> of {totalMarks}</span>
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">In the top 2 gaps</div>
          <div className="stat__value stat__value--sm">
            {intel?.recoverableOpportunity ?? "-"}
            <span className="small muted" style={{ fontWeight: 400 }}> marks</span>
          </div>
        </div>
      </div>

      {intel && intel.subjects.length > 0 ? (
        <section className="section">
          <h2 className="section-q">Where marks were lost</h2>
          <div className="card card--flat" style={{ marginTop: 12 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Subject</th>
                  <th>Chapter</th>
                  <th className="num">Lost</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {intel.subjects.map((s) => (
                  <tr key={s.subject + s.topic}>
                    <td className="strong">{s.subject}</td>
                    <td>
                      {s.topic}
                      <div className="small muted">{s.subskill}</div>
                    </td>
                    <td className="num">{s.lost}</td>
                    <td>
                      <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-start" }}>
                        <UrgencyChip level={s.boardUrgency} withLabel={false} />
                        <ConfidenceMeter level={s.confidence} short />
                      </div>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn btn--sm" onClick={() => setSubject(s.subject)} disabled={subject === s.subject}>
                        {subject === s.subject ? "Shown below" : "Open report"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p style={{ marginTop: 12 }}>{intel.boardXSummary}</p>
        </section>
      ) : (
        <div style={{ marginTop: 20 }}>
          <EvidenceState kind="early">{student.name} scored every mark tested in this assessment, there is no loss to localize.</EvidenceState>
        </div>
      )}

      <section className="section">
        <h2 className="section-q">{subject}, one-page report</h2>
        <div style={{ marginTop: 12 }}>
          {report ? (
            <BoardXReportView report={report} studentName={student.name} section={section} />
          ) : (
            <EvidenceState kind="early">No {subject} marks recorded for this assessment.</EvidenceState>
          )}
        </div>
      </section>
    </>
  );
}
