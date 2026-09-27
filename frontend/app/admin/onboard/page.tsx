"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, KeyRound, Plus, Trash2, UserPlus, X } from "lucide-react";
import { Reveal } from "@/components/motion";
import {
  api,
  ApiError,
  PlatformSchool,
  StaffKeySummary,
  StudentBulkInput,
  Subject,
  TeacherAssignmentInput,
} from "@/lib/api";
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

const STEP_META = ["School", "Principal", "Teachers", "Students", "Review"];

/** A teacher not yet issued a key -- everything the Add Teacher modal collects,
 * kept locally until the Teachers step is submitted. */
type TeacherDraft = {
  key: string; // local id for the list, not a real key id
  name: string;
  mobile: string;
  email: string;
  examCell: boolean; // the modal's "login type": Regular teacher vs Exam cell (a real field, StaffKeySummary.exam_cell)
  classTeacherOf: string; // a section id, or "" for none
  subjectCells: Set<string>; // "SUBJECT_CODE::sectionId"
};

/** A teacher who has actually been issued a key + assignments -- shown once on Review. */
type TeacherIssued = { name: string; label: string; api_key: string; assignmentSummary: string };

/**
 * Ops -> Onboard a school: a real 5-step wizard (School -> Principal ->
 * Teachers -> Students -> Review) matching the reference design's shape.
 * There is no bulk "onboard everything" endpoint, so each step calls its own
 * real /platform endpoint in turn, exactly as this app already does from a
 * school's own account page (app/admin/schools/[schoolId]/page.tsx):
 *
 *   1. School    POST /platform/schools                              -> school + its own key
 *                PATCH /platform/schools/{id}                        -> code/city/address/academic_year
 *                (PlatformSchool really carries these fields; there is
 *                no reference field left over with nothing to write to)
 *   2. Principal POST /platform/schools/{id}/keys (role=principal)    -> principal key
 *                PATCH .../keys/{keyId}                               -> name/email/phone
 *   3. Teachers  one POST .../keys (role=teacher) + PATCH (contact) + PATCH
 *                .../keys/{keyId}/assignments (class + subject cells) per teacher
 *   4. Students  POST .../students/bulk                                -> the roster rows added
 *   5. Review    a real summary of what steps 1-4 actually created, with
 *                the school's and principal's keys shown once (CopySecret)
 *
 * The reference design's own Students and Review screens have not been
 * shared yet -- steps 4 and 5 here are a first, functionally-real pass in
 * the same visual language, to be reskinned once those images arrive.
 */
