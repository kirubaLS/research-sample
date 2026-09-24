import Link from "next/link";
import { FileQuestion } from "lucide-react";

/** Replaces Next's bare "404 This page could not be found." with something
 * on-brand and with a way back, for any URL, valid session or not. */
export default function NotFound() {
  return (
    <div className="error-fallback">
      <div className="error-fallback__icon" style={{ background: "var(--surface-2)", color: "var(--muted)" }}>
        <FileQuestion size={26} />
      </div>
      <h2>Page not found</h2>
      <p>There&apos;s nothing at this address. It may have moved, or the link might be wrong.</p>
      <div className="error-fallback__actions">
        <Link className="btn btn--primary" href="/">
          Go home
        </Link>
      </div>
    </div>
  );
}
