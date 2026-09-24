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
  return a.type === "class" ? `Class Teacher - ${label}` : `${a.subject_code} - ${label}`;
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
    <div style={{ maxWidth: 760, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <h1 className="page-title">Manage Teachers</h1>
        <button type="button" className="btn btn--primary" onClick={() => setAdding(true)}>+ Add teacher</button>
      </div>

      {error && <p style={{ color: "var(--risk)", fontSize: 13.5, marginTop: 12 }}>{error}</p>}
      {loading && <p className="muted" style={{ marginTop: 12 }}>Loading…</p>}

      {!loading && teachers.length === 0 ? (
        <div style={{ textAlign: "center", padding: "60px 0" }}>
          <p className="page-sub">No teacher logins yet</p>
          <button type="button" className="btn btn--primary" onClick={() => setAdding(true)} style={{ marginTop: 10 }}>
            + Add teacher
          </button>
        </div>
      ) : (
        <div className="table-wrap" style={{ marginTop: 20 }}>
          <table className="table">
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
                    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                      {t.assignments.map((a) => (
                        <span className="small" key={a.id}>{assignmentLabel(a, sections)}</span>
                      ))}
                      {t.assignments.length === 0 && <span className="small muted">No assignments yet</span>}
                    </div>
                  </td>
                  <td style={{ position: "relative" }}>
                    {!t.revoked_at && (
                      <div style={{ display: "flex", gap: 6 }} className="menu-wrap">
                        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing(t)}>
                          Edit
                        </button>
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          onClick={() => setMenuFor(menuFor === t.id ? null : t.id)}
                        >
                          ⋮
                        </button>
                        {menuFor === t.id && (
                          <div className="menu">
                            <button
                              type="button"
                              onClick={() => {
                                setMenuFor(null);
                                setRenaming(t);
                              }}
                            >
                              Rename
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setMenuFor(null);
                                setReissuing(t);
                              }}
                            >
                              Reissue key
                            </button>
                            <button
                              type="button"
                              className="danger"
                              onClick={() => {
                                setMenuFor(null);
                                setRevoking(t);
                              }}
                            >
                              Revoke key
                            </button>
                          </div>
                        )}
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

    </div>
  );
}

function Overlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal__body">{children}</div>
      </div>
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
            <input id="tname" className="input" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Mr. Ravi" />
          </div>
          {error && <p style={{ color: "var(--risk)", fontSize: 13.5 }}>{error}</p>}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button type="button" className="btn btn--ghost" onClick={onClose}>Cancel</button>
            <button type="button" className="btn btn--primary" disabled={!label.trim()} onClick={createKey}>Next</button>
          </div>
        </>
      )}

      {step === "key" && issued && (
        <>
          <h3 style={{ marginTop: 0 }}>Sign-in key generated</h3>
          <p className="small muted">
            Give this key to {label}. It is shown once and cannot be retrieved again.
          </p>
          <CopySecret value={issued.api_key} />
          <button type="button" className="btn btn--primary" style={{ marginTop: 12 }} onClick={() => setStep("assignments")}>
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
      <h3 style={{ marginTop: 0 }}>Edit assignments for {teacher.label || "teacher"}</h3>
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
        <button type="button" className="btn--ghost" onClick={add}>Add assignment</button>
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
        <button type="button" className="btn--ghost" onClick={onClose}>Cancel</button>
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
        <button type="button" className="btn--ghost" onClick={onClose}>Cancel</button>
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
        <button type="button" className="btn--ghost" onClick={onClose}>Cancel</button>
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
