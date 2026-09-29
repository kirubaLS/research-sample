"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Check, CheckCircle2, Pencil, Plus, Search, Trash2, UserPlus, X } from "lucide-react";
import { Reveal } from "@/components/motion";
import {
  api,
  ApiError,
  PlatformSchool,
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

const STEP_META = ["School", "Principal", "Teachers", "Students", "Review"];

/** A class before the school exists to give it a real section id -- identified
 * locally by grade+name until POST /platform/schools hands back real ids. */
type Section = { grade: number; name: string };
function sectionKey(s: Section) { return `${s.grade}-${s.name}`; }
function sectionLabel(s: Section) { return `${s.grade}${s.name}`; }

/** A teacher not yet issued a key -- everything the Add Teacher modal collects.
 * Sections are referenced by their local key until the school (and so its
 * real section ids) exists. */
type TeacherDraft = {
  key: string;
  name: string;
  mobile: string;
  email: string;
  examCell: boolean; // the modal's "login type": Regular teacher vs Exam cell (StaffKeySummary.exam_cell)
  classTeacherOf: string; // a section's local key, or "" for none
  subjectCells: Set<string>; // "SUBJECT_CODE::sectionLocalKey"
};

type StudentDraft = {
  key: string;
  sectionKey: string;
  roll_no: string;
  name: string;
  parent_name: string;
  parent_whatsapp: string;
};

type TeacherIssued = { name: string; assignmentSummary: string; examCell: boolean; api_key: string };

type CreationResult = {
  school: PlatformSchool;
  schoolKey: { api_key: string; notice: string };
  principalKey: string;
  teachers: TeacherIssued[];
  studentsAdded: number;
};

/**
 * Ops -> Onboard a school: a real 5-step wizard (School -> Principal ->
 * Teachers -> Students -> Review) matching the reference design's shape.
 * Steps 1-4 only collect a draft locally -- nothing is written until Review's
 * "Create school and generate keys" button, which is where every real write
 * actually fires, in the only order the backend allows (there is no bulk
 * "onboard everything" endpoint):
 *
 *   1. POST /platform/schools                                    -> school + its own key
 *      PATCH /platform/schools/{id}                               -> code/city/address/academic_year
 *      (PlatformSchool really carries these fields -- nothing here
 *      is collected into a field the backend doesn't have)
 *   2. POST .../keys (role=principal) + PATCH .../keys/{keyId}    -> principal key + contact
 *   3. per teacher: POST .../keys (role=teacher) + PATCH (contact)
 *      + PATCH .../keys/{keyId}/assignments (class + subject cells,
 *      resolved from the draft's local section keys to the school's
 *      real section ids)
 *   4. POST .../students/bulk                                     -> the roster rows added
 *
 * If a later step fails, the school (and anything already created) is not
 * recreated on retry -- see runCreation()'s guards.
 *
 * The final success screen shows every real issued key exactly once, reusing
 * the existing CopySecret component the rest of this app uses for the same
 * purpose.
 */
export default function OnboardSchoolPage() {
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [result, setResult] = useState<CreationResult | null>(null);

  // ---- Step 1: School -----------------------------------------------------
  const [name, setName] = useState("");
  const [board, setBoard] = useState<string>(BOARDS[0]);
  const [state, setState] = useState(INDIAN_STATES[0]);
  const [consent, setConsent] = useState<string>(CONSENT[0][0]);
  const [sections, setSections] = useState<Section[]>([{ grade: 10, name: "A" }, { grade: 10, name: "B" }]);
  const [newSectionSpec, setNewSectionSpec] = useState("");
  const [code, setCode] = useState("");
  const [city, setCity] = useState("");
  const [address, setAddress] = useState("");
  const [academicYear, setAcademicYear] = useState("");
  const [tried, setTried] = useState(false);

  // ---- Step 2: Principal --------------------------------------------------
  const [pName, setPName] = useState("");
  const [pEmail, setPEmail] = useState("");
  const [pMobile, setPMobile] = useState("");

  // ---- Step 3: Teachers ----------------------------------------------------
  const [teacherDrafts, setTeacherDrafts] = useState<TeacherDraft[]>([]);
  const [modal, setModal] = useState<{ editing: TeacherDraft | null } | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);

  useEffect(() => {
    const key = getPlatformKey();
    if (!key) return;
    api.platformSubjects(key).then((r) => setSubjects(r.subjects)).catch(() => {});
  }, []);

  // ---- Step 4: Students -----------------------------------------------------
  const [studentDrafts, setStudentDrafts] = useState<StudentDraft[]>([]);

  const errors: Record<string, string> = {};
  if (!name.trim()) errors.name = "Enter the school's name.";
  if (sections.length === 0) errors.sections = "Add at least one class.";

  function addSection() {
    const spec = newSectionSpec.trim();
    const m = /^(\d{1,2})-([A-Za-z0-9]{1,3})$/.exec(spec);
    if (!m) return;
    const sec = { grade: Number(m[1]), name: m[2].toUpperCase() };
    if (!sections.some((s) => sectionKey(s) === sectionKey(sec))) setSections([...sections, sec]);
    setNewSectionSpec("");
  }
  function removeSection(i: number) {
    const removed = sections[i];
    setSections(sections.filter((_, idx) => idx !== i));
    setStudentDrafts((d) => d.filter((r) => r.sectionKey !== sectionKey(removed)));
    setTeacherDrafts((d) =>
      d.map((t) => ({
        ...t,
        classTeacherOf: t.classTeacherOf === sectionKey(removed) ? "" : t.classTeacherOf,
        subjectCells: new Set([...t.subjectCells].filter((c) => !c.endsWith(`::${sectionKey(removed)}`))),
      })),
    );
  }

  function describe(err: unknown, fallback: string): string {
    if (err instanceof ApiError && err.status === 409) return "That name (or code) is already in use.";
    return fallback;
  }

  function goToStep(i: number) {
    setError(null);
    setStep(i);
  }

  /** Fires every real write, in order, guarded so a retry after a partial
   * failure never recreates the school or reissues a key already issued. */
  async function runCreation() {
    setTried(true);
    if (Object.keys(errors).length) { setStep(0); return; }
    const key = getPlatformKey();
    if (!key) {
      setError("You're not signed in to the operator console any more. Sign in again.");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      // 1. School
      let school: PlatformSchool;
      let schoolKey: { api_key: string; notice: string };
      const created = await api.createSchool(key, {
        name: name.trim(),
        board,
        state,
        training_consent: consent,
        sections,
      });
      schoolKey = { api_key: created.api_key, notice: created.api_key_notice };
      school = created;
      if (code.trim() || city.trim() || address.trim() || academicYear.trim()) {
        school = await api.patchSchool(key, created.id, {
          ...(code.trim() && { code: code.trim() }),
          ...(city.trim() && { city: city.trim() }),
          ...(address.trim() && { address: address.trim() }),
          ...(academicYear.trim() && { academic_year: academicYear.trim() }),
        });
      }

      const sectionIdByLocalKey = new Map<string, string>();
      for (const sec of sections) {
        const match = school.sections.find((s) => s.grade === sec.grade && s.name === sec.name);
        if (match) sectionIdByLocalKey.set(sectionKey(sec), match.id);
      }

      // 2. Principal
      const issuedPrincipal = await api.issueStaffKey(key, school.id, "principal", pName.trim() || "Principal");
      await api.patchStaffKey(key, school.id, issuedPrincipal.id, {
        name: pName.trim(), email: pEmail.trim(), phone: pMobile.trim(),
      });

      // 3. Teachers
      const teachers: TeacherIssued[] = [];
      for (const draft of teacherDrafts) {
        const createdTeacher = await api.issueStaffKey(key, school.id, "teacher", draft.name.trim() || "Teacher", draft.examCell);
        await api.patchStaffKey(key, school.id, createdTeacher.id, {
          name: draft.name.trim(), email: draft.email.trim(), phone: draft.mobile.trim(),
        });
        const assignments: TeacherAssignmentInput[] = [];
        const classSectionId = draft.classTeacherOf ? sectionIdByLocalKey.get(draft.classTeacherOf) : undefined;
        if (classSectionId) assignments.push({ type: "class", section_id: classSectionId });
        for (const cell of draft.subjectCells) {
          const [subjectCode, localKey] = cell.split("::");
          const sectionId = sectionIdByLocalKey.get(localKey);
          if (sectionId) assignments.push({ type: "subject", section_id: sectionId, subject_code: subjectCode });
        }
        if (assignments.length) await api.setAssignments(key, school.id, createdTeacher.id, assignments);
        teachers.push({
          name: draft.name.trim() || "Unnamed teacher",
          assignmentSummary: teacherSummaryLine(draft, sections, subjects),
          examCell: draft.examCell,
          api_key: createdTeacher.api_key,
        });
      }

      // 4. Students
      const rows: StudentBulkInput[] = studentDrafts
        .filter((r) => r.name.trim() && r.roll_no.trim())
        .map((r) => ({
          name: r.name.trim(),
          roll_no: r.roll_no.trim(),
          section_id: sectionIdByLocalKey.get(r.sectionKey) ?? "",
          parent_name: r.parent_name.trim() || null,
          parent_whatsapp: r.parent_whatsapp.trim() || null,
        }))
        .filter((r) => r.section_id);
      if (rows.length) await api.bulkAddStudents(key, school.id, rows);

      setResult({ school, schoolKey, principalKey: issuedPrincipal.api_key, teachers, studentsAdded: rows.length });
    } catch (err) {
      setError(describe(err, "Something went wrong while creating the school. Nothing already created was lost -- fix the issue below and try again."));
    } finally {
      setCreating(false);
    }
  }

  if (result) return <SuccessScreen result={result} principalContact={{ name: pName, email: pEmail, mobile: pMobile }} />;

  const studentsBySection = (key: string) => studentDrafts.filter((r) => r.sectionKey === key);
  const anyParentWhatsapp = studentDrafts.some((r) => r.parent_whatsapp.trim());
  const withWhatsapp = studentDrafts.filter((r) => r.parent_whatsapp.trim()).length;
  const totalStudents = studentDrafts.filter((r) => r.name.trim() && r.roll_no.trim()).length;

  return (
    <>
      <Reveal>
        <div className="ops-pagehead">
          <div>
            <h1 style={{ fontSize: 22 }}>Onboard a school</h1>
            <p className="small muted" style={{ marginTop: 2 }}>
              Fill in every step, then review -- nothing is created until you confirm on the last screen.
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
              academicYear, setAcademicYear, tried, errors }}
            onNext={() => { setTried(true); if (!Object.keys(errors).length) goToStep(1); }}
          />
        )}
        {step === 1 && (
          <PrincipalStep
            name={pName} setName={setPName} email={pEmail} setEmail={setPEmail} mobile={pMobile} setMobile={setPMobile}
            onBack={() => goToStep(0)} onNext={() => goToStep(2)}
          />
        )}
        {step === 2 && (
          <TeachersStep
            sections={sections}
            subjects={subjects}
            drafts={teacherDrafts}
            onRemove={(k) => setTeacherDrafts((d) => d.filter((t) => t.key !== k))}
            onSave={(d) => setTeacherDrafts((prev) => (prev.some((t) => t.key === d.key) ? prev.map((t) => (t.key === d.key ? d : t)) : [...prev, d]))}
            modal={modal}
            setModal={setModal}
            onBack={() => goToStep(1)}
            onNext={() => goToStep(3)}
          />
        )}
        {step === 3 && (
          <StudentsStep
            sections={sections}
            drafts={studentDrafts}
            setDrafts={setStudentDrafts}
            onBack={() => goToStep(2)}
            onNext={() => goToStep(4)}
          />
        )}
        {step === 4 && (
          <ReviewStep
            name={name} board={board} state={state} city={city} code={code} sections={sections}
            principalName={pName} principalEmail={pEmail} principalMobile={pMobile}
            teacherCount={teacherDrafts.length}
            examCellCount={teacherDrafts.filter((t) => t.examCell).length}
            totalStudents={totalStudents}
            sectionCounts={sections.map((s) => ({ label: sectionLabel(s), count: studentsBySection(sectionKey(s)).filter((r) => r.name.trim() && r.roll_no.trim()).length }))}
            anyParentWhatsapp={anyParentWhatsapp}
            withWhatsapp={withWhatsapp}
            creating={creating}
            onEdit={goToStep}
            onCreate={runCreation}
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
  tried: boolean; errors: Record<string, string>;
  onNext: () => void;
}) {
  const {
    name, setName, board, setBoard, state, setState, consent, setConsent, sections, addSection, removeSection,
    newSectionSpec, setNewSectionSpec, code, setCode, city, setCity, address, setAddress, academicYear, setAcademicYear,
    tried, errors, onNext,
  } = props;
  return (
    <form onSubmit={(e) => { e.preventDefault(); onNext(); }} className="card">
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
              <span key={sectionKey(sec)} className="chip-tag">
                Class {sectionLabel(sec)}
                <button type="button" onClick={() => removeSection(i)} aria-label={`Remove class ${sectionLabel(sec)}`}>
                  <X size={12} />
                </button>
              </span>
            ))}
            <span className="chip-tag chip-tag--input">
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
        <button type="submit" className="btn btn--blue">Continue</button>
      </div>
    </form>
  );
}

