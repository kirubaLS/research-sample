"use client";

import { useState } from "react";
import Link from "next/link";
import { CheckCircle2, KeyRound, Plus, X } from "lucide-react";
import { Reveal } from "@/components/motion";
import { api, ApiError, IssuedKey, PlatformSchool } from "@/lib/api";
import { getPlatformKey } from "@/lib/session";
import { CopySecret } from "../ui";
import { FieldError } from "../directory";

const CONSENT = [
  ["operational_only", "Operational only: run the product, no model training"],
  ["improve_models", "Improve models: anonymised work may train recognition"],
  ["research", "Research: as above, plus aggregate study"],
] as const;

const BOARDS = ["CBSE", "ICSE", "State Board"];
const INDIAN_STATES = [
  "Andhra Pradesh", "Delhi", "Goa", "Gujarat", "Haryana", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra",
  "Odisha", "Punjab", "Rajasthan", "Tamil Nadu", "Telangana", "Uttar Pradesh", "West Bengal",
];

type Section = { grade: number; name: string };

/**
 * Ops -> Onboard a school. Real: POST /platform/schools takes a name, board,
 * state, training consent and a starting set of classes, and returns the
 * school's own key. That is the entire real onboarding surface -- there is
 * no bulk endpoint for principal / teacher / student import in one shot, so
 * unlike the reference design's five-step wizard (School -> Principal ->
 * Teachers -> Students -> Review) this is one step for the school itself.
 * Once it exists, issue a principal key for it below, or from its account
 * page; teachers and students are added from inside that school's own
 * dashboard by its principal (api.createTeacher / roster self-registration),
 * which is a different, already-real screen outside this task's scope.
 */
