"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Building2,
  Eye,
  EyeOff,
  FileCheck2,
  KeyRound,
  Plus,
  RefreshCw,
  ShieldCheck,
  Users,
} from "lucide-react";
import { CountUp, Reveal, Stagger, StaggerItem } from "@/components/motion";
import { api, ApiError, PlatformOverview, PlatformSchool, StaffKeySummary } from "@/lib/api";
import { getPlatformKey } from "@/lib/session";
import { CopySecret, OpsEmpty, Toast, useToast } from "../../ui";

type Tab = "overview" | "classes" | "keys";
const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "classes", label: "Classes" },
  { key: "keys", label: "Staff keys" },
];

/**
 * One school's account, as far as the real backend can see it: its own
 * counts (GET /platform/overview), its classes (with /t/... links) and the
 * staff keys issued for it. The reference design's Principal / Teachers /
 * Students / Activity tabs -- editable principal contact details, a
 * per-teacher subject/section access matrix, a pasted student roster with
 * parent WhatsApp numbers, and a change log -- have no real endpoint behind
 * them at all: /platform never returns a principal's name/email/phone, has
 * no bulk teacher/student roster, and keeps no audit log. Left out rather
 * than shown against nothing; see the gap note in the wiring report.
 */
export default function AdminSchoolDetailPage() {
  const params = useParams<{ schoolId: string }>();
  const { message, show } = useToast();
  const [tab, setTab] = useState<Tab>("overview");
  const [school, setSchool] = useState<PlatformSchool | null | undefined>(undefined);
  const [overviewRow, setOverviewRow] = useState<PlatformOverview["schools"][number] | null>(null);
  const [keys, setKeys] = useState<StaffKeySummary[]>([]);
  const [issued, setIssued] = useState<{ label: string; api_key: string; notice: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const key = getPlatformKey();
    if (!key) return;
    try {
      const list = await api.listSchools(key);
      setSchool(list.find((s) => s.id === params.schoolId) ?? null);
    } catch {
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
      /* keys tab shows its own load error state */
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
    } catch {
      setError("Could not rotate the key.");
    }
  }

  async function issueKey() {
    const key = getPlatformKey();
    if (!key || !school) return;
    const label = window.prompt(`Who is this principal key for at ${school.name}? (a name, so it can be revoked later)`, "");
    if (label === null) return;
    try {
      const created = await api.issueStaffKey(key, school.id, "principal", label);
      setIssued({ label: `${school.name}, principal key`, api_key: created.api_key, notice: created.api_key_notice });
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
    } catch (err) {
      setError(describe(err, "Could not revoke the key."));
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
              <span className={`tag ${school.hidden_from_directory ? "tag--risk" : "tag--teal"}`}>
                {school.hidden_from_directory ? "Hidden from directory" : "Visible on directory"}
              </span>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              <span className="tag">{school.board}</span>
              <span className="tag">{school.state ?? "—"}</span>
              <span className="tag tag--info">{school.students} students</span>
            </div>
          </div>
        </div>
      </header>

      <div className="tabs ops-tabs" role="tablist" style={{ marginTop: 16 }}>
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} className={`tab ${tab === t.key ? "tab--active" : ""}`} onClick={() => setTab(t.key)}>
            {t.label}
            {t.key === "classes" && ` (${school.sections.length})`}
            {t.key === "keys" && ` (${keys.filter((k) => !k.revoked_at).length})`}
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
        {tab === "overview" && <Overview school={school} overviewRow={overviewRow} />}
        {tab === "classes" && <ClassesTab school={school} onAddSection={addSection} onToggleDirectory={toggleDirectoryVisibility} onRotate={rotate} />}
        {tab === "keys" && <KeysTab keys={keys} onIssue={issueKey} onRevoke={revokeKey} />}
      </div>

      <Toast message={message} />
    </>
  );
}

function Overview({ school, overviewRow }: { school: PlatformSchool; overviewRow: PlatformOverview["schools"][number] | null }) {
  const kpis = [
    { label: "Students", value: school.students, sub: `across ${school.sections.length} class${school.sections.length === 1 ? "" : "es"}`, accent: "var(--brand-blue)", icon: Users },
    { label: "Papers loaded", value: overviewRow?.papers ?? 0, sub: "question papers", accent: "var(--brand-gold)", icon: FileCheck2 },
    { label: "Answer scripts", value: overviewRow?.answer_scripts ?? 0, sub: "scanned", accent: "var(--brand-teal)", icon: Building2 },
    { label: "Reports issued", value: overviewRow?.reports_issued ?? 0, sub: "to students", accent: "var(--brand-green)", icon: ShieldCheck },
  ];
  return (
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
  );
}

function ClassesTab({
  school,
  onAddSection,
  onToggleDirectory,
  onRotate,
}: {
  school: PlatformSchool;
  onAddSection: () => void;
  onToggleDirectory: () => void;
  onRotate: () => void;
}) {
  return (
    <section className="card">
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
  );
}

function KeysTab({ keys, onIssue, onRevoke }: { keys: StaffKeySummary[]; onIssue: () => void; onRevoke: (entry: StaffKeySummary) => void }) {
  return (
    <section className="card">
      <div className="card__body">
        <h2 style={{ fontSize: 15 }}>Staff keys</h2>
        <p className="small muted" style={{ marginTop: 4 }}>
          A principal key has full authority over this school. Teacher keys scoped to specific classes or subjects are
          issued from inside the school&rsquo;s own dashboard by its principal, not from here.
        </p>
        {keys.length === 0 ? (
          <OpsEmpty>None issued. The school&rsquo;s own key already works as one.</OpsEmpty>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
            {keys.map((entry) => (
              <div key={entry.id} style={entry.revoked_at ? { opacity: 0.55 } : undefined}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="small">
                    <strong style={{ textTransform: "capitalize" }}>{entry.role}</strong>
                    {entry.label ? ` · ${entry.label}` : ""}
                    {entry.revoked_at && <span className="muted"> · revoked</span>}
                  </span>
                  {!entry.revoked_at && (
                    <button className="btn btn--ghost btn--sm" onClick={() => onRevoke(entry)}>
                      Revoke
                    </button>
                  )}
                </div>
                <CopySecret value={entry.api_key} />
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="card__foot" style={{ justifyContent: "flex-end" }}>
        <button className="btn btn--ghost btn--sm" onClick={onIssue}>
          <KeyRound size={13} /> Issue a principal key
        </button>
      </div>
    </section>
  );
}