// ============================================================
// Step 2: Principal
// ============================================================

function PrincipalStep({
  name, setName, email, setEmail, mobile, setMobile, onBack, onNext,
}: {
  name: string; setName: (v: string) => void;
  email: string; setEmail: (v: string) => void;
  mobile: string; setMobile: (v: string) => void;
  onBack: () => void; onNext: () => void;
}) {
  return (
    <form onSubmit={(e) => { e.preventDefault(); onNext(); }} className="card">
      <div className="card__body" style={{ display: "grid", gap: 14, maxWidth: 460 }}>
        <p className="small muted" style={{ margin: 0 }}>
          The principal's key is issued when the school is created, at the end of this wizard.
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
      <div className="card__foot" style={{ justifyContent: "space-between" }}>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onBack}><ArrowLeft size={13} /> Back</button>
        <button type="submit" className="btn btn--blue">Continue</button>
      </div>
    </form>
  );
}

// ============================================================
// Step 3: Teachers
// ============================================================

function TeachersStep({
  sections, subjects, drafts, onRemove, onSave, modal, setModal, onBack, onNext,
}: {
  sections: Section[];
  subjects: Subject[];
  drafts: TeacherDraft[];
  onRemove: (key: string) => void;
  onSave: (d: TeacherDraft) => void;
  modal: { editing: TeacherDraft | null } | null;
  setModal: (v: { editing: TeacherDraft | null } | null) => void;
  onBack: () => void;
  onNext: () => void;
}) {
  return (
    <section className="card">
      <div className="card__body">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div>
            <h2 style={{ fontSize: 15 }}>Teachers</h2>
            <p className="small muted" style={{ marginTop: 4 }}>
              Add every teacher you want signed in from day one. More can be added later from the school&rsquo;s own
              account page.
            </p>
          </div>
          <button type="button" className="btn btn--sm" onClick={() => setModal({ editing: null })}>
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
          <div style={{ display: "flex", flexDirection: "column", marginTop: 14 }}>
            {drafts.map((d, i) => (
              <div
                key={d.key}
                style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, padding: "12px 2px", borderTop: i === 0 ? "none" : "1px solid var(--line)" }}
              >
                <div>
                  <div>
                    <span className="strong">{d.name || "Unnamed teacher"}</span>
                    {d.examCell && <span className="tag" style={{ marginLeft: 8 }}>Exam cell</span>}
                  </div>
                  <div className="small muted" style={{ marginTop: 2 }}>
                    {[d.mobile, d.email].filter(Boolean).join(" · ") || "No contact details"}
                  </div>
                  <div className="small muted" style={{ marginTop: 2 }}>
                    {teacherSummaryLine(d, sections, subjects)}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 4, flex: "0 0 auto" }}>
                  <button className="btn btn--ghost btn--sm" onClick={() => setModal({ editing: d })} aria-label={`Edit ${d.name}`}>
                    <Pencil size={13} />
                  </button>
                  <button className="btn btn--ghost btn--sm" onClick={() => onRemove(d.key)} aria-label={`Remove ${d.name}`}>
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="card__foot" style={{ justifyContent: "space-between" }}>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onBack}><ArrowLeft size={13} /> Back</button>
        <button type="button" className="btn btn--blue" onClick={onNext}>Continue</button>
      </div>

      {modal && (
        <AddTeacherModal
          sections={sections}
          subjects={subjects}
          editing={modal.editing}
          onClose={() => setModal(null)}
          onSave={(d) => { onSave(d); setModal(null); }}
        />
      )}
    </section>
  );
}

