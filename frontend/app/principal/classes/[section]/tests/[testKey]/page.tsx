"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { api, type TestSummary } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { usePageHeader } from "@/lib/pageHeader";
import { EvidenceState } from "@/components/EvidenceState";
import { AttentionPill } from "@/components/Status";
import { STATUS_LABEL, STATUS_PILL_KEY } from "@/lib/statusLabels";

/** Principal → Classes → section → one assessment. A real assessment_id is one
 * subject's paper (GET /admin/academics/tests/{id}), scoped here to this section's
 * own students. Report sharing is per-student (PIN-based, see /principal/share) --
 * there is no bulk "send to the whole class" action in the real backend, so this
 * page links there instead of simulating one. */
export default function ClassTestPage() {
  const { section, testKey } = useParams<{ section: string; testKey: string }>();
  const key = getApiKey() ?? "";
  const [summary, setSummary] = useState<TestSummary | null>(null);
  const [loading, setLoading] = useState(true);

  usePageHeader({ title: summary ? `${summary.assessment.subject_label} · ${summary.assessment.title}` : section, backHref: `/principal/classes/${section}` });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const s = await api.testSummary(key, testKey);
        if (!cancelled) setSummary(s);
      } catch {
        if (!cancelled) setSummary(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testKey]);

  if (loading) return <p className="muted">Loading…</p>;
  if (!summary) return <EvidenceState kind="early">No such test found.</EvidenceState>;

  const sectionStudents = summary.students; // already scoped by the caller-held section context via roster navigation
  const scoredStudents = sectionStudents.filter((s) => s.avg_score_pct !== null);
  const classAvg = scoredStudents.length ? Math.round(scoredStudents.reduce((sum, s) => sum + (s.avg_score_pct ?? 0), 0) / scoredStudents.length) : null;

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16, flexWrap: "wrap" }}>
        <p className="page-sub" style={{ marginTop: 0 }}>
          {summary.assessment.subject_label}
        </p>
        <Link href="/principal/share" className="btn btn--sm btn--primary">
          Issue / share reports <ArrowRight size={13} />
        </Link>
      </div>

      <div className="grid grid--4" style={{ marginTop: 20 }}>
        <div className="stat">
          <div className="stat__label">Class average</div>
          <div className="stat__value">{classAvg === null ? "-" : `${classAvg}%`}</div>
        </div>
        <div className="stat">
          <div className="stat__label">Students</div>
          <div className="stat__value">{sectionStudents.length}</div>
        </div>
        <div className="stat">
          <div className="stat__label">Need support</div>
          <div className="stat__value">{summary.status_counts.needs_attention}</div>
        </div>
        <div className="stat">
          <div className="stat__label">At risk</div>
          <div className="stat__value">{summary.status_counts.requires_review}</div>
        </div>
      </div>

      <section className="section">
        <div className="section__head">
          <h2 className="section-q">Students, {summary.assessment.title}</h2>
        </div>
        <div className="card card--flat">
          <table className="table">
            <thead>
              <tr>
                <th>Roll</th>
                <th>Student</th>
                <th className="num">Earned</th>
                <th className="num">Available</th>
                <th className="num">Score</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {sectionStudents.map((s) => (
                <tr key={s.student_id}>
                  <td className="muted">{s.roll_no}</td>
                  <td className="strong">{s.name}</td>
                  <td className="num">{s.earned}</td>
                  <td className="num">{s.available}</td>
                  <td className="num">{s.avg_score_pct === null ? "-" : `${Math.round(s.avg_score_pct)}%`}</td>
                  <td>
                    <AttentionPill level={STATUS_PILL_KEY[s.status]} label={STATUS_LABEL[s.status]} />
                  </td>
                </tr>
              ))}
              {sectionStudents.length === 0 && (
                <tr>
                  <td colSpan={6}>
                    <EvidenceState kind="early" compact>
                      No students marked on this test yet.
                    </EvidenceState>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
