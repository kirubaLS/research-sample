# Per-Person Meeting Digests from Google Meet Transcripts

**The ask.** After a team Meet call, Google drops one transcript containing everything everyone
said. You want that split per person and mailed to each person, automatically.

**The short answer.** Yes, this is very buildable, and it should take a day. But not with a Claude
connector — connectors are interactive, they only run while you are sitting in a conversation, and
there is no "when a transcript appears, do this" event inside Claude. The plumbing belongs in
Google Apps Script, which already lives inside your Workspace, already has the OAuth, and can run
on a timer for free. Claude belongs in the middle of that pipeline, called over the API, doing the
one thing scripts are bad at: deciding what actually matters to each person.

**The one design correction, and it is the important part of this document.** "Split by person"
sounds like *group the transcript lines by speaker*. Do not build that. Nobody wants to read a
transcript of their own voice — they were there. The things a person actually needs after a meeting
are mostly *not in their own utterances*:

- what they committed to, and by when
- decisions made that change their work
- questions asked **of** them that they never answered
- every place someone **else** said their name

That last one is the whole point, and grouping by speaker structurally destroys it. The correct
axis is not *who said it* but *who needs it*. One line can go to three people or none. Get this
right and the feature is genuinely loved; get it wrong and you have built an unread email.

---

## Part 1 — What Claude can and cannot do here

Checked against this account's actual connector list:

| Connector | Status | Useful here? |
|---|---|---|
| Google Drive | connected, enabled | Yes — can read the transcript Doc |
| Voicenotes | connected, enabled | No |
| Gmail | **not connected** | — |
| Google Calendar | **not connected** | — |

So today Claude can *read* the transcript out of Drive but cannot *send* the mail, and even with a
Gmail connector added the harder problem remains: **nothing triggers it.** A connector fires when a
human is in a chat. A meeting ending at 6pm on a Friday is not that.

There is a Claude-native path — Claude Code on the web supports scheduled Routines, so you could
have a session wake every hour, search Drive for new transcripts, and act. It works. It is also a
poll, it burns a model call per check whether or not a meeting happened, and it puts a chat session
in the critical path of your team's email. Fine for a two-week experiment to prove people want the
digest. Wrong as the permanent home.

**Use Claude for judgement, Apps Script for plumbing.** That split is the recommendation.

---

## Part 2 — Do not parse the Google Doc

The obvious approach is to watch the "Meet Recordings" folder in Drive, open the transcript Doc,
and regex out `Name: text`. This is the approach almost every blog post shows, and it is the wrong
one. Speaker names collide, the format drifts, and you are reverse-engineering a document that
Google intends humans to read.

The Meet REST API v2 hands you the structured version. `conferenceRecords.transcripts.entries.list`
returns entries that are **already attributed**:

```
{
  "name": "conferenceRecords/abc-123/transcripts/xyz/entries/1",
  "participant": "conferenceRecords/abc-123/participants/45678",
  "text": "I'll have the migration script ready by Thursday.",
  "languageCode": "en-US",
  "startTime": "2026-08-27T10:14:22Z",
  "endTime": "2026-08-27T10:14:26Z"
}
```

Splitting by person becomes a `groupBy`, not a parser. Worth knowing: Google documents that these
entries may not match the Doc exactly, when speakers interleave within milliseconds or someone
edits the Doc afterward. Treat the API as the source of truth and ignore the Doc entirely.

---

## Part 3 — The two genuinely hard parts

### 3.1 Turning a participant into an email address

> **Superseded in the shipped version, and this is the better call for a single daily
> meeting.** Everything below is correct, and it is still what you need to cover meetings
> across a whole domain. But if the same handful of people meet every day, *typing the email
> addresses into a config property* removes this entire section: no Admin SDK, no directory
> scope, no super admin, and it handles external guests too. `meet-digest/` matches Meet's
> `displayName` against a roster you supply and refuses to guess when a name is ambiguous.
> Keep the directory path in mind only when the roster stops being knowable in advance.


This is where the naive version breaks, and it is worth solving on day one rather than day three.
Transcript entries point at a *participant resource*, not a person. Fetch
`conferenceRecords/{id}/participants` and you get one of three shapes:

- `signedinUser` — has `displayName` **and** `user`, formatted `users/{id}`
- `anonymousUser` — `displayName` only
- `phoneUser` — dial-in, `displayName` only

Only the first is resolvable, and **`displayName` is not an email address**. The `user` ID is
documented as interoperable with both the Admin SDK Directory API and the People API, so:

1. **Primary — Admin SDK Directory** `users.get(userKey = <id>)`. Reliable, domain-wide, needs an
   admin to authorise the scope. This is the one to build.
