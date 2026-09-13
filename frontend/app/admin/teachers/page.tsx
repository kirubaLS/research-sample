"use client";

/**
 * §5.11 -- Manage Teachers.
 *
 * TODO(backend): Dependency Index #1 -- this entire screen manages `teacher_assignment`
 * rows that don't exist in the backend yet. All state here is in-memory only (resets on
 * reload) standing in for what would be real `StaffKey`/assignment endpoints. The
 * [+ Add teacher] / [Edit] / [⋮ Revoke] flows are built to the real shape described in the
 * spec, but wired to nothing real -- see the demo banner below and per-action TODOs.
 */

import { useState } from "react";
import { CopySecret } from "@/components/CopySecret";
import {
  MOCK_MANAGED_TEACHERS,
  MOCK_SUBJECTS,
  assignmentLabel,
  mockGenerateKey,
  type MockManagedTeacher,
  type TeacherAssignment,
} from "@/lib/mocks/teacher";

const SECTIONS = ["10-A", "10-B", "10-C"];

export default function ManageTeachers() {
  const [teachers, setTeachers] = useState<MockManagedTeacher[]>(MOCK_MANAGED_TEACHERS);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<MockManagedTeacher | null>(null);
  const [revoking, setRevoking] = useState<MockManagedTeacher | null>(null);
  const [menuFor, setMenuFor] = useState<string | null>(null);

  const active = teachers.filter((t) => !t.revoked);

  return (
    <main className="narrow">
      <div
        className="notice"
        style={{ borderLeftColor: "var(--info)", background: "var(--info-soft)", marginBottom: 18 }}
      >
        <strong>Demo data.</strong> Teacher logins and assignments aren&rsquo;t backed by a
        real database yet (Dependency Index #1) — everything below resets on reload.
      </div>

      <div className="hero row between" style={{ alignItems: "flex-end" }}>
        <h1 style={{ margin: 0 }}>Manage Teachers</h1>
        <button type="button" onClick={() => setAdding(true)}>+ Add teacher</button>
      </div>

      {active.length === 0 ? (
        <div style={{ textAlign: "center", padding: "60px 0" }}>
          <p className="lede">No teacher logins yet</p>
          <button type="button" onClick={() => setAdding(true)} style={{ marginTop: 10 }}>
            + Add teacher
          </button>
        </div>
      ) : (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Assignments</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {active.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td>
                    <div className="stack" style={{ gap: 3 }}>
                      {t.assignments.map((a, i) => (
                        <span className="small" key={i}>{assignmentLabel(a)}</span>
                      ))}
                    </div>
                  </td>
                  <td style={{ position: "relative" }}>
                    <div className="row" style={{ gap: 6 }}>
                      <button type="button" className="secondary tiny" onClick={() => setEditing(t)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="secondary tiny"
                        onClick={() => setMenuFor(menuFor === t.id ? null : t.id)}
                      >
                        ⋮
                      </button>
                    </div>
                    {menuFor === t.id && (
                      <div className="dropdown">
                        <button
                          type="button"
                          className="dropdown-item risk"
                          onClick={() => {
                            setMenuFor(null);
                            setRevoking(t);
                          }}
                        >
                          Revoke key
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {adding && (
        <AddTeacherModal
          onClose={() => setAdding(false)}
          onCreate={(t) => {
            setTeachers((all) => [...all, t]);
            setAdding(false);
          }}
        />
      )}

      {editing && (
        <EditAssignmentsModal
          teacher={editing}
          onClose={() => setEditing(null)}
          onSave={(updated) => {
            setTeachers((all) => all.map((t) => (t.id === updated.id ? updated : t)));
            setEditing(null);
          }}
        />
      )}

      {revoking && (
        <RevokeConfirmModal
          teacher={revoking}
          onClose={() => setRevoking(null)}
          onConfirm={() => {
            setTeachers((all) =>
              all.map((t) => (t.id === revoking.id ? { ...t, revoked: true } : t)),
            );
            setRevoking(null);
          }}
        />
      )}

      <style jsx>{`
        .dropdown {
          position: absolute; right: 0; top: 100%; margin-top: 4px; background: var(--surface);
          border: 1px solid var(--rule); border-radius: var(--radius-sm); box-shadow: var(--shadow);
          z-index: 20; min-width: 140px;
        }
        .dropdown-item {
          display: block; width: 100%; text-align: left; border: 0; background: transparent;
          padding: 9px 12px; font-size: 13.5px; cursor: pointer;
        }
        .dropdown-item:hover { background: var(--surface-2); }
        .dropdown-item.risk { color: var(--risk); }
      `}</style>
    </main>
  );
}

function Overlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="card modal-card" onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
      <style jsx>{`
        .modal-overlay {
          position: fixed; inset: 0; background: rgba(20, 33, 61, 0.45);
          display: flex; align-items: flex-start; justify-content: center;
          padding: 8vh 16px 40px; z-index: 60; overflow-y: auto;
        }
        .modal-card { max-width: 460px; width: 100%; margin: 0; }
      `}</style>
    </div>
  );
}

function AddTeacherModal({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (t: MockManagedTeacher) => void;
}) {
  const [step, setStep] = useState<"name" | "key" | "assignments">("name");
  const [name, setName] = useState("");
  const [key] = useState(mockGenerateKey);
  const [assignments, setAssignments] = useState<TeacherAssignment[]>([]);

  return (
    <Overlay onClose={onClose}>
      {step === "name" && (
        <>
          <h3 style={{ marginTop: 0 }}>Add teacher</h3>
          <div className="field">
            <label htmlFor="tname">Name</label>
            <input id="tname" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Mr. Ravi" />
          </div>
          <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
            <button type="button" className="secondary" onClick={onClose}>Cancel</button>
            <button type="button" disabled={!name.trim()} onClick={() => setStep("key")}>Next</button>
          </div>
        </>
      )}

      {step === "key" && (
        <>
          <h3 style={{ marginTop: 0 }}>Sign-in key generated</h3>
          <p className="cardnote">
            Give this key to {name}. It is shown once and cannot be retrieved again.
          </p>
          <CopySecret value={key} />
          <p className="small muted" style={{ marginTop: 10 }}>
            TODO(backend): Dependency Index #1 — this key is generated in the browser only
            and does not sign in to anything real; no <code>teacher</code> StaffKey role
            exists yet.
          </p>
          <button type="button" style={{ marginTop: 12 }} onClick={() => setStep("assignments")}>
            Add assignments →
          </button>
        </>
      )}

      {step === "assignments" && (
        <AssignmentEditor
          assignments={assignments}
          setAssignments={setAssignments}
          onDone={() =>
            onCreate({
              id: `t-${Date.now()}`,
              name,
              assignments,
              keyIssuedAt: new Date().toISOString().slice(0, 10),
              revoked: false,
            })
          }
        />
      )}
    </Overlay>
  );
}

function EditAssignmentsModal({
  teacher,
  onClose,
  onSave,
}: {
  teacher: MockManagedTeacher;
  onClose: () => void;
  onSave: (t: MockManagedTeacher) => void;
}) {
  const [assignments, setAssignments] = useState<TeacherAssignment[]>(teacher.assignments);
  return (
    <Overlay onClose={onClose}>
      <h3 style={{ marginTop: 0 }}>Edit assignments — {teacher.name}</h3>
      <AssignmentEditor
        assignments={assignments}
        setAssignments={setAssignments}
        onDone={() => onSave({ ...teacher, assignments })}
        doneLabel="Save"
      />
    </Overlay>
  );
}

function AssignmentEditor({
  assignments,
  setAssignments,
  onDone,
  doneLabel = "Done",
}: {
  assignments: TeacherAssignment[];
  setAssignments: (a: TeacherAssignment[]) => void;
  onDone: () => void;
  doneLabel?: string;
}) {
  const [type, setType] = useState<"class" | "subject">("class");
  const [section, setSection] = useState(SECTIONS[0]);
  const [subject, setSubject] = useState(MOCK_SUBJECTS[0].code);

  function add() {
    if (type === "class") {
      setAssignments([...assignments, { type: "class", sectionId: section, sectionLabel: section, students: 30 }]);
    } else {
      const s = MOCK_SUBJECTS.find((s) => s.code === subject)!;
      setAssignments([
        ...assignments,
        { type: "subject", subjectCode: s.code, subjectLabel: s.label, sectionId: section, sectionLabel: section, students: 30 },
      ]);
    }
  }

  function remove(i: number) {
    setAssignments(assignments.filter((_, idx) => idx !== i));
  }

  return (
    <>
      <div className="row" style={{ gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        {assignments.map((a, i) => (
          <span key={i} className="badge blue" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            {assignmentLabel(a)}
            <button
              type="button"
              aria-label="Remove"
              onClick={() => remove(i)}
              style={{ border: 0, background: "transparent", cursor: "pointer", color: "inherit", padding: 0 }}
            >
              ×
            </button>
          </span>
        ))}
        {assignments.length === 0 && <p className="small muted">No assignments yet.</p>}
      </div>

      <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="field" style={{ marginBottom: 0 }}>
          <label>Type</label>
          <select value={type} onChange={(e) => setType(e.target.value as "class" | "subject")}>
            <option value="class">Class Teacher</option>
            <option value="subject">Subject Teacher</option>
          </select>
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label>Section</label>
          <select value={section} onChange={(e) => setSection(e.target.value)}>
            {SECTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        {type === "subject" && (
          <div className="field" style={{ marginBottom: 0 }}>
            <label>Subject</label>
            <select value={subject} onChange={(e) => setSubject(e.target.value)}>
              {MOCK_SUBJECTS.map((s) => <option key={s.code} value={s.code}>{s.label}</option>)}
            </select>
          </div>
        )}
        <button type="button" className="secondary" onClick={add}>Add assignment</button>
      </div>

      <div className="row" style={{ justifyContent: "flex-end", marginTop: 18 }}>
        <button type="button" onClick={onDone}>{doneLabel}</button>
      </div>
    </>
  );
}

function RevokeConfirmModal({
  teacher,
  onClose,
  onConfirm,
}: {
  teacher: MockManagedTeacher;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <Overlay onClose={onClose}>
      <h3 style={{ marginTop: 0 }}>Revoke {teacher.name}&rsquo;s key?</h3>
      <p className="cardnote">
        This cannot be undone. {teacher.name} will no longer be able to sign in with this
        key.
      </p>
      <div className="row" style={{ justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
        <button type="button" className="secondary" onClick={onClose}>Cancel</button>
        <button
          type="button"
          style={{ background: "var(--risk)", borderColor: "var(--risk)" }}
          onClick={onConfirm}
        >
          Revoke key
        </button>
      </div>
    </Overlay>
  );
}
