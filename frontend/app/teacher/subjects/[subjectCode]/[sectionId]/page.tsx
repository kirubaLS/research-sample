"use client";

// §6.3 -- Subject view (Subject Teacher scope): the real teacher-scoped roster for this
// section (GET /admin/teacher/sections/{id}/students), refused unless this key holds a
// subject assignment naming both subjectCode and sectionId.
//
// "Share with student" stays a mocked affordance (Dependency Index #2 -- there is no
// real student PIN issuance yet); "Enter marks" links to the same gridsheet upload flow
// the principal uses, which now accepts a subject-assigned teacher key too
// (require_scanner_or_teacher).

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { api, type RosterRow } from "@/lib/api";
import { getApiKey } from "@/lib/session";
import { ShareWithStudentModal } from "@/components/teacher/ShareWithStudentModal";

export default function SubjectView({
  params,
}: {
  params: Promise<{ subjectCode: string; sectionId: string }>;
}) {
  const { subjectCode, sectionId } = use(params);
  const [roster, setRoster] = useState<RosterRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shareFor, setShareFor] = useState<{ studentId: string; name: string } | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) return;
    api
      .teacherRoster(key, sectionId)
      .then((res) => setRoster(res.students))
      .catch(() => setError("Could not load this class. It may not be assigned to you."));
  }, [sectionId]);

  return (
    <main className="narrow">
      <div className="hero">
        <h1>{subjectCode} · {sectionId}</h1>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="row between" style={{ marginBottom: 14 }}>
        <p className="cardnote" style={{ margin: 0 }}>Roster &amp; marks</p>
        <Link href={`/admin/answers?assessment_subject=${subjectCode}&section_id=${sectionId}`}>
          <button type="button">Enter marks</button>
        </Link>
      </div>

      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Roll</th>
              <th>Name</th>
              <th>Status</th>
              <th>Papers marked</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(roster ?? []).map((row) => (
              <tr key={row.student_id}>
                <td>{row.roll_no}</td>
                <td>{row.name}</td>
                <td>{row.status.replace("_", " ")}</td>
                <td>{row.papers_marked}</td>
                <td className="row" style={{ gap: 6 }}>
                  <Link href={`/teacher/student/${row.student_id}?subject=${subjectCode}`}>
                    <button type="button" className="secondary tiny">View</button>
                  </Link>
                  <button
                    type="button"
                    className="secondary tiny"
                    title="Report must be issued before it can be shared"
                    onClick={() => setShareFor({ studentId: row.student_id, name: row.name })}
                  >
                    Share ⋮
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {shareFor && (
        <ShareWithStudentModal studentName={shareFor.name} onClose={() => setShareFor(null)} />
      )}
    </main>
  );
}
