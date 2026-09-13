"use client";

// §7.2 -- Student home, "My Reports". Flat list, most recent first, no filters/search.
// TODO(backend): Dependency Index #2 -- a real version reads reports with
// `shared_with_student: true` for the signed-in student; MOCK_STUDENT_REPORTS stands in.

import Link from "next/link";
import { Mascot } from "@/components/Mascot";
import { MOCK_STUDENT_IDENTITY, MOCK_STUDENT_REPORTS } from "@/lib/mocks/student";

export default function StudentHome() {
  const reports = MOCK_STUDENT_REPORTS;

  return (
    <main>
      <div className="hero">
        <h1>Hi {MOCK_STUDENT_IDENTITY.name}</h1>
      </div>

      {reports.length === 0 ? (
        <div style={{ textAlign: "center", padding: "40px 0" }}>
          <Mascot pose="hello" size={72} />
          <p className="lede" style={{ marginTop: 14 }}>
            Nothing shared with you yet — your teacher will let you know when a report is
            ready.
          </p>
        </div>
      ) : (
        <>
          <div className="section-head">
            <h2>Your reports</h2>
          </div>
          <div className="stack" style={{ gap: 10 }}>
            {reports.map((r) => (
              <div className="card row between" key={r.reportId}>
                <div>
                  <strong>{r.subjectLabel} — {r.term}</strong>
                  <p className="cardnote">Shared {r.sharedAt}</p>
                </div>
                <Link href={`/student/report/${r.reportId}`}>
                  <button type="button">Open</button>
                </Link>
              </div>
            ))}
          </div>
        </>
      )}
    </main>
  );
}
