"use client";

import { useCallback, useEffect, useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { ArrowRight, CalendarClock, CalendarPlus, ChevronDown, ChevronRight, ClipboardCheck, TrendingDown } from "lucide-react";
import { api, ApiError, type ConductedExam, type ExamGridCell, type ExamsOverview } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { usePageHeader } from "@/lib/pageHeader";
import { DeltaCell } from "@/components/StudentRosterTable";

/** Whole days from today (the viewer's own calendar day) to an ISO YYYY-MM-DD date. */
function daysUntil(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  const now = new Date();
  const target = Date.UTC(y, m - 1, d);
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target - today) / 86_400_000);
}

function daysAwayLabel(days: number): string {
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days < 0) return `${-days} days ago`;
  return `${days} days away`;
}

function todayIso(): string {
  const now = new Date();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${mm}-${dd}`;
}

/** Group a conducted exam's grid by section, keeping the backend's class/subject order. */
function bySection(grid: ExamGridCell[]): { sectionId: string; label: string; cells: ExamGridCell[] }[] {
  const out: { sectionId: string; label: string; cells: ExamGridCell[] }[] = [];
  for (const cell of grid) {
    let group = out.find((g) => g.sectionId === cell.section_id);
    if (!group) {
      group = { sectionId: cell.section_id, label: cell.section_label, cells: [] };
      out.push(group);
    }
    group.cells.push(cell);
  }
  return out;
}

function ConductedCard({ exam }: { exam: ConductedExam }) {
  const [open, setOpen] = useState(false);
  const sections = bySection(exam.grid);
  return (
    <div className="card card--hover">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="card__head"
        style={{ width: "100%", background: "none", border: 0, textAlign: "left", cursor: "pointer", paddingBottom: 18, font: "inherit", color: "inherit" }}
      >
        <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
          {open ? <ChevronDown size={18} style={{ marginTop: 2 }} /> : <ChevronRight size={18} style={{ marginTop: 2 }} />}
          <div>
            <div className="strong" style={{ fontSize: 15, fontWeight: 650 }}>{exam.name}</div>
            <div className="small muted" style={{ marginTop: 2 }}>
              {exam.date ?? "-"} · {exam.subjects.join(", ")} · {exam.students_marked} students marked
              {exam.kind === "paper" && " · single paper"}
            </div>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="stat__label">School average</div>
          <div className="strong" style={{ display: "flex", alignItems: "baseline", gap: 6, justifyContent: "flex-end" }}>
            {exam.school_avg_pct === null ? "-" : `${exam.school_avg_pct}%`}
            {exam.delta_pct !== null && <DeltaCell delta={exam.delta_pct} />}
          </div>
        </div>
      </button>
      {open && (
        <div className="card__body" style={{ paddingTop: 0 }}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Section</th>
                  <th>Subject</th>
                  <th className="num">Average</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {sections.map((s) =>
                  s.cells.map((c, i) => (
                    <tr key={`${c.section_id}-${c.subject_code}`}>
                      <td className="strong">{i === 0 ? s.label : ""}</td>
                      <td>
                        {c.assessment_ids.length === 1 ? (
                          <Link href={`/principal/classes/${c.section_id}/tests/${c.assessment_ids[0]}`}>{c.subject_label}</Link>
                        ) : (
                          c.subject_label
                        )}
                      </td>
                      <td className="num">{c.avg_score_pct}%</td>
                      <td style={{ textAlign: "right" }}>
                        {i === 0 && (
                          <Link href={`/principal/classes/${s.sectionId}`} className="btn--link" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                            Full report <ArrowRight size={12} />
                          </Link>
                        )}
                      </td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--line)" }}>
            <span className="kpi__label">All-subjects school average</span>
            <span className="strong">{exam.school_avg_pct === null ? "-" : `${exam.school_avg_pct}%`}</span>
          </div>
        </div>
      )}
    </div>
  );
}

/** Principal → Exams. Every number and name here comes from GET /admin/exams: exam days
 * a principal or admin scheduled (POST /admin/exams), their papers' real resolved marks
 * rolled up per section and subject, and papers never attached to an exam shown on their
 * own. Days-away is computed here from the exam's real scheduled date. */
export default function ExamsPage() {
  usePageHeader({ title: "Exams" });
  const key = getApiKey() ?? "";
  const [data, setData] = useState<ExamsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState("");
  const [when, setWhen] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.exams(key));
    } finally {
      setLoading(false);
    }
  }, [key]);

  useEffect(() => {
    void load();
  }, [load]);

  async function schedule(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || !when) {
      setFormError("Give the exam a name and a date.");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      await api.createExam(key, { name: name.trim(), scheduled_date: when });
      setName("");
      setWhen("");
      setFormOpen(false);
      await load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not schedule the exam.");
    } finally {
      setSaving(false);
    }
  }

  const conducted = data?.conducted ?? [];
  const upcoming = data?.upcoming ?? [];
  const awaiting = data?.awaiting_marks ?? [];
  const latest = conducted.find((c) => c.kind === "exam") ?? conducted[0];
  const next = upcoming[0];

  const tiles: { label: string; icon: ReactNode; accent: string; value: ReactNode; sub: string }[] = [
    {
      label: latest ? `${latest.name}, school average` : "Latest exam",
      icon: <ClipboardCheck size={22} />,
      accent: "var(--brand-teal)",
      value: (
        <>
          {latest?.school_avg_pct == null ? "-" : `${latest.school_avg_pct}%`}
          {latest && latest.delta_pct !== null && <DeltaCell delta={latest.delta_pct} />}
        </>
      ),
      sub: latest?.previous ? `vs ${latest.previous.name}` : latest ? "No earlier exam to compare" : "No exam with marks yet",
    },
    {
      label: "Weakest subject",
      icon: <TrendingDown size={22} />,
      accent: "#c2410c",
      value: data?.weakest_subject ? data.weakest_subject.label : "-",
      sub: data?.weakest_subject ? `${data.weakest_subject.avg_score_pct}% average across every mark so far` : "No marks yet",
    },
    {
      label: "Next exam",
      icon: <CalendarClock size={22} />,
      accent: "#4f46e5",
      value: next ? next.name : "-",
      sub: next ? `${next.scheduled_date} · ${daysAwayLabel(daysUntil(next.scheduled_date))}` : "Nothing scheduled",
    },
  ];

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <p className="page-sub" style={{ margin: 0 }}>
          Exam days you have scheduled, and how every section did in every subject.
        </p>
        <button type="button" className="btn btn--primary" onClick={() => setFormOpen((o) => !o)}>
          <CalendarPlus size={15} /> Schedule an exam
        </button>
      </div>

      {formOpen && (
        <form className="card" onSubmit={schedule} style={{ marginTop: 16 }}>
          <div className="card__body" style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
            <div className="field" style={{ flex: "2 1 220px" }}>
              <label htmlFor="exam-name">Exam name</label>
              <input id="exam-name" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Quarterly Exam" maxLength={200} />
            </div>
            <div className="field" style={{ flex: "1 1 160px" }}>
              <label htmlFor="exam-date">Date</label>
              <input id="exam-date" className="input" type="date" value={when} min={todayIso()} onChange={(e) => setWhen(e.target.value)} />
            </div>
            <button type="submit" className="btn btn--primary" disabled={saving}>
              {saving ? "Scheduling…" : "Schedule"}
            </button>
            {formError && <p className="small" style={{ color: "var(--danger, #b91c1c)", width: "100%", margin: 0 }}>{formError}</p>}
          </div>
        </form>
      )}

      {!loading && (
        <div className="grid grid--3" style={{ marginTop: 20 }}>
          {tiles.map((t) => (
            <div className="kpi" key={t.label} style={{ "--accent": t.accent } as CSSProperties}>
              <span className="kpi__icon">{t.icon}</span>
              <div className="kpi__text">
                <span className="kpi__label">{t.label}</span>
                <span className="kpi__value" style={{ fontSize: 20 }}>{t.value}</span>
                <span className="kpi__sub">{t.sub}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <section className="section">
        <div className="section__head">
          <h2 className="section-q">
            <ClipboardCheck size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} /> Conducted
          </h2>
        </div>
        <div style={{ display: "grid", gap: 12 }}>
          {loading && <p className="small muted">Loading…</p>}
          {!loading && conducted.map((c) => <ConductedCard key={`${c.kind}-${c.id}`} exam={c} />)}
          {!loading && conducted.length === 0 && <p className="small muted">No exam has resolved marks yet.</p>}
        </div>
      </section>

      <section className="section">
        <div className="section__head">
          <h2 className="section-q">
            <CalendarClock size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} /> Upcoming
          </h2>
        </div>
        <div style={{ display: "grid", gap: 12 }}>
          {!loading &&
            [...upcoming, ...awaiting].map((u) => {
              const days = daysUntil(u.scheduled_date);
              return (
                <div className="card card--hover" key={u.id}>
                  <div className="card__head" style={{ paddingBottom: 18, alignItems: "center" }}>
                    <div>
                      <div className="strong" style={{ fontSize: 15, fontWeight: 650 }}>{u.name}</div>
                      <div className="small muted" style={{ marginTop: 2 }}>
                        {u.scheduled_date} · {daysAwayLabel(days)}
                        {u.paper_count > 0 && ` · ${u.paper_count} paper${u.paper_count === 1 ? "" : "s"} attached`}
                      </div>
                    </div>
                    <span className="chip">{u.status}</span>
                  </div>
                </div>
              );
            })}
          {!loading && upcoming.length + awaiting.length === 0 && (
            <p className="small muted">Nothing scheduled. Use “Schedule an exam” to add one.</p>
          )}
        </div>
      </section>
    </>
  );
}
