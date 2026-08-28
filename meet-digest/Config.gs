/**
 * Configuration lives in Script Properties, never in this file.
 * Apps Script editor -> Project Settings -> Script Properties.
 *
 * REQUIRED
 *   MEETING_CODE     the code from your daily meeting link, e.g. "abc-mnop-xyz".
 *                    Pins the script to that one meeting so other calls are ignored.
 *   ROSTER           who gets mail, one per line:   Display Name = email@company.com
 *                    The display name must match how the person appears in Meet.
 *   GEMINI_API_KEY   from aistudio.google.com/apikey   (or ANTHROPIC_API_KEY, see AI_PROVIDER)
 *
 * OPTIONAL
 *   DRY_RUN_TO       while set, EVERY digest goes here instead of the real recipient.
 *   AI_PROVIDER      "gemini" (default) or "claude".
 *   AI_MODEL         override the default model id below.
 *   LOOKBACK_HOURS   how far back the first run reaches. Default 24.
 *   KILL_PHRASE      default "off the record". Heard in a meeting, the whole meeting
 *                    is withheld and only the operator is told.
 */
const PROPS = PropertiesService.getScriptProperties();

const DEFAULT_MODELS = {
  // Do not use gemini-2.5-*: those shut down in October 2026.
  gemini: 'gemini-3.6-flash',
  claude: 'claude-sonnet-5'
};

const CONFIG = {
  get meetingCode() { return (PROPS.getProperty('MEETING_CODE') || '').trim(); },
  get rosterRaw()   { return PROPS.getProperty('ROSTER') || ''; },
  get provider()    { return (PROPS.getProperty('AI_PROVIDER') || 'gemini').toLowerCase(); },
  get model()       { return PROPS.getProperty('AI_MODEL') || DEFAULT_MODELS[this.provider]; },
  get geminiKey()   { return PROPS.getProperty('GEMINI_API_KEY'); },
  get claudeKey()   { return PROPS.getProperty('ANTHROPIC_API_KEY'); },
  get dryRunTo()    { return PROPS.getProperty('DRY_RUN_TO') || ''; },
  get lookbackMs()  { return (Number(PROPS.getProperty('LOOKBACK_HOURS')) || 24) * 36e5; },
  get killPhrase()  { return (PROPS.getProperty('KILL_PHRASE') || 'off the record').toLowerCase(); },

  // Re-scan this far behind LAST_RUN so a transcript that finalised late is not missed.
  // Duplicate sends are prevented by the processed-record ledger, not by this window.
  overlapMs: 2 * 36e5,
  triggerMinutes: 15
};
