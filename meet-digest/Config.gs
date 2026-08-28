/**
 * Configuration is read from Script Properties, never hard-coded here.
 * Project Settings -> Script Properties in the Apps Script editor.
 *
 *   ANTHROPIC_API_KEY  (required)  from console.anthropic.com
 *   DRY_RUN_TO         (optional)  while set, EVERY digest goes to this address
 *                                  instead of the real recipient. Delete it to go live.
 *   LOOKBACK_HOURS     (optional)  how far back the first run reaches. Default 24.
 *   KILL_PHRASE        (optional)  default "off the record". If any transcript line
 *                                  contains it, the whole meeting is skipped and only
 *                                  the host is notified.
 */
const PROPS = PropertiesService.getScriptProperties();

const CONFIG = {
  get claudeKey()  { return PROPS.getProperty('ANTHROPIC_API_KEY'); },
  get dryRunTo()   { return PROPS.getProperty('DRY_RUN_TO') || ''; },
  get lookbackMs() { return (Number(PROPS.getProperty('LOOKBACK_HOURS')) || 24) * 36e5; },
  get killPhrase() { return (PROPS.getProperty('KILL_PHRASE') || 'off the record').toLowerCase(); },
  model: 'claude-sonnet-5',
  // Re-scan this far behind LAST_RUN so a transcript that finalised late is not missed.
  // Duplicate sends are prevented by the processed-record ledger, not by this window.
  overlapMs: 2 * 36e5,
  triggerMinutes: 15
};
