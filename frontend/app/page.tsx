export default function Home() {
  return (
    <main>
      <h1>Yaadhum</h1>
      <p className="muted">
        Assessment diagnostics. Students reach this system through a class link given by
        their teacher; staff sign in to the dashboard.
      </p>
      <div className="card">
        <h2>For students</h2>
        <p className="muted">
          Open the link your teacher gave you. It looks like <code>/t/&lt;class-code&gt;</code>.
        </p>
      </div>
      <div className="card">
        <h2>For staff</h2>
        <p className="muted">
          <a href="/admin">Go to the dashboard</a> to review reports and scan answer scripts.
        </p>
      </div>
    </main>
  );
}
