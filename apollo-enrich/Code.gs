/**
 * Apollo enrichment for Google Sheets: LinkedIn URL -> email.
 *
 * Adds an "Apollo" menu. It finds the column whose header contains "linkedin",
 * sends those URLs to Apollo's bulk_match endpoint 10 at a time, and fills in
 * Email / Email Status / Full Name / Title / Company next to them.
 *
 * Rows that already have an Email Status are skipped, so re-running only
 * processes new or unfinished rows and never spends credits twice.
 */

const CONFIG = {
  LINKEDIN_HEADER: 'linkedin',          // header containing this text (case-insensitive)
  OUTPUT_COLUMNS: ['Email', 'Email Status', 'Full Name', 'Title', 'Company'],
  BATCH_SIZE: 10,                       // Apollo bulk_match maximum
  REVEAL_PERSONAL_EMAILS: false,        // true costs extra credits
  MAX_RUNTIME_MS: 5 * 60 * 1000,        // Apps Script kills runs at 6 min
  PAUSE_MS: 1000,                       // between batches, to respect rate limits
  ENDPOINT: 'https://api.apollo.io/api/v1/people/bulk_match'
};

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Apollo')
    .addItem('Find emails (this sheet)', 'enrichActiveSheet')
    .addItem('Set API key', 'setApiKey')
    .addSeparator()
    .addItem('Stop auto-continue', 'stopAutoContinue')
    .addToUi();
}

function setApiKey() {
  const ui = SpreadsheetApp.getUi();
  const res = ui.prompt('Apollo API key', 'Paste your Apollo API key:', ui.ButtonSet.OK_CANCEL);
  if (res.getSelectedButton() !== ui.Button.OK) return;
  PropertiesService.getUserProperties().setProperty('APOLLO_API_KEY', res.getResponseText().trim());
  ui.alert('API key saved.');
}

/** Menu entry: enrich whichever tab is open. */
function enrichActiveSheet() {
  const sheet = SpreadsheetApp.getActiveSheet();
  PropertiesService.getDocumentProperties().setProperty('APOLLO_SHEET', sheet.getName());
  enrichSheet_(sheet);
}

/** Time-driven continuation for sheets too big for one 6-minute run. */
function continueEnrichment() {
  deleteContinueTriggers_();
  const name = PropertiesService.getDocumentProperties().getProperty('APOLLO_SHEET');
  const sheet = name && SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name);
  if (sheet) enrichSheet_(sheet);
}

function stopAutoContinue() {
  deleteContinueTriggers_();
  notify_('Auto-continue stopped.');
}

function enrichSheet_(sheet) {
  const start = Date.now();
  const apiKey = PropertiesService.getUserProperties().getProperty('APOLLO_API_KEY');
  if (!apiKey) return notify_('Set your API key first: Apollo → Set API key');

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return notify_('No data rows found.');

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(String);
  const liIdx = headers.findIndex(h => h.toLowerCase().includes(CONFIG.LINKEDIN_HEADER));
  if (liIdx === -1) return notify_('No column with "linkedin" in its header.');

  // 1-based column numbers for each output field, creating missing headers.
  const outCols = CONFIG.OUTPUT_COLUMNS.map(name => {
    let idx = headers.indexOf(name);
    if (idx === -1) {
      headers.push(name);
      idx = headers.length - 1;
      sheet.getRange(1, idx + 1).setValue(name).setFontWeight('bold');
    }
    return idx + 1;
  });
  const statusCol = outCols[1];

  const urls = sheet.getRange(2, liIdx + 1, lastRow - 1, 1).getValues();
  const statuses = sheet.getRange(2, statusCol, lastRow - 1, 1).getValues();

  const pending = [];
  urls.forEach((r, i) => {
    const url = String(r[0]).trim();
    if (url && !String(statuses[i][0]).trim()) pending.push({ row: i + 2, url: url });
  });
  if (!pending.length) return notify_('Nothing to do — every row already has a status.');

  let done = 0;
  for (let i = 0; i < pending.length; i += CONFIG.BATCH_SIZE) {
    if (Date.now() - start > CONFIG.MAX_RUNTIME_MS) {
      scheduleContinue_();
      return notify_(`Processed ${done} rows. ${pending.length - done} left — continuing automatically in ~1 min.`);
    }

    const batch = pending.slice(i, i + CONFIG.BATCH_SIZE);
    const valid = batch.filter(p => slug_(p.url));
    batch.filter(p => !slug_(p.url)).forEach(p => writeRow_(sheet, outCols, p.row, ['', 'invalid url', '', '', '']));

    if (valid.length) {
      let matches;
      try {
        matches = bulkMatch_(apiKey, valid.map(p => p.url));
      } catch (e) {
        if (e.fatal) return notify_(e.message);  // bad key / no access: stop, don't mark rows
        valid.forEach(p => writeRow_(sheet, outCols, p.row, ['', 'error: ' + e.message.slice(0, 80), '', '', '']));
        matches = null;
      }
      if (matches) {
        const bySlug = {};
        matches.forEach(m => { if (m && m.linkedin_url) bySlug[slug_(m.linkedin_url)] = m; });
        valid.forEach((p, j) => {
          const m = bySlug[slug_(p.url)] || (matches.length === valid.length ? matches[j] : null);
          writeRow_(sheet, outCols, p.row, toRow_(m));
        });
      }
    }

    done += batch.length;
    SpreadsheetApp.flush();
    Utilities.sleep(CONFIG.PAUSE_MS);
  }

  deleteContinueTriggers_();
  notify_(`Done. Processed ${done} rows.`);
}

