"use client";

/**
 * Operator console -- schools. Adapted structurally from the reference design's
 * admin/schools/page.tsx (KPI row, searchable/sortable accounts table, onboarding
 * card) but wired end to end to the real platform API (lib/api.ts). The reference
 * is a UI-only mock: its "activation %", "status" pill and per-school "onboarding
 * progress" all come from fields our backend does not have (no PlatformSchool.status,
 * no checklist, no teachersInvited/teachersActivated) -- see the gap note below the
 * table. Everything shown here is a real field from PlatformSchool / PlatformOverview.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Building2,
  ChevronsUpDown,
  Eye,
  EyeOff,
  FileCheck2,
  KeyRound,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  UserPlus,
  Users,
} from "lucide-react";
import { CopyLink } from "@/components/CopyLink";
import { CopySecret } from "@/components/CopySecret";
import { api, ApiError, apiBaseIsDefault, ApiUnreachable, PlatformOverview, PlatformSchool, StaffKeySummary } from "@/lib/api";
import { getPlatformKey, setActiveSchool, setApiKey } from "@/lib/session";

const CONSENT_LABEL: Record<string, string> = {
  operational_only: "Operational only",
  improve_models: "May improve models",
  research: "Research",
};

const CONSENT = [
  ["operational_only", "Operational only: run the product, no model training"],
  ["improve_models", "Improve models: anonymised work may train recognition"],
  ["research", "Research: as above, plus aggregate study"],
] as const;

type Issued = { name: string; api_key: string; notice: string };
type SortField = "name" | "students" | "papers" | "answer_scripts";
type SortDir = "asc" | "desc";

function SortHeader({
  label,
  field,
  sort,
  dir,
  onSort,
  align = "left",
}: {
  label: string;
  field: SortField;
  sort: SortField;
  dir: SortDir;
  onSort: (field: SortField) => void;
  align?: "left" | "right";
}) {
  const on = sort === field;
  return (
    <th scope="col" aria-sort={on ? (dir === "asc" ? "ascending" : "descending") : "none"} style={{ textAlign: align, whiteSpace: "nowrap" }}>
      <button
        type="button"
        onClick={() => onSort(field)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 5,
          background: "none",
          border: "none",
          padding: 0,
          font: "inherit",
          color: on ? "var(--brand-blue)" : "inherit",
          cursor: "pointer",
        }}
      >
        {label}
        {on ? dir === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} /> : <ChevronsUpDown size={11} style={{ opacity: 0.4 }} />}
      </button>
    </th>
  );
}

export default function PlatformConsole() {
  const [schools, setSchools] = useState<PlatformSchool[] | null>(null);
  const [overview, setOverview] = useState<PlatformOverview | null>(null);
  const [issued, setIssued] = useState<Issued | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [query, setQuery] = useState("");
  const [board, setBoard] = useState("All");
  const [sort, setSort] = useState<SortField>("name");
  const [dir, setDir] = useState<SortDir>("asc");

  function requireKey(): string | null {
    const key = getPlatformKey();
    if (!key) {
      setError("You're not signed in to the platform console any more. Sign in again.");
      return null;
    }
    return key;
  }

  const load = useCallback(async () => {
    const key = requireKey();
    if (!key) return;
    try {
      setSchools(await api.listSchools(key));
    } catch {
      setError("Could not load schools.");
    }
  }, []);

  const loadOverview = useCallback(async () => {
    const key = requireKey();
    if (!key) return;
    try {
      setOverview(await api.platformOverview(key));
    } catch {
      /* the school cards below still load their own counts */
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  function openAsAdmin(school: { id: string; name: string }) {
    const key = requireKey();
    if (!key) return;
    setApiKey(key, school.name);
    setActiveSchool(school.id);
    window.location.href = "/admin";
  }

  const [staffKeys, setStaffKeys] = useState<Record<string, StaffKeySummary[]>>({});
  const [adminKeys, setAdminKeys] = useState<StaffKeySummary[]>([]);
  const [openSchool, setOpenSchool] = useState<string | null>(null);

  const loadAdminKeys = useCallback(async () => {
    const key = requireKey();
    if (!key) return;
    try {
      setAdminKeys(await api.listAdminKeys(key));
    } catch {
      /* console still works */
    }
  }, []);

  useEffect(() => {
    void loadAdminKeys();
  }, [loadAdminKeys]);

  async function issueAdminKey() {
    const key = requireKey();
    if (!key) return;
    const label = window.prompt(
      "Who is this deputy operator key for? (a name, so it can be revoked later)\n\n" +
        "It can create schools and act on every school on this deployment -- almost " +
        "nobody needs this. A school's own staff should get a principal key instead.",
      "",
    );
    if (label === null) return;
    try {
      const created = await api.issueAdminKey(key, label);
      setIssued({ name: `Admin key for ${label || "an unnamed person"}`, api_key: created.api_key, notice: created.api_key_notice });
      await loadAdminKeys();
    } catch (err) {
      setError(describe(err, "Could not issue the admin key."));
    }
  }

  async function revokeAdminKey(entry: StaffKeySummary) {
    const key = requireKey();
    if (!key) return;
    if (!window.confirm(`Revoke the deputy operator key${entry.label ? ` for ${entry.label}` : ""}? They are signed out of every school immediately.`)) return;
    try {
      await api.revokeAdminKey(key, entry.id);
      await loadAdminKeys();
    } catch (err) {
      setError(describe(err, "Could not revoke the key."));
    }
  }

  const loadKeys = useCallback(async (schoolId: string) => {
    const key = requireKey();
    if (!key) return;
    try {
      const rows = await api.listStaffKeys(key, schoolId);
      setStaffKeys((all) => ({ ...all, [schoolId]: rows }));
    } catch {
      /* key panel failed, says nothing false */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    (schools ?? []).forEach((s) => void loadKeys(s.id));
  }, [schools, loadKeys]);

  function describe(err: unknown, fallback: string): string {
    if (err instanceof ApiError && err.status === 409) return "That name is already taken by a school that exists.";
    return fallback;
  }

  async function createSchool(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const key = requireKey();
    if (!key) return;
    const form = new FormData(event.currentTarget);
    const raw = String(form.get("sections") ?? "").trim();
    const sections = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .map((spec) => {
        const [grade, name] = spec.split("-");
        return { grade: Number(grade), name: (name ?? "").toUpperCase() };
      });

    if (!sections.length || sections.some((s) => !Number.isInteger(s.grade) || !s.name)) {
      setError("Classes must look like 10-A, and be separated by commas.");
      return;
    }

    setError(null);
    setBusy(true);
    try {
      const created = await api.createSchool(key, {
        name: String(form.get("name") ?? "").trim(),
        board: String(form.get("board") ?? "CBSE"),
        state: String(form.get("state") ?? ""),
        training_consent: String(form.get("consent") ?? "operational_only"),
        sections,
      });
      setIssued({ name: created.name, api_key: created.api_key, notice: created.api_key_notice });
      (event.target as HTMLFormElement).reset();
      await load();
      await loadOverview();
    } catch (err) {
      setError(describe(err, "Could not create the school."));
    } finally {
      setBusy(false);
    }
  }

  async function issueKey(school: PlatformSchool, role: "principal" | "admin") {
    const key = requireKey();
    if (!key) return;
    const label = window.prompt(`Who is this ${role} key for at ${school.name}? (a name, so it can be revoked later)`, "");
    if (label === null) return;
    try {
      const created = await api.issueStaffKey(key, school.id, role, label);
      setIssued({ name: `${school.name}, ${role} key`, api_key: created.api_key, notice: created.api_key_notice });
      await loadKeys(school.id);
    } catch (err) {
      setError(describe(err, "Could not issue the key."));
    }
  }

  async function revokeKey(school: PlatformSchool, entry: StaffKeySummary) {
    const key = requireKey();
    if (!key) return;
    if (!window.confirm(`Revoke the ${entry.role} key${entry.label ? ` for ${entry.label}` : ""}? They are signed out immediately.`)) return;
    try {
      await api.revokeStaffKey(key, school.id, entry.id);
      await loadKeys(school.id);
    } catch (err) {
      setError(describe(err, "Could not revoke the key."));
    }
  }

  async function rotate(school: PlatformSchool) {
    const key = requireKey();
    if (!key) return;
    const ok = window.confirm(
      `Issue a new key for ${school.name}?\n\nThe school's current key stops working ` +
        `immediately and whoever holds it will have to sign in again. Any principal keys ` +
        `issued below and class links are not affected.`,
    );
    if (!ok) return;
    try {
      const result = await api.rotateKey(key, school.id);
      setIssued({ name: school.name, api_key: result.api_key, notice: result.api_key_notice });
    } catch {
      setError("Could not rotate the key.");
    }
  }

  async function toggleDirectoryVisibility(school: PlatformSchool) {
    const key = requireKey();
    if (!key) return;
    try {
      const updated = await api.setDirectoryVisibility(key, school.id, !school.hidden_from_directory);
      setSchools((all) => all?.map((s) => (s.id === school.id ? updated : s)) ?? all);
    } catch {
      setError("Could not change this school's directory visibility.");
    }
  }

  async function addSection(school: PlatformSchool) {
    const key = requireKey();
    if (!key) return;
    const spec = window.prompt(`Add a class to ${school.name} (e.g. 10-C)`, "10-C");
    if (!spec) return;
    const [grade, name] = spec.split("-");
    try {
      await api.addSection(key, school.id, { grade: Number(grade), name: (name ?? "").toUpperCase() });
      await load();
    } catch (err) {
      setError(describe(err, "Could not add the class."));
    }
  }

  function onSort(field: SortField) {
    if (field === sort) setDir(dir === "asc" ? "desc" : "asc");
    else {
      setSort(field);
      setDir(field === "name" ? "asc" : "desc");
    }
  }

  // overview rows carry papers/answer_scripts/reports_issued/admin_keys/principal_keys;
  // schools carries board/state/consent/directory visibility/sections. Join the two on id
  // so the table can sort and filter by whichever real field it needs.
  const overviewById = useMemo(() => {
    const m = new Map<string, PlatformOverview["schools"][number]>();
    (overview?.schools ?? []).forEach((r) => m.set(r.id, r));
    return m;
  }, [overview]);

  const boards = useMemo(() => Array.from(new Set((schools ?? []).map((s) => s.board))).sort(), [schools]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = (schools ?? []).filter((s) => {
      if (board !== "All" && s.board !== board) return false;
      if (!q) return true;
      return [s.name, s.board, s.state ?? ""].some((f) => f.toLowerCase().includes(q));
    });
    return [...filtered].sort((a, b) => {
      const ov = (id: string) => overviewById.get(id);
      const av: number | string =
        sort === "name" ? a.name : sort === "students" ? a.students : sort === "papers" ? ov(a.id)?.papers ?? 0 : ov(a.id)?.answer_scripts ?? 0;
      const bv: number | string =
        sort === "name" ? b.name : sort === "students" ? b.students : sort === "papers" ? ov(b.id)?.papers ?? 0 : ov(b.id)?.answer_scripts ?? 0;
      const cmp = typeof av === "string" && typeof bv === "string" ? av.localeCompare(bv) : Number(av) - Number(bv);
      return dir === "asc" ? cmp : -cmp;
    });
  }, [schools, query, board, sort, dir, overviewById]);

  const kpis = overview
    ? [
        { label: "Schools", value: overview.totals.schools, sub: "on this deployment", accent: "var(--brand-green)", icon: Building2 },
        { label: "Students", value: overview.totals.students, sub: "across the portfolio", accent: "var(--brand-teal)", icon: Users },
        { label: "Papers loaded", value: overview.totals.papers, sub: `${overview.totals.answer_scripts} answer scripts scanned`, accent: "var(--brand-gold)", icon: FileCheck2 },
        { label: "Reports issued", value: overview.totals.reports_issued, sub: "across the portfolio", accent: "var(--brand-blue)", icon: ShieldCheck },
      ]
    : [];

  return (
    <main className="content">
      <p className="eyebrow">Operator console</p>
      <h1 className="page-title" style={{ marginTop: 6 }}>
        Schools
      </h1>
      <p className="page-sub">
        Create a school, add its classes, and issue the key its principal signs in with. No student data is visible
        here. That stays inside each school&apos;s own dashboard.
      </p>

      {apiBaseIsDefault() && (
        <div className="evidence evidence--gold" style={{ marginTop: 18 }}>
          <div>This site has not been told where its server is, so nothing below will load until it is.</div>
        </div>
      )}

      {overview && (
        <div className="grid grid--4" style={{ marginTop: 20 }}>
          {kpis.map((k) => {
            const Icon = k.icon;
            return (
              <div key={k.label} className="kpi" style={{ "--accent": k.accent } as React.CSSProperties}>
                <span className="kpi__icon">
                  <Icon size={21} />
                </span>
                <div className="kpi__text">
                  <div className="kpi__label">{k.label}</div>
                  <div className="kpi__value">{k.value}</div>
                  <div className="kpi__sub">{k.sub}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {issued && (
        <div className="card" style={{ marginTop: 22, borderLeft: "3px solid var(--brand-teal)" }}>
          <div className="card__body">
            <p className="eyebrow">New key for {issued.name}</p>
            <h2 className="section-q">Copy this now</h2>
            <p className="muted small" style={{ marginBottom: 14 }}>
              {issued.notice}
            </p>
            <CopySecret value={issued.api_key} />
            <button className="btn btn--ghost btn--sm" style={{ marginTop: 14 }} onClick={() => setIssued(null)}>
              I have saved it
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="evidence evidence--gold" style={{ marginTop: 18 }}>
          <div>{error}</div>
        </div>
      )}

      <section className="section" style={{ marginTop: 24 }} aria-labelledby="table-h">
        <div className="section__head">
          <h2 id="table-h" className="section-q" style={{ fontSize: 17 }}>
            All schools
          </h2>
          <span style={{ display: "inline-flex", gap: 10, alignItems: "center" }}>
            <span className="small muted">
              {rows.length} of {schools?.length ?? 0} shown
            </span>
            <a href="#add-a-school" className="btn btn--blue btn--sm">
              <UserPlus size={13} /> Onboard a school
            </a>
          </span>
        </div>

        <div className="filterbar" style={{ position: "static", background: "transparent", backdropFilter: "none" }}>
          <div className="filter" style={{ flex: "1 1 260px", maxWidth: 360 }}>
            <label htmlFor="school-search">Search</label>
            <span style={{ position: "relative", display: "block" }}>
              <Search size={14} className="muted" style={{ position: "absolute", left: 10, top: 9 }} />
              <input
                id="school-search"
                className="input"
                style={{ paddingLeft: 32 }}
                placeholder="Name, board or state"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </span>
          </div>
          <div className="filter">
            <label htmlFor="board-filter">Board</label>
            <select id="board-filter" className="select" value={board} onChange={(e) => setBoard(e.target.value)}>
              <option>All</option>
              {boards.map((b) => (
                <option key={b}>{b}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="card" style={{ marginTop: 12, overflow: "hidden" }}>
          {!schools ? (
            <div className="card__body">
              <p className="muted small" style={{ margin: 0 }}>
                Loading…
              </p>
            </div>
          ) : rows.length === 0 ? (
            <div className="card__body">
              <p className="small muted" style={{ margin: 0 }}>
                {schools.length === 0 ? "No schools yet. Create the first one below." : "No school matches those filters."}
              </p>
            </div>
          ) : (
            <div className="table-wrap table-wrap--scroll" style={{ maxHeight: 560 }}>
              <table className="table table--hover">
                <thead>
                  <tr>
                    <SortHeader label="School" field="name" sort={sort} dir={dir} onSort={onSort} />
                    <th scope="col">Board / State</th>
                    <SortHeader label="Students" field="students" sort={sort} dir={dir} onSort={onSort} align="right" />
                    <SortHeader label="Papers" field="papers" sort={sort} dir={dir} onSort={onSort} align="right" />
                    <SortHeader label="Answer scripts" field="answer_scripts" sort={sort} dir={dir} onSort={onSort} align="right" />
                    <th scope="col">Consent</th>
                    <th scope="col">Directory</th>
                    <th scope="col" aria-label="Open school" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((s) => {
                    const ov = overviewById.get(s.id);
                    const expanded = openSchool === s.id;
                    return (
                      <tr key={s.id} onClick={() => setOpenSchool(expanded ? null : s.id)} style={{ cursor: "pointer" }}>
                        <td style={{ minWidth: 200 }}>
                          <span style={{ fontWeight: 650 }}>{s.name}</span>
                        </td>
                        <td style={{ whiteSpace: "nowrap" }}>
                          <span className="tag">{s.board}</span> {s.state ?? ""}
                        </td>
                        <td className="num">{s.students}</td>
                        <td className="num">{ov?.papers ?? "—"}</td>
                        <td className="num">{ov?.answer_scripts ?? "—"}</td>
                        <td>
                          <span className="tag tag--info">{CONSENT_LABEL[s.training_consent] ?? s.training_consent}</span>
                        </td>
                        <td>
                          <span className={`tag ${s.hidden_from_directory ? "tag--risk" : "tag--teal"}`}>
                            {s.hidden_from_directory ? "Hidden" : "Visible"}
                          </span>
                        </td>
                        <td style={{ width: 90 }}>
                          <button
                            type="button"
                            className="btn btn--ghost btn--sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              openAsAdmin(s);
                            }}
                          >
                            Open
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <p className="small muted" style={{ marginTop: 8 }}>
          There is no separate per-school detail page here: the real backend has no
          per-school detail endpoint beyond what platform/schools and platform/overview
          already return (see gap note in the report), so a row expands in place below
          instead of navigating to a route that doesn&rsquo;t exist.
        </p>
      </section>

      {rows.map((school) => {
        if (openSchool !== school.id) return null;
        return (
          <section className="card" key={school.id} style={{ marginTop: 14 }}>
            <div className="card__body">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                <h3 style={{ fontSize: 16 }}>{school.name}</h3>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setOpenSchool(null)}>
                  Close
                </button>
              </div>

              <p className="small" style={{ marginTop: 4 }}>
                Public directory: <strong>{school.hidden_from_directory ? "Hidden" : "Visible"}</strong>{" "}
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => toggleDirectoryVisibility(school)}>
                  {school.hidden_from_directory ? <Eye size={12} /> : <EyeOff size={12} />}
                  {school.hidden_from_directory ? "Show on /t" : "Hide from /t"}
                </button>
              </p>

              <p className="eyebrow" style={{ marginTop: 18 }}>
                Class links
              </p>
              {school.sections.map((section) => (
                <div key={section.id} style={{ marginBottom: 10 }}>
                  <p className="small" style={{ marginBottom: 4 }}>
                    {section.label}
                  </p>
                  <CopyLink path={section.student_path} />
                </div>
              ))}

              <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
                <button className="btn btn--ghost btn--sm" onClick={() => addSection(school)}>
                  <Plus size={13} /> Add a class
                </button>
                <button className="btn btn--ghost btn--sm" onClick={() => rotate(school)}>
                  <RefreshCw size={13} /> Rotate the school&rsquo;s key
                </button>
              </div>

              <p className="eyebrow" style={{ marginTop: 18 }}>
                Staff keys
              </p>
              <p className="small muted" style={{ marginTop: 0 }}>
                A principal key has full authority over this school. For a teacher scoped to
                specific classes or subjects, use Manage Teachers inside their dashboard instead.
              </p>
              {(staffKeys[school.id] ?? []).length === 0 ? (
                <p className="small muted">None issued. The school&rsquo;s own key already works as one.</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {(staffKeys[school.id] ?? []).map((entry) => (
                    <div key={entry.id} style={entry.revoked_at ? { opacity: 0.55 } : undefined}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span className="small">
                          <strong>Principal</strong>
                          {entry.role === "admin" && <span className="muted"> (issued before this label changed)</span>}
                          {entry.label ? ` · ${entry.label}` : ""}
                          {entry.revoked_at && <span className="muted"> · revoked</span>}
                        </span>
                        {!entry.revoked_at && (
                          <button className="btn btn--ghost btn--sm" onClick={() => revokeKey(school, entry)}>
                            Revoke
                          </button>
                        )}
                      </div>
                      <CopySecret value={entry.api_key} />
                    </div>
                  ))}
                </div>
              )}
              <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
                <button className="btn btn--ghost btn--sm" onClick={() => issueKey(school, "principal")}>
                  <KeyRound size={13} /> Issue a principal key
                </button>
              </div>
            </div>
          </section>
        );
      })}

      <div className="section__head" style={{ marginTop: 24 }}>
        <h2 className="section-q">Deputy operator keys</h2>
      </div>
      <div className="card">
        <div className="card__body">
          <p className="small muted" style={{ marginTop: 0 }}>
            Not a school role. This is a second credential for this console itself -- someone
            who helps run the whole deployment: creating schools, loading books, working
            across every school here. It belongs to no single school, so every request it
            makes has to name the one it is about. Almost nobody needs this; a school&rsquo;s
            day-to-day access is a principal key, issued above under that school&rsquo;s own card.
          </p>
          {adminKeys.length === 0 ? (
            <p className="small muted">None issued yet.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {adminKeys.map((entry) => (
                <div key={entry.id} style={entry.revoked_at ? { opacity: 0.55 } : undefined}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span className="small">
                      {entry.label || <span className="muted">unnamed</span>}
                      {entry.revoked_at && <span className="muted"> · revoked</span>}
                    </span>
                    {!entry.revoked_at && (
                      <button className="btn btn--ghost btn--sm" onClick={() => revokeAdminKey(entry)}>
                        Revoke
                      </button>
                    )}
                  </div>
                  <CopySecret value={entry.api_key} />
                </div>
              ))}
            </div>
          )}
          <div style={{ marginTop: 12 }}>
            <button className="btn btn--ghost btn--sm" onClick={issueAdminKey}>
              <KeyRound size={13} /> Issue a deputy operator key
            </button>
          </div>
        </div>
      </div>

      <div className="section__head" style={{ marginTop: 24 }} id="add-a-school">
        <h2 className="section-q">Onboard a school</h2>
      </div>
      <p className="small muted" style={{ marginTop: -8, marginBottom: 12 }}>
        School, classes and consent, in one step. The real onboarding endpoint (
        <code>POST /platform/schools</code>) takes a name, board, state, consent and a
        starting set of classes -- it has no bulk principal/teacher/student import, so
        unlike the reference design&rsquo;s five-step wizard there are no separate
        Principal/Teachers/Students steps here; add a principal key below once the school
        exists, and roster teachers and students from inside that school&rsquo;s own
        dashboard (see the gap note in the report).
      </p>
      <form onSubmit={createSchool} className="card">
        <div className="card__body ops-form-grid">
          <div className="field field--wide">
            <label htmlFor="name">School name</label>
            <input id="name" name="name" className="input" required placeholder="Bharath International Sr. Sec. School" />
          </div>
          <div className="field">
            <label htmlFor="board">Board</label>
            <input id="board" name="board" className="input" defaultValue="CBSE" />
          </div>
          <div className="field">
            <label htmlFor="state">State</label>
            <input id="state" name="state" className="input" defaultValue="Tamil Nadu" />
          </div>
          <div className="field field--wide">
            <label htmlFor="sections">Classes</label>
            <input id="sections" name="sections" className="input" defaultValue="10-A" placeholder="10-A, 10-B" />
            <p className="muted small">Comma separated, written as grade-section. You can add more later.</p>
          </div>
          <div className="field field--wide">
            <label htmlFor="consent">What the school has agreed to</label>
            <select id="consent" name="consent" className="select" defaultValue="operational_only">
              {CONSENT.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <p className="muted small">
              Recorded per school and honoured at capture time. Start at operational only unless the school has signed
              for more.
            </p>
          </div>
        </div>
        <div className="card__foot" style={{ justifyContent: "flex-end" }}>
          <button type="submit" className="btn btn--primary" disabled={busy}>
            {busy ? "Creating…" : "Create school and issue key"}
          </button>
        </div>
      </form>
    </main>
  );
}
