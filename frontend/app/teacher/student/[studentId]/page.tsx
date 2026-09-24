"use client";

import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { Check, Send, Share2 } from "lucide-react";
import { attentionFor, findStudent, latestTest, mainBlockerFor, teacherReportFor } from "@/lib/avai-mock-data";
import { usePageHeader } from "@/lib/pageHeader";
import { AttentionPill } from "@/components/Status";
import { EvidenceState } from "@/components/EvidenceState";

type ReportState = { issued: boolean; sharedWithStudent: boolean };

/**
 * §6.4 Teacher-facing student report. Issue/Share toggle state locally:
 * Issue → disables itself and enables Share; Share → marks shared.
 * Nothing is persisted (🔧 share is BACKEND REQUIRED).
 */
export default function StudentReportPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const student = findStudent(studentId);
  usePageHeader({ title: student?.name ?? studentId, backHref: "/teacher/home" });
  const base = useMemo(() => (student ? teacherReportFor(student, latestTest.key) : null), [student]);

  const [state, setState] = useState<ReportState[]>(() =>
    (student ? teacherReportFor(student, latestTest.key).subjectReports : []).map((r) => ({ issued: r.issued, sharedWithStudent: r.sharedWithStudent }))
  );

  if (!student || !base) return <EvidenceState kind="early">No student with id {studentId} in this dataset.</EvidenceState>;

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16 }}>
        <p className="page-sub" style={{ marginTop: 0 }}>
          {student.section} · Roll no. {student.rollNo} · Main blocker: {mainBlockerFor(student)}
        </p>
        <AttentionPill level={attentionFor(student)} />
      </div>

      <div style={{ display: "grid", gap: 16, marginTop: 22 }}>
        {base.subjectReports.map((r, i) => {
          const st = state[i];
          return (
            <div className="card" key={r.subject}>
              <div className="card__head">
                <div>
                  <div className="eyebrow">{r.assessment}</div>
                  <h3 style={{ fontSize: 18, marginTop: 4 }}>{r.subject}</h3>
                </div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>{r.score}</div>
              </div>
              <div className="card__body">
                <div className="grid grid--2">
                  <div>
                    <div className="eyebrow">Strengths</div>
                    <ul className="list-plain" style={{ marginTop: 6 }}>
                      {r.strengths.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div className="eyebrow">Focus areas</div>
                    <ul className="list-plain" style={{ marginTop: 6 }}>
                      {r.focusAreas.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
              <div className="card__foot" style={{ justifyContent: "space-between" }}>
                <div style={{ display: "flex", gap: 8 }}>
                  {st.issued ? <span className="tag tag--green"><Check size={12} /> Issued</span> : <span className="tag">Draft</span>}
                  {st.sharedWithStudent ? <span className="tag tag--teal"><Check size={12} /> Shared with student</span> : <span className="tag">Not shared</span>}
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    className="btn"
                    disabled={st.issued}
                    onClick={() => setState((s) => s.map((x, j) => (j === i ? { ...x, issued: true } : x)))}
                  >
                    <Send size={13} /> {st.issued ? "Issued" : "Issue"}
                  </button>
                  <button
                    className="btn btn--primary"
                    disabled={!st.issued || st.sharedWithStudent}
                    onClick={() => setState((s) => s.map((x, j) => (j === i ? { ...x, sharedWithStudent: true } : x)))}
                  >
                    <Share2 size={13} /> {st.sharedWithStudent ? "Shared" : "Share with student"}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: 16 }}>
        <EvidenceState kind="early">Issue and share are demo-only in this build: state resets on reload and nothing reaches the student account.</EvidenceState>
      </div>
    </>
  );
}
