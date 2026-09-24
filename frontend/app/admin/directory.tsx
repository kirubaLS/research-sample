"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ClipboardPaste, Plus, Search, Trash2, X } from "lucide-react";
import { subjects } from "@/lib/avai-mock-data";
import {
  cleanPhone,
  isValidEmail,
  isValidPhone,
  newId,
  TEACHER_ROLES,
  type OpsStudent,
  type OpsTeacher,
  type SubjectAccess,
} from "@/lib/opsDirectory";

/** Shared editors for the onboarding wizard and the school page. */

/** "X-A" -> "10A". */
export function secLabel(section: string) {
  return `10${section.split("-")[1] ?? section}`;
}

export function FieldError({ children }: { children?: React.ReactNode }) {
  if (!children) return null;
  return <span className="ops-err">{children}</span>;
}

// ------------------------------------------------------------
// Subject access: which subjects, in which sections
// ------------------------------------------------------------

export function AccessMatrix({ sections, value, onChange }: { sections: string[]; value: SubjectAccess[]; onChange: (next: SubjectAccess[]) => void }) {
  const has = (subject: string, section: string) => value.find((a) => a.subject === subject)?.sections.includes(section) ?? false;

  function toggle(subject: string, section: string) {
    const current = value.find((a) => a.subject === subject)?.sections ?? [];
    const nextSections = current.includes(section) ? current.filter((s) => s !== section) : [...current, section].sort();
    const rest = value.filter((a) => a.subject !== subject);
    onChange(nextSections.length ? [...rest, { subject, sections: nextSections }].sort((a, b) => subjects.indexOf(a.subject as never) - subjects.indexOf(b.subject as never)) : rest);
  }

  function toggleRow(subject: string) {
    const all = sections.every((sec) => has(subject, sec));
    const rest = value.filter((a) => a.subject !== subject);
    onChange(all ? rest : [...rest, { subject, sections: [...sections] }]);
  }

  return (
    <div className="access-matrix" role="group" aria-label="Subject access by section">
      <div className="access-matrix__row access-matrix__row--head" style={{ gridTemplateColumns: `minmax(120px, 1.4fr) repeat(${sections.length}, minmax(52px, 1fr))` }}>
        <span>Subject</span>
        {sections.map((s) => (
          <span key={s}>{secLabel(s)}</span>
        ))}
      </div>
      {subjects.map((subject) => (
        <div key={subject} className="access-matrix__row" style={{ gridTemplateColumns: `minmax(120px, 1.4fr) repeat(${sections.length}, minmax(52px, 1fr))` }}>
          <button type="button" className="access-matrix__subject" onClick={() => toggleRow(subject)} title="Toggle every section">
            {subject}
          </button>
          {sections.map((sec) => (
            <label key={sec} className={`access-cell ${has(subject, sec) ? "access-cell--on" : ""}`}>
              <input type="checkbox" checked={has(subject, sec)} onChange={() => toggle(subject, sec)} aria-label={`${subject} in ${secLabel(sec)}`} />
            </label>
          ))}
        </div>
      ))}
    </div>
  );
}

export function accessSummary(t: Pick<OpsTeacher, "role" | "access" | "classTeacherOf">): string {
  if (t.role === "Exam cell") return "Exam cell · question papers and marks, every subject";
  const parts = t.access.map((a) => `${a.subject} (${a.sections.map(secLabel).join(", ")})`);
  if (t.classTeacherOf) parts.unshift(`Class teacher ${secLabel(t.classTeacherOf)}`);
  return parts.join(" · ") || "No access yet";
}

// ------------------------------------------------------------
// Teacher form (modal)
// ------------------------------------------------------------

export function blankTeacher(): OpsTeacher {
  return { id: newId("t"), name: "", phone: "", email: "", role: "Subject teacher", access: [], classTeacherOf: null, enabled: true, keyIssued: true, activated: false, keyRotation: 0 };
}