2. **Fallback, no admin needed** — pull the Calendar event behind the meeting and match
   `displayName` against the attendee list, which does carry emails. Works fine for an internal
   team where everyone is invited. Degrades on guests.
3. **Never guess.** Anonymous and phone participants get dropped, and the host gets told who was
   dropped. Silently mailing the wrong person their colleague's action items is the one failure
   mode of this system that is actually expensive.

Spend twenty minutes verifying step 1 against your own tenant before writing anything else. If the
Directory lookup does not work for your domain, the whole architecture shifts to option 2 and you
want to know that first.

### 3.2 Deciding what each person receives

One Claude call **per meeting**, not per person. The model sees the whole transcript once and emits
a structured object keyed by participant. This is both cheaper and better: cheaper because a
60-minute transcript is roughly 8–10k tokens and you pay for it once, better because "Ravi said
Priya should own the API contract" can only be routed to Priya by something that read the whole
conversation.

Force the shape with a tool definition rather than asking for JSON in prose — the schema below is
what makes this reliable enough to send unsupervised.

---

## Part 4 — Reference implementation (Apps Script)

> **Built and ready to deploy:** the code below is now a real project in [`meet-digest/`](../meet-digest/), split into files with setup helpers, run-locking and a
> processed-meeting ledger. Follow [`meet-digest/SETUP.md`](../meet-digest/SETUP.md) to install it.
> The listing here is kept as the readable version of the same design.

Poll-based v1. No GCP project, no Pub/Sub, no deployment. Set a time-driven trigger on `main` every
15 minutes and this runs itself.

`appsscript.json`:

```json
{
  "timeZone": "Asia/Kolkata",
  "oauthScopes": [
    "https://www.googleapis.com/auth/meetings.space.readonly",
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
    "https://www.googleapis.com/auth/script.external_request",
    "https://www.googleapis.com/auth/script.send_mail",
    "https://www.googleapis.com/auth/script.scriptapp"
  ]
}
```

> Confirm the exact Meet scope string against the current API reference before shipping — Google has
> more than one Meet scope and the read surface you need depends on whether the script runs as the
> host or as a domain-wide service account.

`Code.gs`:

