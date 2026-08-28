/**
 * ONE-TIME SETUP. Run these by hand from the Apps Script editor, in this order.
 * See SETUP.md for the full walkthrough.
 */

/** 1. Run this first. Verifies config and permissions. Sends nothing. */
function checkConfig() {
  const ok = [], bad = [];

  if (!CONFIG.meetingCode) bad.push('MEETING_CODE is not set — the script would process every call you join.');
  else ok.push(`Pinned to meeting code ${CONFIG.meetingCode}.`);

  try {
    const roster = loadRoster();
    if (!roster.length) bad.push('ROSTER is empty. Nobody can receive mail.');
    else ok.push(`Roster has ${roster.length} people: ${roster.map(p => p.name).join(', ')}.`);
  } catch (e) {
    bad.push(`ROSTER is malformed: ${e.message}`);
  }

  const key = CONFIG.provider === 'claude' ? CONFIG.claudeKey : CONFIG.geminiKey;
  if (!key) bad.push(`Provider is "${CONFIG.provider}" but its API key property is not set.`);
  else ok.push(`Provider ${CONFIG.provider}, model ${CONFIG.model}.`);

  if (!CONFIG.dryRunTo) {
    bad.push('DRY_RUN_TO is not set, so digests go to REAL recipients. Set it to your own ' +
             'address until you have reviewed a week of output.');
  } else {
    ok.push(`Dry run active — everything goes to ${CONFIG.dryRunTo}.`);
  }

  try {
    const meetings = listMeetings(new Date(Date.now() - 7 * 864e5).toISOString());
    ok.push(`Meet API reachable. ${meetings.length} matching meeting(s) in the last 7 days.`);
    if (!meetings.length) {
      bad.push('No meetings matched. Either MEETING_CODE is wrong, this account was not in ' +
               'those calls, or transcription was never switched on.');
    } else {
      const last = meetings[meetings.length - 1];
      const seen = Object.values(resolveParticipants(last.name).map);
      ok.push('Most recent meeting participants -> ' +
              seen.map(p => `${p.name}${p.email ? ` (${p.email})` : ' (NO MATCH)'}`).join(', '));
      if (!fetchTranscript(last.name).length) {
        bad.push('That meeting has no transcript. Transcription must be ON during the call.');
      }
    }
  } catch (e) {
    bad.push(`Meet API failed: ${e.message}`);
  }

  console.log(['WORKING:', ...ok.map(s => '  + ' + s), '',
               bad.length ? 'NEEDS ATTENTION:' : 'No problems found.',
               ...bad.map(s => '  - ' + s)].join('\n'));
}

/** 2. Run once against the most recent matching meeting. Respects DRY_RUN_TO. */
function testOnce() {
  const meetings = listMeetings(new Date(Date.now() - 7 * 864e5).toISOString());
  if (!meetings.length) return console.log('No matching meetings in the last 7 days.');

  const latest = meetings[meetings.length - 1];
  console.log(`Processing ${latest.name} (started ${latest.startTime})`);
  processConference(latest);
  console.log('Done. Check the inbox of ' + (CONFIG.dryRunTo || 'the participants'));
}

/** 3. Makes it automatic. Idempotent — safe to run more than once. */
function installTrigger() {
  removeTriggers();
  ScriptApp.newTrigger('main').timeBased().everyMinutes(CONFIG.triggerMinutes).create();
  console.log(`Installed. main() now runs every ${CONFIG.triggerMinutes} minutes, by itself.`);
}

/** Turns the automation off. The code stays, it just stops firing. */
function removeTriggers() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'main')
    .forEach(t => ScriptApp.deleteTrigger(t));
  console.log('Existing triggers removed.');
}

/** Forgets which meetings were processed, so they can be re-sent. */
function resetLedger() {
  PROPS.deleteProperty('PROCESSED');
  PROPS.deleteProperty('LAST_RUN');
  console.log('Ledger cleared. The next run will re-process recent meetings.');
}
