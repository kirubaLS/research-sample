"use client";

// §6.3 -- Subject view (Subject Teacher scope): one subject's numbers only, ever.
// [Enter marks] routes into the real existing scan/gridsheet entry flow -- only the
// "which subject/section am I scoped to" framing here is mocked.
// TODO(backend): Dependency Index #1 -- roster/scores are mocked (MOCK_CLASS_ROSTERS);
// "Share with student" is mocked for Dependency Index #2 (no real PIN issuance exists).

import Link from "next/link";
import { use, useState } from "react";
import { MOCK_CLASS_ROSTERS, subjectLabel } from "@/lib/mocks/teacher";
import { ShareWithStudentModal } from "@/components/teacher/ShareWithStudentModal";

export default function SubjectView({
  params,
}: {
  params: Promise<{ subjectCode: string; sectionId: string }>;
}) {
  const { subjectCode, sectionId } = use(params);
  const roster = MOCK_CLASS_ROSTERS[sectionId] ?? [];
  const [shareFor, setShareFor] = useState<{ studentId: string; name: string } | null>(null);

  return (
    <main className="narrow">
      <div className="hero">
        <h1>{subjectLabel(subjectCode)} · {sectionId}</h1>
      </div>

      <div className="row between" style={{ marginBottom: 14 }}>
        <p className="cardnote" style={{ margin: 0 }}>Roster &amp; marks</p>
        <Link href="/admin/answers">
          <button type="button">Enter marks</button>
        </Link>
      </div>

      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Roll</th>
              <th>Name</th>
              <th>Latest score</th>
              <th>Concept gaps</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {roster.map((row) => (
              <tr key={row.studentId}>
                <td>{row.roll}</td>
                <td>{row.name}</td>
                <td>{row.scores[subjectCode] ?? "—"}/80</td>
                <td>{row.conceptGap ?? "—"}</td>
                <td className="row" style={{ gap: 6 }}>
                  <Link href={`/teacher/student/${row.studentId}?subject=${subjectCode}`}>
                    <button type="button" className="secondary tiny">View</button>
                  </Link>
                  <button
                    type="button"
                    className="secondary tiny"
                    title="Report must be issued before it can be shared"
                    onClick={() => setShareFor({ studentId: row.studentId, name: row.name })}
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
