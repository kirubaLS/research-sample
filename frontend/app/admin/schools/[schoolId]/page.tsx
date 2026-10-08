"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft,
  CheckCircle2,
  Circle,
  Eye,
  EyeOff,
  FileCheck2,
  KeyRound,
  ListChecks,
  Plus,
  RefreshCw,
  Send,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import { CountUp, EASE_OUT, Stagger, StaggerItem } from "@/components/motion";
import {
  api,
  ApiError,
  AuditLogRow,
  OnboardingChecklist,
  PlatformOverview,
  PlatformSchool,
  PlatformStudentRow,
  StaffKeySummary,
  StudentBulkInput,
  TeacherAssignmentInput,
  TeacherAssignmentRow,
} from "@/lib/api";
import { getPlatformKey } from "@/lib/session";
import { CopySecret, OpsEmpty, SaveButton, Toast, useSaveState, useToast } from "../../ui";

type Tab = "overview" | "details" | "principal" | "teachers" | "students" | "activity";
const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "details", label: "School details" },
  { key: "principal", label: "Principal" },
  { key: "teachers", label: "Teachers" },
  { key: "students", label: "Students" },
  { key: "activity", label: "Activity" },
];

/**
 * One school's account, wired to real backend data throughout:
 *
 * - Overview / School details / Activity: GET+PATCH /platform/schools/{id}, and
 *   GET /platform/schools/{id}/activity.
 * - Principal: the single active (unrevoked) principal key at this school, its
 *   name/email/phone (PATCH /platform/schools/{id}/keys/{key_id}) and its own
 *   issue/rotate/revoke actions.
 * - Teachers: every teacher key at this school, each with its class/subject
 *   assignments (GET+PATCH .../keys/{key_id}/assignments). No "Resend": there is no
 *   notification infrastructure behind it, so the button is simply not rendered.
 * - Students: the full roster (GET .../students) plus a bulk add form
 *   (POST .../students/bulk) with parent name/WhatsApp fields.
 */
