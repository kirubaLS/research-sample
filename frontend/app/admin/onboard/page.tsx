"use client";

import { useState } from "react";
import Link from "next/link";
import { AnimatePresence } from "framer-motion";
import { ArrowLeft, ArrowRight, Building2, Check, CheckCircle2, GraduationCap, KeyRound, Pencil, Plus, Trash2, UserRound, Users, X } from "lucide-react";
import { boards, type Board } from "@/lib/avai-admin-data";
import { useStaffSession } from "@/lib/adminState";
import {
  cleanPhone,
  formatPhone,
  isValidEmail,
  isValidPhone,
  newId,
  principalKey,
  saveDirectory,
  suggestSchoolCode,
  teacherKey,
  TODAY_ISO,
  type OpsTeacher,
  type SchoolDirectory,
} from "@/lib/opsDirectory";
import { adminSchools } from "@/lib/avai-admin-data";
import { accessSummary, blankTeacher, FieldError, secLabel, StudentsEditor, studentErrors, TeacherModal } from "../directory";

const STEPS = [
  { label: "School", icon: Building2 },
  { label: "Principal", icon: UserRound },
  { label: "Teachers", icon: GraduationCap },
  { label: "Students", icon: Users },
  { label: "Review", icon: Check },
];

const INDIAN_STATES = [
  "Andhra Pradesh", "Delhi", "Goa", "Gujarat", "Haryana", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra",
  "Odisha", "Punjab", "Rajasthan", "Tamil Nadu", "Telangana", "Uttar Pradesh", "West Bengal",
];

function blankSchool(): SchoolDirectory {
  return {
    id: newId("sch"),
    name: "",
    code: "",
    board: "CBSE",
    city: "",
    state: "Tamil Nadu",
    address: "",
    academicYear: "2026-27",
    sections: ["X-A", "X-B"],
    principal: { name: "", email: "", phone: "", keyRotation: 0 },
    teachers: [],
    students: [],
    createdAt: TODAY_ISO,
    owner: "",
    isNew: true,
  };
}

/** Ops → Onboard a school. Five steps from nothing to a school whose
 * principal and teachers can sign in, with every student and parent
 * WhatsApp number on file. */
