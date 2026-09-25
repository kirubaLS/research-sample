"use client";

/**
 * Principal → Share reports. The reference's own KPI row + tabbed, checkbox-select
 * list look (.kpi, .tabs, .sharelist), with its fictional WhatsApp send replaced by
 * this deployment's real issue+share-PIN flow: POST .../reports/{studentId}/issue then
 * POST .../reports/{id}/share (same endpoints the single-student "Share" action already
 * calls elsewhere). There is no messaging integration in this deployment and no phone
 * number field on a student -- inventing one would be exactly the kind of thing this
 * codebase refuses to fake, so the PIN is shown once, for a person to pass along however
 * their school actually reaches parents.
 *
 * A report already issued for this exact test is reused rather than re-issued: issuing
 * always creates a fresh snapshot of that student's marks, so re-issuing on every visit
 * would pile up duplicate snapshots of marks that have not changed.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Clock, KeyRound, Search, Send, X } from "lucide-react";
import { api, type ClassStudentRow, type IssuedReportRow, type SectionSummary } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { usePageHeader } from "@/lib/pageHeader";

/** Masks a stored WhatsApp number down to what a screen actually needs to show: the
 * country code and last few digits, e.g. "+919123456864" -> "+91 91XXX XX864". Purely a
 * display transform -- the full number this school entered is unchanged in storage. */
function maskPhone(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  if (digits.length < 6) return raw;
  const cc = digits.length > 10 ? digits.slice(0, digits.length - 10) : "91";
  const local = digits.slice(-10);
  return `+${cc} ${local.slice(0, 2)}XXX XX${local.slice(-3)}`;
}

type RowStatus = "checking" | "not_issued" | "issued" | "shared";
type View = "all" | "unshared" | "shared";

interface Row {
  student: ClassStudentRow;
  status: RowStatus;
  reportId: string | null;
  pin: string | null;
  error: string | null;
}

