"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { CopyLink } from "@/components/CopyLink";
import { api, ApiError, type RosterRow } from "@/lib/api";
import { getApiKey, getRole } from "@/lib/session";

const STATUS: Record<RosterRow["status"], { label: string; cls: string }> = {
  complete: { label: "Complete", cls: "green" },
  in_progress: { label: "In progress", cls: "amber" },
  not_started: { label: "Not started", cls: "" },
};

export default function RosterPage({ params }: { params: Promise<{ sectionId: string }> }) {
  const { sectionId } = use(params);
  const [data, setData] = useState<Awaited<ReturnType<typeof api.roster>> | null>(null);
  const [cohort, setCohort] = useState<Awaited<ReturnType<typeof api.cohort>> | null>(null);
  // The server is still the authority for what a save is allowed to do -- this only
  // decides whether the add/edit/remove controls render at all, the same courtesy
  // getRole()'s own doc comment describes for every other gated action in the console.
  const canManageRoster = getRole()?.can.manage_roster ?? false;

  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [newRoll, setNewRoll] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [savingAdd, setSavingAdd] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editRoll, setEditRoll] = useState("");
  const [editError, setEditError] = useState<string | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);

  const [removingId, setRemovingId] = useState<string | null>(null);

  function reload() {
    const key = getApiKey();
    if (!key) return;
    api.roster(key, sectionId).then(setData).catch(() => undefined);
  }

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api.roster(key, sectionId).then(setData).catch(() => undefined);
    api.cohort(key, sectionId).then(setCohort).catch(() => undefined);
  }, [sectionId]);

  async function onAdd() {
    const key = getApiKey();
    if (!key || !newName.trim() || !newRoll.trim()) return;
    setSavingAdd(true);
    setAddError(null);
    try {
      await api.createStudent(key, sectionId, { name: newName.trim(), roll_no: newRoll.trim() });
      setNewName("");
      setNewRoll("");
      setAdding(false);
      reload();
    } catch (e) {
      setAddError(e instanceof ApiError ? e.message : "Could not add the student.");
    } finally {
      setSavingAdd(false);
    }
  }

  function startEdit(row: RosterRow) {
    setEditingId(row.student_id);
    setEditName(row.name);
    setEditRoll(row.roll_no);
    setEditError(null);
  }

  async function onSaveEdit(studentId: string) {
    const key = getApiKey();
    if (!key || !editName.trim() || !editRoll.trim()) return;
    setSavingEdit(true);
    setEditError(null);
    try {
      await api.updateStudent(key, studentId, { name: editName.trim(), roll_no: editRoll.trim() });
      setEditingId(null);
      reload();
    } catch (e) {
      setEditError(e instanceof ApiError ? e.message : "Could not save the change.");
    } finally {
      setSavingEdit(false);
    }
  }

  async function onRemove(row: RosterRow) {
    const key = getApiKey();
    if (!key) return;
    if (
      !window.confirm(
        `Remove ${row.name} (roll ${row.roll_no})? This deletes every test session, mark ` +
          `and scanned script that names them -- it cannot be undone.`,
      )
    ) {
      return;
    }
    setRemovingId(row.student_id);
    try {
      await api.deleteStudent(key, row.student_id);
      reload();
    } catch {
      window.alert("Could not remove the student.");
    } finally {
      setRemovingId(null);
    }
  }

  if (!data) {
    return (
      <main>
        <p className="muted">Loading…</p>
      </main>
    );
  }

  return (
    <main>
      <div className="hero">
        <p className="eyebrow">
          <Link href="/admin" style={{ color: "inherit" }}>
            ← Dashboard
          </Link>
        </p>
        <h1>{data.section.label}</h1>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <label>Student link</label>
        <CopyLink path={data.section.student_path} />
      </div>

      {cohort && cohort.counted > 0 && (
        <>
          <div className="section-head">
            <h2>Where this class leans</h2>
          </div>
          <div className="card">
            {Object.entries(cohort.streams)
              .sort((a, b) => b[1] - a[1])
              .map(([stream, n]) => (
                <div className="scalerow" key={stream}>
                  <span className="nm">{stream}</span>
                  <div className="scaletrack">
                    <div
                      className="scalefill"
                      style={{ width: `${(n / cohort.counted) * 100}%` }}
                    />
                  </div>
                  <span className="pct">{n}</span>
                </div>
              ))}
            <p className="small muted" style={{ marginTop: 12, marginBottom: 0 }}>
              {cohort.counted} profile{cohort.counted === 1 ? "" : "s"} counted
              {cohort.withheld > 0 && (
                <> · {cohort.withheld} withheld as too undifferentiated to call</>
              )}
            </p>
          </div>
        </>
      )}

      <div className="section-head">
        <h2>Students</h2>
        {canManageRoster && !adding && (
          <button type="button" className="secondary tiny" onClick={() => setAdding(true)}>
            Add student
          </button>
        )}
      </div>

      {canManageRoster && adding && (
        <div className="card">
          <div className="row" style={{ gap: 8 }}>
            <div>
              <label>Roll no.</label>
              <input value={newRoll} onChange={(e) => setNewRoll(e.target.value)} autoFocus />
            </div>
            <div style={{ flex: 1 }}>
              <label>Name</label>
              <input value={newName} onChange={(e) => setNewName(e.target.value)} />
            </div>
          </div>
          {addError && (
            <p className="error">{addError}</p>
          )}
          <div className="row" style={{ gap: 8, marginTop: 8 }}>
            <button type="button" className="primary" onClick={onAdd} disabled={savingAdd}>
              {savingAdd ? "Adding…" : "Add"}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setAdding(false);
                setAddError(null);
              }}
              disabled={savingAdd}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="card flush">
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Roll</th>
                <th>Name</th>
                <th>Papers marked</th>
                <th>Interest test</th>
                <th>Code</th>
                <th>Indicated stream</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.students.map((s) => (
                <tr key={s.student_id}>
                  {editingId === s.student_id ? (
                    <>
                      <td>
                        <input
                          className="tiny"
                          value={editRoll}
                          onChange={(e) => setEditRoll(e.target.value)}
                          style={{ width: 60 }}
                        />
                      </td>
                      <td colSpan={5}>
                        <div className="row" style={{ gap: 8, alignItems: "center" }}>
                          <input value={editName} onChange={(e) => setEditName(e.target.value)} />
                          <button
                            type="button"
                            className="primary tiny"
                            onClick={() => onSaveEdit(s.student_id)}
                            disabled={savingEdit}
                          >
                            {savingEdit ? "Saving…" : "Save"}
                          </button>
                          <button
                            type="button"
                            className="secondary tiny"
                            onClick={() => setEditingId(null)}
                            disabled={savingEdit}
                          >
                            Cancel
                          </button>
                          {editError && <span className="error">{editError}</span>}
                        </div>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="num strong">{s.roll_no}</td>
                      <td className="strong">{s.name}</td>
                      <td>
                        {s.papers_marked > 0 ? (
                          `${s.papers_marked} paper${s.papers_marked === 1 ? "" : "s"}`
                        ) : (
                          <span className="muted">none yet</span>
                        )}
                      </td>
                      <td>
                        <span className={`badge ${STATUS[s.status].cls}`}>
                          {STATUS[s.status].label}
                        </span>
                        {s.validity && s.validity !== "valid" && (
                          <span className="badge red" style={{ marginLeft: 6 }}>
                            {s.validity}
                          </span>
                        )}
                      </td>
                      <td className="mono">{s.holland_code ?? "not yet"}</td>
                      <td>{s.withheld ? <span className="muted">withheld</span> : (s.top_stream ?? "not yet")}</td>
                      <td>
                        <div className="row" style={{ gap: 6 }}>
                          {/* Always linked. Gating this on the interest test being complete
                              made a student who had sat a written test unreachable, which is
                              the one record a principal opens the roster to read. */}
                          <Link className="btn secondary tiny" href={`/admin/students/${s.student_id}`}>
                            Open
                          </Link>
                          {canManageRoster && (
                            <>
                              <button
                                type="button"
                                className="secondary tiny"
                                onClick={() => startEdit(s)}
                              >
                                Edit
                              </button>
                              <button
                                type="button"
                                className="danger tiny"
                                onClick={() => onRemove(s)}
                                disabled={removingId === s.student_id}
                              >
                                {removingId === s.student_id ? "Removing…" : "Remove"}
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