export default function AdminSchoolDetailPage() {
  const params = useParams<{ schoolId: string }>();
  const { message, show } = useToast();
  const [tab, setTab] = useState<Tab>("overview");
  const [school, setSchool] = useState<PlatformSchool | null | undefined>(undefined);
  const [overviewRow, setOverviewRow] = useState<PlatformOverview["schools"][number] | null>(null);
  const [keys, setKeys] = useState<StaffKeySummary[]>([]);
  const [students, setStudents] = useState<PlatformStudentRow[]>([]);
  const [activity, setActivity] = useState<AuditLogRow[]>([]);
  const [checklist, setChecklist] = useState<OnboardingChecklist | null>(null);
  const [issued, setIssued] = useState<{ label: string; api_key: string; notice: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Ids of rows (teachers, staff keys) that just had a real write succeed --
  // rendered with a brief flash, never before the call actually returns.
  const [flashIds, setFlashIds] = useState<Set<string>>(new Set());

  const flash = useCallback((id: string) => {
    setFlashIds((prev) => new Set(prev).add(id));
    setTimeout(() => {
      setFlashIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }, 1700);
  }, []);

  const load = useCallback(async () => {
    const key = getPlatformKey();
    if (!key) return;
    try {
      setSchool(await api.getSchool(key, params.schoolId));
    } catch {
      setSchool(null);
      setError("Could not load this school.");
    }
    try {
      const ov = await api.platformOverview(key);
      setOverviewRow(ov.schools.find((s) => s.id === params.schoolId) ?? null);
    } catch {
      /* the header still works without this */
    }
    try {
      setKeys(await api.listStaffKeys(key, params.schoolId));
    } catch {
      /* principal/teachers tabs show their own load error state */
    }
    try {
      setStudents(await api.listPlatformStudents(key, params.schoolId));
    } catch {
      /* students tab shows its own load error state */
    }
    try {
      setActivity(await api.listActivity(key, params.schoolId));
    } catch {
      /* activity tab shows its own load error state */
    }
    try {
      setChecklist(await api.onboardingChecklist(key, params.schoolId));
    } catch {
      /* overview KPIs/checklist just fall back to what overviewRow already covers */
    }
  }, [params.schoolId]);

  useEffect(() => {
    void load();
  }, [load]);

  function describe(err: unknown, fallback: string): string {
    if (err instanceof ApiError && err.status === 409) return "That name is already taken.";
    return fallback;
  }

  async function toggleDirectoryVisibility() {
    const key = getPlatformKey();
    if (!key || !school) return;
    try {
      const updated = await api.setDirectoryVisibility(key, school.id, !school.hidden_from_directory);
      setSchool(updated);
      show(updated.hidden_from_directory ? "Hidden from the public directory." : "Now visible on the public directory.");
    } catch {
      setError("Could not change this school's directory visibility.");
    }
  }

  async function addSection() {
    const key = getPlatformKey();
    if (!key || !school) return;
    const spec = window.prompt(`Add a class to ${school.name} (e.g. 10-C)`, "10-C");
    if (!spec) return;
    const [grade, name] = spec.split("-");
    try {
      await api.addSection(key, school.id, { grade: Number(grade), name: (name ?? "").toUpperCase() });
      show("Class added.");
      await load();
    } catch (err) {
      setError(describe(err, "Could not add the class."));
    }
  }

  async function rotate() {
    const key = getPlatformKey();
    if (!key || !school) return;
    const ok = window.confirm(
      `Issue a new key for ${school.name}? The school's current key stops working immediately and whoever holds it will have to sign in again.`,
    );
    if (!ok) return;
    try {
      const result = await api.rotateKey(key, school.id);
      setIssued({ label: `${school.name}'s own key`, api_key: result.api_key, notice: result.api_key_notice });
      await load();
    } catch {
      setError("Could not rotate the key.");
    }
  }

  async function saveSchoolDetails(patch: {
    name: string; board: string; state: string; code: string; city: string; address: string; academic_year: string;
  }): Promise<boolean> {
    const key = getPlatformKey();
    if (!key || !school) return false;
    try {
      const updated = await api.patchSchool(key, school.id, patch);
      setSchool(updated);
      show("School details saved.");
      await load();
      return true;
    } catch (err) {
      setError(describe(err, "Could not save school details."));
      return false;
    }
  }

  async function issueKey(role: "principal" | "teacher", label: string, examCell = false) {
    const key = getPlatformKey();
    if (!key || !school) return;
    try {
      const created = await api.issueStaffKey(key, school.id, role, label, examCell);
      setIssued({ label: `${school.name}, ${role} key`, api_key: created.api_key, notice: created.api_key_notice });
      setKeys(await api.listStaffKeys(key, school.id));
      flash(created.id);
    } catch (err) {
      setError(describe(err, "Could not issue the key."));
    }
  }

  async function revokeKey(entry: StaffKeySummary) {
    const key = getPlatformKey();
    if (!key || !school) return;
    if (!window.confirm(`Revoke the ${entry.role} key${entry.label ? ` for ${entry.label}` : ""}? They are signed out immediately.`)) return;
    try {
      await api.revokeStaffKey(key, school.id, entry.id);
      setKeys(await api.listStaffKeys(key, school.id));
      show("Key revoked.");
    } catch (err) {
      setError(describe(err, "Could not revoke the key."));
    }
  }

  async function changeStaffKey(entry: StaffKeySummary) {
    const key = getPlatformKey();
    if (!key || !school) return;
    const ok = window.confirm(
      `Issue a new key for ${entry.name || entry.label || "this person"}? Their current key stops working immediately.`,
    );
    if (!ok) return;
    try {
      const result = await api.rotateStaffKey(key, school.id, entry.id);
      setIssued({
        label: `${entry.name || entry.label || entry.role}'s key`,
        api_key: result.api_key,
        notice: result.api_key_notice,
      });
      setKeys(await api.listStaffKeys(key, school.id));
    } catch (err) {
      setError(describe(err, "Could not change this key."));
    }
  }

  async function saveKeyContact(entry: StaffKeySummary, patch: { name: string; email: string; phone: string }): Promise<boolean> {
    const key = getPlatformKey();
    if (!key || !school) return false;
    try {
      await api.patchStaffKey(key, school.id, entry.id, patch);
      setKeys(await api.listStaffKeys(key, school.id));
      show("Contact details saved.");
      flash(entry.id);
      return true;
    } catch (err) {
      setError(describe(err, "Could not save contact details."));
      return false;
    }
  }

  async function saveAssignments(entry: StaffKeySummary, assignments: TeacherAssignmentInput[]): Promise<boolean> {
    const key = getPlatformKey();
    if (!key || !school) return false;
    try {
      await api.setAssignments(key, school.id, entry.id, assignments);
      show("Access updated.");
      flash(entry.id);
      return true;
    } catch (err) {
      setError(describe(err, "Could not update access."));
      return false;
    }
  }

  async function bulkAddStudents(rows: StudentBulkInput[]): Promise<boolean> {
    const key = getPlatformKey();
    if (!key || !school) return false;
    try {
      await api.bulkAddStudents(key, school.id, rows);
      show(`${rows.length} student${rows.length === 1 ? "" : "s"} added.`);
      await load();
      return true;
    } catch (err) {
      setError(describe(err, "Could not add students."));
      return false;
    }
  }

  if (school === undefined) {
    return <p className="muted small" style={{ marginTop: 24 }}>Loading…</p>;
  }

  if (school === null) {
    return (
      <div className="placeholder" style={{ marginTop: 24 }}>
        <p>No account with that id.</p>
        <Link href="/admin/schools" className="btn btn--sm" style={{ marginTop: 12 }}>
          <ArrowLeft size={13} /> Back to the portfolio
        </Link>
      </div>
    );
  }

  const principal = keys.find((k) => k.role === "principal" && !k.revoked_at) ?? keys.find((k) => k.role === "principal");
  const teacherKeys = keys.filter((k) => k.role === "teacher");
  const activeTeachers = teacherKeys.filter((k) => !k.revoked_at).length;

  return (
    <>
      <Link href="/admin/schools" className="btn btn--ghost btn--sm" style={{ marginBottom: 12 }}>
        <ArrowLeft size={13} /> All accounts
      </Link>

      <header className="surface surface--raised" style={{ padding: "18px 22px" }}>
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "flex-start", justifyContent: "space-between" }}>
          <div style={{ minWidth: 240, flex: "1 1 340px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <h1 style={{ fontSize: 22, letterSpacing: "-.01em" }}>{school.name}</h1>
              <span className={`tag ${school.hidden_from_directory ? "tag--risk" : "tag--teal"}`}>
                {school.hidden_from_directory ? "Hidden from directory" : "Visible on directory"}
              </span>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              {school.code && <span className="tag mono">{school.code}</span>}
              <span className="tag">{school.board}</span>
              <span className="tag">{[school.city, school.state].filter(Boolean).join(", ") || "—"}</span>
              <span className="tag tag--info">{school.students} students</span>
              {school.sections.map((s) => (
                <span key={s.id} className="tag">{s.grade}{s.name}</span>
              ))}
            </div>
          </div>
          {principal && (
            <div style={{ textAlign: "right", minWidth: 200 }}>
              <p className="eyebrow">Principal</p>
              <p className="strong">{principal.name || principal.label || "—"}</p>
              {principal.email && <p className="small muted">{principal.email}</p>}
              {principal.phone && <p className="small muted">{principal.phone}</p>}
            </div>
          )}
        </div>
      </header>

      <div className="tabs ops-tabs" role="tablist" style={{ marginTop: 16 }}>
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} className={`tab ${tab === t.key ? "tab--active" : ""}`} onClick={() => setTab(t.key)}>
            {t.label}
            {t.key === "teachers" && ` (${teacherKeys.length})`}
            {t.key === "students" && ` (${students.length})`}
          </button>
        ))}
      </div>

      {error && (
        <div className="evidence evidence--gold" style={{ marginTop: 16 }}>
          <div>{error}</div>
        </div>
      )}

      {issued && (
        <div className="card" style={{ marginTop: 16, borderLeft: "3px solid var(--brand-teal)" }}>
          <div className="card__body">
            <p className="eyebrow">New key for {issued.label}</p>
            <h2 className="section-q">Copy this now</h2>
            <p className="muted small" style={{ marginBottom: 14 }}>{issued.notice}</p>
            <CopySecret value={issued.api_key} />
            <button className="btn btn--ghost btn--sm" style={{ marginTop: 14 }} onClick={() => setIssued(null)}>
              I have saved it
            </button>
          </div>
        </div>
      )}

      <div style={{ marginTop: 16 }}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.22, ease: EASE_OUT }}
          >
            {tab === "overview" && (
              <OverviewTab
                school={school}
                overviewRow={overviewRow}
                activeTeachers={activeTeachers}
                checklist={checklist}
                lastActivity={activity[0]}
                onAddSection={addSection}
                onToggleDirectory={toggleDirectoryVisibility}
                onRotate={rotate}
              />
            )}
            {tab === "details" && <SchoolDetailsTab school={school} onSave={saveSchoolDetails} />}
            {tab === "principal" && (
              <PrincipalTab
                principal={principal}
                schoolCode={school.code}
                schoolName={school.name}
                flashIds={flashIds}
                onIssue={(label) => issueKey("principal", label)}
                onRevoke={revokeKey}
                onSaveContact={saveKeyContact}
                onChangeKey={changeStaffKey}
              />
            )}
            {tab === "teachers" && (
              <TeachersTab
                teachers={teacherKeys}
                sections={school.sections}
                schoolCode={school.code}
                flashIds={flashIds}
                onIssue={(label, examCell) => issueKey("teacher", label, examCell)}
                onRevoke={revokeKey}
                onSaveContact={saveKeyContact}
                onSaveAssignments={saveAssignments}
                onChangeKey={changeStaffKey}
              />
            )}
            {tab === "students" && (
              <StudentsTab school={school} students={students} onBulkAdd={bulkAddStudents} />
            )}

            {tab === "activity" && <ActivityTab rows={activity} />}
          </motion.div>
        </AnimatePresence>
      </div>

      <Toast message={message} />
    </>
  );
}