function bulkMatch_(apiKey, urls) {
  const url = CONFIG.ENDPOINT +
    '?reveal_personal_emails=' + CONFIG.REVEAL_PERSONAL_EMAILS +
    '&reveal_phone_number=false';
  const options = {
    method: 'post',
    contentType: 'application/json',
    headers: { 'X-Api-Key': apiKey, 'Cache-Control': 'no-cache' },
    payload: JSON.stringify({ details: urls.map(u => ({ linkedin_url: u })) }),
    muteHttpExceptions: true
  };

  for (let attempt = 0; attempt < 4; attempt++) {
    const res = UrlFetchApp.fetch(url, options);
    const code = res.getResponseCode();
    if (code === 200) return JSON.parse(res.getContentText()).matches || [];
    if (code === 429 || code >= 500) {
      Utilities.sleep(2000 * Math.pow(2, attempt));
      continue;
    }
    const err = new Error(`Apollo HTTP ${code}: ${res.getContentText().slice(0, 200)}`);
    err.fatal = code === 401 || code === 403;
    throw err;
  }
  throw new Error('Apollo rate limit: retries exhausted');
}

function toRow_(m) {
  if (!m) return ['', 'not found', '', '', ''];
  // Apollo returns a placeholder like email_not_unlocked@domain.com when it won't reveal.
  const email = m.email && !/not_unlocked/i.test(m.email) ? m.email : '';
  const company = (m.organization && m.organization.name) ||
    (m.employment_history && m.employment_history[0] && m.employment_history[0].organization_name) || '';
  return [
    email,
    email ? (m.email_status || 'found') : 'no email',
    m.name || [m.first_name, m.last_name].filter(Boolean).join(' '),
    m.title || '',
    company
  ];
}

function writeRow_(sheet, outCols, row, values) {
  outCols.forEach((col, k) => sheet.getRange(row, col).setValue(values[k]));
}

/** "https://www.linkedin.com/in/Jane-Doe/?x=1" -> "jane-doe"; "" if not a profile URL. */
function slug_(url) {
  const m = String(url || '').toLowerCase().match(/linkedin\.com\/in\/([^\/?#\s]+)/);
  return m ? m[1] : '';
}

function scheduleContinue_() {
  deleteContinueTriggers_();
  ScriptApp.newTrigger('continueEnrichment').timeBased().after(60 * 1000).create();
}

function deleteContinueTriggers_() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'continueEnrichment')
    .forEach(t => ScriptApp.deleteTrigger(t));
}

/** Toast works from both menu runs and triggers; getUi() only from menu runs. */
function notify_(msg) {
  Logger.log(msg);
  SpreadsheetApp.getActiveSpreadsheet().toast(msg, 'Apollo', 10);
}