export default function OnboardSchoolPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // ---- Step 1: School -----------------------------------------------------
  const [name, setName] = useState("");
  const [board, setBoard] = useState<string>(BOARDS[0]);
  const [state, setState] = useState(INDIAN_STATES[0]);
  const [consent, setConsent] = useState<string>(CONSENT[0][0]);
  const [sections, setSections] = useState<Section[]>([{ grade: 10, name: "A" }]);
  const [newSectionSpec, setNewSectionSpec] = useState("");
  const [code, setCode] = useState("");
  const [city, setCity] = useState("");
  const [address, setAddress] = useState("");
  const [academicYear, setAcademicYear] = useState("");
  const [tried, setTried] = useState(false);

  const [school, setSchool] = useState<PlatformSchool | null>(null);
  const [schoolKey, setSchoolKey] = useState<{ api_key: string; notice: string } | null>(null);

  // ---- Step 2: Principal --------------------------------------------------
  const [pName, setPName] = useState("");
  const [pEmail, setPEmail] = useState("");
  const [pMobile, setPMobile] = useState("");
  const [principal, setPrincipal] = useState<StaffKeySummary | null>(null);

  // ---- Step 3: Teachers ----------------------------------------------------
  const [teacherDrafts, setTeacherDrafts] = useState<TeacherDraft[]>([]);
  const [showTeacherModal, setShowTeacherModal] = useState(false);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [teachersIssued, setTeachersIssued] = useState<TeacherIssued[]>([]);

  useEffect(() => {
    const key = getPlatformKey();
    if (!key) return;
    api.platformSubjects(key).then((r) => setSubjects(r.subjects)).catch(() => {});
  }, []);

  // ---- Step 4: Students -----------------------------------------------------
  const [studentDrafts, setStudentDrafts] = useState<StudentBulkInput[]>([]);
  const [studentsAdded, setStudentsAdded] = useState(0);

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
    if (err instanceof ApiError && err.status === 409) return "That name (or code) is already in use.";
    return fallback;
  }

  async function submitSchool() {
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
      let final: PlatformSchool = result;
      if (code.trim() || city.trim() || address.trim() || academicYear.trim()) {
        final = await api.patchSchool(key, result.id, {
          ...(code.trim() && { code: code.trim() }),
          ...(city.trim() && { city: city.trim() }),
          ...(address.trim() && { address: address.trim() }),
          ...(academicYear.trim() && { academic_year: academicYear.trim() }),
        });
      }
      setSchool(final);
      setSchoolKey({ api_key: result.api_key, notice: result.api_key_notice });
      setStep(1);
    } catch (err) {
      setError(describe(err, "Could not create the school."));
    } finally {
      setBusy(false);
    }
  }

  async function submitPrincipal() {
    const key = getPlatformKey();
    if (!key || !school) return;
    setBusy(true);
    setError(null);
    try {
      const issued = await api.issueStaffKey(key, school.id, "principal", pName.trim() || "Principal");
      const updated = await api.patchStaffKey(key, school.id, issued.id, {
        name: pName.trim(),
        email: pEmail.trim(),
        phone: pMobile.trim(),
      });
      setPrincipal({ ...updated, api_key: issued.api_key });
      setStep(2);
    } catch (err) {
      setError(describe(err, "Could not issue the principal's key."));
    } finally {
      setBusy(false);
    }
  }

  async function submitTeachers() {
    const key = getPlatformKey();
    if (!key || !school) return;
    setBusy(true);
    setError(null);
    try {
      const issued: TeacherIssued[] = [];
      for (const draft of teacherDrafts) {
        const created = await api.issueStaffKey(key, school.id, "teacher", draft.name.trim() || "Teacher", draft.examCell);
        await api.patchStaffKey(key, school.id, created.id, {
          name: draft.name.trim(),
          email: draft.email.trim(),
          phone: draft.mobile.trim(),
        });
        const assignments: TeacherAssignmentInput[] = [];
        if (draft.classTeacherOf) assignments.push({ type: "class", section_id: draft.classTeacherOf });
        for (const cell of draft.subjectCells) {
          const [subjectCode, sectionId] = cell.split("::");
          assignments.push({ type: "subject", section_id: sectionId, subject_code: subjectCode });
        }
        if (assignments.length) await api.setAssignments(key, school.id, created.id, assignments);

        const classLabel = draft.classTeacherOf ? school.sections.find((s) => s.id === draft.classTeacherOf)?.label : null;
        const summaryBits = [
          classLabel && `class teacher of ${classLabel}`,
          draft.subjectCells.size > 0 && `${draft.subjectCells.size} subject assignment${draft.subjectCells.size === 1 ? "" : "s"}`,
          draft.examCell && "exam cell",
        ].filter(Boolean);
        issued.push({
          name: draft.name.trim() || "Unnamed teacher",
          label: draft.name.trim() || "Teacher",
          api_key: created.api_key,
          assignmentSummary: summaryBits.length ? summaryBits.join(", ") : "no assignments yet",
        });
      }
      setTeachersIssued(issued);
      setStep(3);
    } catch (err) {
      setError(describe(err, "Could not add the teachers."));
    } finally {
      setBusy(false);
    }
  }

  async function submitStudents() {
    const key = getPlatformKey();
    if (!key || !school) return;
    const rows = studentDrafts.filter((r) => r.name.trim() && r.roll_no.trim());
    setBusy(true);
    setError(null);
    try {
      if (rows.length) {
        await api.bulkAddStudents(key, school.id, rows);
      }
      setStudentsAdded(rows.length);
      setStep(4);
    } catch (err) {
      setError(describe(err, "Could not add the students."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Reveal>
        <div className="ops-pagehead">
          <div>
            <h1 style={{ fontSize: 22 }}>Onboard a school</h1>
            <p className="small muted" style={{ marginTop: 2 }}>
              Five real steps, each its own write to the platform: the school itself, its principal, its teachers and
              their class access, then its students.
            </p>
          </div>
        </div>
      </Reveal>

      <div className="surface" style={{ padding: "16px 16px 14px", marginTop: 16 }}>
        <div className="stepper">
          <div className="stepper__bar" style={{ "--progress": `${(step / 4) * 100}%` } as React.CSSProperties} />
          {STEP_META.map((title, i) => (
            <div key={title} className="stepper__step" data-state={i < step ? "done" : i === step ? "current" : "upcoming"}>
              <span className="stepper__dot">{i < step ? <Check size={13} /> : i + 1}</span>
              {title}
            </div>
          ))}
        </div>
      </div>

      {error && (
        <div className="evidence evidence--gold" style={{ marginTop: 16 }}>
          <div>{error}</div>
        </div>
      )}

      <div style={{ marginTop: 16 }}>
        {step === 0 && (
          <SchoolStep
            {...{ name, setName, board, setBoard, state, setState, consent, setConsent, sections, addSection,
              removeSection, newSectionSpec, setNewSectionSpec, code, setCode, city, setCity, address, setAddress,
              academicYear, setAcademicYear, tried, errors, busy }}
            onNext={submitSchool}
          />
        )}
        {step === 1 && school && (
          <PrincipalStep
            schoolName={school.name}
            name={pName} setName={setPName}
            email={pEmail} setEmail={setPEmail}
            mobile={pMobile} setMobile={setPMobile}
            busy={busy}
            onNext={submitPrincipal}
          />
        )}
        {step === 2 && school && (
          <TeachersStep
            school={school}
            subjects={subjects}
            drafts={teacherDrafts}
            onRemove={(k) => setTeacherDrafts((d) => d.filter((t) => t.key !== k))}
            onAdd={(d) => setTeacherDrafts((prev) => [...prev, d])}
            showModal={showTeacherModal}
            setShowModal={setShowTeacherModal}
            busy={busy}
            onNext={submitTeachers}
          />
        )}
        {step === 3 && school && (
          <StudentsStep
            school={school}
            drafts={studentDrafts}
            setDrafts={setStudentDrafts}
            busy={busy}
            onNext={submitStudents}
          />
        )}
        {step === 4 && school && (
          <ReviewStep
            school={school}
            schoolKey={schoolKey}
            principal={principal}
            principalContact={{ name: pName, email: pEmail, mobile: pMobile }}
            teachersIssued={teachersIssued}
            studentsAdded={studentsAdded}
            onDone={() => router.push(`/admin/schools/${school.id}`)}
          />
        )}
      </div>
    </>
  );
}

// ============================================================
// Step 1: School
// ============================================================

function SchoolStep(props: {
  name: string; setName: (v: string) => void;
  board: string; setBoard: (v: string) => void;
  state: string; setState: (v: string) => void;
  consent: string; setConsent: (v: string) => void;
  sections: Section[]; addSection: () => void; removeSection: (i: number) => void;
  newSectionSpec: string; setNewSectionSpec: (v: string) => void;
  code: string; setCode: (v: string) => void;
  city: string; setCity: (v: string) => void;
  address: string; setAddress: (v: string) => void;
  academicYear: string; setAcademicYear: (v: string) => void;
  tried: boolean; errors: Record<string, string>; busy: boolean;
  onNext: () => void;
}) {
  const {
    name, setName, board, setBoard, state, setState, consent, setConsent, sections, addSection, removeSection,
    newSectionSpec, setNewSectionSpec, code, setCode, city, setCity, address, setAddress, academicYear, setAcademicYear,
    tried, errors, busy, onNext,
  } = props;
  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onNext(); }}
      className="card"
    >
      <div className="card__body ops-form-grid">
        <div className="field field--wide">
          <label htmlFor="s-name">School name</label>
          <input id="s-name" className="input" value={name} placeholder="Sri Vidya Mandir Senior Secondary School" onChange={(e) => setName(e.target.value)} />
          <FieldError>{tried && errors.name}</FieldError>
        </div>
        <div className="field">
          <label htmlFor="s-code">School code</label>
          <input id="s-code" className="input" value={code} placeholder="e.g. BISS-TN" onChange={(e) => setCode(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="s-city">City</label>
          <input id="s-city" className="input" value={city} onChange={(e) => setCity(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="s-state">State</label>
          <select id="s-state" className="select" value={state} onChange={(e) => setState(e.target.value)}>
            {INDIAN_STATES.map((s) => (<option key={s}>{s}</option>))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="s-board">Board</label>
          <select id="s-board" className="select" value={board} onChange={(e) => setBoard(e.target.value)}>
            {BOARDS.map((b) => (<option key={b}>{b}</option>))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="s-year">Academic year</label>
          <input id="s-year" className="input" value={academicYear} placeholder="e.g. 2026-27" onChange={(e) => setAcademicYear(e.target.value)} />
        </div>
        <div className="field field--wide">
          <label htmlFor="s-address">Address</label>
          <input id="s-address" className="input" value={address} onChange={(e) => setAddress(e.target.value)} />
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
            {CONSENT.map(([value, label]) => (<option key={value} value={value}>{label}</option>))}
          </select>
        </div>
      </div>
      <div className="card__foot" style={{ justifyContent: "flex-end" }}>
        <button type="submit" className="btn btn--blue" disabled={busy}>
          {busy ? "Creating…" : "Next: Principal"}
        </button>
      </div>
    </form>
  );
}

// ============================================================
// Step 2: Principal
// ============================================================

function PrincipalStep({
  schoolName, name, setName, email, setEmail, mobile, setMobile, busy, onNext,
}: {
  schoolName: string;
  name: string; setName: (v: string) => void;
  email: string; setEmail: (v: string) => void;
  mobile: string; setMobile: (v: string) => void;
  busy: boolean;
  onNext: () => void;
}) {
  return (
    <form onSubmit={(e) => { e.preventDefault(); onNext(); }} className="card">
      <div className="card__body" style={{ display: "grid", gap: 14, maxWidth: 460 }}>
        <p className="small muted" style={{ margin: 0 }}>
          {schoolName}&rsquo;s principal will sign in with this key. It is issued and shown once on the Review step.
        </p>
        <label className="field">
          <span className="field__label">Full name</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">
          <span className="field__label">Email</span>
          <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="field">
          <span className="field__label">Mobile</span>
          <input className="input" value={mobile} onChange={(e) => setMobile(e.target.value)} />
        </label>
      </div>
      <div className="card__foot" style={{ justifyContent: "flex-end" }}>
        <button type="submit" className="btn btn--blue" disabled={busy}>
          <KeyRound size={14} /> {busy ? "Issuing…" : "Next: Teachers"}
        </button>
      </div>
    </form>
  );
}

// ============================================================
// Step 3: Teachers
// ============================================================

function TeachersStep({
  school, subjects, drafts, onRemove, onAdd, showModal, setShowModal, busy, onNext,
}: {
  school: PlatformSchool;
  subjects: Subject[];
  drafts: TeacherDraft[];
  onRemove: (key: string) => void;
  onAdd: (d: TeacherDraft) => void;
  showModal: boolean;
  setShowModal: (v: boolean) => void;
  busy: boolean;
  onNext: () => void;
}) {
  return (
    <section className="card">
      <div className="card__body">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div>
            <h2 style={{ fontSize: 15 }}>Teachers</h2>
            <p className="small muted" style={{ marginTop: 4 }}>
              Add every teacher you want signed in from day one. Each gets their own key, with class and subject
              access set here. You can add more later from the school&rsquo;s own account page.
            </p>
          </div>
          <button type="button" className="btn btn--sm" onClick={() => setShowModal(true)}>
            <UserPlus size={13} /> Add teacher
          </button>
        </div>

        {drafts.length === 0 ? (
          <div style={{ marginTop: 14 }}>
            <div
              className="small muted"
              style={{ border: "1.5px dashed var(--line-strong)", borderRadius: "var(--radius-md)", padding: "22px 16px", textAlign: "center", background: "rgba(255,255,255,.55)" }}
            >
              No teachers added yet. Click &ldquo;Add teacher&rdquo; to add the first one, or skip this step.
            </div>
          </div>
        ) : (
          <div style={{ display: "grid", gap: 10, marginTop: 14 }}>
            {drafts.map((d) => {
              const classLabel = d.classTeacherOf ? school.sections.find((s) => s.id === d.classTeacherOf)?.label : null;
              return (
                <div key={d.key} className="ops-list__row">
                  <div>
                    <span className="strong">{d.name || "Unnamed teacher"}</span>
                    {d.examCell && <span className="tag" style={{ marginLeft: 8 }}>Exam cell</span>}
                    <div className="small muted" style={{ marginTop: 2 }}>
                      {[d.email, d.mobile].filter(Boolean).join(" · ") || "No contact details"}
                    </div>
                    <div className="small muted" style={{ marginTop: 2 }}>
                      {[classLabel && `Class teacher of ${classLabel}`, d.subjectCells.size > 0 && `${d.subjectCells.size} subject cell${d.subjectCells.size === 1 ? "" : "s"}`]
                        .filter(Boolean).join(" · ") || "No assignments yet"}
                    </div>
                  </div>
                  <button className="btn btn--ghost btn--sm" onClick={() => onRemove(d.key)}>
                    <Trash2 size={13} />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
      <div className="card__foot" style={{ justifyContent: "flex-end" }}>
        <button type="button" className="btn btn--blue" disabled={busy} onClick={onNext}>
          {busy ? "Adding teachers…" : "Next: Students"}
        </button>
      </div>

      {showModal && (
        <AddTeacherModal
          sections={school.sections}
          subjects={subjects}
          onClose={() => setShowModal(false)}
          onSave={(d) => { onAdd(d); setShowModal(false); }}
        />
      )}
    </section>
  );
}

function AddTeacherModal({
  sections, subjects, onClose, onSave,
}: {
  sections: PlatformSchool["sections"];
  subjects: Subject[];
  onClose: () => void;
  onSave: (d: TeacherDraft) => void;
}) {
  const [name, setName] = useState("");
  const [mobile, setMobile] = useState("");
  const [email, setEmail] = useState("");
  const [loginType, setLoginType] = useState<"regular" | "exam_cell">("regular");
  const [classTeacherOf, setClassTeacherOf] = useState("");
  const [cells, setCells] = useState<Set<string>>(new Set());

  // De-duplicated subject codes -- one grid row per subject group, one column per section.
  const subjectRows = Array.from(new Map(subjects.map((s) => [s.group_code, s.group_label])).entries());

  function toggle(subjectCode: string, sectionId: string) {
    const cell = `${subjectCode}::${sectionId}`;
    setCells((prev) => {
      const next = new Set(prev);
      if (next.has(cell)) next.delete(cell);
      else next.add(cell);
      return next;
    });
  }

  function save() {
    if (!name.trim()) return;
    onSave({
      key: `t-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      name, mobile, email,
      examCell: loginType === "exam_cell",
      classTeacherOf,
      subjectCells: cells,
    });
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="modal modal--wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal__head">
          <h2 style={{ fontSize: 16 }}>Add teacher</h2>
          <button className="btn btn--ghost btn--sm" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>
        <div className="modal__body">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <label className="field">
              <span className="field__label">Full name</span>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Mobile</span>
              <input className="input" value={mobile} onChange={(e) => setMobile(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Email</span>
              <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Login type</span>
              <select className="select" value={loginType} onChange={(e) => setLoginType(e.target.value as "regular" | "exam_cell")}>
                <option value="regular">Regular teacher</option>
                <option value="exam_cell">Exam cell (papers &amp; marks, every subject)</option>
              </select>
            </label>
          </div>

          <label className="field">
            <span className="field__label">Class teacher of</span>
            <select className="select" value={classTeacherOf} onChange={(e) => setClassTeacherOf(e.target.value)}>
              <option value="">None</option>
              {sections.map((s) => (<option key={s.id} value={s.id}>{s.label}</option>))}
            </select>
          </label>

          {loginType === "exam_cell" ? (
            <p className="small muted">
              Exam cell access already covers papers and marks for every subject and section -- no grid needed.
            </p>
          ) : subjectRows.length === 0 ? (
            <p className="small muted">No subjects loaded on this deployment yet -- assignments can be added later.</p>
          ) : sections.length === 0 ? (
            <p className="small muted">Add a class on the School step first to assign subjects.</p>
          ) : (
            <div>
              <p className="field__label">Subjects taught</p>
              <div className="table-wrap" style={{ marginTop: 6 }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Subject</th>
                      {sections.map((s) => (<th key={s.id} style={{ textAlign: "center" }}>{s.label}</th>))}
                    </tr>
                  </thead>
                  <tbody>
                    {subjectRows.map(([code, label]) => (
                      <tr key={code}>
                        <td>{label}</td>
                        {sections.map((s) => (
                          <td key={s.id} style={{ textAlign: "center" }}>
                            <input
                              type="checkbox"
                              checked={cells.has(`${code}::${s.id}`)}
                              onChange={() => toggle(code, s.id)}
                            />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
        <div className="modal__foot">
          <button className="btn btn--ghost btn--sm" onClick={onClose}>Cancel</button>
          <button className="btn btn--sm" disabled={!name.trim()} onClick={save}>Add teacher</button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Step 4: Students -- kept in the same visual language as the other steps;
// the reference design's own Students screen has not been shared yet.
// ============================================================

function StudentsStep({
  school, drafts, setDrafts, busy, onNext,
}: {
  school: PlatformSchool;
  drafts: StudentBulkInput[];
  setDrafts: (fn: (d: StudentBulkInput[]) => StudentBulkInput[]) => void;
  busy: boolean;
  onNext: () => void;
}) {
  function addRow() {
    setDrafts((d) => [...d, { name: "", roll_no: "", section_id: school.sections[0]?.id ?? "" }]);
  }
  function updateRow(i: number, patch: Partial<StudentBulkInput>) {
    setDrafts((d) => d.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  }
  function removeRow(i: number) {
    setDrafts((d) => d.filter((_, idx) => idx !== i));
  }

  return (
    <section className="card">
      <div className="card__body">
        <h2 style={{ fontSize: 15 }}>Students</h2>
        <p className="small muted" style={{ marginTop: 4 }}>
          Add the starting roster now, or skip this and add students later from the school&rsquo;s own Students tab.
        </p>

        {drafts.length === 0 ? (
          <div style={{ marginTop: 14 }}>
            <div
              className="small muted"
              style={{ border: "1.5px dashed var(--line-strong)", borderRadius: "var(--radius-md)", padding: "22px 16px", textAlign: "center", background: "rgba(255,255,255,.55)" }}
            >
              No students added yet.
            </div>
          </div>
        ) : (
          <div style={{ display: "grid", gap: 8, marginTop: 14 }}>
            {drafts.map((row, i) => (
              <div key={i} style={{ display: "grid", gridTemplateColumns: "120px 80px 1fr 1fr 1fr 32px", gap: 8, alignItems: "center" }}>
                <select className="select" value={row.section_id} onChange={(e) => updateRow(i, { section_id: e.target.value })}>
                  {school.sections.map((s) => (<option key={s.id} value={s.id}>{s.label}</option>))}
                </select>
                <input className="input" placeholder="Roll" value={row.roll_no} onChange={(e) => updateRow(i, { roll_no: e.target.value })} />
                <input className="input" placeholder="Student name" value={row.name} onChange={(e) => updateRow(i, { name: e.target.value })} />
                <input className="input" placeholder="Parent name" value={row.parent_name ?? ""} onChange={(e) => updateRow(i, { parent_name: e.target.value })} />
                <input className="input" placeholder="Parent WhatsApp" value={row.parent_whatsapp ?? ""} onChange={(e) => updateRow(i, { parent_whatsapp: e.target.value })} />
                <button className="btn btn--ghost btn--sm" onClick={() => removeRow(i)} aria-label="Remove row">
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        <button type="button" className="btn btn--ghost btn--sm" style={{ marginTop: 12 }} onClick={addRow} disabled={school.sections.length === 0}>
          <Plus size={12} /> Add row
        </button>
      </div>
      <div className="card__foot" style={{ justifyContent: "flex-end" }}>
        <button type="button" className="btn btn--blue" disabled={busy} onClick={onNext}>
          {busy ? "Adding students…" : "Next: Review"}
        </button>
      </div>
    </section>
  );
}

// ============================================================
// Step 5: Review -- a real summary of what steps 1-4 just created.
// ============================================================

function ReviewStep({
  school, schoolKey, principal, principalContact, teachersIssued, studentsAdded, onDone,
}: {
  school: PlatformSchool;
  schoolKey: { api_key: string; notice: string } | null;
  principal: StaffKeySummary | null;
  principalContact: { name: string; email: string; mobile: string };
  teachersIssued: TeacherIssued[];
  studentsAdded: number;
  onDone: () => void;
}) {
  return (
    <section className="card">
      <div className="card__body" style={{ display: "grid", gap: 20 }}>
        <div>
          <p className="eyebrow">{school.name} is on AVAI</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
            {school.code && <span className="tag mono">{school.code}</span>}
            <span className="tag">{school.board}</span>
            <span className="tag">{[school.city, school.state].filter(Boolean).join(", ") || "—"}</span>
            {school.academic_year && <span className="tag">{school.academic_year}</span>}
            {school.sections.map((s) => (<span key={s.id} className="tag">{s.label}</span>))}
          </div>
        </div>

        {schoolKey && (
          <div>
            <p className="field__label">School key</p>
            <p className="small muted" style={{ marginTop: 2 }}>{schoolKey.notice}</p>
            <CopySecret value={schoolKey.api_key} />
          </div>
        )}

        <div>
          <p className="field__label">Principal</p>
          {principal ? (
            <>
              <p className="small" style={{ marginTop: 4 }}>
                {principalContact.name || "—"}{" "}
                <span className="muted">{[principalContact.email, principalContact.mobile].filter(Boolean).join(" · ")}</span>
              </p>
              <CopySecret value={principal.api_key} />
            </>
          ) : (
            <p className="small muted">No principal key issued.</p>
          )}
        </div>

        <div>
          <p className="field__label">
            Teachers ({teachersIssued.length})
          </p>
          {teachersIssued.length === 0 ? (
            <p className="small muted" style={{ marginTop: 4 }}>None added.</p>
          ) : (
            <div style={{ display: "grid", gap: 10, marginTop: 8 }}>
              {teachersIssued.map((t, i) => (
                <div key={i} className="ops-list__row" style={{ flexDirection: "column", alignItems: "stretch", gap: 6 }}>
                  <div>
                    <span className="strong">{t.name}</span>
                    <div className="small muted" style={{ marginTop: 2 }}>{t.assignmentSummary}</div>
                  </div>
                  <CopySecret value={t.api_key} />
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <p className="field__label">Students</p>
          <p className="small" style={{ marginTop: 4 }}>{studentsAdded} added in this wizard.</p>
        </div>
      </div>
      <div className="card__foot" style={{ justifyContent: "flex-end", gap: 10 }}>
        <Link href="/admin/schools" className="btn btn--ghost btn--sm">Back to Schools</Link>
        <button type="button" className="btn btn--blue" onClick={onDone}>
          <Check size={14} /> Done -- open the school
        </button>
      </div>
    </section>
  );
}