export default function ShareReportsPage() {
  usePageHeader({ title: "Share reports", subtitle: "Issue and share test reports with parents" });
  const key = getApiKey() ?? "";

  const [sections, setSections] = useState<SectionSummary[]>([]);
  const [sectionId, setSectionId] = useState("");
  const [tests, setTests] = useState<{ assessment_id: string; title: string }[]>([]);
  const [assessmentId, setAssessmentId] = useState("");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [by, setBy] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("all");
  const [query, setQuery] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!key) return;
    api
      .overview(key)
      .then((res) => setSections(res.sections))
      .catch(() => setError("Could not load your classes."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!key || !sectionId) {
      setTests([]);
      setAssessmentId("");
      return;
    }
    api
      .classStudents(key, sectionId, {})
      .then((res) => {
        setTests(res.filters.tests);
        setAssessmentId((current) => (res.filters.tests.some((t) => t.assessment_id === current) ? current : ""));
      })
      .catch(() => setError("Could not load this class's tests."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionId]);

  // Every row starts "checking" and resolves independently -- one student's slow or
  // failed lookup must never block the rest of the class from showing its real status.
  useEffect(() => {
    if (!key || !sectionId || !assessmentId) {
      setRows(null);
      return;
    }
    let cancelled = false;
    setError(null);
    api
      .classStudents(key, sectionId, { assessmentId })
      .then((res) => {
        if (cancelled) return;
        setRows(res.students.map((student) => ({ student, status: "checking", reportId: null, pin: null, error: null })));
        for (const student of res.students) {
          api
            .studentIssuedReports(key, student.student_id)
            .then((res: { reports: IssuedReportRow[] }) => {
              if (cancelled) return;
              const existing = res.reports.find((rep) => rep.assessment_id === assessmentId) ?? null;
              setRows(
                (prev) =>
                  prev?.map((row) =>
                    row.student.student_id === student.student_id
                      ? { ...row, status: existing ? (existing.shared ? "shared" : "issued") : "not_issued", reportId: existing?.report_id ?? null }
                      : row,
                  ) ?? null,
              );
            })
            .catch(() => {
              if (cancelled) return;
              setRows(
                (prev) =>
                  prev?.map((row) =>
                    row.student.student_id === student.student_id
                      ? { ...row, status: "not_issued", error: "Could not check this student's reports." }
                      : row,
                  ) ?? null,
              );
            });
        }
      })
      .catch(() => setError("Could not load this class's roster for that test."));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionId, assessmentId]);

  async function shareOne(row: Row): Promise<void> {
    if (!key || !by.trim()) return;
    setRows((prev) => prev?.map((r) => (r.student.student_id === row.student.student_id ? { ...r, error: null } : r)) ?? null);
    try {
      let reportId = row.reportId;
      if (!reportId) {
        const issued = await api.issueReport(key, row.student.student_id, assessmentId, by.trim());
        reportId = issued.report_id;
      }
      const shared = await api.shareReport(key, reportId, by.trim());
      setRows(
        (prev) =>
          prev?.map((r) => (r.student.student_id === row.student.student_id ? { ...r, status: "shared", reportId, pin: shared.pin, error: null } : r)) ?? null,
      );
    } catch {
      setRows((prev) => prev?.map((r) => (r.student.student_id === row.student.student_id ? { ...r, error: "Could not share this report." } : r)) ?? null);
    }
  }

  async function shareAllUnsent() {
    if (!rows || !by.trim()) return;
    setBusy("Sharing with everyone not yet shared");
    for (const row of rows) {
      if (row.status === "shared" || row.status === "checking") continue;
      await shareOne(row);
    }
    setBusy(null);
    setToast(`Reports shared for ${sections.find((s) => s.section_id === sectionId)?.label ?? "this class"}.`);
    setTimeout(() => setToast(null), 3000);
  }

  const unsent = rows?.filter((r) => r.status === "not_issued" || r.status === "issued") ?? [];
  const shared = rows?.filter((r) => r.status === "shared") ?? [];

  const q = query.trim().toLowerCase();
  const shownRows = useMemo(() => {
    if (!rows) return [];
    return rows.filter((r) => {
      if (view === "shared" && r.status !== "shared") return false;
      if (view === "unshared" && r.status === "shared") return false;
      if (q && !r.student.name.toLowerCase().split(/\s+/).some((w) => w.startsWith(q))) return false;
      return true;
    });
  }, [rows, view, q]);

  const testTitle = tests.find((t) => t.assessment_id === assessmentId)?.title ?? "this test";
  const sectionLabel = sections.find((s) => s.section_id === sectionId)?.label ?? "";

  return (
    <>
      <div className="filterbar share-filters">
        <div className="filter">
          <label htmlFor="share-class">Class</label>
          <select id="share-class" className="select" value={sectionId} onChange={(e) => setSectionId(e.target.value)}>
            <option value="">Choose a class…</option>
            {sections.map((s) => (
              <option key={s.section_id} value={s.section_id}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <div className="filter">
          <label htmlFor="share-test">Test</label>
          <select id="share-test" className="select" value={assessmentId} onChange={(e) => setAssessmentId(e.target.value)} disabled={!sectionId}>
            <option value="">Choose a test…</option>
            {tests.map((t) => (
              <option key={t.assessment_id} value={t.assessment_id}>
                {t.title}
              </option>
            ))}
          </select>
        </div>
        <div className="filter">
          <label htmlFor="share-by">Your name</label>
          <input id="share-by" className="input" value={by} onChange={(e) => setBy(e.target.value)} placeholder="required before sharing" />
        </div>
      </div>

      {error && <p style={{ color: "var(--risk)", fontSize: 13.5, marginTop: 12 }}>{error}</p>}

      {rows && (
        <>
          <div className="grid grid--3" style={{ marginTop: 16 }}>
            <div className="kpi" style={{ "--accent": "var(--brand-green)" } as React.CSSProperties}>
              <span className="kpi__icon">
                <CheckCircle2 size={20} />
              </span>
              <div className="kpi__text">
                <div className="kpi__label">Shared</div>
                <div className="kpi__value">
                  {shared.length}
                  <span className="small muted" style={{ fontWeight: 500 }}>
                    of {rows.length}
                  </span>
                </div>
                <div className="kpi__sub">Parents with a live PIN for {testTitle}</div>
              </div>
            </div>
            <div className="kpi" style={{ "--accent": "var(--brand-gold)" } as React.CSSProperties}>
              <span className="kpi__icon">
                <KeyRound size={20} />
              </span>
              <div className="kpi__text">
                <div className="kpi__label">Not yet shared</div>
                <div className="kpi__value">{unsent.length}</div>
                <div className="kpi__sub">{unsent.length ? "Still waiting for a PIN" : "Every report has been shared"}</div>
              </div>
            </div>
            <div className="kpi" style={{ "--accent": "var(--brand-blue)" } as React.CSSProperties}>
              <span className="kpi__icon">
                <Clock size={20} />
              </span>
              <div className="kpi__text">
                <div className="kpi__label">Scope</div>
                <div className="kpi__value" style={{ fontSize: 18 }}>
                  {sectionLabel || "-"}
                </div>
                <div className="kpi__sub">{testTitle}</div>
              </div>
            </div>
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <div className="card__head share-actions">
              <div>
                <h3 style={{ fontSize: 16 }}>Issue &amp; share PINs</h3>
                <p className="small muted" style={{ marginTop: 2 }}>
                  Each PIN opens this student&apos;s {testTitle} report. Shown once here, pass it on yourself.
                </p>
              </div>
              <div className="share-actions__btns">
                <button type="button" className="btn btn--primary" disabled={!by.trim() || !!busy || unsent.length === 0} onClick={() => void shareAllUnsent()}>
                  <Send size={14} /> {busy ? "Working…" : `Share with everyone not yet shared (${unsent.length})`}
                </button>
              </div>
            </div>

            <div className="share-toolbar">
              <div className="tabs" role="tablist">
                {(
                  [
                    ["all", `All (${rows.length})`],
                    ["unshared", `Not shared (${unsent.length})`],
                    ["shared", `Shared (${shared.length})`],
                  ] as [View, string][]
                ).map(([k, l]) => (
                  <button key={k} role="tab" aria-selected={view === k} className={`tab ${view === k ? "tab--active" : ""}`} onClick={() => setView(k)}>
                    {l}
                  </button>
                ))}
              </div>
              <div className="searchbox">
                <Search size={15} aria-hidden="true" />
                <input className="input" type="search" placeholder="Search student" aria-label="Search student" value={query} onChange={(e) => setQuery(e.target.value)} />
                {query && (
                  <button type="button" className="iconbtn" aria-label="Clear search" onClick={() => setQuery("")}>
                    <X size={14} />
                  </button>
                )}
              </div>
            </div>

            <div className="sharelist">
              {shownRows.map((row) => (
                <div key={row.student.student_id} className="sharelist__row">
                  <span className="sharelist__roll mono">{row.student.roll_no}</span>
                  <div className="sharelist__who">
                    <Link href={`/principal/classes/${sectionId}/${row.student.student_id}`} className="strong">
                      {row.student.name}
                    </Link>
                    <span className="small muted">
                      {row.student.parent_whatsapp ? `Parent ${maskPhone(row.student.parent_whatsapp)}` : "No parent contact on file"}
                    </span>
                    <span className="small muted">
                      {row.status === "checking" && "Checking…"}
                      {row.status === "not_issued" && "Not issued"}
                      {row.status === "issued" && "Issued, not shared"}
                      {row.status === "shared" && (row.pin ? `PIN ${row.pin}` : "Shared")}
                    </span>
                    {row.error && (
                      <span className="small" style={{ color: "var(--risk)" }}>
                        {row.error}
                      </span>
                    )}
                  </div>
                  <span className={`tag ${row.status === "shared" ? "tag--green" : ""}`}>
                    {row.status === "checking" && "Checking"}
                    {row.status === "not_issued" && "Not shared"}
                    {row.status === "issued" && "Not shared"}
                    {row.status === "shared" && "Shared"}
                  </span>
                  <button type="button" className="btn btn--sm" disabled={!by.trim() || row.status === "checking"} onClick={() => void shareOne(row)}>
                    <Send size={12} /> {row.status === "shared" ? "Reset PIN" : "Share"}
                  </button>
                </div>
              ))}
              {shownRows.length === 0 && (
                <p className="small muted" style={{ padding: "14px 16px", margin: 0 }}>
                  No students match.
                </p>
              )}
            </div>
          </div>
        </>
      )}

      {sectionId && assessmentId && rows?.length === 0 && <p className="muted" style={{ marginTop: 20 }}>No students in this class.</p>}

      <AnimatePresence>
        {toast && (
          <motion.div className="toast" role="status" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}>
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
