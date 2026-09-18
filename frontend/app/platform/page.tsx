"use client";

import { useCallback, useEffect, useState } from "react";
import { CopyLink } from "@/components/CopyLink";
import { CopySecret } from "@/components/CopySecret";
import { api, ApiError, PlatformOverview, PlatformSchool, StaffKeySummary } from "@/lib/api";
import { getPlatformKey, setActiveSchool, setApiKey } from "@/lib/session";

/** The stored values are for the database. These are what a person reads. */
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

/** A key the operator must copy now: there is no route that reads one back later. */
type Issued = { name: string; api_key: string; notice: string };

export default function PlatformConsole() {
  const [schools, setSchools] = useState<PlatformSchool[] | null>(null);
  const [overview, setOverview] = useState<PlatformOverview | null>(null);
  const [issued, setIssued] = useState<Issued | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Every action below used to do `if (!key) return` silently -- if the stored platform
  // key was ever missing (signed out in another tab, storage cleared, a session that
  // outlived its own key), every button on this console just did nothing with no
  // indication why, which reads exactly like "the CRUD buttons don't work". This surfaces
  // that state instead of swallowing it.
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
      /* the school cards below still load their own counts; a failed summary row is not
         a reason to hide the rest of the console */
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  /** Jump into a school's own admin dashboard as its acting admin -- the platform key
   * already resolves to one there (see app.api.deps.current_staff), so this is the same
   * sign-in AdminGate's own box would do with the same key typed in by hand. */
  function openAsAdmin(school: { id: string; name: string }) {
    const key = requireKey();
    if (!key) return;
    setApiKey(key, school.name);
    setActiveSchool(school.id);
    window.location.href = "/admin";
  }

  const [staffKeys, setStaffKeys] = useState<Record<string, StaffKeySummary[]>>({});
  const [adminKeys, setAdminKeys] = useState<StaffKeySummary[]>([]);

  const loadAdminKeys = useCallback(async () => {
    const key = requireKey();
    if (!key) return;
    try {
      setAdminKeys(await api.listAdminKeys(key));
    } catch {
      /* the console still works; a panel that failed to load says nothing false */
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
      setIssued({
        name: `Admin key for ${label || "an unnamed person"}`,
        api_key: created.api_key,
        notice: created.api_key_notice,
      });
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
      /* the school still lists; a key panel that failed to load says nothing false */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Once the schools are known, fetch each one's staff keys. Listing carries no secrets,
  // only who holds what -- there is no route anywhere that reads a key back.
  useEffect(() => {
    (schools ?? []).forEach((s) => void loadKeys(s.id));
  }, [schools, loadKeys]);

  function describe(err: unknown, fallback: string): string {
    if (err instanceof ApiError && err.status === 409) {
      return "That name is already taken by a school that exists.";
    }
    return fallback;
  }

  async function createSchool(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const key = requireKey();
    if (!key) return;
    const form = new FormData(event.currentTarget);
    const raw = String(form.get("sections") ?? "").trim();

    // "10-A, 10-B" — the operator types classes the way they say them out loud
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
      setIssued({
        name: created.name,
        api_key: created.api_key,
        notice: created.api_key_notice,
      });
      (event.target as HTMLFormElement).reset();
      await load();
    } catch (err) {
      setError(describe(err, "Could not create the school."));
    } finally {
      setBusy(false);
    }
  }

  async function issueKey(school: PlatformSchool, role: "principal" | "admin") {
    const key = requireKey();
    if (!key) return;
    const label = window.prompt(
      `Who is this ${role} key for at ${school.name}? (a name, so it can be revoked later)`,
      "",
    );
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
      const updated = await api.setDirectoryVisibility(
        key, school.id, !school.hidden_from_directory,
      );
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
      await api.addSection(key, school.id, {
        grade: Number(grade),
        name: (name ?? "").toUpperCase(),
      });
      await load();
    } catch (err) {
      setError(describe(err, "Could not add the class."));
    }
  }

  return (
    <main>
      <div className="hero">
        <p className="eyebrow">Operator console</p>
        <h1>Schools</h1>
        <p className="lede">
          Create a school, add its classes, and issue the key its principal signs in with.
          No student data is visible here. That stays inside each school&apos;s own dashboard.
        </p>
      </div>

      {overview && (
        <>
          <div className="section-head">
            <h2>Every school, at a glance</h2>
          </div>
          <div className="grid three" style={{ marginBottom: 18 }}>
            <div className="stat">
              <span className="label">Schools</span>
              <span className="value">{overview.totals.schools}</span>
            </div>
            <div className="stat">
              <span className="label">Students</span>
              <span className="value">{overview.totals.students}</span>
            </div>
            <div className="stat">
              <span className="label">Papers</span>
              <span className="value">{overview.totals.papers}</span>
            </div>
            <div className="stat">
              <span className="label">Answer scripts</span>
              <span className="value">{overview.totals.answer_scripts}</span>
            </div>
          </div>
          <div className="card flush">
            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th>School</th>
                    <th>Students</th>
                    <th>Papers</th>
                    <th>Answer scripts</th>
                    <th>Reports issued</th>
                    <th>Admin keys</th>
                    <th>Principal keys</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {overview.schools.map((row) => (
                    <tr key={row.id}>
                      <td className="strong">{row.name}</td>
                      <td className="num">{row.students}</td>
                      <td className="num">{row.papers}</td>
                      <td className="num">{row.answer_scripts}</td>
                      <td className="num">{row.reports_issued}</td>
                      <td className="num">{row.admin_keys}</td>
                      <td className="num">{row.principal_keys}</td>
                      <td>
                        <button
                          type="button"
                          className="secondary tiny"
                          onClick={() => openAsAdmin(row)}
                        >
                          Open dashboard
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {overview.cross_school_admin_keys > 0 && (
              <p className="small muted" style={{ margin: "12px 16px 0" }}>
                Plus {overview.cross_school_admin_keys} admin key
                {overview.cross_school_admin_keys === 1 ? "" : "s"} that belong to no single
                school.
              </p>
            )}
          </div>
        </>
      )}

      {issued && (
        <div className="card accentbar" style={{ marginTop: 22 }}>
          <p className="eyebrow">New key for {issued.name}</p>
          <h2>Copy this now</h2>
          <p className="cardnote" style={{ marginBottom: 14 }}>
            {issued.notice}
          </p>
          <CopySecret value={issued.api_key} />
          <button
            className="secondary tiny"
            style={{ marginTop: 14 }}
            onClick={() => setIssued(null)}
          >
            I have saved it
          </button>
        </div>
      )}

      {error && <div className="notice warn" style={{ marginTop: 18 }}>{error}</div>}

      <div className="section-head">
        <h2>Deputy operator keys</h2>
      </div>
      <div className="card">
        <p className="small muted" style={{ marginTop: 0 }}>
          Not a school role. This is a second credential for this console itself --
          someone who helps run the whole deployment: creating schools, loading books,
          working across every school here. It belongs to no single school, so every
          request it makes has to name the one it is about. Almost nobody needs this;
          a school's day-to-day access is a principal key, issued below under that
          school&rsquo;s own card.
        </p>
        {adminKeys.length === 0 ? (
          <p className="small muted">None issued yet.</p>
        ) : (
          <div className="stack" style={{ gap: 10 }}>
            {adminKeys.map((entry) => (
              <div key={entry.id} style={entry.revoked_at ? { opacity: 0.55 } : undefined}>
                <div className="row between">
                  <span className="small">
                    {entry.label || <span className="muted">unnamed</span>}
                    {entry.revoked_at && <span className="muted"> · revoked</span>}
                  </span>
                  {!entry.revoked_at && (
                    <button className="secondary tiny" onClick={() => revokeAdminKey(entry)}>
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
          <button className="secondary tiny" onClick={issueAdminKey}>
            Issue a deputy operator key
          </button>
        </div>
      </div>

      <div className="section-head">
        <h2>Add a school</h2>
      </div>
      <form onSubmit={createSchool} className="card">
        <div className="field">
          <label htmlFor="name">School name</label>
          <input id="name" name="name" required placeholder="Bharath International Sr. Sec. School" />
        </div>
        <div className="grid two">
          <div className="field">
            <label htmlFor="board">Board</label>
            <input id="board" name="board" defaultValue="CBSE" />
          </div>
          <div className="field">
            <label htmlFor="state">State</label>
            <input id="state" name="state" defaultValue="Tamil Nadu" />
          </div>
        </div>
        <div className="field">
          <label htmlFor="sections">Classes</label>
          <input id="sections" name="sections" defaultValue="10-A" placeholder="10-A, 10-B" />
          <p className="hint">Comma separated, written as grade-section. You can add more later.</p>
        </div>
        <div className="field">
          <label htmlFor="consent">What the school has agreed to</label>
          <select id="consent" name="consent" defaultValue="operational_only">
            {CONSENT.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <p className="hint">
            Recorded per school and honoured at capture time. Start at operational only unless
            the school has signed for more.
          </p>
        </div>
        <button type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create school and issue key"}
        </button>
      </form>

      <div className="section-head">
        <h2>Existing schools</h2>
      </div>
      {!schools && <p className="cardnote">Loading…</p>}
      {schools?.length === 0 && (
        <div className="notice">No schools yet. Create the first one above.</div>
      )}
      <div className="grid two">
        {schools?.map((school) => (
          <div key={school.id} className="card">
            <h3>{school.name}</h3>
            <p className="cardnote">
              {school.board}
              {school.state ? ` · ${school.state}` : ""} · {school.students} students ·{" "}
              {CONSENT_LABEL[school.training_consent] ?? school.training_consent}
            </p>
            <p className="small" style={{ marginTop: 4 }}>
              Public directory:{" "}
              <strong>{school.hidden_from_directory ? "Hidden" : "Visible"}</strong>
              {" — "}
              <button
                type="button"
                className="secondary tiny"
                onClick={() => toggleDirectoryVisibility(school)}
              >
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
              <button className="secondary tiny" onClick={() => addSection(school)}>
                Add a class
              </button>
              <button className="secondary tiny" onClick={() => rotate(school)}>
                Rotate the school&rsquo;s key
              </button>
            </div>

            <p className="eyebrow" style={{ marginTop: 18 }}>
              Staff keys
            </p>
            <p className="small muted" style={{ marginTop: 0 }}>
              A principal key has full authority over this school: reading results,
              scanning papers, entering marks, and managing the roster and teachers.
              Issue one per person who needs that. For a teacher scoped to specific
              classes or subjects instead, use Manage Teachers inside their dashboard,
              not a key issued from here.
            </p>
            {(staffKeys[school.id] ?? []).length === 0 ? (
              <p className="small muted">
                None issued. The school&rsquo;s own key below already works as one.
              </p>
            ) : (
              <div className="stack" style={{ gap: 10 }}>
                {(staffKeys[school.id] ?? []).map((entry) => (
                  <div key={entry.id} style={entry.revoked_at ? { opacity: 0.55 } : undefined}>
                    <div className="row between">
                      <span className="small">
                        <strong>Principal</strong>
                        {entry.role === "admin" && (
                          <span className="muted"> (issued before this label changed)</span>
                        )}
                        {entry.label ? ` · ${entry.label}` : ""}
                        {entry.revoked_at && <span className="muted"> · revoked</span>}
                      </span>
                      {!entry.revoked_at && (
                        <button
                          className="secondary tiny"
                          onClick={() => revokeKey(school, entry)}
                        >
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
              <button className="secondary tiny" onClick={() => issueKey(school, "principal")}>
                Issue a principal key
              </button>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
