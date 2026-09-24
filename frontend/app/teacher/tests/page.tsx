"use client";

/**
 * Every paper with a resolved mark inside this teacher key's own scope -- a subject
 * assignment never sees a paper from a subject it wasn't given, even in a section it
 * otherwise holds. Real data only: GET /admin/teacher/academics/tests.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { Mascot } from "@/components/Mascot";
import { api, type AcademicTestRow } from "@/lib/api";
import { getApiKey } from "@/lib/session";

export default function TeacherTestsPage() {
  const [tests, setTests] = useState<AcademicTestRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherAcademicsTests(key)
      .then((res) => setTests(res.tests))
      .catch(() => setError("Could not load tests."));
  }, []);

  return (
    <>
      <p className="eyebrow">Test</p>
      <h1 className="page-title" style={{ marginTop: 4 }}>Every Test</h1>
      <p className="page-sub">Every paper with marks recorded in your own classes and subjects.</p>

      {error && <p className="page-sub" style={{ color: "var(--risk)" }}>{error}</p>}
      {!tests && !error && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 16 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      )}
      {tests && tests.length === 0 && <p className="muted" style={{ marginTop: 16 }}>No test has any marks recorded yet.</p>}

      {tests && tests.length > 0 && (
        <div className="card" style={{ marginTop: 18 }}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Test</th>
                  <th>Subject</th>
                  <th>Students Marked</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {tests.map((t) => (
                  <tr key={t.assessment_id}>
                    <td className="strong">{t.title}</td>
                    <td>{t.label}</td>
                    <td className="num">{t.students_marked}</td>
                    <td>
                      <Link href={`/teacher/tests/${t.assessment_id}`} className="btn btn--ghost btn--sm">View</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
