"use client";

/** §5.11 -- Manage Teachers: real StaffKey (role "teacher") issuance and
 * TeacherAssignment management, principal-scoped exactly like every other roster route.
 */

import { useEffect, useState } from "react";
import { CopySecret } from "@/components/CopySecret";
import {
  api,
  type SectionSummary,
  type Subject,
  type TeacherAssignmentSpec,
  type TeacherAssignmentView,
  type TeacherKeyView,
} from "@/lib/api";
import { getApiKey } from "@/lib/session";

function assignmentLabel(a: TeacherAssignmentSpec | TeacherAssignmentView, sections: SectionSummary[]): string {
  const section = sections.find((s) => s.section_id === a.section_id);
  const label = section?.label ?? a.section_id;
  return a.type === "class" ? `Class Teacher — ${label}` : `${a.subject_code} — ${label}`;
}

export default function ManageTeachers() {
  const [teachers, setTeachers] = useState<TeacherKeyView[]>([]);
  const [sections, setSections] = useState<SectionSummary[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<TeacherKeyView | null>(null);
  const [revoking, setRevoking] = useState<TeacherKeyView | null>(null);
  const [renaming, setRenaming] = useState<TeacherKeyView | null>(null);
  const [reissuing, setReissuing] = useState<TeacherKeyView | null>(null);
  const [menuFor, setMenuFor] = useState<string | null>(null);

  async function refresh() {
    const key = getApiKey();
    if (!key) return;
    try {
      const [t, ov, subj] = await Promise.all([
        api.listTeachers(key), api.overview(key), api.subjects(key),
      ]);
      setTeachers(t);
      setSections(ov.sections);
      setSubjects(subj.subjects);
    } catch {
      setError("Could not load teachers. Try again in a minute.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="narrow">
      <div className="hero row between" style={{ alignItems: "flex-end" }}>
        <h1 style={{ margin: 0 }}>Manage Teachers</h1>
        <button type="button" onClick={() => setAdding(true)}>+ Add teacher</button>
      </div>

      {error && <p className="error">{error}</p>}
      {loading && <p className="muted">Loading…</p>}

      {!loading && teachers.length === 0 ? (
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
                <th>Label</th>
                <th>Sign-in key</th>
                <th>Assignments</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {teachers.map((t) => (
                <tr key={t.id} style={t.revoked_at ? { opacity: 0.55 } : undefined}>
                  <td>
                    {t.label || "(unnamed)"}
                    {t.revoked_at && <span className="muted"> · revoked</span>}
                  </td>
                  <td style={{ minWidth: 220 }}>
                    <CopySecret value={t.api_key} />
                  </td>
                  <td>
                    <div className="stack" style={{ gap: 3 }}>
                      {t.assignments.map((a) => (
                        <span className="small" key={a.id}>{assignmentLabel(a, sections)}</span>
                      ))}
                      {t.assignments.length === 0 && <span className="small muted">No assignments yet</span>}
                    </div>
                  </td>
                  <td style={{ position: "relative" }}>
                    {!t.revoked_at && (
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
                    )}
                    {menuFor === t.id && (
                      <div className="dropdown">
                        <button
                          type="button"
                          className="dropdown-item"
                          onClick={() => {
                            setMenuFor(null);
                            setRenaming(t);
                          }}
                        >
                          Rename
                        </button>
                        <button
                          type="button"
                          className="dropdown-item"
                          onClick={() => {
                            setMenuFor(null);
                            setReissuing(t);
                          }}
                        >
                          Reissue key
                        </button>
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
          sections={sections}
          subjects={subjects}
          onClose={() => setAdding(false)}
          onCreated={() => {
            setAdding(false);
            refresh();
          }}
        />
      )}

      {editing && (
        <EditAssignmentsModal
          teacher={editing}
          sections={sections}
          subjects={subjects}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refresh();
          }}
        />
      )}

      {revoking && (
        <RevokeConfirmModal
          teacher={revoking}
          onClose={() => setRevoking(null)}
          onConfirm={async () => {
            const key = getApiKey();
            if (key) await api.revokeTeacher(key, revoking.id);
            setRevoking(null);
            refresh();
          }}
        />
      )}

      {renaming && (
        <RenameModal
          teacher={renaming}
          onClose={() => setRenaming(null)}
          onSaved={() => {
            setRenaming(null);
            refresh();
          }}
        />
      )}

      {reissuing && (
        <ReissueModal
          teacher={reissuing}
          onClose={() => {
            setReissuing(null);
            refresh();
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
  sections,
  subjects,
  onClose,
  onCreated,
}: {
  sections: SectionSummary[];
  subjects: Subject[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [step, setStep] = useState<"name" | "key" | "assignments">("name");
  const [label, setLabel] = useState("");
  const [issued, setIssued] = useState<{ id: string; api_key: string } | null>(null);
  const [assignments, setAssignments] = useState<TeacherAssignmentSpec[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function createKey() {
    const key = getApiKey();
    if (!key) return;
    try {
      const created = await api.createTeacher(key, { label, assignments: [] });
      setIssued({ id: created.id, api_key: created.api_key });
      setStep("key");
    } catch {
      setError("Could not create this teacher key.");
    }
  }

  async function saveAssignments() {
    const key = getApiKey();
    if (!key || !issued) return onCreated();
    for (const a of assignments) {
      await api.addTeacherAssignment(key, issued.id, a);
    }
    onCreated();
  }

  return (
    <Overlay onClose={onClose}>
      {step === "name" && (
        <>
          <h3 style={{ marginTop: 0 }}>Add teacher</h3>
          <div className="field">
            <label htmlFor="tname">Label (name)</label>
            <input id="tname" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Mr. Ravi" />
          </div>
          {error && <p className="error">{error}</p>}
          <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
            <button type="button" className="secondary" onClick={onClose}>Cancel</button>
            <button type="button" disabled={!label.trim()} onClick={createKey}>Next</button>
          </div>
        </>
      )}

      {step === "key" && issued && (
        <>
          <h3 style={{ marginTop: 0 }}>Sign-in key generated</h3>
          <p className="cardnote">
            Give this key to {label}. It is shown once and cannot be retrieved again.
          </p>
          <CopySecret value={issued.api_key} />
          <button type="button" style={{ marginTop: 12 }} onClick={() => setStep("assignments")}>
            Add assignments →
          </button>
        </>
      )}

      {step === "assignments" && (
        <AssignmentEditor
          sections={sections}
          subjects={subjects}
          assignments={assignments}
          setAssignments={setAssignments}
          onDone={saveAssignments}
        />
      )}
    </Overlay>
  );
}

function EditAssignmentsModal({
  teacher,
  sections,
  subjects,
  onClose,
  onSaved,
}: {
  teacher: TeacherKeyView;
  sections: SectionSummary[];
  subjects: Subject[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [existing, setExisting] = useState(teacher.assignments);
  const [added, setAdded] = useState<TeacherAssignmentSpec[]>([]);

  async function removeExisting(id: string) {
    const key = getApiKey();
    if (!key) return;
    await api.removeTeacherAssignment(key, teacher.id, id);
    setExisting((all) => all.filter((a) => a.id !== id));
  }

  async function save() {
    const key = getApiKey();
    if (!key) return onSaved();
    for (const a of added) {
      await api.addTeacherAssignment(key, teacher.id, a);
    }
    onSaved();
  }

  return (
    <Overlay onClose={onClose}>
      <h3 style={{ marginTop: 0 }}>Edit assignments — {teacher.label || "teacher"}</h3>
      <div className="row" style={{ gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        {existing.map((a) => (
          <span key={a.id} className="badge blue" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            {assignmentLabel(a, sections)}
            <button
              type="button"
              aria-label="Remove"
              onClick={() => removeExisting(a.id)}
              style={{ border: 0, background: "transparent", cursor: "pointer", color: "inherit", padding: 0 }}
            >
              ×
            </button>
          </span>
        ))}
        {existing.length === 0 && added.length === 0 && (
          <p className="small muted">No assignments yet.</p>
        )}
      </div>
      <AssignmentEditor
        sections={sections}
        subjects={subjects}
        assignments={added}
        setAssignments={setAdded}
        onDone={save}
        doneLabel="Save"
      />
    </Overlay>
  );
}

function AssignmentEditor({
  sections,
  subjects,
  assignments,
  setAssignments,
  onDone,
  doneLabel = "Done",
}: {
  sections: SectionSummary[];
  subjects: Subject[];
  assignments: TeacherAssignmentSpec[];
  setAssignments: (a: TeacherAssignmentSpec[]) => void;
  onDone: () => void;
  doneLabel?: string;
}) {
  const [type, setType] = useState<"class" | "subject">("class");
  const [sectionId, setSectionId] = useState(sections[0]?.section_id ?? "");
  const [subjectCode, setSubjectCode] = useState(subjects[0]?.subject_code ?? "");

  function add() {
    if (!sectionId) return;
    if (type === "class") {
      setAssignments([...assignments, { type: "class", section_id: sectionId }]);
    } else {
      if (!subjectCode) return;
      setAssignments([...assignments, { type: "subject", section_id: sectionId, subject_code: subjectCode }]);
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
            {assignmentLabel(a, sections)}
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
          <select value={sectionId} onChange={(e) => setSectionId(e.target.value)}>
            {sections.map((s) => <option key={s.section_id} value={s.section_id}>{s.label}</option>)}
          </select>
        </div>
        {type === "subject" && (
          <div className="field" style={{ marginBottom: 0 }}>
            <label>Subject</label>
            <select value={subjectCode} onChange={(e) => setSubjectCode(e.target.value)}>
              {subjects.map((s) => <option key={s.subject_code} value={s.subject_code}>{s.label}</option>)}
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

function RenameModal({
  teacher,
  onClose,
  onSaved,
}: {
  teacher: TeacherKeyView;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [label, setLabel] = useState(teacher.label);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const key = getApiKey();
    if (!key || !label.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api.renameTeacher(key, teacher.id, label.trim());
      onSaved();
    } catch {
      setError("Could not rename this teacher.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Overlay onClose={onClose}>
      <h3 style={{ marginTop: 0 }}>Rename teacher</h3>
      <div className="field">
        <label htmlFor="rname">Label (name)</label>
        <input
          id="rname"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g. Mr. Ravi"
          autoFocus
        />
      </div>
      {error && <p className="error">{error}</p>}
      <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
        <button type="button" className="secondary" onClick={onClose}>Cancel</button>
        <button type="button" disabled={!label.trim() || saving} onClick={save}>
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </Overlay>
  );
}

function ReissueModal({
  teacher,
  onClose,
}: {
  teacher: TeacherKeyView;
  onClose: () => void;
}) {
  const [issued, setIssued] = useState<{ api_key: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function reissue() {
    const key = getApiKey();
    if (!key) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.reissueTeacherKey(key, teacher.id);
      setIssued({ api_key: result.api_key });
    } catch {
      setError("Could not reissue this key.");
    } finally {
      setBusy(false);
    }
  }

  if (issued) {
    return (
      <Overlay onClose={onClose}>
        <h3 style={{ marginTop: 0 }}>New sign-in key generated</h3>
        <p className="cardnote">
          Give this key to {teacher.label || "this teacher"}. Their old key has already
          stopped working. This is shown once and cannot be retrieved again.
        </p>
        <CopySecret value={issued.api_key} />
        <div className="row" style={{ justifyContent: "flex-end", marginTop: 14 }}>
          <button type="button" onClick={onClose}>Done</button>
        </div>
      </Overlay>
    );
  }

  return (
    <Overlay onClose={onClose}>
      <h3 style={{ marginTop: 0 }}>Reissue {teacher.label || "this teacher"}&rsquo;s key?</h3>
      <p className="cardnote">
        Their current key stops working the moment a new one is issued -- useful if they
        lost it or never received it. Their assignments are kept exactly as they are.
      </p>
      {error && <p className="error">{error}</p>}
      <div className="row" style={{ justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
        <button type="button" className="secondary" onClick={onClose}>Cancel</button>
        <button type="button" disabled={busy} onClick={reissue}>
          {busy ? "Issuing…" : "Reissue key"}
        </button>
      </div>
    </Overlay>
  );
}

function RevokeConfirmModal({
  teacher,
  onClose,
  onConfirm,
}: {
  teacher: TeacherKeyView;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <Overlay onClose={onClose}>
      <h3 style={{ marginTop: 0 }}>Revoke {teacher.label || "this teacher"}&rsquo;s key?</h3>
      <p className="cardnote">
        This cannot be undone. They will no longer be able to sign in with this key.
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
