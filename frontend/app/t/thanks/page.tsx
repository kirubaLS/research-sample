/**
 * Screen 5 — the end of the student journey.
 *
 * No score. No Holland code. No stream suggestion. An interest result handed to a
 * fifteen-year-old without a counsellor beside them is how this product would do harm,
 * so the boundary is a database rule and this page is its visible half.
 */
export default function ThanksPage() {
  return (
    <main className="narrow">
      <div className="hero" style={{ textAlign: "center", paddingTop: 60 }}>
        <div
          aria-hidden
          style={{
            width: 56,
            height: 56,
            margin: "0 auto 20px",
            borderRadius: "50%",
            background: "var(--verify-soft)",
            color: "var(--verify)",
            display: "grid",
            placeItems: "center",
            fontSize: 28,
          }}
        >
          &#10003;
        </div>
        <h1>Thank you</h1>
        <p className="lede" style={{ margin: "0 auto" }}>
          Your answers have been recorded.
        </p>
      </div>

      <div className="notice" style={{ marginTop: 26 }}>
        Your school&apos;s counsellor will go through the results with you. There is nothing
        else to do here. You can close this page.
      </div>
    </main>
  );
}