```javascript
const PROPS       = PropertiesService.getScriptProperties();
const CLAUDE_KEY  = PROPS.getProperty('ANTHROPIC_API_KEY');
const DRY_RUN_TO  = PROPS.getProperty('DRY_RUN_TO');   // set this to your own address at first
const MEET        = 'https://meet.googleapis.com/v2';

function main() {
  const since = PROPS.getProperty('LAST_RUN')
             || new Date(Date.now() - 864e5).toISOString();
  const now   = new Date().toISOString();

  listConferenceRecords(since).forEach(record => {
    try { processConference(record); }
    catch (e) { console.error(`${record.name}: ${e.message}`); }
  });

  PROPS.setProperty('LAST_RUN', now);
}

// ---------- Meet API ----------

function api(path) {
  const res = UrlFetchApp.fetch(`${MEET}/${path}`, {
    headers: { Authorization: `Bearer ${ScriptApp.getOAuthToken()}` },
    muteHttpExceptions: true
  });
  if (res.getResponseCode() !== 200) {
    throw new Error(`${path} -> ${res.getResponseCode()} ${res.getContentText()}`);
  }
  return JSON.parse(res.getContentText());
}

function paged(path, key) {
  const out = [];
  let token = '';
  do {
    const sep  = path.includes('?') ? '&' : '?';
    const page = api(`${path}${token ? `${sep}pageToken=${token}` : ''}`);
    out.push(...(page[key] || []));
    token = page.nextPageToken || '';
  } while (token);
  return out;
}

const listConferenceRecords = since =>
  paged(`conferenceRecords?filter=${encodeURIComponent(`start_time>="${since}"`)}`,
        'conferenceRecords');

// ---------- identity ----------

/** participantResourceName -> { name, email } */
function buildDirectory(recordName) {
  const map = {};
  const unresolved = [];

  paged(`${recordName}/participants`, 'participants').forEach(p => {
    const who   = p.signedinUser || p.anonymousUser || p.phoneUser || {};
    const entry = { name: who.displayName || 'Unknown', email: null };

    if (p.signedinUser && p.signedinUser.user) {
      const id = p.signedinUser.user.split('/').pop();
      try {
        entry.email = AdminDirectory.Users.get(id).primaryEmail;
      } catch (e) {
        unresolved.push(entry.name);          // guest, or no directory access
      }
    } else {
      unresolved.push(entry.name);            // anonymous or dial-in: never guess
    }
    map[p.name] = entry;
  });

  return { map, unresolved };
}

// ---------- pipeline ----------

function processConference(record) {
  const { map, unresolved } = buildDirectory(record.name);

  const entries = paged(`${record.name}/transcripts`, 'transcripts')
    .flatMap(t => paged(`${t.name}/entries`, 'entries'))
    .sort((a, b) => a.startTime.localeCompare(b.startTime));

  if (!entries.length) return;                // recorded but not transcribed

  const script = entries.map(e => {
    const who = map[e.participant] || { name: 'Unknown' };
    return `[${e.startTime.slice(11, 16)}] ${who.name}: ${e.text}`;
  }).join('\n');

  const roster  = Object.values(map).filter(p => p.email);
  const digests = askClaude(script, roster.map(p => p.name));

  roster.forEach(person => {
    const d = digests[person.name];
    if (d && hasContent(d)) sendDigest(person, d, record, unresolved);
  });
}

const hasContent = d =>
  (d.my_commitments || []).length ||
  (d.mentions_of_me || []).length ||
  (d.open_questions_for_me || []).length ||
  (d.decisions_affecting_me || []).length;

// ---------- Claude ----------

const DIGEST_TOOL = {
  name: 'emit_digests',
  description: 'Emit one digest per named participant.',
  input_schema: {
    type: 'object',
    properties: {
      digests: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            person:  { type: 'string' },
            summary: { type: 'string', description: 'One or two sentences, only what changed for this person.' },
            my_commitments: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  task:  { type: 'string' },
                  due:   { type: 'string', description: 'ISO date, or "" if none was stated. Never invent one.' },
                  quote: { type: 'string', description: 'Verbatim line this came from.' }
                },
                required: ['task', 'due', 'quote']
              }
            },
            mentions_of_me: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  speaker: { type: 'string' },
                  quote:   { type: 'string' }
                },
                required: ['speaker', 'quote']
              }
            },
            open_questions_for_me:  { type: 'array', items: { type: 'string' } },
            decisions_affecting_me: { type: 'array', items: { type: 'string' } }
          },
          required: ['person', 'summary', 'my_commitments', 'mentions_of_me',
                     'open_questions_for_me', 'decisions_affecting_me']
        }
      }
    },
    required: ['digests']
  }
};

function askClaude(script, names) {
  const prompt = [
    'Below is a timestamped meeting transcript. Produce one digest per participant listed.',
    '',
    `Participants: ${names.join(', ')}`,
    '',
    'Rules:',
    '- A digest is about what the person NEEDS, not what they SAID. Do not summarise their own speech back to them.',
    '- mentions_of_me must contain lines spoken by OTHER people that name or clearly refer to this person.',
    '- Only record a commitment if the person actually accepted it. "Could you look at X?" with no answer',
    '  is an open question, not a commitment.',
    '- Never infer a deadline that was not spoken. Empty string is correct and expected.',
    '- Every quote must be verbatim from the transcript.',
    '- If a person has nothing meaningful, return them with empty arrays. Do not pad.',
    '',
    '--- TRANSCRIPT ---',
    script
  ].join('\n');

  const res = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', {
    method: 'post',
    contentType: 'application/json',
    headers: { 'x-api-key': CLAUDE_KEY, 'anthropic-version': '2023-06-01' },
    payload: JSON.stringify({
      model: 'claude-sonnet-5',
      max_tokens: 4096,
      tools: [DIGEST_TOOL],
      tool_choice: { type: 'tool', name: 'emit_digests' },
      messages: [{ role: 'user', content: prompt }]
    }),
    muteHttpExceptions: true
  });

  const body = JSON.parse(res.getContentText());
  if (res.getResponseCode() !== 200) throw new Error(`Claude: ${res.getContentText()}`);

  const block = body.content.find(c => c.type === 'tool_use');
  const out   = {};
  block.input.digests.forEach(d => { out[d.person] = d; });
  return out;
}

// ---------- delivery ----------

function sendDigest(person, d, record, unresolved) {
  const when = Utilities.formatDate(new Date(record.startTime),
                                    Session.getScriptTimeZone(), 'd MMM, h:mm a');
  const li = s => `<li>${s}</li>`;
  const section = (title, items) =>
    items.length ? `<h3 style="font:600 14px system-ui;margin:20px 0 6px">${title}</h3>
                    <ul style="font:14px/1.6 system-ui;margin:0;padding-left:20px">
                    ${items.join('')}</ul>` : '';

  const html = `
    <div style="max-width:600px;font:14px/1.6 system-ui;color:#1a1a1a">
      <p style="color:#666;margin:0 0 4px">${when}</p>
      <p style="margin:0 0 16px">${d.summary}</p>
      ${section('Your commitments', d.my_commitments.map(c =>
        li(`<b>${c.task}</b>${c.due ? ` — due ${c.due}` : ''}
            <div style="color:#777;font-size:13px">“${c.quote}”</div>`)))}
      ${section('Questions waiting on you', d.open_questions_for_me.map(li))}
      ${section('You were mentioned', d.mentions_of_me.map(m =>
        li(`<b>${m.speaker}:</b> “${m.quote}”`)))}
      ${section('Decisions affecting your work', d.decisions_affecting_me.map(li))}
      ${unresolved.length ? `<p style="color:#999;font-size:12px;margin-top:24px">
        Not matched to an account: ${unresolved.join(', ')}</p>` : ''}
      <p style="color:#999;font-size:12px;margin-top:24px">
        Auto-generated from the meeting transcript. Reply here if something looks wrong.</p>
    </div>`;

  MailApp.sendEmail({
    to: DRY_RUN_TO || person.email,
    subject: `${DRY_RUN_TO ? `[would send to ${person.email}] ` : ''}Your notes — ${when}`,
    htmlBody: html
  });
}
```

