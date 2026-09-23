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
    <main className="wrap">
      <div className="hero">
        <p className="eyebrow">Test</p>
        <h1 style={{ margin: 0 }}>Every Test</h1>
        <p className="lede">Every paper with marks recorded in your own classes and subjects.</p>
      </div>

      {error && <p className="error">{error}</p>}
      {!tests && !error && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Mascot pose="loading" size={24} />
          <p className="muted" style={{ margin: 0 }}>Loading…</p>
        </div>
      )}
      {tests && tests.length === 0 && <p className="muted">No test has any marks recorded yet.</p>}

      {tests && tests.length > 0 && (
        <div className="tablewrap">
          <table>
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
                    <Link href={`/teacher/tests/${t.assessment_id}`}>
                      <button type="button" className="btn--ghost btn--sm">View</button>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
