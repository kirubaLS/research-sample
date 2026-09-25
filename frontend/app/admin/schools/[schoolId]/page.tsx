"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Eye,
  EyeOff,
  FileCheck2,
  KeyRound,
  ListChecks,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import { CountUp, Stagger, StaggerItem } from "@/components/motion";
import {
  api,
  ApiError,
  AuditLogRow,
  PlatformOverview,
  PlatformSchool,
  PlatformStudentRow,
  StaffKeySummary,
  StudentBulkInput,
  TeacherAssignmentInput,
  TeacherAssignmentRow,
} from "@/lib/api";
import { getPlatformKey } from "@/lib/session";
import { CopySecret, OpsEmpty, Toast, useToast } from "../../ui";

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
  const [issued, setIssued] = useState<{ label: string; api_key: string; notice: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

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
  }) {
    const key = getPlatformKey();
    if (!key || !school) return;
    try {
      const updated = await api.patchSchool(key, school.id, patch);
      setSchool(updated);
      show("School details saved.");
      await load();
    } catch (err) {
      setError(describe(err, "Could not save school details."));
    }
  }

  async function issueKey(role: "principal" | "teacher", label: string) {
    const key = getPlatformKey();
    if (!key || !school) return;
    try {
      const created = await api.issueStaffKey(key, school.id, role, label);
      setIssued({ label: `${school.name}, ${role} key`, api_key: created.api_key, notice: created.api_key_notice });
      setKeys(await api.listStaffKeys(key, school.id));
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

  async function saveKeyContact(entry: StaffKeySummary, patch: { name: string; email: string; phone: string }) {
    const key = getPlatformKey();
    if (!key || !school) return;
    try {
      await api.patchStaffKey(key, school.id, entry.id, patch);
      setKeys(await api.listStaffKeys(key, school.id));
      show("Contact details saved.");
    } catch (err) {
      setError(describe(err, "Could not save contact details."));
    }
  }

  async function saveAssignments(entry: StaffKeySummary, assignments: TeacherAssignmentInput[]) {
    const key = getPlatformKey();
    if (!key || !school) return;
    try {
      await api.setAssignments(key, school.id, entry.id, assignments);
      show("Access updated.");
    } catch (err) {
      setError(describe(err, "Could not update access."));
    }
  }

  async function bulkAddStudents(rows: StudentBulkInput[]) {
    const key = getPlatformKey();
    if (!key || !school) return;
    try {
      await api.bulkAddStudents(key, school.id, rows);
      show(`${rows.length} student${rows.length === 1 ? "" : "s"} added.`);
      await load();
    } catch (err) {
      setError(describe(err, "Could not add students."));
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
        {tab === "overview" && (
          <OverviewTab
            school={school}
            overviewRow={overviewRow}
            activeTeachers={activeTeachers}
            onAddSection={addSection}
            onToggleDirectory={toggleDirectoryVisibility}
            onRotate={rotate}
          />
        )}
        {tab === "details" && <SchoolDetailsTab school={school} onSave={saveSchoolDetails} />}
        {tab === "principal" && (
          <PrincipalTab
            principal={principal}
            schoolName={school.name}
            onIssue={(label) => issueKey("principal", label)}
            onRevoke={revokeKey}
            onSaveContact={saveKeyContact}
          />
        )}
        {tab === "teachers" && (
          <TeachersTab
            teachers={teacherKeys}
            sections={school.sections}
            onIssue={(label) => issueKey("teacher", label)}
            onRevoke={revokeKey}
            onSaveContact={saveKeyContact}
            onSaveAssignments={saveAssignments}
          />
        )}
        {tab === "students" && (
          <StudentsTab school={school} students={students} onBulkAdd={bulkAddStudents} />
        )}
        {tab === "activity" && <ActivityTab rows={activity} />}
      </div>

      <Toast message={message} />
    </>
  );
}

function OverviewTab({
  school,
  overviewRow,
  activeTeachers,
  onAddSection,
  onToggleDirectory,
  onRotate,
}: {
  school: PlatformSchool;
  overviewRow: PlatformOverview["schools"][number] | null;
  activeTeachers: number;
  onAddSection: () => void;
  onToggleDirectory: () => void;
  onRotate: () => void;
}) {
  const kpis = [
    { label: "Students", value: school.students, sub: `across ${school.sections.length} class${school.sections.length === 1 ? "" : "es"}`, accent: "var(--brand-blue)", icon: Users },
    { label: "Teachers", value: activeTeachers, sub: "with active access", accent: "var(--brand-gold)", icon: KeyRound },
    { label: "Papers loaded", value: overviewRow?.papers ?? 0, sub: "question papers", accent: "var(--brand-teal)", icon: FileCheck2 },
    { label: "Reports issued", value: overviewRow?.reports_issued ?? 0, sub: "to students", accent: "var(--brand-green)", icon: ShieldCheck },
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
                  </div>
                  <div className="kpi__sub">{k.sub}</div>
                </div>
              </div>
            </StaggerItem>
          );
        })}
      </Stagger>

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
  onSave: (patch: { name: string; board: string; state: string; code: string; city: string; address: string; academic_year: string }) => void;
}) {
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
        <button
          className="btn btn--sm"
          onClick={() => onSave({ name, board, state, code, city, address, academic_year: academicYear })}
        >
          Save changes
        </button>
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

function PrincipalTab({
  principal,
  schoolName,
  onIssue,
  onRevoke,
  onSaveContact,
}: {
  principal: StaffKeySummary | undefined;
  schoolName: string;
  onIssue: (label: string) => void;
  onRevoke: (entry: StaffKeySummary) => void;
  onSaveContact: (entry: StaffKeySummary, patch: { name: string; email: string; phone: string }) => void;
}) {
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

  return (
    <div className="grid grid--2" style={{ gap: 16, alignItems: "start" }}>
      <section className="card">
        <div className="card__body">
          <h2 style={{ fontSize: 15 }}>Principal&rsquo;s details</h2>
          <div style={{ marginTop: 12 }}>
            <ContactFields name={name} email={email} phone={phone} setName={setName} setEmail={setEmail} setPhone={setPhone} />
          </div>
        </div>
        <div className="card__foot" style={{ justifyContent: "flex-end" }}>
          <button className="btn btn--sm" onClick={() => onSaveContact(principal, { name, email, phone })}>
            Save principal
          </button>
        </div>
      </section>
      <section className="card">
        <div className="card__body">
          <h2 style={{ fontSize: 15 }}>Principal login</h2>
          <p className="small muted" style={{ marginTop: 4 }}>Sees every section and subject for this school.</p>
          {principal.revoked_at ? (
            <p className="small muted" style={{ marginTop: 10 }}>Revoked. Issue a new key below.</p>
          ) : (
            <div style={{ marginTop: 10 }}>
              <CopySecret value={principal.api_key} />
              <p className="small muted" style={{ marginTop: 6 }}>
                Last used: {principal.last_used_at ? new Date(principal.last_used_at).toLocaleString() : "never"}
              </p>
            </div>
          )}
        </div>
        <div className="card__foot" style={{ justifyContent: "flex-end", gap: 8 }}>
          {!principal.revoked_at && (
            <button className="btn btn--ghost btn--sm" onClick={() => onRevoke(principal)}>
              Revoke
            </button>
          )}
          <button
            className="btn btn--ghost btn--sm"
            onClick={() => {
              const label = window.prompt("Principal's name, for the new key's label", principal.label);
              if (label !== null) onIssue(label);
            }}
          >
            <RefreshCw size={13} /> Change key
          </button>
        </div>
      </section>
    </div>
  );
}

function TeachersTab({
  teachers,
  sections,
  onIssue,
  onRevoke,
  onSaveContact,
  onSaveAssignments,
}: {
  teachers: StaffKeySummary[];
  sections: PlatformSchool["sections"];
  onIssue: (label: string) => void;
  onRevoke: (entry: StaffKeySummary) => void;
  onSaveContact: (entry: StaffKeySummary, patch: { name: string; email: string; phone: string }) => void;
  onSaveAssignments: (entry: StaffKeySummary, assignments: TeacherAssignmentInput[]) => void;
}) {
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
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => {
              const label = window.prompt("Teacher's name, for this key's label", "");
              if (label !== null) onIssue(label);
            }}
          >
            <UserPlus size={13} /> Add teacher
          </button>
        </div>

        {teachers.length === 0 ? (
          <OpsEmpty>No teacher keys issued yet.</OpsEmpty>
        ) : (
          <div style={{ display: "grid", gap: 12, marginTop: 14 }}>
            {teachers.map((t) => (
              <TeacherRow
                key={t.id}
                entry={t}
                sections={sections}
                onRevoke={onRevoke}
                onSaveContact={onSaveContact}
                onSaveAssignments={onSaveAssignments}
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
  onRevoke,
  onSaveContact,
  onSaveAssignments,
}: {
  entry: StaffKeySummary;
  sections: PlatformSchool["sections"];
  onRevoke: (entry: StaffKeySummary) => void;
  onSaveContact: (entry: StaffKeySummary, patch: { name: string; email: string; phone: string }) => void;
  onSaveAssignments: (entry: StaffKeySummary, assignments: TeacherAssignmentInput[]) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [name, setName] = useState(entry.name ?? "");
  const [email, setEmail] = useState(entry.email ?? "");
  const [phone, setPhone] = useState(entry.phone ?? "");
  const [assignments, setAssignments] = useState<TeacherAssignmentRow[]>([]);
  const [loadedAssignments, setLoadedAssignments] = useState(false);

  async function toggle() {
    const next = !expanded;
    setExpanded(next);
    if (next && !loadedAssignments) {
      const key = getPlatformKey();
      if (!key) return;
      try {
        const rows = await api.listAssignments(key, entry.school_id!, entry.id);
        setAssignments(rows);
        setLoadedAssignments(true);
      } catch {
        /* the row just stays without an assignment list */
      }
    }
  }

  function toggleSectionClass(sectionId: string) {
    setAssignments((prev) => {
      const exists = prev.some((a) => a.type === "class" && a.section_id === sectionId);
      if (exists) return prev.filter((a) => !(a.type === "class" && a.section_id === sectionId));
      return [...prev, { id: `new-${sectionId}`, staff_key_id: entry.id, type: "class", section_id: sectionId, subject_code: null }];
    });
  }

  function addSubject() {
    const subject = window.prompt("Subject code (e.g. MATH, SCI, ENG)", "");
    if (!subject) return;
    const sectionId = sections[0]?.id;
    if (!sectionId) return;
    setAssignments((prev) => [
      ...prev,
      { id: `new-subj-${Date.now()}`, staff_key_id: entry.id, type: "subject", section_id: sectionId, subject_code: subject.toUpperCase() },
    ]);
  }

  function updateSubjectSection(assignmentId: string, sectionId: string) {
    setAssignments((prev) => prev.map((a) => (a.id === assignmentId ? { ...a, section_id: sectionId } : a)));
  }

  function removeAssignment(assignmentId: string) {
    setAssignments((prev) => prev.filter((a) => a.id !== assignmentId));
  }

  const classAssignments = assignments.filter((a) => a.type === "class");
  const subjectAssignments = assignments.filter((a) => a.type === "subject");

  return (
    <div className="ops-list__row" style={{ flexDirection: "column", alignItems: "stretch", gap: 10, opacity: entry.revoked_at ? 0.55 : 1 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <div>
          <span className="strong">{entry.name || entry.label || "Unnamed teacher"}</span>
          {entry.revoked_at && <span className="tag tag--risk" style={{ marginLeft: 8 }}>Revoked</span>}
          <div className="small muted" style={{ marginTop: 2 }}>
            {[entry.email, entry.phone].filter(Boolean).join(" · ") || "No contact details on file"}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <button className="btn btn--ghost btn--sm" onClick={toggle}>
            <ListChecks size={13} /> {expanded ? "Hide access" : "Edit access"}
          </button>
          {!entry.revoked_at && (
            <button className="btn btn--ghost btn--sm" onClick={() => onRevoke(entry)}>
              Turn off
            </button>
          )}
        </div>
      </div>

      {!entry.revoked_at && <CopySecret value={entry.api_key} />}

      {expanded && (
        <div className="surface" style={{ padding: 14, display: "grid", gap: 14 }}>
          <ContactFields name={name} email={email} phone={phone} setName={setName} setEmail={setEmail} setPhone={setPhone} />
          <button className="btn btn--ghost btn--sm" style={{ justifySelf: "start" }} onClick={() => onSaveContact(entry, { name, email, phone })}>
            Save contact details
          </button>

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
                    <span className="tag mono">{a.subject_code}</span>
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

          <button
            className="btn btn--sm"
            style={{ justifySelf: "start" }}
            onClick={() =>
              onSaveAssignments(
                entry,
                assignments.map((a) => ({ type: a.type, section_id: a.section_id, subject_code: a.subject_code })),
              )
            }
          >
            Save access
          </button>
        </div>
      )}
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
  onBulkAdd: (rows: StudentBulkInput[]) => void;
}) {
  const [activeSection, setActiveSection] = useState(school.sections[0]?.id ?? "");
  const [draft, setDraft] = useState<StudentBulkInput[]>([]);

  useEffect(() => {
    if (!activeSection && school.sections[0]) setActiveSection(school.sections[0].id);
  }, [school.sections, activeSection]);

  const filtered = students.filter((s) => s.section_id === activeSection);

  function addRow() {
    setDraft((d) => [...d, { name: "", roll_no: "", section_id: activeSection }]);
  }

  function updateRow(i: number, patch: Partial<StudentBulkInput>) {
    setDraft((d) => d.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  }

  function removeRow(i: number) {
    setDraft((d) => d.filter((_, idx) => idx !== i));
  }

  function submit() {
    const rows = draft.filter((r) => r.name.trim() && r.roll_no.trim());
    if (rows.length === 0) return;
    onBulkAdd(rows);
    setDraft([]);
  }

  return (
    <section className="card">
      <div className="card__body">
        <h2 style={{ fontSize: 15 }}>Students and parent WhatsApp numbers</h2>
        <p className="small muted" style={{ marginTop: 4 }}>{students.length} on roll.</p>

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
                  <tr key={s.id}>
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
      <div className="card__foot" style={{ justifyContent: "flex-end" }}>
        <button className="btn btn--sm" disabled={draft.length === 0} onClick={submit}>
          Save students
        </button>
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
