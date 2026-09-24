"use client";

/**
 * Catches a crash in the root layout itself (AuthProvider, globals.css
 * failing to apply, etc.), the one place error.tsx can't help, since
 * error.tsx renders inside the layout that might be what's broken. Kept
 * dependency-free (no components, no globals.css) so it can render even
 * when nothing else in the app can.
 */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, -apple-system, sans-serif", background: "#faf6ee", color: "#15252e" }}>
        <div
          style={{
            minHeight: "100vh",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            textAlign: "center",
            gap: 12,
            padding: 24,
          }}
        >
          <h2 style={{ margin: 0 }}>AVAI hit a problem loading</h2>
          <p style={{ color: "#6c7880", fontSize: 14, maxWidth: 420 }}>
            Something went wrong before the app could start. Reloading usually fixes this.
          </p>
          <button
            onClick={reset}
            style={{
              marginTop: 8,
              background: "#1f8a8a",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              padding: "10px 18px",
              fontSize: 14,
              cursor: "pointer",
            }}
          >
            Reload
          </button>
          {error?.digest && <div style={{ marginTop: 10, fontSize: 11, color: "#9aa0a4", fontFamily: "monospace" }}>Error {error.digest}</div>}
        </div>
      </body>
    </html>
  );
}