export default function OnboardSchoolPage() {
  const { staff } = useStaffSession();
  const [step, setStep] = useState(0);
  const [d, setD] = useState<SchoolDirectory>(blankSchool);
  const [codeTouched, setCodeTouched] = useState(false);
  const [tried, setTried] = useState<Set<number>>(new Set());
  const [teacherEdit, setTeacherEdit] = useState<OpsTeacher | null>(null);
  const [created, setCreated] = useState<SchoolDirectory | null>(null);
  const [newSection, setNewSection] = useState("");

  const set = <K extends keyof SchoolDirectory>(k: K, v: SchoolDirectory[K]) => setD((cur) => ({ ...cur, [k]: v }));
  const setPrincipal = (k: keyof SchoolDirectory["principal"], v: string) => setD((cur) => ({ ...cur, principal: { ...cur.principal, [k]: v } }));

  // ---------- validation per step ----------
  const schoolErr: Record<string, string> = {};
  if (!d.name.trim()) schoolErr.name = "Enter the school's name.";
  else if (adminSchools.some((s) => s.name.toLowerCase() === d.name.trim().toLowerCase())) schoolErr.name = "A school with this name is already on AVAI.";
  if (!d.city.trim()) schoolErr.city = "Enter the city.";
  if (!/^[A-Z0-9-]{3,12}$/.test(d.code)) schoolErr.code = "Use 3 to 12 capital letters, numbers or dashes.";
  else if (adminSchools.some((s) => s.code === d.code)) schoolErr.code = "This code is taken, choose another.";
  if (d.sections.length === 0) schoolErr.sections = "Add at least one Class 10 section.";

  const principalErr: Record<string, string> = {};
  if (!d.principal.name.trim()) principalErr.name = "Enter the principal's name.";
  if (!isValidEmail(d.principal.email)) principalErr.email = "Enter a valid email.";
  if (!isValidPhone(d.principal.phone)) principalErr.phone = "Enter a 10-digit mobile number.";

  const teacherErr = d.teachers.length === 0 ? "Add at least one teacher." : "";
  const badStudents = d.students.filter((s) => studentErrors(s).length > 0).length;
  const studentErr = d.students.length === 0 ? "Add at least one student." : badStudents ? `${badStudents} student${badStudents === 1 ? " needs" : "s need"} a name or a valid WhatsApp number.` : "";

  const stepValid = [Object.keys(schoolErr).length === 0, Object.keys(principalErr).length === 0, !teacherErr, !studentErr, true];
  const showErr = tried.has(step);

  function next() {
    setTried((t) => new Set(t).add(step));
    if (!stepValid[step]) return;
    setStep((s) => Math.min(STEPS.length - 1, s + 1));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function goTo(i: number) {
    if (i <= step || stepValid.slice(0, i).every(Boolean)) setStep(i);
  }

  function onNameOrCity(name: string, city: string) {
    setD((cur) => ({ ...cur, name, city, code: codeTouched ? cur.code : name.trim() ? suggestSchoolCode(name, city) : "" }));
  }

  function addSection() {
    const letter = newSection.trim().toUpperCase().replace(/[^A-Z]/g, "").slice(0, 2);
    if (!letter) return;
    const sec = `X-${letter}`;
    if (!d.sections.includes(sec)) set("sections", [...d.sections, sec].sort());
    setNewSection("");
  }

  function removeSection(sec: string) {
    setD((cur) => ({
      ...cur,
      sections: cur.sections.filter((s) => s !== sec),
      students: cur.students.filter((s) => s.section !== sec),
      teachers: cur.teachers.map((t) => ({
        ...t,
        classTeacherOf: t.classTeacherOf === sec ? null : t.classTeacherOf,
        access: t.access.map((a) => ({ ...a, sections: a.sections.filter((s) => s !== sec) })).filter((a) => a.sections.length),
      })),
    }));
  }

  function saveTeacher(t: OpsTeacher) {
    setD((cur) => ({ ...cur, teachers: cur.teachers.some((x) => x.id === t.id) ? cur.teachers.map((x) => (x.id === t.id ? t : x)) : [...cur.teachers, t] }));
    setTeacherEdit(null);
  }

  function create() {
    const final: SchoolDirectory = {
      ...d,
      name: d.name.trim(),
      city: d.city.trim(),
      owner: staff?.id ?? "",
      principal: { ...d.principal, name: d.principal.name.trim(), email: d.principal.email.trim(), phone: cleanPhone(d.principal.phone) },
      students: d.students.map((s) => ({ ...s, name: s.name.trim(), parentName: s.parentName.trim(), whatsapp: cleanPhone(s.whatsapp) })),
    };
    saveDirectory(final, staff?.name ?? "AVAI ops", `School onboarded with ${final.teachers.length} teachers and ${final.students.length} students.`);
    setCreated(final);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  if (created) return <Created d={created} onAnother={() => { setCreated(null); setD(blankSchool()); setStep(0); setTried(new Set()); setCodeTouched(false); }} />;

  return (
    <>
      <div className="ops-pagehead">
        <div>
          <h1 style={{ fontSize: 22 }}>Onboard a school</h1>
          <p className="small muted" style={{ marginTop: 2 }}>
            Set up the school, its principal, teachers and every Class 10 student. Access keys are generated when you create it.
          </p>
        </div>
      </div>

      <ol className="ops-steps" aria-label="Onboarding steps">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          const state = i === step ? "current" : i < step ? "done" : "todo";
          return (
            <li key={s.label}>
              <button type="button" className={`ops-step ops-step--${state}`} onClick={() => goTo(i)} aria-current={i === step ? "step" : undefined}>
                <span className="ops-step__dot">{state === "done" ? <Check size={13} /> : <Icon size={13} />}</span>
                <span className="ops-step__label">{s.label}</span>
              </button>
            </li>
          );
        })}
      </ol>

      <section className="card" style={{ marginTop: 16 }}>
        <div className="card__body">
          {step === 0 && (
            <div className="ops-form-grid">
              <div className="field field--wide">
                <label htmlFor="s-name">School name</label>
                <input id="s-name" className="input" value={d.name} placeholder="Sri Vidya Mandir Senior Secondary School" onChange={(e) => onNameOrCity(e.target.value, d.city)} />
                <FieldError>{showErr && schoolErr.name}</FieldError>
              </div>
              <div className="field">
                <label htmlFor="s-city">City</label>
                <input id="s-city" className="input" value={d.city} placeholder="Chennai" onChange={(e) => onNameOrCity(d.name, e.target.value)} />
                <FieldError>{showErr && schoolErr.city}</FieldError>
              </div>
              <div className="field">
                <label htmlFor="s-state">State</label>
                <select id="s-state" className="select" value={d.state} onChange={(e) => set("state", e.target.value)}>
                  {INDIAN_STATES.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="s-board">Board</label>
                <select id="s-board" className="select" value={d.board} onChange={(e) => set("board", e.target.value as Board)}>
                  {boards.map((b) => (
                    <option key={b}>{b}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="s-year">Academic year</label>
                <input id="s-year" className="input" value={d.academicYear} onChange={(e) => set("academicYear", e.target.value)} />
              </div>
              <div className="field field--wide">
                <label htmlFor="s-address">Address</label>
                <input id="s-address" className="input" value={d.address} placeholder="Street, area, PIN code" onChange={(e) => set("address", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="s-code">School code</label>
                <input
                  id="s-code"
                  className="input mono"
                  value={d.code}
                  onChange={(e) => {
                    setCodeTouched(true);
                    set("code", e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, ""));
                  }}
                />
                <span className="small muted">Shared by everyone at this school when they sign in.</span>
                <FieldError>{showErr && schoolErr.code}</FieldError>
              </div>
              <div className="field field--wide">
                <label>Class 10 sections</label>
                <div className="chip-row">
                  {d.sections.map((sec) => (
                    <span key={sec} className="chip">
                      Class {secLabel(sec)}
                      <button type="button" onClick={() => removeSection(sec)} aria-label={`Remove section ${secLabel(sec)}`}>
                        <X size={12} />
                      </button>
                    </span>
                  ))}
                  <span className="chip chip--input">
                    10
                    <input
                      value={newSection}
                      maxLength={2}
                      placeholder="C"
                      aria-label="New section letter"
                      onChange={(e) => setNewSection(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addSection())}
                    />
                    <button type="button" onClick={addSection} aria-label="Add section">
                      <Plus size={12} />
                    </button>
                  </span>
                </div>
                <FieldError>{showErr && schoolErr.sections}</FieldError>
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="ops-form-grid">
              <div className="field field--wide">
                <label htmlFor="p-name">Principal&apos;s full name</label>
                <input id="p-name" className="input" value={d.principal.name} placeholder="Dr. Meena Subramanian" onChange={(e) => setPrincipal("name", e.target.value)} />
                <FieldError>{showErr && principalErr.name}</FieldError>
              </div>
              <div className="field">
                <label htmlFor="p-email">Email</label>
                <input id="p-email" className="input" type="email" value={d.principal.email} onChange={(e) => setPrincipal("email", e.target.value)} />
                <FieldError>{showErr && principalErr.email}</FieldError>
              </div>
              <div className="field">
                <label htmlFor="p-phone">Mobile / WhatsApp</label>
                <input id="p-phone" className="input" inputMode="tel" value={d.principal.phone} placeholder="98765 43210" onChange={(e) => setPrincipal("phone", e.target.value)} />
                <FieldError>{showErr && principalErr.phone}</FieldError>
              </div>
              <p className="small muted field--wide" style={{ margin: 0 }}>
                The principal sees every section and subject. Their access key is sent to this number and email.
              </p>
            </div>
          )}

          {step === 2 && (
            <>
              <div className="ops-toolbar">
                <p className="small muted" style={{ margin: 0 }}>
                  Give each teacher only the subjects and sections they teach. Exam cell logins handle papers and answer cards for every subject.
                </p>
                <button type="button" className="btn btn--blue btn--sm" onClick={() => setTeacherEdit(blankTeacher())}>
                  <Plus size={13} /> Add teacher
                </button>
              </div>
              {d.teachers.length === 0 ? (
                <div className="placeholder" style={{ marginTop: 12 }}>
                  <p>No teachers yet.</p>
                </div>
              ) : (
                <div className="ops-list" style={{ marginTop: 12 }}>
                  {d.teachers.map((t) => (
                    <div key={t.id} className="ops-list__row">
                      <div style={{ minWidth: 0 }}>
                        <div className="strong">{t.name}</div>
                        <div className="small muted">
                          {formatPhone(t.phone)}
                          {t.email ? ` · ${t.email}` : ""}
                        </div>
                        <div className="small" style={{ marginTop: 3 }}>
                          {accessSummary(t)}
                        </div>
                      </div>
                      <div className="ops-list__actions">
                        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setTeacherEdit(t)}>
                          <Pencil size={12} /> Edit
                        </button>
                        <button type="button" className="iconbtn" onClick={() => set("teachers", d.teachers.filter((x) => x.id !== t.id))} aria-label={`Remove ${t.name}`}>
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <FieldError>{showErr && teacherErr}</FieldError>
            </>
          )}

          {step === 3 && (
            <>
              <StudentsEditor sections={d.sections} students={d.students} onChange={(v) => set("students", v)} showErrors={showErr} />
              <div style={{ marginTop: 10 }}>
                <FieldError>{showErr && studentErr}</FieldError>
              </div>
            </>
          )}

          {step === 4 && <Review d={d} onEdit={setStep} />}
        </div>

        <div className="card__foot" style={{ justifyContent: "space-between" }}>
          <button type="button" className="btn" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>
            <ArrowLeft size={14} /> Back
          </button>
          {step < STEPS.length - 1 ? (
            <button type="button" className="btn btn--blue" onClick={next}>
              Continue <ArrowRight size={14} />
            </button>
          ) : (
            <button type="button" className="btn btn--blue" onClick={create}>
              <CheckCircle2 size={15} /> Create school and generate keys
            </button>
          )}
        </div>
      </section>

      <AnimatePresence>
        {teacherEdit && (
          <TeacherModal
            key={teacherEdit.id}
            initial={teacherEdit}
            sections={d.sections}
            others={d.teachers}
            title={d.teachers.some((t) => t.id === teacherEdit.id) ? "Edit teacher" : "Add teacher"}
            onClose={() => setTeacherEdit(null)}
            onSave={saveTeacher}
          />
        )}
      </AnimatePresence>
    </>
  );
}

function Review({ d, onEdit }: { d: SchoolDirectory; onEdit: (step: number) => void }) {
  const noNumber = d.students.filter((s) => !isValidPhone(s.whatsapp)).length;
  const rows: [string, React.ReactNode, number][] = [
    ["School", `${d.name} · ${d.board} · ${d.city}, ${d.state}`, 0],
    ["School code", <span key="c" className="mono">{d.code}</span>, 0],
    ["Class 10 sections", d.sections.map(secLabel).join(", "), 0],
    ["Principal", `${d.principal.name} · ${formatPhone(d.principal.phone)} · ${d.principal.email}`, 1],
    ["Teachers", `${d.teachers.length} (${d.teachers.filter((t) => t.role === "Exam cell").length} exam cell)`, 2],
    ["Students", `${d.students.length} across ${d.sections.length} section${d.sections.length === 1 ? "" : "s"} · ${d.sections.map((s) => `${secLabel(s)}: ${d.students.filter((x) => x.section === s).length}`).join(", ")}`, 3],
    ["Parent WhatsApp numbers", noNumber ? `${d.students.length - noNumber} on file, ${noNumber} missing` : `All ${d.students.length} on file`, 3],
  ];
  return (
    <div className="ops-review">
      {rows.map(([k, v, s]) => (
        <div key={k} className="ops-review__row">
          <span className="muted">{k}</span>
          <span>{v}</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => onEdit(s)}>
            Edit
          </button>
        </div>
      ))}
    </div>
  );
}

function Created({ d, onAnother }: { d: SchoolDirectory; onAnother: () => void }) {
  return (
    <>
      <section className="card" style={{ padding: "22px 22px 18px" }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span className="kpi__icon" style={{ "--accent": "var(--brand-green)" } as React.CSSProperties}>
            <CheckCircle2 size={22} />
          </span>
          <div>
            <h1 style={{ fontSize: 20 }}>{d.name} is on AVAI</h1>
            <p className="small muted" style={{ marginTop: 2 }}>
              {d.teachers.length} teachers and {d.students.length} students added. Share the school code and each person&apos;s key with them.
            </p>
          </div>
        </div>
        <div className="ops-keys">
          <div className="ops-keys__row ops-keys__row--head">
            <span>School code</span>
            <span className="mono strong">{d.code}</span>
          </div>
          <div className="ops-keys__row">
            <span>
              <b>{d.principal.name}</b>
              <span className="small muted"> · Principal</span>
            </span>
            <span className="mono ops-key">{principalKey(d)}</span>
          </div>
          {d.teachers.map((t) => (
            <div key={t.id} className="ops-keys__row">
              <span>
                <b>{t.name}</b>
                <span className="small muted"> · {accessSummary(t)}</span>
              </span>
              <span className="mono ops-key">{teacherKey(d.id, t)}</span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 16 }}>
          <Link href={`/admin/schools/${d.id}`} className="btn btn--blue">
            <KeyRound size={14} /> Open the school
          </Link>
          <button type="button" className="btn" onClick={onAnother}>
            <Plus size={14} /> Onboard another school
          </button>
        </div>
      </section>
    </>
  );
}
