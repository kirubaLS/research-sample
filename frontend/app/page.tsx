import Link from "next/link";

/**
 * The front door. Two audiences, two doors — the previous version described them in prose
 * and offered no way in.
 */
export default function Home() {
  return (
    <main>
      <div className="hero">
        <p className="eyebrow">CBSE Class X · Tamil Nadu</p>
        <h1>
          Turn a mark sheet into
          <br />
          something a teacher can act on.
        </h1>
        <p className="lede">
          Yaadhum reads question-level performance and says where marks were lost, whether
          the gap is recall or application, and which concepts need reteaching — plus an
          interest profile that helps a student choose a stream.
        </p>
      </div>

      <div className="grid two" style={{ marginTop: 30 }}>
        <div className="card accentbar">
          <p className="eyebrow">For students</p>
          <h2>Take the interest test</h2>
          <p className="cardnote" style={{ marginBottom: 16 }}>
            36 short questions, about eight minutes, in English, தமிழ் or हिन्दी. There are no
            right or wrong answers.
          </p>
          <div className="notice">
            Your teacher gives you a <strong>class link</strong>. It looks like{" "}
            <span className="mono">/t/&lt;class-code&gt;</span> — open that link to begin.
            There is no login and no password.
          </div>
        </div>

        <Link href="/admin" className="card accentbar verify">
          <p className="eyebrow" style={{ color: "var(--verify)" }}>
            For principals and staff
          </p>
          <h2>Open the dashboard</h2>
          <p className="cardnote" style={{ marginBottom: 16 }}>
            Class links to hand out, who has finished, each student&apos;s interest profile,
            and the answer-script scanner.
          </p>
          <span className="arrow">Sign in with your school key →</span>
        </Link>
      </div>

      <div className="section-head">
        <h2>What it does</h2>
      </div>
      <div className="grid three">
        <div className="card">
          <h3>Interest profiling</h3>
          <p className="cardnote">
            A validated six-type inventory, scored with the person&apos;s own baseline removed —
            and withheld entirely when a profile is too flat to call.
          </p>
        </div>
        <div className="card">
          <h3>Question-level diagnosis</h3>
          <p className="cardnote">
            Every mark maps to a chapter, a sub-topic and a cognitive tier, so &ldquo;weak in
            Surface Areas&rdquo; becomes &ldquo;knows the formula, can&apos;t apply it&rdquo;.
          </p>
        </div>
        <div className="card">
          <h3>Paper quality</h3>
          <p className="cardnote">
            Whether the paper matches the board&apos;s own balance of recall, application and
            analysis — and which chapters it never tested at all.
          </p>
        </div>
      </div>
    </main>
  );
}