export default function OnboardSchoolPage() {
  const [name, setName] = useState("");
  const [board, setBoard] = useState<string>(BOARDS[0]);
  const [state, setState] = useState(INDIAN_STATES[0]);
  const [consent, setConsent] = useState<string>(CONSENT[0][0]);
  const [sections, setSections] = useState<Section[]>([{ grade: 10, name: "A" }]);
  const [newSectionSpec, setNewSectionSpec] = useState("");
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<(PlatformSchool & IssuedKey) | null>(null);
  const [principalKey, setPrincipalKey] = useState<{ label: string; api_key: string; notice: string } | null>(null);

  const errors: Record<string, string> = {};
  if (!name.trim()) errors.name = "Enter the school's name.";
  if (sections.length === 0) errors.sections = "Add at least one class.";

  function addSection() {
    const spec = newSectionSpec.trim();
    const m = /^(\d{1,2})-([A-Za-z0-9]{1,3})$/.exec(spec);
    if (!m) return;
    const section = { grade: Number(m[1]), name: m[2].toUpperCase() };
    if (!sections.some((s) => s.grade === section.grade && s.name === section.name)) setSections([...sections, section]);
    setNewSectionSpec("");
  }

  function removeSection(i: number) {
    setSections(sections.filter((_, idx) => idx !== i));
  }

  function describe(err: unknown, fallback: string): string {
    if (err instanceof ApiError && err.status === 409) return "A school with this name (or code) already exists.";
    return fallback;
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setTried(true);
    if (Object.keys(errors).length) return;
    const key = getPlatformKey();
    if (!key) {
      setError("You're not signed in to the operator console any more. Sign in again.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await api.createSchool(key, {
        name: name.trim(),
        board,
        state,
        training_consent: consent,
        sections,
      });
      setCreated(result);
    } catch (err) {
      setError(describe(err, "Could not create the school."));
    } finally {
      setBusy(false);
    }
  }

  async function issuePrincipalKey() {
    const key = getPlatformKey();
    if (!key || !created) return;
    const label = window.prompt(`Who is this principal key for at ${created.name}? (a name, so it can be revoked later)`, "");
    if (label === null) return;
    try {
      const issued = await api.issueStaffKey(key, created.id, "principal", label);
      setPrincipalKey({ label: `${created.name}, principal key`, api_key: issued.api_key, notice: issued.api_key_notice });
    } catch (err) {
      setError(describe(err, "Could not issue the key."));
    }
  }

  if (created) {
    return (
      <section className="card" style={{ padding: "22px 22px 18px" }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span className="kpi__icon" style={{ "--accent": "var(--brand-green)" } as React.CSSProperties}>
            <CheckCircle2 size={22} />
          </span>
          <div>
            <h1 style={{ fontSize: 20 }}>{created.name} is on AVAI</h1>
            <p className="small muted" style={{ marginTop: 2 }}>
              {created.sections.length} class{created.sections.length === 1 ? "" : "es"} created. Copy the school&rsquo;s
              own key now -- it is shown once.
            </p>
          </div>
        </div>

        <div style={{ marginTop: 16 }}>
          <p className="eyebrow">School key</p>
          <p className="small muted" style={{ marginTop: 0 }}>{created.api_key_notice}</p>
          <CopySecret value={created.api_key} />
        </div>

        {principalKey ? (
          <div style={{ marginTop: 16 }}>
            <p className="eyebrow">{principalKey.label}</p>
            <p className="small muted" style={{ marginTop: 0 }}>{principalKey.notice}</p>
            <CopySecret value={principalKey.api_key} />
          </div>
        ) : (
          <div style={{ marginTop: 16 }}>
            <button type="button" className="btn btn--ghost btn--sm" onClick={issuePrincipalKey}>
              <KeyRound size={13} /> Issue a principal key
            </button>
          </div>
        )}

        {error && (
          <div className="evidence evidence--gold" style={{ marginTop: 16 }}>
            <div>{error}</div>
          </div>
        )}

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 20 }}>
          <Link href={`/admin/schools/${created.id}`} className="btn btn--blue">
            <KeyRound size={14} /> Open the school
          </Link>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setCreated(null);
              setPrincipalKey(null);
              setName("");
              setSections([{ grade: 10, name: "A" }]);
              setTried(false);
            }}
          >
            <Plus size={14} /> Onboard another school
          </button>
        </div>
      </section>
    );
  }

  return (
    <>
      <Reveal>
        <div className="ops-pagehead">
          <div>
            <h1 style={{ fontSize: 22 }}>Onboard a school</h1>
            <p className="small muted" style={{ marginTop: 2 }}>
              Name, board, state, consent and starting classes. The school&rsquo;s own access key is generated when you
              create it. Teachers and students are added afterwards from inside the school&rsquo;s own dashboard.
            </p>
          </div>
        </div>
      </Reveal>

      <form onSubmit={create} className="card" style={{ marginTop: 16 }}>
        <div className="card__body ops-form-grid">
          <div className="field field--wide">
            <label htmlFor="s-name">School name</label>
            <input id="s-name" className="input" value={name} placeholder="Sri Vidya Mandir Senior Secondary School" onChange={(e) => setName(e.target.value)} />
            <FieldError>{tried && errors.name}</FieldError>
          </div>
          <div className="field">
            <label htmlFor="s-state">State</label>
            <select id="s-state" className="select" value={state} onChange={(e) => setState(e.target.value)}>
              {INDIAN_STATES.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="s-board">Board</label>
            <select id="s-board" className="select" value={board} onChange={(e) => setBoard(e.target.value)}>
              {BOARDS.map((b) => (
                <option key={b}>{b}</option>
              ))}
            </select>
          </div>
          <div className="field field--wide">
            <label>Classes</label>
            <div className="chip-row">
              {sections.map((sec, i) => (
                <span key={`${sec.grade}-${sec.name}`} className="chip">
                  Class {sec.grade}{sec.name}
                  <button type="button" onClick={() => removeSection(i)} aria-label={`Remove class ${sec.grade}${sec.name}`}>
                    <X size={12} />
                  </button>
                </span>
              ))}
              <span className="chip chip--input">
                <input
                  value={newSectionSpec}
                  placeholder="10-C"
                  aria-label="New class, e.g. 10-C"
                  onChange={(e) => setNewSectionSpec(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addSection())}
                />
                <button type="button" onClick={addSection} aria-label="Add class">
                  <Plus size={12} />
                </button>
              </span>
            </div>
            <span className="small muted">Written as grade-section, e.g. 10-A. You can add more later.</span>
            <FieldError>{tried && errors.sections}</FieldError>
          </div>
          <div className="field field--wide">
            <label htmlFor="s-consent">What the school has agreed to</label>
            <select id="s-consent" className="select" value={consent} onChange={(e) => setConsent(e.target.value)}>
              {CONSENT.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <span className="small muted">
              Recorded per school and honoured at capture time. Start at operational only unless the school has signed for more.
            </span>
          </div>
        </div>

        {error && (
          <div className="card__body" style={{ paddingTop: 0 }}>
            <div className="evidence evidence--gold">
              <div>{error}</div>
            </div>
          </div>
        )}

        <div className="card__foot" style={{ justifyContent: "flex-end" }}>
          <button type="submit" className="btn btn--blue" disabled={busy}>
            <CheckCircle2 size={15} /> {busy ? "Creating…" : "Create school and generate key"}
          </button>
        </div>
      </form>
    </>
  );
}
