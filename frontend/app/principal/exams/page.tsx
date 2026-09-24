"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, CalendarCheck } from "lucide-react";
import { api, type AcademicTestRow } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { usePageHeader } from "@/lib/pageHeader";
import { DeltaCell } from "@/components/StudentRosterTable";

/** Principal → Exams. Every real paper with at least one resolved mark (GET
 * /admin/academics/tests), most recent first. The reference's "Upcoming" calendar
 * and per-section subject grid have no backend equivalent -- this deployment has no
 * scheduled-exam data model, and a test here already belongs to one subject, not a
 * whole exam day across every subject -- so this view lists real papers instead of
 * simulating a calendar. */
export default function ExamsPage() {
  usePageHeader({ title: "Exams" });
  const key = getApiKey() ?? "";
  const [tests, setTests] = useState<AcademicTestRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.academicsTests(key);
        if (!cancelled) setTests(res.tests);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ordered = [...tests].reverse();
  const latest = tests[tests.length - 1];
  const weakest = [...tests].filter((t) => t.avg_score_pct !== null).sort((a, b) => (a.avg_score_pct ?? 0) - (b.avg_score_pct ?? 0))[0];

  return (
    <>
      <p className="page-sub" style={{ marginTop: 0 }}>
        Every paper with resolved marks. Open one to see how students did.
      </p>

      {!loading && (
        <div className="grid grid--3" style={{ marginTop: 20 }}>
          <div className="stat">
            <div className="stat__label">{latest ? `${latest.title}, average` : "Latest test"}</div>
            <div className="stat__value" style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              {latest?.avg_score_pct === null || latest?.avg_score_pct === undefined ? "-" : `${latest.avg_score_pct}%`}
              {latest?.delta_pct !== null && latest?.delta_pct !== undefined && <DeltaCell delta={latest.delta_pct} />}
            </div>
          </div>
          <div className="stat">
            <div className="stat__label">Weakest paper</div>
            <div className="stat__value stat__value--sm">
              {weakest ? weakest.title : "-"}
              {weakest && <span className="small muted" style={{ fontWeight: 400 }}> · {weakest.avg_score_pct}% average</span>}
            </div>
          </div>
          <div className="stat">
            <div className="stat__label">Papers with marks</div>
            <div className="stat__value stat__value--sm">{tests.length}</div>
          </div>
        </div>
      )}

      <section className="section">
        <div className="section__head">
          <div>
            <h2 className="section-q">
              <CalendarCheck size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} /> Papers
            </h2>
          </div>
        </div>
        <div style={{ display: "grid", gap: 12 }}>
          {loading && <p className="small muted">Loading…</p>}
          {!loading &&
            ordered.map((t) => (
              <div className="card" key={t.assessment_id}>
                <div className="card__head">
                  <div>
                    <div className="strong" style={{ fontSize: 15 }}>
                      {t.title}
                    </div>
                    <div className="small muted" style={{ marginTop: 2 }}>
                      {t.label} · {t.students_marked} students marked
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                    <div style={{ textAlign: "right" }}>
                      <div className="stat__label">Average</div>
                      <div className="strong" style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                        {t.avg_score_pct === null ? "-" : `${t.avg_score_pct}%`}
                        {t.delta_pct !== null && <DeltaCell delta={t.delta_pct} />}
                      </div>
                    </div>
                    <Link href={`/principal/classes/all/tests/${t.assessment_id}`} className="btn--link" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                      Full report <ArrowRight size={12} />
                    </Link>
                  </div>
                </div>
              </div>
            ))}
          {!loading && ordered.length === 0 && <p className="small muted">No tests with resolved marks yet.</p>}
        </div>
      </section>
    </>
  );
}