Set `DRY_RUN_TO` to your own address, run it against last week's meetings, and read every digest
yourself for a week before you point it at the team. That is not caution for its own sake — see
Part 7.

---

## Part 5 — Making it event-driven, later

The poll above is deliberately the v1: no GCP project, no service account, nothing to deploy. When
you want it instant, the Google Workspace Events API lets you subscribe a meeting space to Meet
events and receive them over Pub/Sub. The event you want is transcript file generation completing
(`google.workspace.meet.transcript.v2.fileGenerationEnded`), which fires exactly when the transcript
is ready to read. Point Pub/Sub at a Cloud Function and lift `processConference` into it unchanged.

Do this only once people are actually reading the mail. A 15-minute delay is not the reason a
feature fails.

---

## Part 6 — Buying instead of building

Worth an honest hour before you write code. Several meeting-notetaker products (Fireflies, Otter,
Fathom, Read.ai and others) join the call as a bot, transcribe, and can mail per-attendee summaries
with assigned action items. If that covers you, it is cheaper than any engineering.

Two reasons to build anyway, and they are the reasons that usually win:

1. **A bot has to join your calls.** Every external participant sees a recorder in the room. Meet's
   native transcript has no such tax — it is already on.
2. **The routing is yours.** "Mentions of me", "questions I never answered", and the exact tone of
   the mail are the entire value here, and they are the part no vendor lets you change.

The no-code middle ground — Zapier, Make, or n8n on a Drive "new file in folder" trigger — removes
the Apps Script but not the thinking: you still need an AI step to do the per-person split, and you
are back to parsing the Doc because those tools do not speak the Meet API. It costs a subscription
to end up with something less good. Skip it.

---

## Part 7 — Before this touches the team

Two things, and neither is optional.

**Tell people first.** A mail that quotes a colleague back at them, unannounced, reads as
surveillance even when it is helpful. Announce it in the standup before the first send.

**Meetings contain things that must not be forwarded.** The moment a team discusses someone's
performance, a salary, a departure, or a client complaint, an automatic per-person mailer becomes a
leak with a delivery schedule. Two mitigations, cheap to build:

- Keep the host in the loop for the first month — send the full set to the host, who forwards. Slow,
  but you learn what the model gets wrong on your meetings before anyone else sees it.
- Add a spoken kill-phrase. If any transcript line contains "off the record", drop the whole
  conference and mail only the host. One `if`, and it is the feature that makes people relax.

---

## Recommended sequence

1. **Half a day.** Verify Directory resolution on your tenant — `signedinUser.user` → `primaryEmail`.
   Everything else depends on this and nothing else is worth writing until it works.
2. **Half a day.** Apps Script above, `DRY_RUN_TO` set to yourself, run over last week.
3. **One week.** Read every digest. Tune the prompt rules in `askClaude` — that list of rules is
   where all the quality lives, not the code.
4. **Then** turn on host-forwarding, then direct send, then Pub/Sub if the latency ever annoys you.

## Sources

- [Method: conferenceRecords.transcripts.entries.list](https://developers.google.com/workspace/meet/api/reference/rest/v2/conferenceRecords.transcripts.entries/list)
- [REST Resource: conferenceRecords.participants](https://developers.google.com/workspace/meet/api/reference/rest/v2/conferenceRecords.participants)
- [Work with participants](https://developers.google.com/workspace/meet/api/guides/participants)
- [Google Meet REST API overview](https://developers.google.com/workspace/meet/api/guides/overview)
- [Subscribe to Google Meet events](https://developers.google.com/workspace/events/guides/events-meet)
- [Respond to events from Google Meet](https://developers.google.com/workspace/meet/api/guides/events-overview)
- [Use Transcripts with Google Meet](https://support.google.com/meet/answer/12849897?hl=en)
