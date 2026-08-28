const MEET_API = 'https://meet.googleapis.com/v2';

function meetApi(path) {
  const res = UrlFetchApp.fetch(`${MEET_API}/${path}`, {
    headers: { Authorization: `Bearer ${ScriptApp.getOAuthToken()}` },
    muteHttpExceptions: true
  });
  const code = res.getResponseCode();
  if (code !== 200) throw new Error(`${path} -> HTTP ${code}: ${res.getContentText()}`);
  return JSON.parse(res.getContentText());
}

/** Follows nextPageToken to the end and returns the flattened list. */
function meetPaged(path, key) {
  const out = [];
  let token = '';
  do {
    const sep  = path.includes('?') ? '&' : '?';
    const page = meetApi(path + (token ? `${sep}pageToken=${encodeURIComponent(token)}` : ''));
    out.push(...(page[key] || []));
    token = page.nextPageToken || '';
  } while (token);
  return out;
}

/**
 * Conference records this account can see — i.e. meetings it hosted or attended.
 * A script running as one person will not see meetings they were not in; that is a
 * property of the API, not a bug. See SETUP.md "Whose account should this run as".
 */
function listConferenceRecords(sinceIso) {
  const filter = encodeURIComponent(`start_time>="${sinceIso}"`);
  return meetPaged(`conferenceRecords?filter=${filter}`, 'conferenceRecords')
    .sort((a, b) => (a.startTime || '').localeCompare(b.startTime || ''));
}

/**
 * Maps participant resource names to people.
 * Returns { map: { <resourceName>: {name, email} }, unresolved: [names] }.
 *
 * Only signedinUser participants carry an ID that resolves to an email. Anonymous
 * and dial-in participants are listed as unresolved and never receive mail — a wrong
 * recipient is the one failure here that actually costs something.
 */
function buildDirectory(recordName) {
  const map = {};
  const unresolved = [];

  meetPaged(`${recordName}/participants`, 'participants').forEach(p => {
    const who   = p.signedinUser || p.anonymousUser || p.phoneUser || {};
    const entry = { name: who.displayName || 'Unknown', email: null };

    if (p.signedinUser && p.signedinUser.user) {
      const id = p.signedinUser.user.split('/').pop();
      try {
        entry.email = AdminDirectory.Users.get(id).primaryEmail;
      } catch (e) {
        unresolved.push(entry.name);   // external guest, or no directory access
      }
    } else {
      unresolved.push(entry.name);     // anonymous or phone: nothing to resolve
    }
    map[p.name] = entry;
  });

  return { map, unresolved };
}

/** All transcript entries for a conference, in spoken order. */
function fetchTranscript(recordName) {
  return meetPaged(`${recordName}/transcripts`, 'transcripts')
    .flatMap(t => meetPaged(`${t.name}/entries`, 'entries'))
    .sort((a, b) => (a.startTime || '').localeCompare(b.startTime || ''));
}