export function teacherErrors(t: OpsTeacher, others: OpsTeacher[]): Record<string, string> {
  const e: Record<string, string> = {};
  if (!t.name.trim()) e.name = "Enter the teacher's name.";
  if (!isValidPhone(t.phone)) e.phone = "Enter a 10-digit mobile number.";
  else if (others.some((o) => o.id !== t.id && cleanPhone(o.phone) === cleanPhone(t.phone))) e.phone = "Another teacher already uses this number.";
  if (t.email && !isValidEmail(t.email)) e.email = "Check the email address.";
  if (t.role === "Subject teacher" && t.access.length === 0 && !t.classTeacherOf) e.access = "Give at least one subject, or make them a class teacher.";
  return e;
}

export function TeacherModal({
  initial,
  sections,
  others,
  title,
  onClose,
  onSave,
}: {
  initial: OpsTeacher;
  sections: string[];
  others: OpsTeacher[];
  title: string;
  onClose: () => void;
  onSave: (t: OpsTeacher) => void;
}) {
  const [t, setT] = useState<OpsTeacher>(initial);
  const [tried, setTried] = useState(false);
  const errors = teacherErrors(t, others);
  const set = <K extends keyof OpsTeacher>(k: K, v: OpsTeacher[K]) => setT((cur) => ({ ...cur, [k]: v }));

  function submit() {
    setTried(true);
    if (Object.keys(errors).length) return;
    onSave({ ...t, name: t.name.trim(), phone: cleanPhone(t.phone), email: t.email.trim() });
  }

  return (
    <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
      <motion.div
        className="modal modal--wide"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        initial={{ y: 16, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 16, opacity: 0 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__head">
          <h3>{title}</h3>
          <button className="iconbtn" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="modal__body">
          <div className="ops-form-grid">
            <div className="field">
              <label htmlFor="t-name">Full name</label>
              <input id="t-name" className="input" value={t.name} placeholder="Mrs. Anitha Kumar" onChange={(e) => set("name", e.target.value)} />
              <FieldError>{tried && errors.name}</FieldError>
            </div>
            <div className="field">
              <label htmlFor="t-phone">Mobile / WhatsApp</label>
              <input id="t-phone" className="input" inputMode="tel" value={t.phone} placeholder="98765 43210" onChange={(e) => set("phone", e.target.value)} />
              <FieldError>{tried && errors.phone}</FieldError>
            </div>
            <div className="field">
              <label htmlFor="t-email">Email (optional)</label>
              <input id="t-email" className="input" type="email" value={t.email} onChange={(e) => set("email", e.target.value)} />
              <FieldError>{tried && errors.email}</FieldError>
            </div>
            <div className="field">
              <label htmlFor="t-role">Login type</label>
              <select id="t-role" className="select" value={t.role} onChange={(e) => set("role", e.target.value as OpsTeacher["role"])}>
                {TEACHER_ROLES.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="t-class">Class teacher of</label>
              <select id="t-class" className="select" value={t.classTeacherOf ?? ""} onChange={(e) => set("classTeacherOf", e.target.value || null)}>
                <option value="">None</option>
                {sections.map((s) => (
                  <option key={s} value={s}>
                    Class {secLabel(s)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {t.role === "Exam cell" ? (
            <p className="small muted" style={{ margin: 0 }}>
              Exam cell logins upload question papers and answer cards for every subject and section. They do not see dashboards or reports.
            </p>
          ) : (
            <div className="field">
              <label>Subjects and sections this teacher can see</label>
              <AccessMatrix sections={sections} value={t.access} onChange={(v) => set("access", v)} />
              <FieldError>{tried && errors.access}</FieldError>
            </div>
          )}
        </div>
        <div className="modal__foot">
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn--blue" onClick={submit}>
            Save teacher
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ------------------------------------------------------------
// Students: editable table per section + paste from a spreadsheet
// ------------------------------------------------------------

export function studentErrors(s: OpsStudent): string[] {
  const e: string[] = [];
  if (!s.name.trim()) e.push("name");
  if (!isValidPhone(s.whatsapp)) e.push("whatsapp");
  return e;
}

/** Rows of "name, parent name, WhatsApp" (tab or comma separated). */
export function parseStudentPaste(text: string): { name: string; parentName: string; whatsapp: string }[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.split(/\t|,/).map((c) => c.trim()))
    .filter((cells) => cells[0] && !/^(student|name)$/i.test(cells[0]))
    .map((cells) => ({ name: cells[0] ?? "", parentName: cells[1] ?? "", whatsapp: cleanPhone(cells[2] ?? "") }));
}

export function StudentsEditor({
  sections,
  students,
  onChange,
  showErrors,
  lockedIds,
}: {
  sections: string[];
  students: OpsStudent[];
  onChange: (next: OpsStudent[]) => void;
  showErrors: boolean;
  /** Students whose section and roll can't change (already being analysed). */
  lockedIds?: Set<string>;
}) {
  const [section, setSection] = useState(sections[0] ?? "");
  const [query, setQuery] = useState("");
  const [pasteOpen, setPasteOpen] = useState(false);
  const [paste, setPaste] = useState("");

  const active = sections.includes(section) ? section : sections[0] ?? "";
  const inSection = students.filter((s) => s.section === active && !s.left);
  const q = query.trim().toLowerCase();
  const shown = useMemo(
    () => (q ? inSection.filter((s) => s.name.toLowerCase().split(/\s+/).some((w) => w.startsWith(q)) || s.whatsapp.includes(q)) : inSection),
    [inSection, q],
  );

  function nextRoll() {
    const max = Math.max(0, ...students.filter((s) => s.section === active).map((s) => Number(s.rollNo) || 0));
    return String(max + 1).padStart(2, "0");
  }

  function patch(id: string, p: Partial<OpsStudent>) {
    onChange(students.map((s) => (s.id === id ? { ...s, ...p } : s)));
  }

  function addRow() {
    onChange([...students, { id: newId("s"), rollNo: nextRoll(), name: "", section: active, parentName: "", whatsapp: "" }]);
  }

  function remove(id: string) {
    if (lockedIds?.has(id)) patch(id, { left: true });
    else onChange(students.filter((s) => s.id !== id));
  }

  function importPaste() {
    const rows = parseStudentPaste(paste);
    let roll = Number(nextRoll());
    const added = rows.map((r) => ({ id: newId("s"), rollNo: String(roll++).padStart(2, "0"), section: active, ...r }));
    onChange([...students, ...added]);
    setPaste("");
    setPasteOpen(false);
  }

  const pastePreview = parseStudentPaste(paste);

  return (
    <div>
      <div className="ops-toolbar">
        <div className="tabs" role="tablist">
          {sections.map((s) => (
            <button key={s} role="tab" aria-selected={s === active} className={`tab ${s === active ? "tab--active" : ""}`} onClick={() => setSection(s)}>
              Class {secLabel(s)} ({students.filter((x) => x.section === s && !x.left).length})
            </button>
          ))}
        </div>
        <div className="ops-toolbar__right">
          <div className="searchbox">
            <Search size={15} aria-hidden="true" />
            <input className="input" type="search" placeholder="Search name or number" aria-label="Search students" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <button type="button" className="btn btn--sm" onClick={() => setPasteOpen(true)} disabled={!active}>
            <ClipboardPaste size={13} /> Paste from sheet
          </button>
          <button type="button" className="btn btn--blue btn--sm" onClick={addRow} disabled={!active}>
            <Plus size={13} /> Add student
          </button>
        </div>
      </div>

      {inSection.length === 0 ? (
        <div className="placeholder" style={{ marginTop: 12 }}>
          <p>No students in Class {secLabel(active)} yet. Add them one by one, or paste the list from a spreadsheet.</p>
        </div>
      ) : (
        <div className="table-wrap table-wrap--scroll" style={{ maxHeight: 460, marginTop: 12 }}>
          <table className="table ops-edit-table">
            <thead>
              <tr>
                <th style={{ width: 64 }}>Roll</th>
                <th>Student name</th>
                <th>Parent name</th>
                <th>Parent WhatsApp</th>
                <th style={{ width: 44 }} aria-label="Remove" />
              </tr>
            </thead>
            <tbody>
              {shown.map((s) => {
                const errs = showErrors ? studentErrors(s) : [];
                return (
                  <tr key={s.id}>
                    <td>
                      <input className="input" value={s.rollNo} aria-label="Roll number" onChange={(e) => patch(s.id, { rollNo: e.target.value.replace(/\D/g, "").slice(0, 3) })} readOnly={lockedIds?.has(s.id)} />
                    </td>
                    <td>
                      <input className={`input ${errs.includes("name") ? "input--flag" : ""}`} value={s.name} aria-label="Student name" placeholder="Student name" onChange={(e) => patch(s.id, { name: e.target.value })} />
                    </td>
                    <td>
                      <input className="input" value={s.parentName} aria-label="Parent name" placeholder="Parent name" onChange={(e) => patch(s.id, { parentName: e.target.value })} />
                    </td>
                    <td>
                      <input
                        className={`input ${errs.includes("whatsapp") ? "input--flag" : ""}`}
                        inputMode="tel"
                        value={s.whatsapp}
                        aria-label="Parent WhatsApp number"
                        placeholder="10-digit number"
                        onChange={(e) => patch(s.id, { whatsapp: e.target.value.replace(/[^\d+ ]/g, "") })}
                        onBlur={(e) => patch(s.id, { whatsapp: cleanPhone(e.target.value) })}
                      />
                    </td>
                    <td>
                      <button type="button" className="iconbtn" onClick={() => remove(s.id)} aria-label={`Remove ${s.name || "student"}`}>
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <AnimatePresence>
        {pasteOpen && (
          <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setPasteOpen(false)}>
            <motion.div className="modal modal--wide" role="dialog" aria-modal="true" aria-label="Paste students" initial={{ y: 16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 16, opacity: 0 }} onClick={(e) => e.stopPropagation()}>
              <div className="modal__head">
                <h3>Paste students into Class {secLabel(active)}</h3>
                <button className="iconbtn" onClick={() => setPasteOpen(false)} aria-label="Close">
                  <X size={16} />
                </button>
              </div>
              <div className="modal__body">
                <p className="small muted" style={{ margin: 0 }}>
                  Copy three columns from Excel or Google Sheets and paste below: <b>student name</b>, <b>parent name</b>, <b>parent WhatsApp number</b>. Roll numbers continue from the last one.
                </p>
                <textarea
                  className="input"
                  rows={8}
                  value={paste}
                  onChange={(e) => setPaste(e.target.value)}
                  placeholder={"Aarav Sharma\tRakesh Sharma\t9876543210\nDiya Nair\tSunitha Nair\t9845012345"}
                  style={{ fontFamily: "monospace", fontSize: 13 }}
                />
                {paste && (
                  <p className="small" style={{ margin: 0 }}>
                    {pastePreview.length} student{pastePreview.length === 1 ? "" : "s"} found
                    {pastePreview.filter((r) => !isValidPhone(r.whatsapp)).length > 0 &&
                      `, ${pastePreview.filter((r) => !isValidPhone(r.whatsapp)).length} without a valid WhatsApp number (they will be highlighted to fix)`}
                    .
                  </p>
                )}
              </div>
              <div className="modal__foot">
                <button className="btn" onClick={() => setPasteOpen(false)}>
                  Cancel
                </button>
                <button className="btn btn--blue" disabled={pastePreview.length === 0} onClick={importPaste}>
                  Add {pastePreview.length || ""} students
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
