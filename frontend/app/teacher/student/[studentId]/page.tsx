"use client";

import { useParams } from "next/navigation";
import { useEffect, useState, type CSSProperties } from "react";
import { Check, Send, Share2 } from "lucide-react";
import { api, IssuedReportRow, StudentAcademicsOverview, StudentSubjectBreakdown } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { usePageHeader } from "@/lib/pageHeader";
import { useAuth } from "@/lib/auth";
import { AttentionPill } from "@/components/Status";
import { EvidenceState } from "@/components/EvidenceState";
import { LoadingScreen } from "@/components/Shell";
import { STATUS_LABEL, STATUS_PILL_KEY } from "@/lib/statusLabels";

/**
 * §6.4 Teacher-facing student report -- real cross-subject overview
 * (GET /admin/teacher/academics/students/{id}) plus, per subject, the
 * chapter-wise breakdown a teacher would issue/share. Issue = issueReport(),
 * Share = shareReport()/unshareReport(); both are real, persisted calls
 * against the exact same routes the principal side already uses.
 */
export default function StudentReportPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const [overview, setOverview] = useState<StudentAcademicsOverview | null>(null);
  const [breakdowns, setBreakdowns] = useState<Record<string, StudentSubjectBreakdown>>({});
  const [issued, setIssued] = useState<IssuedReportRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // Real, not a step a teacher should have to type through every time -- attributed to
  // whoever is actually signed in, the same fix already made on the principal Share
  // reports page.
  const { user } = useAuth();
  const by = user && "name" in user && user.name ? user.name : "";

  usePageHeader({ title: overview?.student.name ?? studentId, backHref: "/teacher/home" });

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherStudentAcademics(key, studentId)
      .then((o) => {
        setOverview(o);
        return Promise.all(o.subjects.map((s) => api.teacherStudentSubjectBreakdown(key, studentId, s.subject_code)));
      })
      .then((rows) => {
        const map: Record<string, StudentSubjectBreakdown> = {};
        rows?.forEach((r) => (map[r.subject.subject_code] = r));
        setBreakdowns(map);
      })
      .catch(() => setError("Could not load this student's marks."));
    api
      .studentIssuedReports(key, studentId)
      .then((r) => setIssued(r.reports))
      .catch(() => {
        /* the report list is secondary -- overview above still works without it */
      });
  }, [studentId]);

  async function issue(assessmentId: string) {
    const key = getApiKey();
    if (!key) return;
    setBusy(assessmentId);
    try {
      await api.issueReport(key, studentId, assessmentId, by || "teacher");
      const r = await api.studentIssuedReports(key, studentId);
      setIssued(r.reports);
    } catch {
      setError("Could not issue this report.");
    } finally {
      setBusy(null);
    }
  }

  async function toggleShare(row: IssuedReportRow) {
    const key = getApiKey();
    if (!key) return;
    setBusy(row.report_id);
    try {
      if (row.shared) await api.unshareReport(key, row.report_id);
      else await api.shareReport(key, row.report_id, by || "teacher");
      const r = await api.studentIssuedReports(key, studentId);
      setIssued(r.reports);
    } catch {
      setError("Could not update sharing for this report.");
    } finally {
      setBusy(null);
    }
  }

  if (error) return <EvidenceState kind="early">{error}</EvidenceState>;
  if (!overview) return <LoadingScreen label="Loading this student…" />;

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16 }}>
        <p className="page-sub" style={{ marginTop: 0 }}>
          {overview.student.section_label ?? overview.student.section_id} · Roll no. {overview.student.roll_no}
        </p>
        <AttentionPill level={STATUS_PILL_KEY[overview.overall.status]} label={STATUS_LABEL[overview.overall.status]} />
      </div>

      <div style={{ display: "grid", gap: 16, marginTop: 22 }}>
        {overview.subjects.map((s) => {
          const breakdown = breakdowns[s.subject_code];
          const reportsForSubject = issued.filter((r) => breakdown?.tests.some((t) => t.assessment_id === r.assessment_id));
          const latestTest = breakdown?.tests[breakdown.tests.length - 1];
          const existingReport = latestTest ? reportsForSubject.find((r) => r.assessment_id === latestTest.assessment_id) : undefined;
          return (
            <div className="card card--hover" style={{ "--accent": "var(--brand-blue)" } as CSSProperties} key={s.subject_code}>
              <div className="card__head">
                <div>
                  <div className="eyebrow">{latestTest?.title ?? "No test yet"}</div>
                  <h3 style={{ fontSize: 18, marginTop: 4 }}>{s.label}</h3>
                </div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>{s.avg_score_pct != null ? `${Math.round(s.avg_score_pct)}%` : "—"}</div>
              </div>
              <div className="card__body">
                <div className="grid grid--2">
                  <div>
                    <div className="eyebrow">Strengths</div>
                    <ul className="list-plain" style={{ marginTop: 6 }}>
                      {s.strengths.length ? s.strengths.map((x) => <li key={x}>{x}</li>) : <li className="muted">Not enough evidence yet.</li>}
                    </ul>
                  </div>
                  <div>
                    <div className="eyebrow">Focus areas</div>
                    <ul className="list-plain" style={{ marginTop: 6 }}>
                      {s.improve.length ? s.improve.map((x) => <li key={x}>{x}</li>) : <li className="muted">Not enough evidence yet.</li>}
                    </ul>
                  </div>
                </div>
              </div>
              <div className="card__foot" style={{ justifyContent: "space-between" }}>
                <div style={{ display: "flex", gap: 8 }}>
                  {existingReport ? <span className="tag tag--green"><Check size={12} /> Issued</span> : <span className="tag">Draft</span>}
                  {existingReport?.shared ? <span className="tag tag--teal"><Check size={12} /> Shared with student</span> : <span className="tag">Not shared</span>}
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    className="btn"
                    disabled={!latestTest || !!existingReport || busy === latestTest?.assessment_id}
                    onClick={() => latestTest && issue(latestTest.assessment_id)}
                  >
                    <Send size={13} /> {existingReport ? "Issued" : "Issue"}
                  </button>
                  <button
                    className="btn btn--primary"
                    disabled={!existingReport || busy === existingReport?.report_id}
                    onClick={() => existingReport && toggleShare(existingReport)}
                  >
                    <Share2 size={13} /> {existingReport?.shared ? "Unshare" : "Share with student"}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
