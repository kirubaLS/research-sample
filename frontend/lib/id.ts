/**
 * A session/capture id, with or without HTTPS.
 *
 * `crypto.randomUUID()` only exists in a "secure context" -- HTTPS, or localhost -- so a
 * deployment still on plain HTTP (no domain yet to get a certificate for) throws
 * "crypto.randomUUID is not a function" the instant a page that calls it loads, taking
 * the whole page down with it. Nothing here needs cryptographic randomness -- it is a
 * local grouping key for a scan session, never a security token -- so the fallback below
 * is `Math.random`, not a hardened alternative to the real thing.
 */
export function newSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const rand = () => Math.random().toString(16).slice(2).padEnd(12, "0").slice(0, 12);
  return `${Date.now().toString(16)}-${rand()}-${rand()}`;
}
