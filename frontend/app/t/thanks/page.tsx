/**
 * Screen 5 — the end of the student journey.
 *
 * No score. No Holland code. No stream suggestion. An interest result handed to a
 * fifteen-year-old without a counsellor beside them is how this product would do harm,
 * so the boundary is a database rule and this page is its visible half.
 */
export default function ThanksPage() {
  return (
    <main>
      <h1>Thank you</h1>
      <p>Your answers have been recorded.</p>
      <div className="card">
        <p className="muted" style={{ margin: 0 }}>
          Your school&apos;s counsellor will go through the results with you. There is nothing
          else to do here — you can close this page.
        </p>
      </div>
    </main>
  );
}
