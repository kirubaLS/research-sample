"use client";

import { useCallback, useEffect, useState } from "react";
import { CopyLink } from "@/components/CopyLink";
import { CopySecret } from "@/components/CopySecret";
import { api, ApiError, PlatformSchool } from "@/lib/api";
import { getPlatformKey } from "@/lib/session";

const CONSENT = [
  ["operational_only", "Operational only — run the product, no model training"],
  ["improve_models", "Improve models — anonymised work may train recognition"],
  ["research", "Research — as above, plus aggregate study"],
] as const;

/** A key the operator must copy now: there is no route that reads one back later. */
type Issued = { name: string; api_key: string; notice: string };

export default function PlatformConsole() {
  const [schools, setSchools] = useState<PlatformSchool[] | null>(null);
  const [issued, setIssued] = useState<Issued | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const key = getPlatformKey();
    if (!key) return;
    try {
      setSchools(await api.listSchools(key));
    } catch {
      setError("Could not load schools.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function describe(err: unknown, fallback: string): string {
    if (err instanceof ApiError && err.status === 409) {
      return "That name is already taken — a school with it exists.";
    }
    return fallback;
  }

  async function createSchool(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const key = getPlatformKey();
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

  async function rotate(school: PlatformSchool) {
    const key = getPlatformKey();
    if (!key) return;
    const ok = window.confirm(
      `Issue a new key for ${school.name}?\n\nThe principal's current key stops working ` +
        `immediately and they will have to sign in again. Class links are not affected.`,
    );
    if (!ok) return;
    try {
      const result = await api.rotateKey(key, school.id);
      setIssued({ name: school.name, api_key: result.api_key, notice: result.api_key_notice });
    } catch {
      setError("Could not rotate the key.");
    }
  }

  async function addSection(school: PlatformSchool) {
    const key = getPlatformKey();
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
          No student data is visible here — that stays inside each school&apos;s own dashboard.
        </p>
      </div>

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
              <span className="mono">{school.training_consent}</span>
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
                Issue a new principal key
              </button>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