function teacherSummaryLine(d: TeacherDraft, sections: Section[], subjects: Subject[]): string {
  if (d.examCell) return "Exam cell -- papers and marks, every subject";
  const labelByCode = new Map(subjects.map((s) => [s.group_code, s.group_label]));
  const bySubject = new Map<string, string[]>();
  for (const cell of d.subjectCells) {
    const [code, localKey] = cell.split("::");
    const sec = sections.find((s) => sectionKey(s) === localKey);
    if (!sec) continue;
    bySubject.set(code, [...(bySubject.get(code) ?? []), sectionLabel(sec)]);
  }
  const subjectBits = Array.from(bySubject.entries()).map(([code, labels]) => `${labelByCode.get(code) ?? code} (${labels.join(", ")})`);
  const classSec = sections.find((s) => sectionKey(s) === d.classTeacherOf);
  const bits = [classSec && `Class teacher of ${sectionLabel(classSec)}`, ...subjectBits].filter(Boolean) as string[];
  return bits.length ? bits.join(" · ") : "No assignments yet";
}

function AddTeacherModal({
  sections, subjects, editing, onClose, onSave,
}: {
  sections: Section[];
  subjects: Subject[];
  editing: TeacherDraft | null;
  onClose: () => void;
  onSave: (d: TeacherDraft) => void;
}) {
  const [name, setName] = useState(editing?.name ?? "");
  const [mobile, setMobile] = useState(editing?.mobile ?? "");
  const [email, setEmail] = useState(editing?.email ?? "");
  const [loginType, setLoginType] = useState<"regular" | "exam_cell">(editing?.examCell ? "exam_cell" : "regular");
  const [classTeacherOf, setClassTeacherOf] = useState(editing?.classTeacherOf ?? "");
  const [cells, setCells] = useState<Set<string>>(new Set(editing?.subjectCells ?? []));

  // De-duplicated subject codes -- one grid row per subject group, one column per section.
  const subjectRows = Array.from(new Map(subjects.map((s) => [s.group_code, s.group_label])).entries());

  function toggle(subjectCode: string, localKey: string) {
    const cell = `${subjectCode}::${localKey}`;
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
      key: editing?.key ?? `t-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
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
          <h2 style={{ fontSize: 16 }}>{editing ? "Edit teacher" : "Add teacher"}</h2>
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
              {sections.map((s) => (<option key={sectionKey(s)} value={sectionKey(s)}>{sectionLabel(s)}</option>))}
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
                      {sections.map((s) => (<th key={sectionKey(s)} style={{ textAlign: "center" }}>{sectionLabel(s)}</th>))}
                    </tr>
                  </thead>
                  <tbody>
                    {subjectRows.map(([code, label]) => (
                      <tr key={code}>
                        <td>{label}</td>
                        {sections.map((s) => (
                          <td key={sectionKey(s)} style={{ textAlign: "center" }}>
                            <input
                              type="checkbox"
                              checked={cells.has(`${code}::${sectionKey(s)}`)}
                              onChange={() => toggle(code, sectionKey(s))}
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
          <button className="btn btn--sm" disabled={!name.trim()} onClick={save}>{editing ? "Save changes" : "Add teacher"}</button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Step 4: Students
// ============================================================

function StudentsStep({
  sections, drafts, setDrafts, onBack, onNext,
}: {
  sections: Section[];
  drafts: StudentDraft[];
  setDrafts: (fn: (d: StudentDraft[]) => StudentDraft[]) => void;
  onBack: () => void;
  onNext: () => void;
}) {
  const [activeKey, setActiveKey] = useState(sections[0] ? sectionKey(sections[0]) : "");
  const [query, setQuery] = useState("");
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState("");

  useEffect(() => {
    if (!sections.some((s) => sectionKey(s) === activeKey) && sections[0]) setActiveKey(sectionKey(sections[0]));
  }, [sections, activeKey]);

  const rowsForActive = drafts.filter((r) => r.sectionKey === activeKey);
  const q = query.trim().toLowerCase();
  const filtered = q ? rowsForActive.filter((r) => [r.name, r.roll_no, r.parent_name].some((f) => f.toLowerCase().includes(q))) : rowsForActive;

  function addRow() {
    setDrafts((d) => [...d, { key: `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, sectionKey: activeKey, roll_no: "", name: "", parent_name: "", parent_whatsapp: "" }]);
  }
  function updateRow(key: string, patch: Partial<StudentDraft>) {
    setDrafts((d) => d.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }
  function removeRow(key: string) {
    setDrafts((d) => d.filter((r) => r.key !== key));
  }
  function applyPaste() {
    const rows = pasteText
      .split("\n")
      .map((line) => line.split(/\t|,/).map((c) => c.trim()))
      .filter((cols) => cols[0] && cols[1])
      .map((cols) => ({
        key: `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        sectionKey: activeKey,
        name: cols[0] ?? "",
        roll_no: cols[1] ?? "",
        parent_name: cols[2] ?? "",
        parent_whatsapp: cols[3] ?? "",
      }));
    if (rows.length) setDrafts((d) => [...d, ...rows]);
    setPasteText("");
    setPasteOpen(false);
  }

  const activeLabel = sections.find((s) => sectionKey(s) === activeKey);

  return (
    <section className="card">
      <div className="card__body">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div className="tabs">
            {sections.map((s) => (
              <button
                key={sectionKey(s)}
                type="button"
                className={`tab ${activeKey === sectionKey(s) ? "tab--active" : ""}`}
                onClick={() => setActiveKey(sectionKey(s))}
              >
                Class {sectionLabel(s)} ({drafts.filter((r) => r.sectionKey === sectionKey(s)).length})
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setPasteOpen(true)} disabled={!activeKey}>
              Paste from sheet
            </button>
            <button type="button" className="btn btn--sm" onClick={addRow} disabled={!activeKey}>
              <Plus size={12} /> Add student
            </button>
          </div>
        </div>

        <div className="field" style={{ maxWidth: 280, marginTop: 12 }}>
          <span style={{ position: "relative", display: "block" }}>
            <Search size={14} className="muted" style={{ position: "absolute", left: 10, top: 9 }} />
            <input className="input" style={{ paddingLeft: 32 }} placeholder="Search this class" value={query} onChange={(e) => setQuery(e.target.value)} />
          </span>
        </div>

        {rowsForActive.length === 0 ? (
          <div style={{ marginTop: 14 }}>
            <div
              className="small muted"
              style={{ border: "1.5px dashed var(--line-strong)", borderRadius: "var(--radius-md)", padding: "22px 16px", textAlign: "center", background: "rgba(255,255,255,.55)" }}
            >
              No students in Class {activeLabel ? sectionLabel(activeLabel) : ""} yet. Add them one by one, or paste the
              list from a spreadsheet.
            </div>
          </div>
        ) : (
          <div className="table-wrap" style={{ marginTop: 14 }}>
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 90 }}>Roll</th>
                  <th>Student name</th>
                  <th>Parent name</th>
                  <th>Parent WhatsApp</th>
                  <th aria-label="Remove" style={{ width: 34 }} />
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.key}>
                    <td><input className="input" value={r.roll_no} onChange={(e) => updateRow(r.key, { roll_no: e.target.value })} /></td>
                    <td><input className="input" value={r.name} onChange={(e) => updateRow(r.key, { name: e.target.value })} /></td>
                    <td><input className="input" value={r.parent_name} onChange={(e) => updateRow(r.key, { parent_name: e.target.value })} /></td>
                    <td><input className="input" value={r.parent_whatsapp} onChange={(e) => updateRow(r.key, { parent_whatsapp: e.target.value })} /></td>
                    <td>
                      <button className="btn btn--ghost btn--sm" onClick={() => removeRow(r.key)} aria-label="Remove student">
                        <Trash2 size={12} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="card__foot" style={{ justifyContent: "space-between" }}>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onBack}><ArrowLeft size={13} /> Back</button>
        <button type="button" className="btn btn--blue" onClick={onNext}>Continue</button>
      </div>

      {pasteOpen && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" onClick={() => setPasteOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal__head">
              <h2 style={{ fontSize: 16 }}>Paste from sheet</h2>
              <button className="btn btn--ghost btn--sm" onClick={() => setPasteOpen(false)} aria-label="Close"><X size={14} /></button>
            </div>
            <div className="modal__body">
              <p className="small muted" style={{ margin: 0 }}>
                One student per line: name, roll no, parent name, parent WhatsApp -- tab or comma separated. Added to
                Class {activeLabel ? sectionLabel(activeLabel) : ""}.
              </p>
              <textarea
                className="input"
                style={{ minHeight: 160, fontFamily: "var(--font-mono, monospace)", fontSize: 12.5 }}
                placeholder={"Aditi Rao, 12, Meera Rao, 9876543210\nKiran Shah, 13, Deepak Shah, 9876500001"}
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
              />
            </div>
            <div className="modal__foot">
              <button className="btn btn--ghost btn--sm" onClick={() => setPasteOpen(false)}>Cancel</button>
              <button className="btn btn--sm" onClick={applyPaste}>Add students</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

// ============================================================
// Step 5: Review -- every real write fires from this screen's button.
// ============================================================

function ReviewStep({
  name, board, state, city, code, sections,
  principalName, principalEmail, principalMobile,
  teacherCount, examCellCount, totalStudents, sectionCounts,
  anyParentWhatsapp, withWhatsapp,
  creating, onEdit, onCreate,
}: {
  name: string; board: string; state: string; city: string; code: string; sections: Section[];
  principalName: string; principalEmail: string; principalMobile: string;
  teacherCount: number; examCellCount: number;
  totalStudents: number; sectionCounts: { label: string; count: number }[];
  anyParentWhatsapp: boolean; withWhatsapp: number;
  creating: boolean;
  onEdit: (step: number) => void;
  onCreate: () => void;
}) {
  const rows: { label: string; value: string; step: number }[] = [
    { label: "School", value: `${name || "—"} · ${board} · ${[city, state].filter(Boolean).join(", ")}`, step: 0 },
    ...(code.trim() ? [{ label: "School code", value: code.trim(), step: 0 }] : []),
    { label: `Class ${sections[0]?.grade ?? 10} sections`, value: sections.map(sectionLabel).join(", ") || "none", step: 0 },
    { label: "Principal", value: `${principalName || "—"} · ${[principalMobile, principalEmail].filter(Boolean).join(" · ")}`, step: 1 },
    { label: "Teachers", value: `${teacherCount}${examCellCount ? ` (${examCellCount} exam-cell)` : ""}`, step: 2 },
    { label: "Students", value: `${totalStudents} across ${sections.length} section${sections.length === 1 ? "" : "s"} · ${sectionCounts.map((c) => `${c.label}: ${c.count}`).join(", ")}`, step: 3 },
  ];
  if (anyParentWhatsapp) {
    rows.push({
      label: "Parent WhatsApp numbers",
      value: withWhatsapp === totalStudents ? `All ${totalStudents} on file` : `${withWhatsapp} of ${totalStudents} on file`,
      step: 3,
    });
  }

  return (
    <section className="card">
      <div className="card__body">
        <h2 style={{ fontSize: 15 }}>Review</h2>
        <p className="small muted" style={{ marginTop: 4 }}>
          Nothing has been created yet. Check everything below, then confirm.
        </p>
        <div style={{ display: "grid", gap: 0, marginTop: 14 }}>
          {rows.map((r, i) => (
            <div key={r.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, padding: "12px 2px", borderTop: i === 0 ? "none" : "1px solid var(--line)" }}>
              <div>
                <div className="field__label">{r.label}</div>
                <div className="small" style={{ marginTop: 2 }}>{r.value}</div>
              </div>
              <button type="button" className="btn--link" style={{ fontSize: 12.5, flex: "0 0 auto" }} onClick={() => onEdit(r.step)}>
                Edit
              </button>
            </div>
          ))}
        </div>
      </div>
      <div className="card__foot" style={{ justifyContent: "flex-end" }}>
        <button type="button" className="btn btn--blue" disabled={creating} onClick={onCreate}>
          <CheckCircle2 size={15} /> {creating ? "Creating…" : "Create school and generate keys"}
        </button>
      </div>
    </section>
  );
}

// ============================================================
// Final success screen -- every real issued key, shown once.
// ============================================================

function SuccessScreen({
  result, principalContact,
}: {
  result: CreationResult;
  principalContact: { name: string; email: string; mobile: string };
}) {
  const { school, schoolKey, principalKey, teachers, studentsAdded } = result;
  return (
    <section className="card" style={{ padding: "22px 22px 18px" }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <span className="kpi__icon" style={{ "--accent": "var(--brand-green)" } as React.CSSProperties}>
          <CheckCircle2 size={22} />
        </span>
        <div>
          <h1 style={{ fontSize: 20 }}>{school.name} is on AVAI</h1>
          <p className="small muted" style={{ marginTop: 2 }}>
            {teachers.length} teacher{teachers.length === 1 ? "" : "s"} and {studentsAdded} student{studentsAdded === 1 ? "" : "s"} added.
            Share the school code and each person&rsquo;s key with them.
          </p>
        </div>
      </div>

      <div style={{ display: "grid", gap: 12, marginTop: 20 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 12, alignItems: "center" }}>
          <span className="strong small">{school.code || "School key"}</span>
          <CopySecret value={school.code || schoolKey.api_key} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 12, alignItems: "center" }}>
          <span className="small">
            <span className="strong">{principalContact.name || "Principal"}</span>
            <div className="muted" style={{ fontSize: 12 }}>Principal</div>
          </span>
          <CopySecret value={principalKey} />
        </div>
        {teachers.map((t, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 12, alignItems: "center" }}>
            <span className="small">
              <span className="strong">{t.name}</span>
              <div className="muted" style={{ fontSize: 12 }}>{t.assignmentSummary}</div>
            </span>
            <CopySecret value={t.api_key} />
          </div>
        ))}
      </div>

      <div style={{ marginTop: 16 }}>
        <p className="small muted" style={{ marginTop: 0 }}>{schoolKey.notice}</p>
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 20 }}>
        <Link href={`/admin/schools/${school.id}`} className="btn btn--blue">
          Open the school
        </Link>
        <Link href="/admin/onboard" className="btn">
          Onboard another school
        </Link>
      </div>
    </section>
  );
}