function OverviewTab({
  school,
  overviewRow,
  activeTeachers,
  checklist,
  lastActivity,
  onAddSection,
  onToggleDirectory,
  onRotate,
}: {
  school: PlatformSchool;
  overviewRow: PlatformOverview["schools"][number] | null;
  activeTeachers: number;
  checklist: OnboardingChecklist | null;
  lastActivity: AuditLogRow | undefined;
  onAddSection: () => void;
  onToggleDirectory: () => void;
  onRotate: () => void;
}) {
  const enrolled = checklist?.students_enrolled ?? school.students;
  const onboarded = checklist?.students_onboarded_count ?? 0;
  const teachersWithAccess = checklist?.teachers_with_access ?? activeTeachers;
  const teachersActivated = checklist?.teachers_activated ?? 0;
  const papersUploaded = checklist?.papers_uploaded_count ?? overviewRow?.papers ?? 0;
  const assessmentsCount = checklist?.assessments_count ?? 0;

  const kpis = [
    {
      label: "Students onboarded",
      value: onboarded,
      sub: `of ${enrolled} enrolled`,
      accent: "var(--brand-blue)",
      icon: Users,
    },
    {
      label: "Teachers activated",
      value: teachersActivated,
      sub: `of ${teachersWithAccess} with access`,
      accent: "var(--brand-gold)",
      icon: KeyRound,
    },
    {
      label: "Onboarding",
      value: checklist?.percent ?? 0,
      suffix: "%",
      sub: checklist ? `${checklist.done_count} of ${checklist.total_steps} steps done` : "loading…",
      accent: "var(--brand-teal)",
      icon: ListChecks,
    },
    {
      label: "Tests conducted",
      value: assessmentsCount,
      sub: `${papersUploaded} of ${assessmentsCount} papers uploaded`,
      accent: "var(--brand-green)",
      icon: FileCheck2,
    },
  ];
  return (
    <>
      <Stagger className="grid grid--4" gap={0.05}>
        {kpis.map((k, i) => {
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
                    <CountUp value={k.value} delay={0.1 + i * 0.05} />
                    {k.suffix}
                  </div>
                  <div className="kpi__sub">{k.sub}</div>
                </div>
              </div>
            </StaggerItem>
          );
        })}
      </Stagger>

      <section className="card card--hover" style={{ marginTop: 16 }}>
        <div className="card__body">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
            <h2 style={{ fontSize: 15 }}>Onboarding checklist</h2>
            {lastActivity?.created_at && (
              <span className="small muted">
                Last activity {new Date(lastActivity.created_at).toLocaleString()}
              </span>
            )}
          </div>
          {!checklist ? (
            <p className="small muted" style={{ marginTop: 10 }}>Loading…</p>
          ) : (
            <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
              {checklist.steps.map((s) => (
                <div key={s.key} className="ops-list__row">
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    {s.done ? (
                      <CheckCircle2 size={16} color="var(--brand-teal)" />
                    ) : (
                      <Circle size={16} className="muted" />
                    )}
                    <span className={s.done ? "strong" : ""}>{s.label}</span>
                  </div>
                  <div className="small muted">
                    {s.done && s.at ? new Date(s.at).toLocaleDateString() : "Not started"}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <div className="card__body">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
            <h2 style={{ fontSize: 15 }}>Classes and sign-in links</h2>
            <button type="button" className="btn btn--ghost btn--sm" onClick={onAddSection}>
              <Plus size={13} /> Add a class
            </button>
          </div>
          {school.sections.length === 0 ? (
            <OpsEmpty>No classes yet.</OpsEmpty>
          ) : (
            <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
              {school.sections.map((section) => (
                <div key={section.id} className="ops-list__row">
                  <div>
                    <span className="strong">{section.label}</span>
                    <div className="small mono muted" style={{ marginTop: 2 }}>{section.student_path}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
          <p className="small" style={{ marginTop: 16 }}>
            Public directory: <strong>{school.hidden_from_directory ? "Hidden" : "Visible"}</strong>{" "}
            <button type="button" className="btn btn--ghost btn--sm" onClick={onToggleDirectory}>
              {school.hidden_from_directory ? <Eye size={12} /> : <EyeOff size={12} />}
              {school.hidden_from_directory ? "Show on /t" : "Hide from /t"}
            </button>
          </p>
        </div>
        <div className="card__foot" style={{ justifyContent: "flex-end" }}>
          <button className="btn btn--ghost btn--sm" onClick={onRotate}>
            <RefreshCw size={13} /> Rotate the school&rsquo;s own key
          </button>
        </div>
      </section>
    </>
  );
}

function SchoolDetailsTab({
  school,
  onSave,
}: {
  school: PlatformSchool;
  onSave: (patch: { name: string; board: string; state: string; code: string; city: string; address: string; academic_year: string }) => Promise<boolean>;
}) {
  const { state: saveState, run } = useSaveState();
  const [name, setName] = useState(school.name);
  const [board, setBoard] = useState(school.board);
  const [state, setState] = useState(school.state ?? "");
  const [code, setCode] = useState(school.code ?? "");
  const [city, setCity] = useState(school.city ?? "");
  const [address, setAddress] = useState(school.address ?? "");
  const [academicYear, setAcademicYear] = useState(school.academic_year ?? "");

  useEffect(() => {
    setName(school.name);
    setBoard(school.board);
    setState(school.state ?? "");
    setCode(school.code ?? "");
    setCity(school.city ?? "");
    setAddress(school.address ?? "");
    setAcademicYear(school.academic_year ?? "");
  }, [school]);

  return (
    <section className="card">
      <div className="card__body" style={{ display: "grid", gap: 14, maxWidth: 640 }}>
        <label className="field">
          <span className="field__label">School name</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
          <label className="field">
            <span className="field__label">School code</span>
            <input className="input" value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. BISS-TN" />
          </label>
          <label className="field">
            <span className="field__label">Board</span>
            <input className="input" value={board} onChange={(e) => setBoard(e.target.value)} />
          </label>
          <label className="field">
            <span className="field__label">City</span>
            <input className="input" value={city} onChange={(e) => setCity(e.target.value)} />
          </label>
        </div>
        <label className="field">
          <span className="field__label">State</span>
          <input className="input" value={state} onChange={(e) => setState(e.target.value)} />
        </label>
        <label className="field">
          <span className="field__label">Address</span>
          <input className="input" value={address} onChange={(e) => setAddress(e.target.value)} />
        </label>
        <label className="field">
          <span className="field__label">Academic year</span>
          <input className="input" value={academicYear} onChange={(e) => setAcademicYear(e.target.value)} placeholder="e.g. 2026-27" />
        </label>
        <p className="small muted">
          Classes: {school.sections.map((s) => s.label).join(", ") || "none yet"}. Add a class from the Overview tab.
        </p>
      </div>
      <div className="card__foot" style={{ justifyContent: "flex-end" }}>
        <SaveButton
          state={saveState}
          onClick={() => run(() => onSave({ name, board, state, code, city, address, academic_year: academicYear }))}
        >
          Save changes
        </SaveButton>
      </div>
    </section>
  );
}

function ContactFields({
  name, email, phone, setName, setEmail, setPhone,
}: {
  name: string; email: string; phone: string;
  setName: (v: string) => void; setEmail: (v: string) => void; setPhone: (v: string) => void;
}) {
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <label className="field">
        <span className="field__label">Full name</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="field">
        <span className="field__label">Email</span>
        <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <label className="field">
        <span className="field__label">Mobile / WhatsApp</span>
        <input className="input" value={phone} onChange={(e) => setPhone(e.target.value)} />
      </label>
    </div>
  );
}

function ResendLink({ entry, schoolCode }: { entry: StaffKeySummary; schoolCode: string | null }) {
  if (entry.revoked_at) return null;
  const text = `Hi ${entry.name || entry.label || "there"}, here's your Yaadhum login -- school code ${schoolCode ?? "—"}, key: ${entry.api_key}`;
  const mailHref = entry.email
    ? `mailto:${encodeURIComponent(entry.email)}?subject=${encodeURIComponent("Your Yaadhum login")}&body=${encodeURIComponent(text)}`
    : null;
  const waHref = entry.phone
    ? `https://wa.me/${entry.phone.replace(/[^\d]/g, "")}?text=${encodeURIComponent(text)}`
    : null;
  if (!mailHref && !waHref) return null;
  return (
    <a
      className="btn btn--ghost btn--sm"
      href={waHref ?? mailHref ?? "#"}
      target="_blank"
      rel="noreferrer"
      title="Opens a prefilled message with their real key -- you send it yourself"
    >
      <Send size={13} /> Resend
    </a>
  );
}

function PrincipalTab({
  principal,
  schoolCode,
  schoolName,
  flashIds,
  onIssue,
  onRevoke,
  onSaveContact,
  onChangeKey,
}: {
  principal: StaffKeySummary | undefined;
  schoolCode: string | null;
  schoolName: string;
  flashIds: Set<string>;
  onIssue: (label: string) => void;
  onRevoke: (entry: StaffKeySummary) => void;
  onSaveContact: (entry: StaffKeySummary, patch: { name: string; email: string; phone: string }) => Promise<boolean>;
  onChangeKey: (entry: StaffKeySummary) => void;
}) {
  const { state: saveState, run } = useSaveState();
  const [name, setName] = useState(principal?.name ?? "");
  const [email, setEmail] = useState(principal?.email ?? "");
  const [phone, setPhone] = useState(principal?.phone ?? "");

  useEffect(() => {
    setName(principal?.name ?? "");
    setEmail(principal?.email ?? "");
    setPhone(principal?.phone ?? "");
  }, [principal]);

  if (!principal) {
    return (
      <section className="card">
        <div className="card__body">
          <OpsEmpty>No principal key issued yet for {schoolName}.</OpsEmpty>
        </div>
        <div className="card__foot" style={{ justifyContent: "flex-end" }}>
          <button
            className="btn btn--sm"
            onClick={() => {
              const label = window.prompt("Principal's name, for this key's label", "");
              if (label !== null) onIssue(label);
            }}
          >
            <KeyRound size={13} /> Issue a principal key
          </button>
        </div>
      </section>
    );
  }

  const flashed = flashIds.has(principal.id);
  return (
    <div className="grid grid--2" style={{ gap: 16, alignItems: "start" }}>
      <section className={`card ${flashed ? "row-flash" : ""}`}>
        <div className="card__body">
          <h2 style={{ fontSize: 15 }}>Principal&rsquo;s details</h2>
          <div style={{ marginTop: 12 }}>
            <ContactFields name={name} email={email} phone={phone} setName={setName} setEmail={setEmail} setPhone={setPhone} />
          </div>
        </div>
        <div className="card__foot" style={{ justifyContent: "flex-end" }}>
          <SaveButton state={saveState} onClick={() => run(() => onSaveContact(principal, { name, email, phone }))}>
            Save principal
          </SaveButton>
        </div>
      </section>
      <section className="card">
        <div className="card__body">
          <h2 style={{ fontSize: 15 }}>Principal login</h2>
          <p className="small muted" style={{ marginTop: 4 }}>Sees every section and subject for this school.</p>
          <p className="small" style={{ marginTop: 8 }}>
            School code: <span className="tag mono">{schoolCode || "—"}</span>
          </p>
          {principal.revoked_at ? (
            <p className="small muted" style={{ marginTop: 10 }}>Revoked. Issue a new key below.</p>
          ) : (
            <div style={{ marginTop: 10 }}>
              <CopySecret value={principal.api_key} />
              <p className="small muted" style={{ marginTop: 6 }}>
                Last used: {principal.last_used_at ? new Date(principal.last_used_at).toLocaleString() : "never"}
                {principal.credential_changed_at && ` · Password set by the principal on ${new Date(principal.credential_changed_at).toLocaleString()}`}
              </p>
            </div>
          )}
        </div>
        <div className="card__foot" style={{ justifyContent: "flex-end", gap: 8 }}>
          <ResendLink entry={principal} schoolCode={schoolCode} />
          {!principal.revoked_at && (
            <button className="btn btn--ghost btn--sm" onClick={() => onRevoke(principal)}>
              Revoke
            </button>
          )}
          {!principal.revoked_at && (
            <button className="btn btn--ghost btn--sm" onClick={() => onChangeKey(principal)}>
              <RefreshCw size={13} /> Change key
            </button>
          )}
          <button
            className="btn btn--ghost btn--sm"
            onClick={() => {
              const label = window.prompt("Principal's name, for the new key's label", principal.label);
              if (label !== null) onIssue(label);
            }}
          >
            Issue new key
          </button>
        </div>
      </section>
    </div>
  );
}

function TeachersTab({
  teachers,
  sections,
  schoolCode,
  flashIds,
  onIssue,
  onRevoke,
  onSaveContact,
  onSaveAssignments,
  onChangeKey,
}: {
  teachers: StaffKeySummary[];
  sections: PlatformSchool["sections"];
  schoolCode: string | null;
  flashIds: Set<string>;
  onIssue: (label: string, examCell: boolean) => void;
  onRevoke: (entry: StaffKeySummary) => void;
  onSaveContact: (entry: StaffKeySummary, patch: { name: string; email: string; phone: string }) => Promise<boolean>;
  onSaveAssignments: (entry: StaffKeySummary, assignments: TeacherAssignmentInput[]) => Promise<boolean>;
  onChangeKey: (entry: StaffKeySummary) => void;
}) {
  const [search, setSearch] = useState("");
  const filtered = teachers.filter((t) => {
    if (!search.trim()) return true;
    const q = search.trim().toLowerCase();
    return [t.name, t.label, t.email, t.phone].filter(Boolean).some((v) => v!.toLowerCase().includes(q));
  });

  // The real subject_code list this deployment carries, fetched once here rather than
  // per row -- so "Add subject" below can offer an actual pick list instead of the free
  // text a typo in could never match what create_assessment checks a teacher's own
  // assignments against.
  const [subjects, setSubjects] = useState<{ subject_code: string; label: string }[]>([]);
  useEffect(() => {
    const key = getPlatformKey();
    if (!key) return;
    api
      .platformSubjects(key)
      .then((r) => setSubjects(r.subjects))
      .catch(() => {
        /* the row below falls back to a plain text prompt if this never loads */
      });
  }, []);

  return (
    <section className="card">
      <div className="card__body">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div>
            <h2 style={{ fontSize: 15 }}>Teachers and their access</h2>
            <p className="small muted" style={{ marginTop: 4 }}>
              Each teacher only sees the classes and subjects assigned to them. Changes here apply to this
              school&rsquo;s teacher logins straight away.
            </p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              className="btn btn--sm"
              onClick={() => {
                const label = window.prompt("Teacher's name, for this key's label", "");
                if (label !== null) onIssue(label, false);
              }}
            >
              <UserPlus size={13} /> Add teacher
            </button>
            <button
              type="button"
              className="btn btn--sm"
              title="Papers-and-marks rights across every subject, no class or subject of their own -- the exam cell"
              onClick={() => {
                const label = window.prompt("Exam cell key: whose name is this for?", "");
                if (label !== null) onIssue(label, true);
              }}
            >
              <UserPlus size={13} /> Add exam-cell key
            </button>
          </div>
        </div>

        <input
          className="input"
          style={{ marginTop: 12, maxWidth: 320 }}
          placeholder="Search teachers…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        {teachers.length === 0 ? (
          <OpsEmpty>No teacher keys issued yet.</OpsEmpty>
        ) : filtered.length === 0 ? (
          <OpsEmpty>No teacher matches &ldquo;{search}&rdquo;.</OpsEmpty>
        ) : (
          <div style={{ display: "grid", gap: 12, marginTop: 14 }}>
            {filtered.map((t) => (
              <TeacherRow
                key={t.id}
                entry={t}
                sections={sections}
                subjects={subjects}
                schoolCode={schoolCode}
                flashed={flashIds.has(t.id)}
                onRevoke={onRevoke}
                onSaveContact={onSaveContact}
                onSaveAssignments={onSaveAssignments}
                onChangeKey={onChangeKey}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function TeacherRow({
  entry,
  sections,
  subjects,
  schoolCode,
  flashed,
  onRevoke,
  onSaveContact,
  onSaveAssignments,
  onChangeKey,
}: {
  entry: StaffKeySummary;
  sections: PlatformSchool["sections"];
  subjects: { subject_code: string; label: string }[];
  schoolCode: string | null;
  flashed: boolean;
  onRevoke: (entry: StaffKeySummary) => void;
  onSaveContact: (entry: StaffKeySummary, patch: { name: string; email: string; phone: string }) => Promise<boolean>;
  onSaveAssignments: (entry: StaffKeySummary, assignments: TeacherAssignmentInput[]) => Promise<boolean>;
  onChangeKey: (entry: StaffKeySummary) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [name, setName] = useState(entry.name ?? "");
  const [email, setEmail] = useState(entry.email ?? "");
  const [phone, setPhone] = useState(entry.phone ?? "");
  const [assignments, setAssignments] = useState<TeacherAssignmentRow[]>([]);
  const [loadedAssignments, setLoadedAssignments] = useState(false);
  const { state: contactSaveState, run: runContactSave } = useSaveState();
  const { state: assignSaveState, run: runAssignSave } = useSaveState();

  const loadAssignments = useCallback(async () => {
    const key = getPlatformKey();
    if (!key || !entry.school_id) return;
    try {
      const rows = await api.listAssignments(key, entry.school_id, entry.id);
      setAssignments(rows);
      setLoadedAssignments(true);
    } catch {
      /* the row just stays without an assignment list */
    }
  }, [entry.id, entry.school_id]);

  // Loaded eagerly (not only on expand) so the summary line below is always real,
  // not only visible once someone opens "Edit access".
  useEffect(() => {
    void loadAssignments();
  }, [loadAssignments]);

  function toggle() {
    setExpanded((e) => !e);
  }

  function toggleSectionClass(sectionId: string) {
    setAssignments((prev) => {
      const exists = prev.some((a) => a.type === "class" && a.section_id === sectionId);
      if (exists) return prev.filter((a) => !(a.type === "class" && a.section_id === sectionId));
      return [...prev, { id: `new-${sectionId}`, staff_key_id: entry.id, type: "class", section_id: sectionId, subject_code: null }];
    });
  }

  function addSubject() {
    const sectionId = sections[0]?.id;
    if (!sectionId || subjects.length === 0) return;
    // A real subject_code from the deployment's own curriculum, not free text -- picking
    // whichever one isn't already assigned yet is just a sane starting point; the row's
    // own dropdown below is what actually decides it, exactly like section already works.
    const already = new Set(assignments.filter((a) => a.type === "subject").map((a) => a.subject_code));
    const first = subjects.find((s) => !already.has(s.subject_code)) ?? subjects[0];
    setAssignments((prev) => [
      ...prev,
      { id: `new-subj-${Date.now()}`, staff_key_id: entry.id, type: "subject", section_id: sectionId, subject_code: first.subject_code },
    ]);
  }

  function updateSubjectCode(assignmentId: string, subjectCode: string) {
    setAssignments((prev) => prev.map((a) => (a.id === assignmentId ? { ...a, subject_code: subjectCode } : a)));
  }

  function updateSubjectSection(assignmentId: string, sectionId: string) {
    setAssignments((prev) => prev.map((a) => (a.id === assignmentId ? { ...a, section_id: sectionId } : a)));
  }

  function removeAssignment(assignmentId: string) {
    setAssignments((prev) => prev.filter((a) => a.id !== assignmentId));
  }

  const classAssignments = assignments.filter((a) => a.type === "class");
  const subjectAssignments = assignments.filter((a) => a.type === "subject");

  // "Mathematics (10A) · Social Science (10A, 10B)" -- one entry per subject code,
  // every section it covers grouped into that one entry, in the order first seen.
  const sectionLabel = (id: string) => sections.find((s) => s.id === id)?.label ?? id;
  const bySubject = new Map<string, string[]>();
  for (const a of subjectAssignments) {
    if (!a.subject_code) continue;
    const list = bySubject.get(a.subject_code) ?? [];
    list.push(sectionLabel(a.section_id));
    bySubject.set(a.subject_code, list);
  }
  const subjectSummary = Array.from(bySubject.entries())
    .map(([code, secs]) => `${code} (${secs.join(", ")})`)
    .join(" · ");
  const classSummary = classAssignments.length > 0
    ? `Class teacher ${classAssignments.map((a) => sectionLabel(a.section_id)).join(", ")}`
    : "";
  const summaryLine = [classSummary, subjectSummary].filter(Boolean).join(" · ");

  const statusTag = entry.revoked_at
    ? null
    : entry.exam_cell
      ? { label: "Exam cell", className: "tag" }
      : entry.last_used_at
        ? { label: "Active", className: "tag tag--teal" }
        : { label: "Key not used yet", className: "tag tag--gold" };

  return (
    <div
      className={`ops-list__row card--hover ${flashed ? "row-flash" : ""}`}
      style={{ flexDirection: "column", alignItems: "stretch", gap: 10, opacity: entry.revoked_at ? 0.55 : 1 }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <div>
          <span className="strong">{entry.name || entry.label || "Unnamed teacher"}</span>
          {statusTag && <span className={statusTag.className} style={{ marginLeft: 8 }}>{statusTag.label}</span>}
          {entry.revoked_at && <span className="tag tag--risk" style={{ marginLeft: 8 }}>Revoked</span>}
          <div className="small muted" style={{ marginTop: 2 }}>
            {[entry.phone, entry.email].filter(Boolean).join(" · ") || "No contact details on file"}
          </div>
          {loadedAssignments && summaryLine && (
            <div className="small muted" style={{ marginTop: 2 }}>{summaryLine}</div>
          )}
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <button className="btn btn--ghost btn--sm" onClick={toggle}>
            <ListChecks size={13} /> {expanded ? "Hide access" : "Edit access"}
          </button>
          {!entry.revoked_at && (
            <button className="btn btn--ghost btn--sm" onClick={() => onChangeKey(entry)}>
              <RefreshCw size={13} /> Change key
            </button>
          )}
          <ResendLink entry={entry} schoolCode={schoolCode} />
          {!entry.revoked_at && (
            <button className="btn btn--ghost btn--sm" onClick={() => onRevoke(entry)}>
              Turn off
            </button>
          )}
        </div>
      </div>

      {!entry.revoked_at && <CopySecret value={entry.api_key} />}

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.24, ease: EASE_OUT }}
            style={{ overflow: "hidden" }}
          >
        <div className="surface" style={{ padding: 14, display: "grid", gap: 14 }}>
          <ContactFields name={name} email={email} phone={phone} setName={setName} setEmail={setEmail} setPhone={setPhone} />
          <SaveButton
            state={contactSaveState}
            className="btn btn--ghost btn--sm"
            onClick={() => runContactSave(() => onSaveContact(entry, { name, email, phone }))}
          >
            Save contact details
          </SaveButton>

          <div>
            <p className="field__label">Class teacher for</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 6 }}>
              {sections.map((s) => (
                <label key={s.id} className="small" style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <input
                    type="checkbox"
                    checked={classAssignments.some((a) => a.section_id === s.id)}
                    onChange={() => toggleSectionClass(s.id)}
                  />
                  {s.label}
                </label>
              ))}
            </div>
          </div>

          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <p className="field__label">Subjects taught</p>
              <button className="btn btn--ghost btn--sm" onClick={addSubject}>
                <Plus size={12} /> Add subject
              </button>
            </div>
            {subjectAssignments.length === 0 ? (
              <p className="small muted" style={{ marginTop: 4 }}>None yet.</p>
            ) : (
              <div style={{ display: "grid", gap: 6, marginTop: 6 }}>
                {subjectAssignments.map((a) => (
                  <div key={a.id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <select className="input" style={{ maxWidth: 200 }} value={a.subject_code ?? ""} onChange={(e) => updateSubjectCode(a.id, e.target.value)}>
                      {/* A stored code from before this picker existed may not match any
                         real subject_code any more -- keep it selectable rather than
                         silently swap it out for something the admin never chose. */}
                      {a.subject_code && !subjects.some((s) => s.subject_code === a.subject_code) && (
                        <option value={a.subject_code}>{a.subject_code} (unrecognised)</option>
                      )}
                      {subjects.map((s) => (
                        <option key={s.subject_code} value={s.subject_code}>{s.label}</option>
                      ))}
                    </select>
                    <select className="input" style={{ maxWidth: 160 }} value={a.section_id} onChange={(e) => updateSubjectSection(a.id, e.target.value)}>
                      {sections.map((s) => (
                        <option key={s.id} value={s.id}>{s.label}</option>
                      ))}
                    </select>
                    <button className="btn btn--ghost btn--sm" onClick={() => removeAssignment(a.id)}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <SaveButton
            state={assignSaveState}
            className="btn btn--sm"
            onClick={() =>
              runAssignSave(() =>
                onSaveAssignments(
                  entry,
                  assignments.map((a) => ({ type: a.type, section_id: a.section_id, subject_code: a.subject_code })),
                ),
              )
            }
          >
            Save access
          </SaveButton>
        </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function StudentsTab({
  school,
  students,
  onBulkAdd,
}: {
  school: PlatformSchool;
  students: PlatformStudentRow[];
  onBulkAdd: (rows: StudentBulkInput[]) => Promise<boolean>;
}) {
  const [activeSection, setActiveSection] = useState(school.sections[0]?.id ?? "");
  const [draft, setDraft] = useState<StudentBulkInput[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(true);
  const [justAdded, setJustAdded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!activeSection && school.sections[0]) setActiveSection(school.sections[0].id);
  }, [school.sections, activeSection]);

  const filtered = students.filter((s) => s.section_id === activeSection);
  const withWhatsapp = students.filter((s) => s.parent_whatsapp).length;

  function addRow() {
    setDraft((d) => [...d, { name: "", roll_no: "", section_id: activeSection }]);
    setSaved(false);
  }

  function updateRow(i: number, patch: Partial<StudentBulkInput>) {
    setDraft((d) => d.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
    setSaved(false);
  }

  function removeRow(i: number) {
    setDraft((d) => d.filter((_, idx) => idx !== i));
  }

  function discard() {
    setDraft([]);
    setSaved(true);
  }

  async function submit() {
    const rows = draft.filter((r) => r.name.trim() && r.roll_no.trim());
    if (rows.length === 0) return;
    setSaving(true);
    // "All changes saved" is only ever shown once this call has actually returned 200 --
    // never claimed instantly on click.
    const ok = await onBulkAdd(rows);
    setSaving(false);
    if (ok) {
      setDraft([]);
      setSaved(true);
      const keys = new Set(rows.map((r) => `${r.section_id}::${r.roll_no.trim()}`));
      setJustAdded(keys);
      setTimeout(() => setJustAdded(new Set()), 1700);
    }
  }

  return (
    <section className="card">
      <div className="card__body">
        <h2 style={{ fontSize: 15 }}>Students and parent WhatsApp numbers</h2>
        <p className="small muted" style={{ marginTop: 4 }}>
          {students.length} on roll · {withWhatsapp} WhatsApp number{withWhatsapp === 1 ? "" : "s"} on file
        </p>

        <div className="tabs" style={{ marginTop: 12 }}>
          {school.sections.map((s) => (
            <button
              key={s.id}
              className={`tab ${activeSection === s.id ? "tab--active" : ""}`}
              onClick={() => setActiveSection(s.id)}
            >
              {s.label} ({students.filter((st) => st.section_id === s.id).length})
            </button>
          ))}
        </div>

        {filtered.length === 0 ? (
          <OpsEmpty>No students in this class yet.</OpsEmpty>
        ) : (
          <div className="table-wrap table-wrap--scroll" style={{ marginTop: 12 }}>
            <table className="table table--hover">
              <thead>
                <tr>
                  <th>Roll</th>
                  <th>Student name</th>
                  <th>Parent name</th>
                  <th>Parent WhatsApp</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <tr key={s.id} className={justAdded.has(`${s.section_id}::${s.roll_no}`) ? "row-flash" : ""}>
                    <td className="mono">{s.roll_no}</td>
                    <td>{s.name}</td>
                    <td>{s.parent_name || "—"}</td>
                    <td className="mono">{s.parent_whatsapp || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div style={{ marginTop: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <p className="field__label">Add students to {school.sections.find((s) => s.id === activeSection)?.label ?? "this class"}</p>
            <button className="btn btn--ghost btn--sm" onClick={addRow}>
              <Plus size={12} /> Add row
            </button>
          </div>
          {draft.length > 0 && (
            <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
              {draft.map((row, i) => (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "80px 1fr 1fr 1fr 32px", gap: 8 }}>
                  <input className="input" placeholder="Roll" value={row.roll_no} onChange={(e) => updateRow(i, { roll_no: e.target.value })} />
                  <input className="input" placeholder="Student name" value={row.name} onChange={(e) => updateRow(i, { name: e.target.value })} />
                  <input className="input" placeholder="Parent name" value={row.parent_name ?? ""} onChange={(e) => updateRow(i, { parent_name: e.target.value })} />
                  <input className="input" placeholder="Parent WhatsApp" value={row.parent_whatsapp ?? ""} onChange={(e) => updateRow(i, { parent_whatsapp: e.target.value })} />
                  <button className="btn btn--ghost btn--sm" onClick={() => removeRow(i)}>
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="card__foot" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <span className="small muted">
          {saved ? "All changes saved" : saving ? "Saving…" : "Unsaved changes"}
        </span>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn--ghost btn--sm" disabled={draft.length === 0 || saving} onClick={discard}>
            Discard
          </button>
          <SaveButton
            state={saving ? "saving" : "idle"}
            disabled={draft.length === 0 || saving}
            onClick={submit}
          >
            Save students
          </SaveButton>
        </div>
      </div>
    </section>
  );
}

function ActivityTab({ rows }: { rows: AuditLogRow[] }) {
  return (
    <section className="card">
      <div className="card__body">
        <h2 style={{ fontSize: 15 }}>Changes made from the console</h2>
        {rows.length === 0 ? (
          <OpsEmpty>No changes yet.</OpsEmpty>
        ) : (
          <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
            {rows.map((r) => (
              <div key={r.id} className="ops-list__row">
                <div>
                  <span className="strong" style={{ textTransform: "capitalize" }}>{r.action.replace(/_/g, " ")}</span>
                  {r.detail && <div className="small muted" style={{ marginTop: 2 }}>{r.detail}</div>}
                </div>
                <div className="small muted">{r.created_at ? new Date(r.created_at).toLocaleString() : ""}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
