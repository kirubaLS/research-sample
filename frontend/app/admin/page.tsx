import Link from "next/link";

export default function AdminHome() {
  return (
    <main>
      <h1>Dashboard</h1>
      <p className="muted">Principal and admin only.</p>

      <div className="card">
        <h2>Interest profiles</h2>
        <p className="muted">
          Holland codes, stream fit and the class distribution. Profiles that were withheld
          because the response pattern was flat or invalid are marked as such.
        </p>
      </div>

      <div className="card">
        <h2>Answer scripts</h2>
        <p className="muted">
          <Link href="/admin/scan">Scan a script</Link> — capture the cover page and every page,
          then let the engine reconcile the marks against the totals.
        </p>
      </div>

      <div className="card">
        <h2>Extraction accuracy</h2>
        <p className="muted">
          The live error rate from the audit sample: 10% of scripts are re-keyed by hand,
          including cells the system was confident about. Published here rather than claimed.
        </p>
      </div>
    </main>
  );
}
