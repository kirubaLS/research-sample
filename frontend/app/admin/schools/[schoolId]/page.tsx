"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  ArrowLeft,
  BellRing,
  Building2,
  Check,
  FileUp,
  KeyRound,
  Mail,
  Pencil,
  Phone,
  Plus,
  Power,
  RefreshCw,
  Save,
  Search,
  Trash2,
  UserPlus,
  X,
  type LucideIcon,
} from "lucide-react";
import { CountUp, Reveal, Stagger, StaggerItem } from "@/components/motion";
import { boards, checklistAccent, checklistLength, daysUntil, formatAgo, formatDate, onboardingPct, schoolById, statusAccent, type Board } from "@/lib/avai-admin-data";
import { markReminded, useStaffSession } from "@/lib/adminState";
import { school as flagshipSchool } from "@/lib/avai-mock-data";
import {
  auditFor,
  cleanPhone,
  deleteConsoleSchool,
  directoryFor,
  formatPhone,
  isValidEmail,
  isValidPhone,
  principalKey,
  teacherKey,
  updateDirectory,
  useOpsVersion,
  type OpsStudent,
  type OpsTeacher,
  type SchoolDirectory,
} from "@/lib/opsDirectory";
import { OpsEmpty, StatusPill, Toast, useToast } from "../../ui";
import { accessSummary, blankTeacher, FieldError, secLabel, StudentsEditor, studentErrors, TeacherModal } from "../../directory";

type Tab = "overview" | "details" | "principal" | "teachers" | "students" | "activity";
const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "details", label: "School details" },
  { key: "principal", label: "Principal" },
  { key: "teachers", label: "Teachers" },
  { key: "students", label: "Students" },
  { key: "activity", label: "Activity" },
];

/** One school's account with full control: the onboarding picture, and
 * every detail of the school, its principal, teachers (and exactly which
 * subjects and sections each can see) and students. Every change is saved,
 * logged, and shows up across the console straight away. */
export default function AdminSchoolDetailPage() {
  const params = useParams<{ schoolId: string }>();
  useOpsVersion();
  const school = schoolById(params.schoolId);
  const dir = directoryFor(params.schoolId);
  const { staff } = useStaffSession();
  const { message, show } = useToast();
  const [tab, setTab] = useState<Tab>("overview");

  if (!school || !dir) {
    return (
      <div className="placeholder" style={{ marginTop: 24 }}>
        <p>No account with that id.</p>
        <Link href="/admin/schools" className="btn btn--sm" style={{ marginTop: 12 }}>
          <ArrowLeft size={13} /> Back to the portfolio
        </Link>
      </div>
    );
  }

  const by = staff?.name ?? "AVAI ops";
  const edit = (note: string, change: (d: SchoolDirectory) => void, toast?: string) => {
    updateDirectory(dir.id, by, note, change);
    show(toast ?? note);
  };

  return (
    <>
      <Link href="/admin/schools" className="btn btn--ghost btn--sm" style={{ marginBottom: 12 }}>
        <ArrowLeft size={13} /> All accounts
      </Link>

      <header className="surface surface--raised" style={{ padding: "18px 22px" }}>
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "flex-start" }}>
          <div style={{ minWidth: 240, flex: "1 1 340px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <h1 style={{ fontSize: 22, letterSpacing: "-.01em" }}>{school.name}</h1>
              <StatusPill status={school.status} />
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              <span className="tag mono">{school.code}</span>
              <span className="tag">{school.board}</span>
              <span className="tag">
                {school.city}, {school.state}
              </span>
              <span className="tag tag--info">{dir.sections.map((s) => secLabel(s)).join(" · ")}</span>
            </div>
          </div>
          <div style={{ flex: "0 1 280px", borderLeft: "1px solid var(--line)", paddingLeft: 18, display: "grid", gap: 2 }}>
            <div className="eyebrow">Principal</div>
            <div style={{ fontWeight: 650 }}>{dir.principal.name}</div>
            <span className="small" style={{ display: "inline-flex", gap: 6, alignItems: "center", marginTop: 4 }}>
              <Mail size={12} /> {dir.principal.email}
            </span>
            <span className="small muted" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <Phone size={12} /> {formatPhone(dir.principal.phone)}
            </span>
          </div>
        </div>
      </header>

      <div className="tabs ops-tabs" role="tablist" style={{ marginTop: 16 }}>
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} className={`tab ${tab === t.key ? "tab--active" : ""}`} onClick={() => setTab(t.key)}>
            {t.label}
            {t.key === "teachers" && ` (${dir.teachers.filter((x) => x.enabled).length})`}
            {t.key === "students" && ` (${dir.students.filter((x) => !x.left).length})`}
          </button>
        ))}
      </div>

      <div style={{ marginTop: 16 }}>
        {tab === "overview" && <Overview schoolId={school.id} onRemind={() => { markReminded(school.id); show(`Reminder sent to ${dir.principal.name}.`); }} />}
        {tab === "details" && <DetailsTab dir={dir} edit={edit} />}
        {tab === "principal" && <PrincipalTab dir={dir} edit={edit} />}
        {tab === "teachers" && <TeachersTab dir={dir} edit={edit} show={show} />}
        {tab === "students" && <StudentsTab dir={dir} edit={edit} />}
        {tab === "activity" && <ActivityTab schoolId={dir.id} />}
      </div>

      <Toast message={message} />
    </>
  );
}

