/**
 * ONE-TIME SETUP. Run these by hand from the Apps Script editor, in this order.
 * See SETUP.md for the full walkthrough.
 */

/** 1. Run this first. Verifies config and permissions without sending anything. */
function checkConfig() {
  const problems = [];
  const ok = [];

  if (!CONFIG.claudeKey) problems.push('ANTHROPIC_API_KEY script property is not set.');
  else ok.push('Anthropic API key present.');

  if (!CONFIG.dryRunTo) {
    problems.push('DRY_RUN_TO is not set. This means digests go to REAL recipients. ' +
                  'Set it to your own address until you have reviewed a week of output.');
  } else {
    ok.push(`Dry run active — everything goes to ${CONFIG.dryRunTo}.`);
  }

  try {
    const n = listConferenceRecords(new Date(Date.now() - 7 * 864e5).toISOString()).length;
    ok.push(`Meet API reachable. ${n} conference record(s) in the last 7 days.`);
    if (!n) problems.push('No conference records found. Either you have not hosted a ' +
                          'transcribed meeting recently, or this account was not in them.');
  } catch (e) {
    problems.push(`Meet API failed: ${e.message}`);
  }

  try {
    AdminDirectory.Users.get(Session.getEffectiveUser().getEmail());
    ok.push('Admin Directory lookup works — participant emails will resolve.');
  } catch (e) {
    problems.push(`Admin Directory failed (${e.message}). Without this, participants ` +
                  'cannot be resolved to email addresses and nothing will send.');
  }

  console.log(['WORKING:', ...ok.map(s => '  + ' + s), '',
               problems.length ? 'NEEDS ATTENTION:' : 'No problems found.',
               ...problems.map(s => '  - ' + s)].join('\n'));
}

/** 2. Run once against recent meetings. Respects DRY_RUN_TO. */
function testOnce() {
  const since = new Date(Date.now() - 7 * 864e5).toISOString();
  const records = listConferenceRecords(since);
  if (!records.length) return console.log('No conference records in the last 7 days.');

  const latest = records[records.length - 1];
  console.log(`Processing ${latest.name} (started ${latest.startTime})`);
  processConference(latest);
  console.log('Done. Check the inbox of ' + (CONFIG.dryRunTo || 'the participants'));
}

/** 3. Makes it automatic. Idempotent — safe to run more than once. */
function installTrigger() {
  removeTriggers();
  ScriptApp.newTrigger('main').timeBased().everyMinutes(CONFIG.triggerMinutes).create();
  console.log(`Installed. main() now runs every ${CONFIG.triggerMinutes} minutes.`);
}

/** Turns the automation off. The script stays, it just stops firing. */
function removeTriggers() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'main')
    .forEach(t => ScriptApp.deleteTrigger(t));
  console.log('Existing triggers removed.');
}

/** Clears the ledger of already-processed meetings, so they can be re-sent. */
function resetLedger() {
  PROPS.deleteProperty('PROCESSED');
  PROPS.deleteProperty('LAST_RUN');
  console.log('Ledger cleared. The next run will re-process recent meetings.');
}
