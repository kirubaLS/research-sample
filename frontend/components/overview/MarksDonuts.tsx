"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { api, type CohortReport } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { TOTAL_BAND_COLORS } from "@/lib/bandColors";
import { EASE_OUT } from "@/components/motion";

const BAND_KEYS: (keyof CohortReport["band_counts"])[] = ["full_mastery", "band_80_89", "band_60_79", "below_60"];
const BAND_LABELS = ["90-100", "80-89", "60-79", "Below 60"];

interface Slice {
  label: string;
  count: number;
  color: string;
}

function slicesOf(report: CohortReport | null): Slice[] {
  if (!report) return [];
  return BAND_KEYS.map((k, i) => ({ label: BAND_LABELS[i], count: report.band_counts[k], color: TOTAL_BAND_COLORS[i] }));
}

/** One ring. Segments are separated by a 2px surface gap (the band ramp's orange/red
 * pair sits close together, so the gap, the legend's labels and the hover readout carry
 * identity alongside color). Hovering a segment or its legend row names it. */
function Donut({ title, caption, slices, onSelect }: { title: string; caption: string; slices: Slice[]; onSelect?: (i: number) => void }) {
  const reduce = useReducedMotion();
  const [hover, setHover] = useState<number | null>(null);
  const total = slices.reduce((s, x) => s + x.count, 0);
  const R = 62;
  const C = 2 * Math.PI * R;
  const GAP = total > 0 && slices.filter((s) => s.count > 0).length > 1 ? 3 : 0;

  let offset = 0;
  const arcs = slices.map((s, i) => {
    const len = total ? (s.count / total) * C : 0;
    const arc = { i, s, start: offset, len: Math.max(0, len - GAP) };
    offset += len;
    return arc;
  });
  const active = hover !== null ? slices[hover] : null;

  return (
    <div className="donut-card">
      <div className="donut-card__head">
        <div className="strong">{title}</div>
        <div className="small muted">{caption}</div>
      </div>
      <div className="donut-card__body">
        <div className="donut">
          <svg viewBox="0 0 160 160" width="160" height="160" role="img" aria-label={`${title}: ${slices.map((s) => `${s.count} scoring ${s.label}`).join(", ")}`}>
            <circle cx="80" cy="80" r={R} fill="none" stroke="var(--surface-2, #f1efe9)" strokeWidth="18" />
            {arcs.map(({ i, s, start, len }) =>
              s.count === 0 ? null : (
                <motion.circle
                  key={s.label}
                  cx="80"
                  cy="80"
                  r={R}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={hover === i ? 22 : 18}
                  strokeDasharray={`${len} ${C - len}`}
                  strokeDashoffset={-start}
                  transform="rotate(-90 80 80)"
                  initial={reduce ? false : { opacity: 0 }}
                  animate={{ opacity: hover === null || hover === i ? 1 : 0.45 }}
                  transition={{ duration: 0.35, ease: EASE_OUT, delay: reduce ? 0 : 0.05 * i }}
                  style={{ cursor: onSelect ? "pointer" : "default", transition: "stroke-width .28s cubic-bezier(.22,1,.36,1)" }}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                  onClick={() => onSelect?.(i)}
                >
                  <title>{`${s.count} students scoring ${s.label} (${total ? Math.round((s.count / total) * 100) : 0}%)`}</title>
                </motion.circle>
              ),
            )}
          </svg>
          <div className="donut__center" aria-hidden="true">
            <b>{active ? active.count : total}</b>
            <span>{active ? `scoring ${active.label}` : "students"}</span>
          </div>
        </div>
        <ul className="donut-legend">
          {slices.map((s, i) => (
            <li key={s.label}>
              <button
                type="button"
                className={`donut-legend__row ${hover === i ? "is-on" : ""}`}
                style={{ "--accent": s.color } as React.CSSProperties}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                onClick={() => onSelect?.(i)}
                disabled={!onSelect || s.count === 0}
              >
                <span className="donut-legend__swatch" aria-hidden="true" />
                <span className="donut-legend__label">{s.label}</span>
                <span className="donut-legend__val">
                  {s.count} <span className="muted">· {total ? Math.round((s.count / total) * 100) : 0}%</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** "Where the marks land": the same four bands GET /reports/cohort/{id} already reports
 * (band_counts), drawn twice -- the whole class, and one section of it read from the
 * same endpoint narrowed by section_id. Nothing here is computed client-side beyond
 * percentages of those counts. */
export function MarksDonuts({
  assessmentId,
  testTitle,
  wholeLabel,
  sections,
  defaultSectionId,
  onSelectWhole,
}: {
  assessmentId: string;
  testTitle: string;
  wholeLabel: string;
  sections: { section_id: string; label: string }[];
  defaultSectionId?: string;
  onSelectWhole?: (bandIndex: number) => void;
}) {
  const key = getApiKey() ?? "";
  const [sectionId, setSectionId] = useState<string>(defaultSectionId ?? sections[0]?.section_id ?? "");
  const [whole, setWhole] = useState<CohortReport | null>(null);
  const [part, setPart] = useState<CohortReport | null>(null);
  const [partMissing, setPartMissing] = useState(false);

  useEffect(() => {
    if (!sectionId && sections.length) setSectionId(defaultSectionId ?? sections[0].section_id);
  }, [sections, sectionId, defaultSectionId]);

  useEffect(() => {
    let cancelled = false;
    api.cohortReport(key, assessmentId).then(
      (r) => !cancelled && setWhole(r),
      () => !cancelled && setWhole(null),
    );
    return () => {
      cancelled = true;
    };
  }, [key, assessmentId]);

  useEffect(() => {
    if (!sectionId) return;
    let cancelled = false;
    setPartMissing(false);
    api.cohortReport(key, assessmentId, sectionId).then(
      (r) => !cancelled && setPart(r),
      () => {
        if (!cancelled) {
          setPart(null);
          setPartMissing(true);
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [key, assessmentId, sectionId]);

  const wholeSlices = useMemo(() => slicesOf(whole), [whole]);
  const partSlices = useMemo(() => slicesOf(part), [part]);
  const sectionLabel = sections.find((s) => s.section_id === sectionId)?.label ?? "";

  if (!whole) return null;

  return (
    <div className="card">
      <div className="card__head">
        <div>
          <h3 style={{ fontSize: 16 }}>Where the marks land</h3>
          <p className="small muted" style={{ marginTop: 2 }}>
            Compare one section against the whole of {wholeLabel}, on {testTitle}.
          </p>
        </div>
        {sections.length > 0 && (
          <div className="filter">
            <label htmlFor="donut-section">Section</label>
            <select id="donut-section" className="select" value={sectionId} onChange={(e) => setSectionId(e.target.value)}>
              {sections.map((s) => (
                <option key={s.section_id} value={s.section_id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
      <div className="card__body donut-pair">
        <Donut title={`All of ${wholeLabel}`} caption={`${whole.students_analysed} students on this test`} slices={wholeSlices} onSelect={onSelectWhole} />
        {part ? (
          <Donut title={sectionLabel} caption={`${part.students_analysed} students on this test`} slices={partSlices} />
        ) : (
          <div className="donut-card donut-card--empty">
            <div className="strong">{sectionLabel}</div>
            <p className="small muted">{partMissing ? "No marks entered for this section on this test yet." : "Loading…"}</p>
          </div>
        )}
      </div>
    </div>
  );
}
