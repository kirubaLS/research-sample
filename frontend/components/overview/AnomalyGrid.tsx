"use client";

import Link from "next/link";
import { ArrowUpRight, Sparkles, Target, TrendingDown } from "lucide-react";
import { Stagger, StaggerItem } from "@/components/motion";
import type { AnomalyInsight } from "@/lib/avai-mock-data";

const KIND: Record<AnomalyInsight["kind"], { label: string; accent: string; icon: React.ReactNode }> = {
  "hidden-strength": { label: "Hidden strength", accent: "var(--brand-teal)", icon: <Sparkles size={13} /> },
  "all-rounder": { label: "All-rounder", accent: "var(--brand-gold)", icon: <Target size={13} /> },
  "section-subject-slump": { label: "Section slump", accent: "var(--risk)", icon: <TrendingDown size={13} /> },
};

/** The anomalies half of the intelligence layer: each card carries the
 * numbers behind its claim, so nothing here is a bare assertion. */
export function AnomalyGrid({ anomalies }: { anomalies: AnomalyInsight[] }) {
  if (anomalies.length === 0) {
    return <p className="small muted">No anomalies stand out against this assessment&apos;s data.</p>;
  }

  return (
    <Stagger className="grid grid--2" gap={0.06}>
      {anomalies.map((a) => {
        const kind = KIND[a.kind];
        return (
          <StaggerItem key={a.id}>
            <div
              className="card hoverlift"
              style={{
                height: "100%",
                display: "flex",
                flexDirection: "column",
                borderTop: `3px solid ${kind.accent}`,
              }}
            >
              <div className="card__body" style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span className="finding__subject">{a.subject ?? a.section ?? "School-wide"}</span>
                  <span className="tag" style={{ color: kind.accent }}>
                    {kind.icon} {kind.label}
                  </span>
                </div>
                <div className="strong" style={{ marginTop: 4, fontSize: 15, lineHeight: 1.35 }}>
                  {a.headline}
                </div>
                <p className="small muted" style={{ marginTop: 6 }}>
                  {a.detail}
                </p>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(104px, 1fr))", gap: 8, marginTop: 12 }}>
                  {a.numbers.map((n) => (
                    <div className="metric" key={n.label}>
                      <div className="metric__label">{n.label}</div>
                      <div className="metric__value" style={{ fontSize: 16 }}>
                        {n.value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              {a.studentId && (
                <div className="card__foot" style={{ justifyContent: "flex-end" }}>
                  <Link href={`/principal/classes/${a.section}/${a.studentId}`} className="btn btn--sm">
                    View student <ArrowUpRight size={13} />
                  </Link>
                </div>
              )}
            </div>
          </StaggerItem>
        );
      })}
    </Stagger>
  );
}
