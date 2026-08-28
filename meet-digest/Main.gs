/** Entry point. This is what the time-driven trigger calls. */
function main() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return console.log('Another run is in progress. Skipping.');

  try {
    const since = PROPS.getProperty('LAST_RUN')
      ? new Date(Date.parse(PROPS.getProperty('LAST_RUN')) - CONFIG.overlapMs).toISOString()
      : new Date(Date.now() - CONFIG.lookbackMs).toISOString();

    const now       = new Date().toISOString();
    const processed = new Set(JSON.parse(PROPS.getProperty('PROCESSED') || '[]'));
    let handled     = 0;

    listMeetings(since).forEach(record => {
      if (processed.has(record.name)) return;
      if (!record.endTime) return;              // still in progress, catch it next run

      try {
        processConference(record);
        processed.add(record.name);
        handled++;
      } catch (e) {
        // Deliberately not added to the ledger, so the next run retries it.
        console.error(`${record.name} failed: ${e.message}`);
      }
    });

    // Keep the ledger bounded; the overlap window is far shorter than 200 meetings.
    PROPS.setProperty('PROCESSED', JSON.stringify([...processed].slice(-200)));
    PROPS.setProperty('LAST_RUN', now);
    console.log(`Processed ${handled} new meeting(s).`);
  } finally {
    lock.releaseLock();
  }
}

function processConference(record) {
  const { map, unmatched } = resolveParticipants(record.name);
  const entries = fetchTranscript(record.name);

  if (!entries.length) {
    return console.log(`${record.name}: no transcript — was transcription on? Skipping.`);
  }

  const script = entries.map(e => {
    const who = map[e.participant] || { name: 'Unknown' };
    return `[${(e.startTime || '').slice(11, 16)}] ${who.name}: ${e.text}`;
  }).join('\n');

  const operator = Session.getEffectiveUser().getEmail();

  if (script.toLowerCase().includes(CONFIG.killPhrase)) {
    MailApp.sendEmail(operator, 'Meeting digest withheld',
      `Someone said "${CONFIG.killPhrase}" during the meeting starting ${record.startTime}, ` +
      'so no digests were sent. Send them by hand if that is appropriate.');
    return console.log(`${record.name}: kill phrase found, withheld.`);
  }

  // Deduplicate: one person can join twice (phone + laptop) and would otherwise
  // appear as two recipients of the same address.
  const roster = [];
  const seen   = new Set();
  Object.values(map).forEach(p => {
    if (p.email && !seen.has(p.email)) { seen.add(p.email); roster.push(p); }
  });

  if (!roster.length) {
    return console.log(`${record.name}: nobody matched ROSTER (saw: ${unmatched.join(', ')}).`);
  }

  const digests = generateDigests(script, roster.map(p => p.name));

  roster.forEach(person => {
    const d = digests[person.name];
    if (d && hasContent(d)) sendDigest(person, d, record, unmatched);
    else console.log(`${person.name}: nothing worth sending.`);
  });
}

const hasContent = d =>
  (d.my_commitments || []).length ||
  (d.mentions_of_me || []).length ||
  (d.open_questions_for_me || []).length ||
  (d.decisions_affecting_me || []).length;
