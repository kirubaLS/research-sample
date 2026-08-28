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
 * Conference records for ONE meeting — the daily standup identified by MEETING_CODE.
 * Without this filter the script would also process every other call you join.
 */
function listMeetings(sinceIso) {
  const clauses = [`start_time>="${sinceIso}"`];
  if (CONFIG.meetingCode) clauses.push(`space.meeting_code = "${CONFIG.meetingCode}"`);

  return meetPaged(`conferenceRecords?filter=${encodeURIComponent(clauses.join(' AND '))}`,
                   'conferenceRecords')
    .sort((a, b) => (a.startTime || '').localeCompare(b.startTime || ''));
}

/**
 * Maps participant resource names to roster entries.
 * Returns { map: { <resourceName>: {name, email} }, unmatched: [displayNames] }.
 *
 * A participant whose display name is not in ROSTER gets no mail and is listed as
 * unmatched. Never guessed: a wrong recipient is the one failure here that actually
 * costs something.
 */
function resolveParticipants(recordName) {
  const roster = loadRoster();
  const map = {};
  const unmatched = [];

  meetPaged(`${recordName}/participants`, 'participants').forEach(p => {
    const who    = p.signedinUser || p.anonymousUser || p.phoneUser || {};
    const shown  = who.displayName || 'Unknown';
    const person = matchPerson(shown, roster);

    map[p.name] = { name: shown, email: person ? person.email : null };
    if (!person) unmatched.push(shown);
  });

  return { map, unmatched };
}

/** All transcript entries for a conference, in spoken order. */
function fetchTranscript(recordName) {
  return meetPaged(`${recordName}/transcripts`, 'transcripts')
    .flatMap(t => meetPaged(`${t.name}/entries`, 'entries'))
    .sort((a, b) => (a.startTime || '').localeCompare(b.startTime || ''));
}
