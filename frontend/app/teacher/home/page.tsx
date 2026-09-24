"use client";

import Link from "next/link";
import { ArrowRight, BookOpen } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { assessmentContext, latestTest, subjectSnapshotFor } from "@/lib/avai-mock-data";
import { usePageHeader } from "@/lib/pageHeader";
import { EvidenceState } from "@/components/EvidenceState";

/** §6.1 Teacher home, the signed-in teacher's own subjects. */
export default function TeacherHome() {
  usePageHeader({ title: "Teacher Home" });
  const { user } = useAuth();
  if (!user || user.role !== "teacher") return null;

  const subjectAssignments = user.assignments.filter((a) => a.type === "subject");

  return (
    <>
      <p className="page-sub" style={{ marginTop: 0 }}>
        Welcome, {user.name} · {assessmentContext.assessmentName} has been analysed. Here is what it says about your subjects.
      </p>

      <section style={{ marginTop: 24 }}>
        <div className="section__head">
          <h2 className="section-q">
            <BookOpen size={18} style={{ verticalAlign: "-3px", marginRight: 8 }} /> My Subjects
          </h2>
        </div>
        {subjectAssignments.length === 0 ? (
          <EvidenceState kind="early">No subject assignments yet.</EvidenceState>
        ) : (
          <div className="grid grid--2" style={{ gap: 12 }}>
            {subjectAssignments.map((a) => {
              if (a.type !== "subject") return null;
              return (
                <div className="card" key={a.subject}>
                  <div className="card__body">
                    <h3 style={{ fontSize: 18 }}>{a.subject}</h3>
                    {/* One row per section: a subject average only means
                        something against the class it was scored in. */}
                    <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
                      {a.sections.map((sec) => {
                        const snap = subjectSnapshotFor(a.subject, sec, latestTest.key);
                        return (
                          <Link key={sec} href={`/teacher/subject/${encodeURIComponent(a.subject)}/${sec}`} className="subject-row">
                            <div>
                              <div className="strong">{sec}</div>
                              <div className="small muted">
                                avg {snap.avgAttainment} / {snap.marksTested} · {snap.atExpectedLevelPct}% at expected level · {snap.topGap}
                              </div>
                            </div>
                            <ArrowRight size={14} className="muted" />
                          </Link>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </>
  );
}
