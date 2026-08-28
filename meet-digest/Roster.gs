/**
 * You supply the email addresses. This is deliberately simple.
 *
 * The alternative — resolving Meet's participant IDs through the Admin SDK Directory
 * API — needs a super admin to grant a directory scope, and it is the step most likely
 * to block you for days. For one daily meeting with a known team, a typed list is
 * better in every way: no admin, no extra API, and it works for external guests too.
 *
 * ROSTER property format, one person per line:
 *
 *   Kingshuk Dey = kingshuk@leadstrategus.com
 *   Ravi Kumar   = ravi@leadstrategus.com
 */
function loadRoster() {
  const roster = [];
  CONFIG.rosterRaw.split('\n').forEach(line => {
    const t = line.trim();
    if (!t || t.startsWith('#')) return;
    const i = t.indexOf('=');
    if (i < 0) throw new Error(`ROSTER line is missing "=": ${t}`);

    const name  = t.slice(0, i).trim();
    const email = t.slice(i + 1).trim();
    if (!name || !email.includes('@')) throw new Error(`ROSTER line is malformed: ${t}`);

    roster.push({ name, email, key: normaliseName(name) });
  });
  return roster;
}

const normaliseName = s => String(s).toLowerCase().replace(/[^a-z ]/g, '').replace(/\s+/g, ' ').trim();

/**
 * Meet display name -> roster entry, or null.
 * Exact normalised match first, then an unambiguous first-name match, so "Ravi" and
 * "Ravi Kumar" both land. Ambiguity never guesses — two Ravis means no match, and the
 * digest is skipped rather than sent to the wrong person.
 */
function matchPerson(displayName, roster) {
  const key = normaliseName(displayName);
  if (!key) return null;

  const exact = roster.filter(p => p.key === key);
  if (exact.length === 1) return exact[0];

  const first    = key.split(' ')[0];
  const partial  = roster.filter(p => p.key.split(' ')[0] === first);
  return partial.length === 1 ? partial[0] : null;
}