type EditFn = (note: string, change: (d: SchoolDirectory) => void, toast?: string) => void;

// ------------------------------------------------------------
// Overview: where onboarding stands
// ------------------------------------------------------------

function Overview({ schoolId, onRemind }: { schoolId: string; onRemind: () => void }) {
  const school = schoolById(schoolId)!;
  const renewalIn = daysUntil(school.renewalDate);
  const headline: { label: string; value: number; sub: string; accent: string; icon: LucideIcon; suffix?: string }[] = [
    { label: "Students onboarded", value: school.studentsOnboarded, sub: `of ${school.students} enrolled`, accent: "var(--brand-blue)", icon: UserPlus },
    { label: "Teachers activated", value: school.teachersActivated, sub: `of ${school.teachersInvited} with access`, accent: "var(--brand-gold)", icon: KeyRound },
    { label: "Onboarding", value: onboardingPct(school), sub: `${school.progress} of ${checklistLength} steps done`, accent: statusAccent(school.status), icon: Building2, suffix: "%" },
    { label: "Tests conducted", value: school.testsConducted, sub: `${school.papersUploaded} of ${school.papersExpected} papers uploaded`, accent: "var(--brand-teal)", icon: FileUp },
  ];
  return (
    <>
      <Stagger className="grid grid--4" gap={0.05}>
        {headline.map((k, i) => {
          const Icon = k.icon;
          return (
            <StaggerItem key={k.label}>
              <div className="kpi" style={{ "--accent": k.accent } as React.CSSProperties}>
                <span className="kpi__icon">
                  <Icon size={21} />
                </span>
                <div className="kpi__text">
                  <div className="kpi__label">{k.label}</div>
                  <div className="kpi__value">
                    <CountUp value={k.value} delay={0.12 + i * 0.05} suffix={k.suffix ?? ""} />
                  </div>
                  <div className="kpi__sub">{k.sub}</div>
                </div>
              </div>
            </StaggerItem>
          );
        })}
      </Stagger>

      {school.blocker && (
        <div className="evidence" style={{ marginTop: 16, background: "var(--risk-soft)", borderColor: "#eec3bb", color: "#8f3226" }}>
          <AlertTriangle size={15} />
          <span>
            <span className="evidence__title">
              Blocker · {school.daysInStage} days in {school.stage}
            </span>
            {school.blocker}
          </span>
        </div>
      )}

      <Reveal delay={0.1}>
        <section className="card" style={{ marginTop: 16 }} aria-labelledby="checklist-h">
          <div className="card__body">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <h2 id="checklist-h" style={{ fontSize: 15 }}>
                Onboarding checklist
              </h2>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span className="small muted">
                  Renewal {formatDate(school.renewalDate)}
                  {renewalIn > 0 ? ` · ${renewalIn}d` : " · lapsed"} · last activity {formatAgo(school.lastActivity)}
                </span>
                <button type="button" className="btn btn--sm" onClick={onRemind}>
                  <BellRing size={13} /> Send reminder
                </button>
              </div>
            </div>
            <div style={{ display: "grid", gap: 2, marginTop: 12 }}>
              {school.checklist.map((step) => {
                const accent = checklistAccent(step.state);
                const done = step.state === "done";
                return (
                  <div key={step.key} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0", borderBottom: "1px dashed var(--line)" }}>
                    <span
                      style={{
                        width: 20,
                        height: 20,
                        borderRadius: "50%",
                        display: "grid",
                        placeItems: "center",
                        flex: "0 0 auto",
                        color: step.state === "todo" ? "var(--muted)" : "#fff",
                        background: step.state === "todo" ? "var(--surface-2)" : accent,
                        border: step.state === "todo" ? "1px solid var(--line-strong)" : "none",
                      }}
                    >
                      {done ? <Check size={12} /> : step.state === "blocked" ? <AlertTriangle size={11} /> : null}
                    </span>
                    <span style={{ flex: 1, minWidth: 0, fontSize: 13.5, fontWeight: done ? 500 : 650, color: step.state === "todo" ? "var(--muted)" : "var(--text)" }}>
                      {step.label}
                      <span className="small muted" style={{ display: "block", fontWeight: 400 }}>
                        {step.detail}
                      </span>
                    </span>
                    {step.state === "active" && <span className="tag tag--info">In progress</span>}
                    {step.state === "blocked" && <span className="tag tag--risk">Blocked</span>}
                    {step.date && <span className="small muted">{formatDate(step.date)}</span>}
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      </Reveal>
    </>
  );
}

// ------------------------------------------------------------
// School details
// ------------------------------------------------------------

function DetailsTab({ dir, edit }: { dir: SchoolDirectory; edit: EditFn }) {
  const router = useRouter();
  const [f, setF] = useState({ name: dir.name, code: dir.code, board: dir.board, city: dir.city, state: dir.state, address: dir.address, academicYear: dir.academicYear });
  const [sections, setSections] = useState(dir.sections);
  const [newSection, setNewSection] = useState("");
  const [tried, setTried] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const isFlagship = dir.id === flagshipSchool.id;

  const errors: Record<string, string> = {};
  if (!f.name.trim()) errors.name = "Enter the school's name.";
  if (!f.city.trim()) errors.city = "Enter the city.";
  if (!/^[A-Z0-9-]{3,12}$/.test(f.code)) errors.code = "Use 3 to 12 capital letters, numbers or dashes.";
  if (!sections.length) errors.sections = "Keep at least one section.";

  const removedWithStudents = dir.sections.filter((s) => !sections.includes(s) && dir.students.some((st) => st.section === s && !st.left));
  const dirty = JSON.stringify(f) !== JSON.stringify({ name: dir.name, code: dir.code, board: dir.board, city: dir.city, state: dir.state, address: dir.address, academicYear: dir.academicYear }) || sections.join() !== dir.sections.join();

  function save() {
    setTried(true);
    if (Object.keys(errors).length || removedWithStudents.length) return;
    edit("School details updated.", (d) => {
      Object.assign(d, { ...f, name: f.name.trim(), city: f.city.trim() });
      d.sections = sections;
      d.teachers = d.teachers.map((t) => ({
        ...t,
        classTeacherOf: t.classTeacherOf && sections.includes(t.classTeacherOf) ? t.classTeacherOf : null,
        access: t.access.map((a) => ({ ...a, sections: a.sections.filter((s) => sections.includes(s)) })).filter((a) => a.sections.length),
      }));
    });
  }

  function addSection() {
    const letter = newSection.trim().toUpperCase().replace(/[^A-Z]/g, "").slice(0, 2);
    if (letter && !sections.includes(`X-${letter}`)) setSections([...sections, `X-${letter}`].sort());
    setNewSection("");
  }

  return (
    <section className="card">
      <div className="card__body">
        <div className="ops-form-grid">
          <div className="field field--wide">
            <label htmlFor="d-name">School name</label>
            <input id="d-name" className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
            <FieldError>{tried && errors.name}</FieldError>
          </div>
          <div className="field">
            <label htmlFor="d-code">School code</label>
            <input id="d-code" className="input mono" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, "") })} />
            <span className="small muted">Changing it means everyone signs in with the new code.</span>
            <FieldError>{tried && errors.code}</FieldError>
          </div>
          <div className="field">
            <label htmlFor="d-board">Board</label>
            <select id="d-board" className="select" value={f.board} onChange={(e) => setF({ ...f, board: e.target.value as Board })}>
              {boards.map((b) => (
                <option key={b}>{b}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="d-city">City</label>
            <input id="d-city" className="input" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} />
            <FieldError>{tried && errors.city}</FieldError>
          </div>
          <div className="field">
            <label htmlFor="d-state">State</label>
            <input id="d-state" className="input" value={f.state} onChange={(e) => setF({ ...f, state: e.target.value })} />
          </div>
          <div className="field field--wide">
            <label htmlFor="d-address">Address</label>
            <input id="d-address" className="input" value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="d-year">Academic year</label>
            <input id="d-year" className="input" value={f.academicYear} onChange={(e) => setF({ ...f, academicYear: e.target.value })} />
          </div>
          <div className="field field--wide">
            <label>Class 10 sections</label>
            {isFlagship ? (
              <p className="small muted" style={{ margin: 0 }}>
                {sections.map(secLabel).join(", ")}. Sections are fixed while this school has tests being analysed.
              </p>
            ) : (
              <div className="chip-row">
                {sections.map((sec) => (
                  <span key={sec} className="chip">
                    Class {secLabel(sec)}
                    <button type="button" onClick={() => setSections(sections.filter((s) => s !== sec))} aria-label={`Remove section ${secLabel(sec)}`}>
                      <X size={12} />
                    </button>
                  </span>
                ))}
                <span className="chip chip--input">
                  10
                  <input value={newSection} maxLength={2} placeholder="C" aria-label="New section letter" onChange={(e) => setNewSection(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addSection())} />
                  <button type="button" onClick={addSection} aria-label="Add section">
                    <Plus size={12} />
                  </button>
                </span>
              </div>
            )}
            <FieldError>{tried && errors.sections}</FieldError>
            <FieldError>{removedWithStudents.length > 0 && `Move or remove the students in ${removedWithStudents.map(secLabel).join(", ")} before deleting the section.`}</FieldError>
          </div>
        </div>
      </div>
      <div className="card__foot" style={{ justifyContent: "space-between" }}>
        {dir.isNew ? (
          confirmDelete ? (
            <span style={{ display: "inline-flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <span className="small" style={{ color: "var(--risk)" }}>
                Delete {dir.name} and all its people?
              </span>
              <button
                type="button"
                className="btn btn--sm btn--danger"
                onClick={() => {
                  deleteConsoleSchool(dir.id);
                  router.push("/admin/schools");
                }}
              >
                Delete school
              </button>
              <button type="button" className="btn btn--sm" onClick={() => setConfirmDelete(false)}>
                Keep
              </button>
            </span>
          ) : (
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setConfirmDelete(true)}>
              <Trash2 size={13} /> Delete school
            </button>
          )
        ) : (
          <span />
        )}
        <button type="button" className="btn btn--blue" onClick={save} disabled={!dirty}>
          <Save size={14} /> Save changes
        </button>
      </div>
    </section>
  );
}

// ------------------------------------------------------------
// Principal
// ------------------------------------------------------------

function PrincipalTab({ dir, edit }: { dir: SchoolDirectory; edit: EditFn }) {
  const [p, setP] = useState({ name: dir.principal.name, email: dir.principal.email, phone: dir.principal.phone });
  const [tried, setTried] = useState(false);
  const errors: Record<string, string> = {};
  if (!p.name.trim()) errors.name = "Enter the principal's name.";
  if (!isValidEmail(p.email)) errors.email = "Enter a valid email.";
  if (!isValidPhone(p.phone)) errors.phone = "Enter a 10-digit mobile number.";
  const dirty = p.name !== dir.principal.name || p.email !== dir.principal.email || p.phone !== dir.principal.phone;

  return (
    <div className="grid grid--2" style={{ alignItems: "start" }}>
      <section className="card">
        <div className="card__body">
          <h2 style={{ fontSize: 15, marginBottom: 12 }}>Principal&apos;s details</h2>
          <div className="ops-form-grid ops-form-grid--one">
            <div className="field">
              <label htmlFor="pr-name">Full name</label>
              <input id="pr-name" className="input" value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} />
              <FieldError>{tried && errors.name}</FieldError>
            </div>
            <div className="field">
              <label htmlFor="pr-email">Email</label>
              <input id="pr-email" className="input" value={p.email} onChange={(e) => setP({ ...p, email: e.target.value })} />
              <FieldError>{tried && errors.email}</FieldError>
            </div>
            <div className="field">
              <label htmlFor="pr-phone">Mobile / WhatsApp</label>
              <input id="pr-phone" className="input" inputMode="tel" value={p.phone} onChange={(e) => setP({ ...p, phone: e.target.value })} />
              <FieldError>{tried && errors.phone}</FieldError>
            </div>
          </div>
        </div>
        <div className="card__foot" style={{ justifyContent: "flex-end" }}>
          <button
            type="button"
            className="btn btn--blue"
            disabled={!dirty}
            onClick={() => {
              setTried(true);
              if (Object.keys(errors).length) return;
              edit(`Principal details updated (${p.name.trim()}).`, (d) => {
                d.principal = { ...d.principal, name: p.name.trim(), email: p.email.trim(), phone: cleanPhone(p.phone) };
              });
            }}
          >
            <Save size={14} /> Save principal
          </button>
        </div>
      </section>

      <section className="card">
        <div className="card__body">
          <h2 style={{ fontSize: 15 }}>Principal login</h2>
          <p className="small muted" style={{ marginTop: 4 }}>
            School code <b className="mono">{dir.code}</b> and this access key. Sees every section and subject.
          </p>
          <div className="ops-keybox">
            <span className="mono ops-key">{principalKey(dir)}</span>
            <button
              type="button"
              className="btn btn--sm"
              onClick={() =>
                edit("Principal access key changed.", (d) => {
                  d.principal.keyRotation += 1;
                }, "New principal key generated, the old key stops working.")
              }
            >
              <RefreshCw size={12} /> Change key
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

// ------------------------------------------------------------
// Teachers
// ------------------------------------------------------------

function TeachersTab({ dir, edit, show }: { dir: SchoolDirectory; edit: EditFn; show: (m: string) => void }) {
  const [editing, setEditing] = useState<OpsTeacher | null>(null);
  const [query, setQuery] = useState("");
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const q = query.trim().toLowerCase();
  const rows = dir.teachers.filter((t) => !q || t.name.toLowerCase().includes(q) || t.access.some((a) => a.subject.toLowerCase().includes(q)));
  const isFlagship = dir.id === flagshipSchool.id;

  function save(t: OpsTeacher) {
    const exists = dir.teachers.some((x) => x.id === t.id);
    edit(
      exists ? `${t.name}'s access updated: ${accessSummary(t)}.` : `${t.name} added: ${accessSummary(t)}.`,
      (d) => {
        d.teachers = exists ? d.teachers.map((x) => (x.id === t.id ? t : x)) : [...d.teachers, t];
      },
      exists ? `${t.name} updated.` : `${t.name} added. Key ${teacherKey(dir.id, t)} is ready to share.`,
    );
    setEditing(null);
  }

  return (
    <section className="card">
      <div className="card__body" style={{ paddingBottom: 6 }}>
        <div className="ops-toolbar">
          <div>
            <h2 style={{ fontSize: 15 }}>Teachers and their access</h2>
            <p className="small muted" style={{ marginTop: 2 }}>
              Each teacher only sees the subjects and sections ticked for them.
              {isFlagship && " Changes here apply to this school's teacher logins straight away."}
            </p>
          </div>
          <div className="ops-toolbar__right">
            <div className="searchbox">
              <Search size={15} aria-hidden="true" />
              <input className="input" type="search" placeholder="Search name or subject" aria-label="Search teachers" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
            <button type="button" className="btn btn--blue btn--sm" onClick={() => setEditing(blankTeacher())}>
              <Plus size={13} /> Add teacher
            </button>
          </div>
        </div>
      </div>

      {dir.teachers.length === 0 ? (
        <div className="card__body">
          <OpsEmpty>No teachers yet. Add the first one.</OpsEmpty>
        </div>
      ) : (
        <div className="ops-list">
          {rows.map((t) => (
            <div key={t.id} className={`ops-list__row ${t.enabled ? "" : "ops-list__row--off"}`}>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span className="strong">{t.name}</span>
                  {t.role === "Exam cell" && <span className="tag tag--info">Exam cell</span>}
                  {!t.enabled ? <span className="tag tag--risk">Access off</span> : t.activated ? <span className="tag tag--teal">Active</span> : <span className="tag tag--gold">Key not used yet</span>}
                </div>
                <div className="small muted">
                  {formatPhone(t.phone)}
                  {t.email ? ` · ${t.email}` : ""}
                </div>
                <div className="small" style={{ marginTop: 3 }}>
                  {accessSummary(t)}
                </div>
              </div>
              <div className="ops-list__key">
                {t.enabled && <span className="mono ops-key">{teacherKey(dir.id, t)}</span>}
              </div>
              <div className="ops-list__actions">
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing(t)}>
                  <Pencil size={12} /> Edit access
                </button>
                {t.enabled && (
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() =>
                      edit(`${t.name}'s access key changed.`, (d) => {
                        const x = d.teachers.find((y) => y.id === t.id)!;
                        x.keyRotation += 1;
                        x.activated = false;
                      }, `New key generated for ${t.name}, the old key stops working.`)
                    }
                  >
                    <RefreshCw size={11} /> Change key
                  </button>
                )}
                {t.enabled && (
                  <button type="button" className="btn btn--ghost btn--sm" onClick={() => show(`Key re-sent to ${t.name} on WhatsApp (${formatPhone(t.phone)}).`)}>
                    Resend
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() =>
                    edit(t.enabled ? `${t.name}'s access turned off.` : `${t.name}'s access turned back on.`, (d) => {
                      const x = d.teachers.find((y) => y.id === t.id)!;
                      x.enabled = !x.enabled;
                    })
                  }
                >
                  <Power size={11} /> {t.enabled ? "Turn off" : "Turn on"}
                </button>
                {confirmRemove === t.id ? (
                  <>
                    <button
                      type="button"
                      className="btn btn--sm btn--danger"
                      onClick={() => {
                        edit(`${t.name} removed from the school.`, (d) => {
                          d.teachers = d.teachers.filter((y) => y.id !== t.id);
                        });
                        setConfirmRemove(null);
                      }}
                    >
                      Remove
                    </button>
                    <button type="button" className="btn btn--sm" onClick={() => setConfirmRemove(null)}>
                      Keep
                    </button>
                  </>
                ) : (
                  <button type="button" className="iconbtn" onClick={() => setConfirmRemove(t.id)} aria-label={`Remove ${t.name}`}>
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            </div>
          ))}
          {rows.length === 0 && <p className="small muted" style={{ padding: "12px 22px", margin: 0 }}>No teachers match.</p>}
        </div>
      )}

      <AnimatePresence>
        {editing && (
          <TeacherModal
            key={editing.id}
            initial={editing}
            sections={dir.sections}
            others={dir.teachers}
            title={dir.teachers.some((t) => t.id === editing.id) ? `Edit ${editing.name}` : "Add teacher"}
            onClose={() => setEditing(null)}
            onSave={save}
          />
        )}
      </AnimatePresence>
    </section>
  );
}

// ------------------------------------------------------------
// Students
// ------------------------------------------------------------

function StudentsTab({ dir, edit }: { dir: SchoolDirectory; edit: EditFn }) {
  const [draft, setDraft] = useState<OpsStudent[]>(dir.students);
  const [tried, setTried] = useState(false);
  const isFlagship = dir.id === flagshipSchool.id;
  const [lockedIds] = useState(() => new Set(isFlagship ? dir.students.map((s) => s.id) : []));
  const dirty = JSON.stringify(draft) !== JSON.stringify(dir.students);
  const bad = draft.filter((s) => !s.left && studentErrors(s).length > 0).length;
  const onRoll = draft.filter((s) => !s.left);
  const missing = onRoll.filter((s) => !isValidPhone(s.whatsapp)).length;

  function save() {
    setTried(true);
    if (bad) return;
    const added = draft.filter((s) => !dir.students.some((o) => o.id === s.id)).length;
    const removed = dir.students.filter((o) => !draft.some((s) => s.id === o.id) || (draft.find((s) => s.id === o.id)?.left && !o.left)).length;
    const parts = [added && `${added} added`, removed && `${removed} removed`, "details updated"].filter(Boolean).join(", ");
    edit(`Students: ${parts}.`, (d) => {
      d.students = draft.map((s) => ({ ...s, name: s.name.trim(), parentName: s.parentName.trim(), whatsapp: cleanPhone(s.whatsapp) }));
    }, "Student list saved.");
  }

  return (
    <section className="card">
      <div className="card__body">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
          <div>
            <h2 style={{ fontSize: 15 }}>Students and parent WhatsApp numbers</h2>
            <p className="small muted" style={{ marginTop: 2 }}>
              {onRoll.length} on roll · {onRoll.length - missing} WhatsApp numbers on file{missing ? `, ${missing} missing` : ""}.
              {isFlagship && " New students here join the analysis from the next test."}
            </p>
          </div>
        </div>
        <StudentsEditor sections={dir.sections} students={draft} onChange={setDraft} showErrors={tried} lockedIds={lockedIds} />
        <FieldError>{tried && bad > 0 && `${bad} student${bad === 1 ? " needs" : "s need"} a name or a valid WhatsApp number.`}</FieldError>
      </div>
      <div className="card__foot" style={{ justifyContent: "space-between", position: "sticky", bottom: 0, background: "var(--surface)", zIndex: 2 }}>
        <span className="small muted">{dirty ? "Unsaved changes" : "All changes saved"}</span>
        <span style={{ display: "flex", gap: 8 }}>
          <button type="button" className="btn" disabled={!dirty} onClick={() => { setDraft(dir.students); setTried(false); }}>
            Discard
          </button>
          <button type="button" className="btn btn--blue" disabled={!dirty} onClick={save}>
            <Save size={14} /> Save students
          </button>
        </span>
      </div>
    </section>
  );
}

// ------------------------------------------------------------
// Activity
// ------------------------------------------------------------

function ActivityTab({ schoolId }: { schoolId: string }) {
  const log = auditFor(schoolId);
  return (
    <section className="card">
      <div className="card__body">
        <h2 style={{ fontSize: 15 }}>Changes made from the console</h2>
        {log.length === 0 ? (
          <OpsEmpty>No changes yet.</OpsEmpty>
        ) : (
          <div className="ops-audit">
            {log.map((a, i) => (
              <div key={i} className="ops-audit__row">
                <span className="small muted">{new Date(a.at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}</span>
                <span>{a.text}</span>
                <span className="small muted">{a.by}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
