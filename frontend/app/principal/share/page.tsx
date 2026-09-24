"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Clock, MessageCircle, Search, Send, X } from "lucide-react";
import { analysedTests, classRosterFull, latestTest, school, sectionLabel, sections, type FullRosterStudent } from "@/lib/avai-mock-data";
import { markSent, sentLog, useLiveVersion } from "@/lib/liveData";
import { parentWhatsAppFor } from "@/lib/opsDirectory";
import { usePageHeader } from "@/lib/pageHeader";

type View = "all" | "unsent" | "sent";

/** The parent's WhatsApp number held by AVAI ops, masked as it would be on screen. */
function parentPhone(id: string): string {
  const n = parentWhatsAppFor(id);
  return n ? `+91 ${n.slice(0, 2)}XXX XX${n.slice(-3)}` : "No number on file";
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function when(iso: string): string {
  const d = new Date(iso);
  const hh = d.getHours();
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${((hh + 11) % 12) + 1}:${mm} ${hh < 12 ? "am" : "pm"}`;
}

/** Principal → Share reports. Pick a class and a test, then send every
 * student's report to their parent on WhatsApp, or pick individual
 * students. Every send is logged per student, so the page always shows who
 * has it and who is still waiting.
 * 🔧 BACKEND REQUIRED, nothing is actually sent from this demo. */
export default function ShareReportsPage() {
  usePageHeader({ title: "Share reports", subtitle: "Send test reports to parents on WhatsApp" });
  useLiveVersion();

  const [section, setSection] = useState<string>(sections[0]);
  const [testKey, setTestKey] = useState<string>(latestTest.key);
  const [view, setView] = useState<View>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirm, setConfirm] = useState<FullRosterStudent[] | null>(null);
  const [sending, setSending] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const roster = useMemo(() => classRosterFull[section] ?? [], [section]);
  const test = analysedTests.find((t) => t.key === testKey) ?? latestTest;
  const log = sentLog(section, testKey);
  const sentIds = roster.filter((s) => log[s.id]);
  const unsent = roster.filter((s) => !log[s.id]);
  const lastSent = Object.values(log).sort().at(-1);

  const history = useMemo(() => {
    const byTime = new Map<string, number>();
    for (const t of Object.values(log)) byTime.set(t, (byTime.get(t) ?? 0) + 1);
    return [...byTime.entries()].sort((a, b) => b[0].localeCompare(a[0]));
  }, [log]);

  const q = query.trim().toLowerCase();
  const rows = roster.filter((s) => {
    if (view === "sent" && !log[s.id]) return false;
    if (view === "unsent" && log[s.id]) return false;
    if (q && !s.name.toLowerCase().split(/\s+/).some((w) => w.startsWith(q))) return false;
    return true;
  });

  function changeScope(nextSection: string, nextTest: string) {
    setSection(nextSection);
    setTestKey(nextTest);
    setSelected(new Set());
  }

  function toggle(id: string) {
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const allShownSelected = rows.length > 0 && rows.every((s) => selected.has(s.id));
  function toggleAllShown() {
    setSelected((cur) => {
      const next = new Set(cur);
      if (allShownSelected) rows.forEach((s) => next.delete(s.id));
      else rows.forEach((s) => next.add(s.id));
      return next;
    });
  }

  function send(list: FullRosterStudent[]) {
    setSending(true);
    setTimeout(() => {
      markSent(section, testKey, list.map((s) => s.id), new Date().toISOString());
      setSending(false);
      setConfirm(null);
      setSelected(new Set());
      setToast(`${test.name} report sent on WhatsApp to ${list.length} parent${list.length === 1 ? "" : "s"}.`);
      setTimeout(() => setToast(null), 3000);
    }, 900);
  }

  const selectedStudents = roster.filter((s) => selected.has(s.id));

  return (
    <>
      <div className="filterbar share-filters">
        <div className="filter">
          <label htmlFor="share-class">Class</label>
          <select id="share-class" className="select" value={section} onChange={(e) => changeScope(e.target.value, testKey)}>
            {sections.map((s) => (
              <option key={s} value={s}>
                {sectionLabel(s)}
              </option>
            ))}
          </select>
        </div>
        <div className="filter">
          <label htmlFor="share-test">Test</label>
          <select id="share-test" className="select" value={testKey} onChange={(e) => changeScope(section, e.target.value)}>
            {[...analysedTests].reverse().map((t) => (
              <option key={t.key} value={t.key}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid--3" style={{ marginTop: 16 }}>
        <div className="kpi" style={{ "--accent": "var(--brand-green)" } as React.CSSProperties}>
          <span className="kpi__icon">
            <CheckCircle2 size={20} />
          </span>
          <div className="kpi__text">
            <div className="kpi__label">Sent</div>
            <div className="kpi__value">
              {sentIds.length}
              <span className="small muted" style={{ fontWeight: 500 }}>
                of {roster.length}
              </span>
            </div>
            <div className="kpi__sub">Parents who have the {test.name} report</div>
          </div>
        </div>
        <div className="kpi" style={{ "--accent": "var(--brand-gold)" } as React.CSSProperties}>
          <span className="kpi__icon">
            <MessageCircle size={20} />
          </span>
          <div className="kpi__text">
            <div className="kpi__label">Not sent</div>
            <div className="kpi__value">{unsent.length}</div>
            <div className="kpi__sub">{unsent.length ? "Still waiting for their report" : "Every parent has it"}</div>
          </div>
        </div>
        <div className="kpi" style={{ "--accent": "var(--brand-blue)" } as React.CSSProperties}>
          <span className="kpi__icon">
            <Clock size={20} />
          </span>
          <div className="kpi__text">
            <div className="kpi__label">Last sent</div>
            <div className="kpi__value" style={{ fontSize: 18 }}>
              {lastSent ? when(lastSent) : "Never"}
            </div>
            <div className="kpi__sub">
              {sectionLabel(section)} · {test.name}
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card__head share-actions">
          <div>
            <h3 style={{ fontSize: 16 }}>Send on WhatsApp</h3>
            <p className="small muted" style={{ marginTop: 2 }}>
              Each parent gets their child&apos;s {test.name} report for all subjects.
            </p>
          </div>
          <div className="share-actions__btns">
            <button className="btn" disabled={selected.size === 0 || sending} onClick={() => setConfirm(selectedStudents)}>
              <Send size={14} /> Send selected ({selected.size})
            </button>
            <button className="btn btn--primary btn--wa" disabled={unsent.length === 0 || sending} onClick={() => setConfirm(unsent)}>
              <MessageCircle size={15} /> Send to all not sent ({unsent.length})
            </button>
          </div>
        </div>

        <div className="share-toolbar">
          <div className="tabs" role="tablist">
            {(
              [
                ["all", `All (${roster.length})`],
                ["unsent", `Not sent (${unsent.length})`],
                ["sent", `Sent (${sentIds.length})`],
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
          <label className="sharelist__row sharelist__row--head">
            <input type="checkbox" checked={allShownSelected} onChange={toggleAllShown} aria-label="Select all shown" />
            <span>Select all shown ({rows.length})</span>
          </label>
          {rows.map((s) => {
            const at = log[s.id];
            return (
              <div key={s.id} className={`sharelist__row ${selected.has(s.id) ? "sharelist__row--on" : ""}`}>
                <input type="checkbox" checked={selected.has(s.id)} onChange={() => toggle(s.id)} aria-label={`Select ${s.name}`} />
                <span className="sharelist__roll mono">{s.rollNo}</span>
                <div className="sharelist__who">
                  <Link href={`/principal/classes/${section}/${s.id}`} className="strong">
                    {s.name}
                  </Link>
                  <span className="small muted">Parent {parentPhone(s.id)}</span>
                </div>
                <span className={`tag ${at ? "tag--green" : ""}`}>{at ? `Sent ${when(at)}` : "Not sent"}</span>
                <button className="btn btn--sm" disabled={sending} onClick={() => setConfirm([s])}>
                  <Send size={12} /> {at ? "Resend" : "Send"}
                </button>
              </div>
            );
          })}
          {rows.length === 0 && <p className="small muted" style={{ padding: "14px 16px", margin: 0 }}>No students match.</p>}
        </div>
      </div>

      <section className="section">
        <h2 className="section-q">Send history</h2>
        <p className="section__lead">
          {sectionLabel(section)} · {test.name}
        </p>
        <div className="card" style={{ marginTop: 12 }}>
          {history.length === 0 ? (
            <p className="small muted" style={{ padding: 16, margin: 0 }}>
              Nothing sent yet for this class and test.
            </p>
          ) : (
            <div className="sharelist">
              {history.map(([t, n]) => (
                <div key={t} className="sharelist__row">
                  <Clock size={15} style={{ color: "var(--muted)" }} />
                  <div className="sharelist__who">
                    <span className="strong">{when(t)}</span>
                    <span className="small muted">
                      {n} parent{n === 1 ? "" : "s"} on WhatsApp
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <AnimatePresence>
        {confirm && (
          <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => !sending && setConfirm(null)}>
            <motion.div
              className="modal"
              role="dialog"
              aria-modal="true"
              initial={{ y: 16, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 16, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="modal__head">
                <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <MessageCircle size={16} style={{ color: "#1faa59" }} /> Send on WhatsApp
                </h3>
                <button className="iconbtn" onClick={() => setConfirm(null)} aria-label="Close" disabled={sending}>
                  <X size={16} />
                </button>
              </div>
              <div className="modal__body">
                <p style={{ margin: 0 }}>
                  Send the <b>{test.name}</b> report to{" "}
                  <b>
                    {confirm.length === 1 ? `${confirm[0].name}'s parent` : `${confirm.length} parents`}
                  </b>{" "}
                  in {sectionLabel(section)}?
                </p>
                <div className="wa-preview">
                  Dear parent, {confirm[0]?.name ?? "your child"}&apos;s {test.name} report from {school.name} is ready. Open it here: avai.in/r/…
                </div>
              </div>
              <div className="modal__foot">
                <button className="btn" onClick={() => setConfirm(null)} disabled={sending}>
                  Cancel
                </button>
                <button className="btn btn--primary btn--wa" onClick={() => send(confirm)} disabled={sending}>
                  <Send size={14} /> {sending ? "Sending…" : `Send ${confirm.length === 1 ? "report" : `${confirm.length} reports`}`}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

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
